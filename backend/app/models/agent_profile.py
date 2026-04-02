"""Agent behavioral profile — per-agent baseline for anomaly detection.

Agents are expected to have high transaction volumes, so they need their
own baseline profile rather than being compared to global thresholds.
Updated nightly by the agent_profile_update Celery task.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AgentProfile(Base, TimestampMixin):
    """Behavioral baseline computed from an agent's last 30 days of activity."""

    __tablename__ = "agent_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Agent identity (from Fineract office/staff hierarchy)
    agent_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    branch_id: Mapped[str | None] = mapped_column(String(100))

    # Volume baseline (30-day rolling averages)
    avg_daily_tx_count_30d: Mapped[float | None] = mapped_column(Float)
    avg_daily_volume_30d: Mapped[float | None] = mapped_column(Float)
    std_daily_volume_30d: Mapped[float | None] = mapped_column(Float)

    # Float balance pattern (ratio of deposits to total activity)
    # Legitimate agents: ~0.5 (balanced deposits and withdrawals)
    typical_float_ratio: Mapped[float | None] = mapped_column(Float)

    # Customer service metrics
    served_customer_count_30d: Mapped[int | None] = mapped_column(Integer)
    avg_new_customers_per_day_30d: Mapped[float | None] = mapped_column(Float)
    unique_customers_30d: Mapped[int | None] = mapped_column(Integer)

    # Transaction amount distribution
    avg_tx_amount_30d: Mapped[float | None] = mapped_column(Float)
    p95_tx_amount_30d: Mapped[float | None] = mapped_column(Float)

    # Timing patterns
    peak_hour_distribution: Mapped[str | None] = mapped_column(Text)  # JSON: {hour: count}

    # Profile metadata
    computed_from_days: Mapped[int | None] = mapped_column(Integer)   # how many days of data
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
