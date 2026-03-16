"""Case management endpoints for the compliance dashboard."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_token
from app.models.case import CaseStatus
from app.schemas.case import (
    CaseAssign,
    CaseCreate,
    CaseListResponse,
    CaseResponse,
    CaseStatusUpdate,
)
from app.services.case_service import CaseService

router = APIRouter(
    prefix="/cases", tags=["Cases"], dependencies=[Depends(verify_token)]
)


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    data: CaseCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new investigation case."""
    service = CaseService(db)
    case = await service.create_case(data)
    return CaseResponse.model_validate(case)


@router.get("", response_model=CaseListResponse)
async def list_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: CaseStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    """List investigation cases."""
    service = CaseService(db)
    cases, total = await service.list_cases(page, page_size, status_filter)
    return CaseListResponse(
        items=[CaseResponse.model_validate(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(case_id: UUID, db: AsyncSession = Depends(get_db)):
    service = CaseService(db)
    case = await service.get_case(case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )
    return CaseResponse.model_validate(case)


@router.patch("/{case_id}/status", response_model=CaseResponse)
async def update_case_status(
    case_id: UUID,
    data: CaseStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = CaseService(db)
    case = await service.update_status(case_id, data.status)
    return CaseResponse.model_validate(case)


@router.patch("/{case_id}/assign", response_model=CaseResponse)
async def assign_case(
    case_id: UUID,
    data: CaseAssign,
    db: AsyncSession = Depends(get_db),
):
    service = CaseService(db)
    case = await service.assign_case(case_id, data.assigned_to)
    return CaseResponse.model_validate(case)
