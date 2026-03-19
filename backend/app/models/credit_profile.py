"""Customer credit profile — behavioral credit score and tier segmentation.

Each profile represents a customer's creditworthiness computed from their
transaction history. Profiles are refreshed nightly via a Celery Beat task
and can be recalculated on demand.

Scoring pipeline:
1. Extract customer-level features (deposit patterns, savings rate, etc.)
2. Apply rule-based weighted scoring → credit_score (0-1)
3. Map score to segment tier (A-E) with configurable thresholds
4. Optionally run ML clustering for segment validation
5. Compute max credit amount from tier configuration
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CreditSegment(str, enum.Enum):
    """Customer credit tier — determines max borrowable amount."""

    TIER_A = "tier_a"  # Excellent
    TIER_B = "tier_b"  # Good
    TIER_C = "tier_c"  # Fair
    TIER_D = "tier_d"  # Poor
    TIER_E = "tier_e"  # Very poor / ineligible


class ScoringMethod(str, enum.Enum):
    """How the credit score was computed."""

    RULE_BASED = "rule_based"
    ML_CLUSTER = "ml_cluster"
    HYBRID = "hybrid"


class CustomerCreditProfile(Base, TimestampMixin):
    """A customer's credit score, segment tier, and max credit amount."""

    __tablename__ = "customer_credit_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fineract_client_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )

    # Rule-based credit score (0.0 = worst, 1.0 = best)
    credit_score: Mapped[float] = mapped_column(Float, nullable=False)
    segment: Mapped[CreditSegment] = mapped_column(
        Enum(CreditSegment, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    max_credit_amount: Mapped[float] = mapped_column(Float, nullable=False)

    # JSON-serialized dict of individual component scores
    score_components: Mapped[str | None] = mapped_column(Text)

    # ML clustering results (populated when cluster model is trained)
    ml_cluster_id: Mapped[int | None] = mapped_column(Integer)
    ml_segment_suggestion: Mapped[CreditSegment | None] = mapped_column(
        Enum(CreditSegment, name="ml_credit_segment", values_callable=lambda e: [x.value for x in e]),
    )

    scoring_method: Mapped[ScoringMethod] = mapped_column(
        Enum(ScoringMethod, values_callable=lambda e: [x.value for x in e]),
        default=ScoringMethod.RULE_BASED,
        nullable=False,
    )
    last_computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_credit_profiles_segment", "segment"),
        Index("ix_credit_profiles_score", "credit_score"),
    )
