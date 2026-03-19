"""Review model — analyst decisions on alerts (builds labeled training data)."""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ReviewDecision(str, enum.Enum):
    LEGITIMATE = "legitimate"
    SUSPICIOUS = "suspicious"
    CONFIRMED_FRAUD = "confirmed_fraud"


class Review(Base, TimestampMixin):
    """A compliance analyst's review of an alert.

    Each review becomes a labeled data point for ML model training:
    - CONFIRMED_FRAUD → positive label (is_fraud=1)
    - LEGITIMATE → negative label (is_fraud=0)
    - SUSPICIOUS → escalated for further investigation
    """

    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id"), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    decision: Mapped[ReviewDecision] = mapped_column(
        Enum(ReviewDecision, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    sar_filed: Mapped[bool] = mapped_column(default=False)
    sar_reference: Mapped[str | None] = mapped_column(String(100))

    # Relationships
    alert: Mapped["Alert"] = relationship(back_populates="reviews")  # noqa: F821
    reviewer: Mapped["User"] = relationship()  # noqa: F821
