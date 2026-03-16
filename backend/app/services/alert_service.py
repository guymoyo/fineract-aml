"""Service layer for alert management."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import Alert, AlertStatus
from app.models.review import Review, ReviewDecision
from app.schemas.review import ReviewCreate


class AlertService:
    """Handles alert querying, assignment, and review."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_alerts(
        self,
        page: int = 1,
        page_size: int = 50,
        status: AlertStatus | None = None,
        assigned_to: UUID | None = None,
    ) -> tuple[list[Alert], int]:
        """List alerts with optional filters."""
        query = select(Alert).options(selectinload(Alert.transaction))
        count_query = select(func.count(Alert.id))

        if status:
            query = query.where(Alert.status == status)
            count_query = count_query.where(Alert.status == status)

        if assigned_to:
            query = query.where(Alert.assigned_to == assigned_to)
            count_query = count_query.where(Alert.assigned_to == assigned_to)

        query = query.order_by(Alert.risk_score.desc(), Alert.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        alerts = list(result.scalars().all())

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        return alerts, total

    async def get_alert(self, alert_id: UUID) -> Alert | None:
        result = await self.db.execute(
            select(Alert)
            .options(selectinload(Alert.transaction), selectinload(Alert.reviews))
            .where(Alert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def assign_alert(self, alert_id: UUID, user_id: UUID) -> Alert:
        result = await self.db.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one()
        alert.assigned_to = user_id
        alert.status = AlertStatus.UNDER_REVIEW
        await self.db.flush()
        return alert

    async def update_status(self, alert_id: UUID, status: AlertStatus) -> Alert:
        result = await self.db.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one()
        alert.status = status
        await self.db.flush()
        return alert

    async def submit_review(
        self, alert_id: UUID, reviewer_id: UUID, review_data: ReviewCreate
    ) -> Review:
        """Submit a review decision for an alert.

        This is the key step that generates labeled training data.
        """
        review = Review(
            alert_id=alert_id,
            reviewer_id=reviewer_id,
            decision=review_data.decision,
            notes=review_data.notes,
            evidence=review_data.evidence,
            sar_filed=review_data.sar_filed,
            sar_reference=review_data.sar_reference,
        )
        self.db.add(review)

        # Update alert status based on decision
        result = await self.db.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one()

        match review_data.decision:
            case ReviewDecision.CONFIRMED_FRAUD:
                alert.status = AlertStatus.CONFIRMED_FRAUD
            case ReviewDecision.LEGITIMATE:
                alert.status = AlertStatus.FALSE_POSITIVE
            case ReviewDecision.SUSPICIOUS:
                alert.status = AlertStatus.ESCALATED

        await self.db.flush()
        return review
