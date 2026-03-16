"""Alert model — generated when a transaction is flagged as suspicious."""

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AlertStatus(str, enum.Enum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    CONFIRMED_FRAUD = "confirmed_fraud"
    FALSE_POSITIVE = "false_positive"
    ESCALATED = "escalated"
    DISMISSED = "dismissed"


class AlertSource(str, enum.Enum):
    RULE_ENGINE = "rule_engine"
    ANOMALY_DETECTION = "anomaly_detection"
    ML_MODEL = "ml_model"
    MANUAL = "manual"


class Alert(Base, TimestampMixin):
    """An alert raised when suspicious activity is detected."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False
    )

    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus), default=AlertStatus.PENDING, nullable=False
    )
    source: Mapped[AlertSource] = mapped_column(Enum(AlertSource), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    triggered_rules: Mapped[str | None] = mapped_column(Text)

    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    # Relationships
    transaction: Mapped["Transaction"] = relationship(back_populates="alerts")  # noqa: F821
    assignee: Mapped["User | None"] = relationship()  # noqa: F821
    reviews: Mapped[list["Review"]] = relationship(back_populates="alert")  # noqa: F821

    __table_args__ = (
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_assigned", "assigned_to", "status"),
    )
