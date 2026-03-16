"""Webhook endpoint — receives transaction events from Fineract."""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_webhook_signature
from app.schemas.transaction import WebhookPayload
from app.services.transaction_service import TransactionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["Webhook"])


@router.post("/fineract", status_code=status.HTTP_202_ACCEPTED)
async def receive_fineract_webhook(
    request: Request,
    payload: WebhookPayload,
    db: AsyncSession = Depends(get_db),
    x_webhook_signature: str | None = Header(default=None),
):
    """Receive a transaction event from Fineract.

    This endpoint:
    1. Verifies the webhook signature (if configured)
    2. Ingests the transaction into the database
    3. Triggers async analysis (rule engine + anomaly detection)
    """
    # Verify signature in production
    if settings.fineract_webhook_secret != "change-me-in-production":
        if not x_webhook_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing webhook signature",
            )
        raw_body = await request.body()
        if not verify_webhook_signature(raw_body, x_webhook_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    # Capture client IP from request if not in payload
    if not payload.ip_address and request.client:
        payload.ip_address = request.client.host

    service = TransactionService(db)
    transaction = await service.ingest_transaction(payload)

    # Trigger async analysis via Celery
    from app.tasks.analysis import analyze_transaction

    analyze_transaction.delay(str(transaction.id))

    return {
        "status": "accepted",
        "transaction_id": str(transaction.id),
        "message": "Transaction queued for AML analysis",
    }
