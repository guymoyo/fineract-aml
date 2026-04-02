"""Model health and drift monitoring API endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_token
from app.models.model_health import ModelHealthSnapshot

router = APIRouter(
    prefix="/model-health", tags=["Model Health"], dependencies=[Depends(verify_token)]
)


class ModelHealthResponse(BaseModel):
    model_name: str
    model_version: str | None
    trained_at: str | None
    training_sample_count: int | None
    auc_score: float | None
    precision_score: float | None
    recall_score: float | None
    psi_score: float | None
    drift_status: str | None
    snapshot_at: str


class DriftSummary(BaseModel):
    model_name: str
    psi_score: float | None
    drift_status: str
    recommendation: str


@router.get("", response_model=list[ModelHealthResponse])
async def get_model_health(db: AsyncSession = Depends(get_db)):
    """Return the latest health snapshot for each tracked model."""
    # Get the latest snapshot per model_name using a subquery
    from sqlalchemy import func

    subq = (
        select(
            ModelHealthSnapshot.model_name,
            func.max(ModelHealthSnapshot.created_at).label("latest"),
        )
        .group_by(ModelHealthSnapshot.model_name)
        .subquery()
    )
    result = await db.execute(
        select(ModelHealthSnapshot).join(
            subq,
            (ModelHealthSnapshot.model_name == subq.c.model_name)
            & (ModelHealthSnapshot.created_at == subq.c.latest),
        )
    )
    snapshots = list(result.scalars().all())

    if not snapshots:
        # Fall back to Redis cache if no DB snapshots
        try:
            import redis

            from app.core.config import settings

            r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
            raw = r.get("model_health:latest")
            if raw:
                data = json.loads(raw)
                return [
                    ModelHealthResponse(
                        model_name=data.get("model_name", "unknown"),
                        model_version=data.get("version"),
                        trained_at=data.get("trained_at"),
                        training_sample_count=data.get("sample_count"),
                        auc_score=data.get("auc"),
                        precision_score=None,
                        recall_score=None,
                        psi_score=None,
                        drift_status=data.get("drift_status", "unknown"),
                        snapshot_at=data.get("snapshot_at", ""),
                    )
                ]
        except Exception:
            pass
        return []

    return [
        ModelHealthResponse(
            model_name=s.model_name,
            model_version=s.model_version,
            trained_at=s.trained_at.isoformat() if s.trained_at else None,
            training_sample_count=s.training_sample_count,
            auc_score=s.auc_score,
            precision_score=s.precision_score,
            recall_score=s.recall_score,
            psi_score=s.psi_score,
            drift_status=s.drift_status,
            snapshot_at=s.created_at.isoformat(),
        )
        for s in snapshots
    ]


@router.get("/drift", response_model=list[DriftSummary])
async def get_drift_summary(db: AsyncSession = Depends(get_db)):
    """Return drift status and recommendations for all tracked models."""
    snapshots = await get_model_health(db)

    summaries = []
    for snap in snapshots:
        psi = snap.psi_score
        if psi is None:
            drift_status = "unknown"
            rec = "Retrain model to establish baseline PSI"
        elif psi < 0.1:
            drift_status = "stable"
            rec = "No action required"
        elif psi < 0.25:
            drift_status = "warning"
            rec = "Monitor closely — consider retraining within 7 days"
        else:
            drift_status = "drift"
            rec = "Significant drift detected — immediate retraining required"

        summaries.append(
            DriftSummary(
                model_name=snap.model_name,
                psi_score=psi,
                drift_status=drift_status,
                recommendation=rec,
            )
        )
    return summaries


@router.get("/history/{model_name}", response_model=list[ModelHealthResponse])
async def get_model_history(
    model_name: str,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Return the last N health snapshots for a specific model."""
    result = await db.execute(
        select(ModelHealthSnapshot)
        .where(ModelHealthSnapshot.model_name == model_name)
        .order_by(ModelHealthSnapshot.created_at.desc())
        .limit(limit)
    )
    snapshots = list(result.scalars().all())
    if not snapshots:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No health snapshots found for model '{model_name}'",
        )
    return [
        ModelHealthResponse(
            model_name=s.model_name,
            model_version=s.model_version,
            trained_at=s.trained_at.isoformat() if s.trained_at else None,
            training_sample_count=s.training_sample_count,
            auc_score=s.auc_score,
            precision_score=s.precision_score,
            recall_score=s.recall_score,
            psi_score=s.psi_score,
            drift_status=s.drift_status,
            snapshot_at=s.created_at.isoformat(),
        )
        for s in snapshots
    ]
