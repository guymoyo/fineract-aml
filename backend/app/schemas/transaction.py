"""Pydantic schemas for transaction endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.transaction import RiskLevel, TransactionType


class WebhookPayload(BaseModel):
    """Payload received from Fineract webhook."""

    transaction_id: str = Field(..., description="Fineract transaction ID")
    account_id: str = Field(..., description="Fineract savings/loan account ID")
    client_id: str = Field(..., description="Fineract client ID")
    transaction_type: TransactionType
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD", max_length=3)
    transaction_date: datetime
    counterparty_account_id: str | None = None
    counterparty_name: str | None = None
    description: str | None = None


class TransactionResponse(BaseModel):
    """Transaction data returned to the client."""

    id: UUID
    fineract_transaction_id: str
    fineract_account_id: str
    fineract_client_id: str
    transaction_type: TransactionType
    amount: float
    currency: str
    transaction_date: datetime
    risk_score: float | None
    risk_level: RiskLevel | None
    anomaly_score: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    """Paginated list of transactions."""

    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int


class TransactionStats(BaseModel):
    """Transaction statistics for the dashboard."""

    total_transactions: int
    total_flagged: int
    total_confirmed_fraud: int
    total_false_positives: int
    average_risk_score: float | None
    transactions_today: int
    alerts_pending: int
