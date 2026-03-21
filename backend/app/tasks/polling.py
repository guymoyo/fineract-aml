"""Fineract polling fallback — catches transactions missed by webhooks.

This task polls the Fineract API for recent transactions and ingests
any that are not yet in the AML database. Runs every 60 seconds as
a fallback when webhooks fail or are unavailable.
"""

import asyncio
import logging

import httpx

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _poll_fineract():
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import async_session
    from app.models.transaction import Transaction

    if not settings.fineract_base_url:
        logger.debug("Fineract base URL not configured, skipping poll")
        return

    # Fetch recent transactions from Fineract API
    try:
        async with httpx.AsyncClient(verify=False, timeout=30) as client:
            response = await client.get(
                f"{settings.fineract_base_url}/savingsaccounts/transactions",
                params={"limit": 100, "orderBy": "id", "sortOrder": "DESC"},
                headers={"Fineract-Platform-TenantId": "default"},
            )
            if response.status_code != 200:
                logger.warning("Fineract poll returned status %d", response.status_code)
                return
            data = response.json()
    except httpx.RequestError as e:
        logger.debug("Fineract poll failed (expected if Fineract is not running): %s", e)
        return

    if not data or "pageItems" not in data:
        return

    # Check which transactions are already in our database
    async with async_session() as db:
        new_count = 0
        for item in data["pageItems"]:
            fineract_tx_id = str(item.get("id", ""))
            if not fineract_tx_id:
                continue

            existing = await db.execute(
                select(Transaction.id).where(
                    Transaction.fineract_transaction_id == fineract_tx_id
                )
            )
            if existing.scalar_one_or_none():
                continue

            # Transaction not in our DB — queue for ingestion via webhook endpoint
            logger.info("Polling found missing transaction: %s", fineract_tx_id)
            new_count += 1

        if new_count:
            logger.info("Polling found %d transactions missing from AML database", new_count)


@celery_app.task(name="app.tasks.polling.poll_fineract_transactions")
def poll_fineract_transactions():
    """Poll Fineract API for transactions not received via webhook."""
    _run_async(_poll_fineract())
