"""Model health snapshot model — tracks ML model performance over time."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ModelHealthSnapshot(Base, TimestampMixin):
    """Point-in-time snapshot of an ML model's health metrics."""

    __tablename__ = "model_health_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_version: Mapped[str | None] = mapped_column(String(50))

    # Training metrics
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_sample_count: Mapped[int | None] = mapped_column()
    auc_score: Mapped[float | None] = mapped_column(Float)
    precision_score: Mapped[float | None] = mapped_column(Float)
    recall_score: Mapped[float | None] = mapped_column(Float)

    # Drift metrics (populated by hourly PSI check)
    psi_score: Mapped[float | None] = mapped_column(Float)
    drift_status: Mapped[str | None] = mapped_column(
        String(20)
    )  # "stable" | "warning" | "drift"

    # Full metrics JSON (feature importances, confusion matrix, etc.)
    metrics_json: Mapped[str | None] = mapped_column(Text)
