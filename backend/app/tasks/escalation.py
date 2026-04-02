"""Hourly Celery task for case escalation and SLA deadline enforcement."""

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _run_escalation():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.services.escalation_service import EscalationService

    engine = create_async_engine(settings.database_url, pool_size=2, max_overflow=1)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        svc = EscalationService(db)
        escalated = await svc.auto_escalate_pending_cases()
        overdue = await svc.check_sar_deadlines()
        await db.commit()

    await engine.dispose()
    logger.info(
        "Escalation check complete: %d cases escalated, %d past SAR deadline",
        escalated, overdue,
    )


@celery_app.task(name="app.tasks.escalation.check_escalations")
def check_escalations() -> None:
    """Auto-escalate stale high-risk cases and flag overdue SAR deadlines."""
    _run_async(_run_escalation())
