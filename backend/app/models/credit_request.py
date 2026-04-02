"""Credit request model — tracks loan applications and compliance reviews.

Every credit request requires compliance review. The system auto-computes
a recommendation (APPROVE / REVIEW_CAREFULLY / REJECT) based on the
customer's credit profile, but never auto-approves.

Flow:
1. Credit request submitted (via API or webhook)
2. Real-time credit score computed/refreshed
3. Auto-recommendation generated
4. Compliance analyst reviews and approves/rejects
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.credit_profile import CreditSegment


class CreditRequestStatus(str, enum.Enum):
    """Lifecycle status of a credit request."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CreditRecommendation(str, enum.Enum):
    """System-generated recommendation for compliance reviewers."""

    APPROVE = "approve"
    REVIEW_CAREFULLY = "review_carefully"
    REJECT = "reject"


class CreditRequest(Base, TimestampMixin):
    """A customer's request for credit, pending compliance review."""

    __tablename__ = "credit_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fineract_client_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    requested_amount: Mapped[float] = mapped_column(Float, nullable=False)

    # Snapshot of credit profile at time of request
    credit_score_at_request: Mapped[float] = mapped_column(Float, nullable=False)
    segment_at_request: Mapped[CreditSegment] = mapped_column(
        Enum(CreditSegment, name="request_credit_segment", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    max_credit_at_request: Mapped[float] = mapped_column(Float, nullable=False)

    # System recommendation
    recommendation: Mapped[CreditRecommendation] = mapped_column(
        Enum(CreditRecommendation, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )

    # Score gaming detection
    score_inflation_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    explanation_text: Mapped[str | None] = mapped_column(Text)  # LLM-generated explanation

    # Review workflow
    status: Mapped[CreditRequestStatus] = mapped_column(
        Enum(CreditRequestStatus, values_callable=lambda e: [x.value for x in e]),
        default=CreditRequestStatus.PENDING_REVIEW,
        nullable=False,
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    # Relationships
    assignee: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[assigned_to]
    )
    reviewer: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[reviewed_by]
    )

    __table_args__ = (
        Index("ix_credit_requests_status", "status"),
        Index("ix_credit_requests_client", "fineract_client_id"),
    )
