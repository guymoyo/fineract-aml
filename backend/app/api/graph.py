"""Graph visualization API — returns transaction network data for D3/Cytoscape."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_token
from app.schemas.graph import GraphResponse
from app.services.graph_service import GraphService

router = APIRouter(
    prefix="/graph", tags=["Graph"], dependencies=[Depends(verify_token)]
)


@router.get("/account/{account_id}", response_model=GraphResponse)
async def get_account_graph(
    account_id: str,
    days: int = Query(30, ge=1, le=90, description="Days of history to include"),
    depth: int = Query(2, ge=1, le=3, description="Network hop depth"),
    db: AsyncSession = Depends(get_db),
):
    """Return the transaction network graph centered on an account.

    Suitable for rendering in D3.js force-directed graphs or Cytoscape.
    Results are cached for 15 minutes.
    """
    service = GraphService(db)
    return await service.get_account_graph(account_id, days=days, depth=depth)


@router.get("/case/{case_id}", response_model=GraphResponse)
async def get_case_graph(
    case_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return the transaction network for all accounts in a case."""
    service = GraphService(db)
    return await service.get_case_graph(case_id)
