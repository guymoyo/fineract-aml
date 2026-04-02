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
    currency: str | None = Field(default=None, max_length=3, description="Defaults to AML_DEFAULT_CURRENCY if not provided")
    transaction_date: datetime
    counterparty_account_id: str | None = None
    counterparty_name: str | None = None
    description: str | None = None
    ip_address: str | None = Field(default=None, description="Client IP address (auto-captured from request if not provided)")
    user_agent: str | None = None
    country_code: str | None = Field(default=None, max_length=2, description="ISO 3166-1 alpha-2 country code")
    geo_location: str | None = Field(default=None, description="Latitude,longitude or city name")

    # WeBank actor context — populated by the BFF from Keycloak token claims
    actor_type: str | None = Field(default=None, description="Actor role: 'customer' | 'agent' | 'merchant'")
    agent_id: str | None = Field(default=None, description="Fineract office/staff ID of the serving agent")
    branch_id: str | None = Field(default=None, description="Fineract branch/office ID")
    merchant_id: str | None = Field(default=None, description="Merchant account ID for QR payments")
    device_id: str | None = Field(default=None, description="SHA-256 device fingerprint hash")
    kyc_level: int | None = Field(default=None, ge=1, le=4, description="KYC level 1–4 from KYC manager")


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
    ip_address: str | None
    country_code: str | None
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
