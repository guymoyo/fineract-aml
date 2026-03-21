"""Transaction model — stores every transaction received from Fineract."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    LOAN_DISBURSEMENT = "loan_disbursement"
    LOAN_REPAYMENT = "loan_repayment"
    SHARE_PURCHASE = "share_purchase"
    SHARE_REDEMPTION = "share_redemption"
    FIXED_DEPOSIT = "fixed_deposit"
    RECURRING_DEPOSIT = "recurring_deposit"
    CHARGE = "charge"
    FEE = "fee"
    OTHER = "other"  # Catch-all for unrecognized Fineract event types


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Transaction(Base, TimestampMixin):
    """A financial transaction received from Fineract via webhook."""

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fineract_transaction_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    fineract_account_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    fineract_client_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )

    transaction_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, values_callable=lambda e: [x.value for x in e]), nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Counterparty info (if transfer)
    counterparty_account_id: Mapped[str | None] = mapped_column(String(100))
    counterparty_name: Mapped[str | None] = mapped_column(String(255))

    # Client network info (captured from webhook request)
    ip_address: Mapped[str | None] = mapped_column(String(45))  # IPv6 max length
    user_agent: Mapped[str | None] = mapped_column(String(500))
    country_code: Mapped[str | None] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    geo_location: Mapped[str | None] = mapped_column(String(100))  # "lat,lon" or city

    # Risk scoring
    risk_score: Mapped[float | None] = mapped_column(Float)
    risk_level: Mapped[RiskLevel | None] = mapped_column(Enum(RiskLevel, values_callable=lambda e: [x.value for x in e]))
    anomaly_score: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(50))
    score_explanation: Mapped[str | None] = mapped_column(Text)  # JSON: per-feature contributions
    shadow_score: Mapped[float | None] = mapped_column(Float)  # Shadow model score for A/B comparison

    # Metadata
    description: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[str | None] = mapped_column(Text)

    # Relationships
    alerts: Mapped[list["Alert"]] = relationship(back_populates="transaction")  # noqa: F821
    rule_matches: Mapped[list["RuleMatch"]] = relationship(back_populates="transaction")  # noqa: F821

    __table_args__ = (
        Index("ix_transactions_date_account", "transaction_date", "fineract_account_id"),
        Index("ix_transactions_risk", "risk_level", "risk_score"),
    )
