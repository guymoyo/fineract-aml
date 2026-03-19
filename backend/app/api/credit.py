"""Credit scoring endpoints for the compliance dashboard.

All credit requests require compliance review — the system provides
recommendations but never auto-approves.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_token
from app.models.credit_profile import CreditSegment
from app.models.credit_request import CreditRequestStatus
from app.schemas.credit import (
    CreditAnalytics,
    CreditProfileListResponse,
    CreditProfileResponse,
    CreditRequestCreate,
    CreditRequestListResponse,
    CreditRequestResponse,
    CreditReviewAction,
    CreditSegmentStats,
)
from app.services.credit_service import CreditService

router = APIRouter(
    prefix="/credit", tags=["Credit"], dependencies=[Depends(verify_token)]
)


# ── Credit Profiles ───────────────────────────────────────


@router.get("/profiles", response_model=CreditProfileListResponse)
async def list_credit_profiles(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    segment: CreditSegment | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List customer credit profiles, ordered by score (highest first)."""
    service = CreditService(db)
    profiles, total = await service.list_profiles(page, page_size, segment)
    return CreditProfileListResponse(
        items=[CreditProfileResponse.model_validate(p) for p in profiles],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/profiles/{client_id}", response_model=CreditProfileResponse)
async def get_credit_profile(
    client_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a customer's credit profile."""
    service = CreditService(db)
    profile = await service.get_profile(client_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credit profile found for client {client_id}",
        )
    return CreditProfileResponse.model_validate(profile)


@router.post("/profiles/{client_id}/refresh", response_model=CreditProfileResponse)
async def refresh_credit_profile(
    client_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Trigger on-demand re-scoring for a specific customer."""
    service = CreditService(db)
    profile = await service.compute_credit_profile(client_id)
    return CreditProfileResponse.model_validate(profile)


# ── Credit Requests ───────────────────────────────────────


@router.post("/request", response_model=CreditRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_credit_request(
    data: CreditRequestCreate,
    db: AsyncSession = Depends(get_db),
):
    """Submit a credit request. Triggers real-time scoring and creates
    a pending review for compliance.

    The system generates a recommendation (approve/review_carefully/reject)
    but NEVER auto-approves — all requests require compliance review.
    """
    service = CreditService(db)
    request = await service.create_credit_request(
        client_id=data.fineract_client_id,
        requested_amount=data.requested_amount,
    )
    return CreditRequestResponse.model_validate(request)


@router.get("/requests", response_model=CreditRequestListResponse)
async def list_credit_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: CreditRequestStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    """List credit requests. Pending reviews are shown first."""
    service = CreditService(db)
    requests, total = await service.list_credit_requests(page, page_size, status_filter)
    return CreditRequestListResponse(
        items=[CreditRequestResponse.model_validate(r) for r in requests],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/requests/{request_id}", response_model=CreditRequestResponse)
async def get_credit_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific credit request."""
    service = CreditService(db)
    request = await service.get_credit_request(request_id)
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credit request not found",
        )
    return CreditRequestResponse.model_validate(request)


@router.put("/requests/{request_id}/review", response_model=CreditRequestResponse)
async def review_credit_request(
    request_id: UUID,
    data: CreditReviewAction,
    token_data: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a credit request.

    Only requests in PENDING_REVIEW status can be reviewed.
    """
    if data.status not in (CreditRequestStatus.APPROVED, CreditRequestStatus.REJECTED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review status must be 'approved' or 'rejected'",
        )

    reviewer_id = UUID(token_data["sub"])
    service = CreditService(db)
    try:
        request = await service.review_credit_request(
            request_id=request_id,
            status=data.status,
            reviewer_id=reviewer_id,
            notes=data.reviewer_notes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return CreditRequestResponse.model_validate(request)


# ── Analytics ─────────────────────────────────────────────


@router.get("/analytics", response_model=CreditAnalytics)
async def get_credit_analytics(
    db: AsyncSession = Depends(get_db),
):
    """Get credit scoring analytics for the dashboard."""
    service = CreditService(db)
    analytics = await service.get_analytics()
    return CreditAnalytics(
        segment_distribution=[
            CreditSegmentStats(**s) for s in analytics["segment_distribution"]
        ],
        total_profiles=analytics["total_profiles"],
        avg_credit_score=analytics["avg_credit_score"],
        total_pending_requests=analytics["total_pending_requests"],
        total_approved=analytics["total_approved"],
        total_rejected=analytics["total_rejected"],
    )
