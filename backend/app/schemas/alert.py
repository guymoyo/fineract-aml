"""Pydantic schemas for alert endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.alert import AlertSource, AlertStatus
from app.schemas.transaction import TransactionResponse


class AlertResponse(BaseModel):
    """Alert data returned to the client."""

    id: UUID
    transaction_id: UUID
    status: AlertStatus
    source: AlertSource
    risk_score: float
    title: str
    description: str | None
    triggered_rules: str | None
    assigned_to: UUID | None
    created_at: datetime
    updated_at: datetime
    transaction: TransactionResponse | None = None

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    """Paginated list of alerts."""

    items: list[AlertResponse]
    total: int
    page: int
    page_size: int


class AlertAssign(BaseModel):
    """Assign an alert to an analyst."""

    assigned_to: UUID = Field(..., description="User ID of the analyst")


class AlertStatusUpdate(BaseModel):
    """Update alert status."""

    status: AlertStatus
