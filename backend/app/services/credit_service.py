"""Service layer for credit scoring, profiles, and request management.

Orchestrates credit feature extraction, scoring, profile management,
and the compliance review workflow for credit requests.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.credit_extractor import CreditFeatureExtractor
from app.ml.credit_scorer import CreditClusterModel, CreditScorer
from app.models.alert import Alert, AlertStatus
from app.models.credit_profile import (
    CreditSegment,
    CustomerCreditProfile,
    ScoringMethod,
)
from app.models.credit_request import (
    CreditRecommendation,
    CreditRequest,
    CreditRequestStatus,
)
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


class CreditService:
    """Handles credit scoring, profile management, and request workflow."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Transaction & Alert Queries ───────────────────────────

    async def get_client_transactions(
        self, client_id: str, days: int = 180
    ) -> list[Transaction]:
        """Get all transactions for a client within a time window.

        Args:
            client_id: Fineract client ID.
            days: Number of days of history to retrieve.

        Returns:
            List of transactions ordered by date descending.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.db.execute(
            select(Transaction)
            .where(Transaction.fineract_client_id == client_id)
            .where(Transaction.transaction_date >= cutoff)
            .order_by(Transaction.transaction_date.desc())
        )
        return list(result.scalars().all())

    async def get_fraud_alert_info(self, client_id: str) -> tuple[int, int | None]:
        """Get fraud alert statistics for a client.

        Returns:
            (total_confirmed_fraud_alerts, days_since_most_recent_fraud_alert).
            days_since is None if no fraud alerts exist.
        """
        # Count confirmed fraud alerts for this client's transactions
        result = await self.db.execute(
            select(func.count(Alert.id))
            .join(Transaction, Alert.transaction_id == Transaction.id)
            .where(Transaction.fineract_client_id == client_id)
            .where(Alert.status == AlertStatus.CONFIRMED_FRAUD)
        )
        total = result.scalar_one()

        if total == 0:
            return 0, None

        # Most recent fraud alert date
        result = await self.db.execute(
            select(func.max(Alert.created_at))
            .join(Transaction, Alert.transaction_id == Transaction.id)
            .where(Transaction.fineract_client_id == client_id)
            .where(Alert.status == AlertStatus.CONFIRMED_FRAUD)
        )
        latest_date = result.scalar_one()
        if latest_date:
            days_since = (datetime.now(timezone.utc) - latest_date).days
        else:
            days_since = None

        return total, days_since

    async def get_account_age_days(self, client_id: str) -> int:
        """Get the age of a client's account in days (since first transaction)."""
        result = await self.db.execute(
            select(func.min(Transaction.transaction_date))
            .where(Transaction.fineract_client_id == client_id)
        )
        first_date = result.scalar_one()
        if first_date:
            return (datetime.now(timezone.utc) - first_date).days
        return 0

    # ── Credit Profile Management ─────────────────────────────

    async def compute_credit_profile(
        self, client_id: str
    ) -> CustomerCreditProfile:
        """Compute or update a customer's credit profile.

        Orchestrates the full scoring pipeline:
        1. Fetch transaction history (180 days)
        2. Get fraud alert info
        3. Extract credit features
        4. Run rule-based scoring
        5. Run ML clustering (if model available)
        6. Upsert the profile

        Args:
            client_id: Fineract client ID.

        Returns:
            The created or updated CustomerCreditProfile.
        """
        transactions = await self.get_client_transactions(client_id, days=180)

        if len(transactions) < settings.credit_min_transactions:
            logger.info(
                "Client %s has only %d transactions (need %d), assigning Tier E",
                client_id, len(transactions), settings.credit_min_transactions,
            )
            return await self._upsert_profile(
                client_id,
                credit_score=0.0,
                segment=CreditSegment.TIER_E,
                max_credit_amount=0.0,
                score_components="{}",
                scoring_method=ScoringMethod.RULE_BASED,
            )

        # Gather metadata
        fraud_count, days_since_fraud = await self.get_fraud_alert_info(client_id)
        account_age = await self.get_account_age_days(client_id)

        # Extract features
        features = CreditFeatureExtractor.extract(
            transactions, fraud_count, days_since_fraud, account_age
        )

        # Rule-based scoring
        scorer = CreditScorer()
        score, components = scorer.score(features)
        segment = scorer.classify_segment(score)
        max_amount = scorer.compute_max_amount(segment)

        # ML clustering (if available)
        ml_cluster_id = None
        ml_segment = None
        scoring_method = ScoringMethod.RULE_BASED

        cluster_model = CreditClusterModel()
        if cluster_model.is_ready:
            ml_cluster_id, ml_segment = cluster_model.predict(features)
            scoring_method = ScoringMethod.HYBRID

        return await self._upsert_profile(
            client_id,
            credit_score=score,
            segment=segment,
            max_credit_amount=max_amount,
            score_components=json.dumps(components),
            scoring_method=scoring_method,
            ml_cluster_id=ml_cluster_id,
            ml_segment_suggestion=ml_segment,
        )

    async def _upsert_profile(
        self,
        client_id: str,
        credit_score: float,
        segment: CreditSegment,
        max_credit_amount: float,
        score_components: str,
        scoring_method: ScoringMethod,
        ml_cluster_id: int | None = None,
        ml_segment_suggestion: CreditSegment | None = None,
    ) -> CustomerCreditProfile:
        """Create or update a credit profile."""
        result = await self.db.execute(
            select(CustomerCreditProfile).where(
                CustomerCreditProfile.fineract_client_id == client_id
            )
        )
        profile = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if profile:
            profile.credit_score = credit_score
            profile.segment = segment
            profile.max_credit_amount = max_credit_amount
            profile.score_components = score_components
            profile.scoring_method = scoring_method
            profile.ml_cluster_id = ml_cluster_id
            profile.ml_segment_suggestion = ml_segment_suggestion
            profile.last_computed_at = now
        else:
            profile = CustomerCreditProfile(
                fineract_client_id=client_id,
                credit_score=credit_score,
                segment=segment,
                max_credit_amount=max_credit_amount,
                score_components=score_components,
                scoring_method=scoring_method,
                ml_cluster_id=ml_cluster_id,
                ml_segment_suggestion=ml_segment_suggestion,
                last_computed_at=now,
                is_active=True,
            )
            self.db.add(profile)

        await self.db.flush()
        logger.info(
            "Credit profile updated for client %s: score=%.2f, segment=%s, max=%,.0f",
            client_id, credit_score, segment.value, max_credit_amount,
        )
        return profile

    async def get_profile(self, client_id: str) -> CustomerCreditProfile | None:
        """Get a customer's credit profile by client ID."""
        result = await self.db.execute(
            select(CustomerCreditProfile).where(
                CustomerCreditProfile.fineract_client_id == client_id
            )
        )
        return result.scalar_one_or_none()

    async def list_profiles(
        self,
        page: int = 1,
        page_size: int = 50,
        segment: CreditSegment | None = None,
    ) -> tuple[list[CustomerCreditProfile], int]:
        """List credit profiles with optional filtering and pagination."""
        query = select(CustomerCreditProfile).where(
            CustomerCreditProfile.is_active == True  # noqa: E712
        )
        count_query = select(func.count(CustomerCreditProfile.id)).where(
            CustomerCreditProfile.is_active == True  # noqa: E712
        )

        if segment:
            query = query.where(CustomerCreditProfile.segment == segment)
            count_query = count_query.where(CustomerCreditProfile.segment == segment)

        query = query.order_by(CustomerCreditProfile.credit_score.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        profiles = list(result.scalars().all())

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        return profiles, total

    # ── Credit Request Workflow ────────────────────────────────

    async def create_credit_request(
        self, client_id: str, requested_amount: float
    ) -> CreditRequest:
        """Submit a credit request with auto-generated recommendation.

        Always creates with PENDING_REVIEW status — compliance must review.

        Args:
            client_id: Fineract client ID.
            requested_amount: Amount the customer wants to borrow.

        Returns:
            The created CreditRequest with recommendation.
        """
        # Compute/refresh the credit profile first
        profile = await self.compute_credit_profile(client_id)

        # Generate recommendation
        scorer = CreditScorer()
        recommendation = scorer.recommend(
            score=profile.credit_score,
            segment=profile.segment,
            requested_amount=requested_amount,
            max_amount=profile.max_credit_amount,
        )

        request = CreditRequest(
            fineract_client_id=client_id,
            requested_amount=requested_amount,
            credit_score_at_request=profile.credit_score,
            segment_at_request=profile.segment,
            max_credit_at_request=profile.max_credit_amount,
            recommendation=recommendation,
            status=CreditRequestStatus.PENDING_REVIEW,
        )
        self.db.add(request)
        await self.db.flush()

        logger.info(
            "Credit request created for client %s: amount=%.0f, score=%.2f, "
            "recommendation=%s",
            client_id, requested_amount, profile.credit_score,
            recommendation.value,
        )
        return request

    async def list_credit_requests(
        self,
        page: int = 1,
        page_size: int = 50,
        status: CreditRequestStatus | None = None,
    ) -> tuple[list[CreditRequest], int]:
        """List credit requests with optional status filtering."""
        query = select(CreditRequest)
        count_query = select(func.count(CreditRequest.id))

        if status:
            query = query.where(CreditRequest.status == status)
            count_query = count_query.where(CreditRequest.status == status)

        # Pending first, then by creation date
        query = query.order_by(CreditRequest.status.asc(), CreditRequest.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        requests = list(result.scalars().all())

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        return requests, total

    async def get_credit_request(self, request_id: UUID) -> CreditRequest | None:
        """Get a specific credit request by ID."""
        result = await self.db.execute(
            select(CreditRequest).where(CreditRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def review_credit_request(
        self,
        request_id: UUID,
        status: CreditRequestStatus,
        reviewer_id: UUID,
        notes: str | None = None,
    ) -> CreditRequest:
        """Approve or reject a credit request.

        Args:
            request_id: The credit request UUID.
            status: Must be APPROVED or REJECTED.
            reviewer_id: UUID of the reviewing user.
            notes: Optional reviewer comments.

        Returns:
            The updated CreditRequest.

        Raises:
            ValueError: If the request is not in PENDING_REVIEW status.
        """
        result = await self.db.execute(
            select(CreditRequest).where(CreditRequest.id == request_id)
        )
        request = result.scalar_one()

        if request.status != CreditRequestStatus.PENDING_REVIEW:
            raise ValueError(
                f"Cannot review request in {request.status.value} status"
            )

        request.status = status
        request.reviewed_by = reviewer_id
        request.reviewed_at = datetime.now(timezone.utc)
        request.reviewer_notes = notes

        await self.db.flush()
        logger.info(
            "Credit request %s reviewed: %s by %s",
            request_id, status.value, reviewer_id,
        )
        return request

    # ── Analytics ─────────────────────────────────────────────

    async def get_segment_stats(self) -> list[dict]:
        """Get aggregate statistics per credit segment.

        Returns:
            List of dicts with segment, count, avg_score, avg_max_amount.
        """
        result = await self.db.execute(
            select(
                CustomerCreditProfile.segment,
                func.count(CustomerCreditProfile.id).label("count"),
                func.avg(CustomerCreditProfile.credit_score).label("avg_score"),
                func.avg(CustomerCreditProfile.max_credit_amount).label("avg_max_amount"),
            )
            .where(CustomerCreditProfile.is_active == True)  # noqa: E712
            .group_by(CustomerCreditProfile.segment)
            .order_by(CustomerCreditProfile.segment)
        )
        return [
            {
                "segment": row.segment,
                "count": row.count,
                "avg_score": float(row.avg_score) if row.avg_score else 0.0,
                "avg_max_amount": float(row.avg_max_amount) if row.avg_max_amount else 0.0,
            }
            for row in result.all()
        ]

    async def get_analytics(self) -> dict:
        """Get comprehensive credit analytics for the dashboard."""
        segment_stats = await self.get_segment_stats()

        total_profiles = sum(s["count"] for s in segment_stats)
        avg_score = (
            sum(s["avg_score"] * s["count"] for s in segment_stats) / total_profiles
            if total_profiles > 0
            else 0.0
        )

        pending = (
            await self.db.execute(
                select(func.count(CreditRequest.id)).where(
                    CreditRequest.status == CreditRequestStatus.PENDING_REVIEW
                )
            )
        ).scalar_one()

        approved = (
            await self.db.execute(
                select(func.count(CreditRequest.id)).where(
                    CreditRequest.status == CreditRequestStatus.APPROVED
                )
            )
        ).scalar_one()

        rejected = (
            await self.db.execute(
                select(func.count(CreditRequest.id)).where(
                    CreditRequest.status == CreditRequestStatus.REJECTED
                )
            )
        ).scalar_one()

        return {
            "segment_distribution": segment_stats,
            "total_profiles": total_profiles,
            "avg_credit_score": avg_score,
            "total_pending_requests": pending,
            "total_approved": approved,
            "total_rejected": rejected,
        }
