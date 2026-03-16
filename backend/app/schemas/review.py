"""Pydantic schemas for review endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.review import ReviewDecision


class ReviewCreate(BaseModel):
    """Create a new review (analyst decision)."""

    decision: ReviewDecision
    notes: str | None = None
    evidence: str | None = None
    sar_filed: bool = False
    sar_reference: str | None = None


class ReviewResponse(BaseModel):
    """Review data returned to the client."""

    id: UUID
    alert_id: UUID
    reviewer_id: UUID
    decision: ReviewDecision
    notes: str | None
    evidence: str | None
    sar_filed: bool
    sar_reference: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
