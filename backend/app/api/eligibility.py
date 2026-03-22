"""Webank eligibility endpoint for BFF."""

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.eligibility import EligibilityResponse
from app.services.webank_eligibility_service import compute_eligibility

logger = logging.getLogger(__name__)
router = APIRouter(tags=["eligibility"])

# Redis — graceful fallback if unavailable
_redis = None
try:
    import redis
    _redis = redis.from_url(str(settings.redis_url), decode_responses=True)
except Exception:
    logger.warning("Redis unavailable for eligibility cache — caching disabled")


def _verify_api_key(x_eml_api_key: str = Header(..., alias="X-EML-Api-Key")):
    """Verify BFF-to-EML API key."""
    if x_eml_api_key != settings.eml_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get(
    "/eligibility/{fineract_client_id}",
    response_model=EligibilityResponse,
    dependencies=[Depends(_verify_api_key)],
)
async def get_eligibility(
    fineract_client_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get credit eligibility for a customer. Cached for 24h."""
    cache_key = f"eml_score:{fineract_client_id}"

    # Check cache
    if _redis:
        try:
            cached = _redis.get(cache_key)
            if cached:
                logger.debug("Cache hit for %s", fineract_client_id)
                return EligibilityResponse(**json.loads(cached))
        except Exception as e:
            logger.warning("Redis cache read failed: %s", e)

    # Compute fresh
    result = await compute_eligibility(db, fineract_client_id)

    # Cache result
    if _redis:
        try:
            _redis.setex(cache_key, settings.eligibility_cache_ttl, result.model_dump_json())
        except Exception as e:
            logger.warning("Redis cache write failed: %s", e)

    return result
