"""Pydantic schemas for case management endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.case import CaseStatus


class CaseCreate(BaseModel):
    """Create a new investigation case."""

    title: str
    description: str | None = None
    fineract_client_id: str | None = None
    transaction_ids: list[UUID] = []


class CaseResponse(BaseModel):
    """Case data returned to the client."""

    id: UUID
    case_number: str
    title: str
    description: str | None
    status: CaseStatus
    assigned_to: UUID | None
    fineract_client_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CaseListResponse(BaseModel):
    """Paginated list of cases."""

    items: list[CaseResponse]
    total: int
    page: int
    page_size: int


class CaseStatusUpdate(BaseModel):
    """Update case status."""

    status: CaseStatus


class CaseAssign(BaseModel):
    """Assign a case to an analyst."""

    assigned_to: UUID
