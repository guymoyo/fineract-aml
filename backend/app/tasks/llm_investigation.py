"""LLM-powered alert investigation task.

Triggered automatically for HIGH/CRITICAL alerts when llm_investigation_enabled is True.
Uses Claude API with agentic tool use to investigate alerts and generate
SAR-ready narratives in French for COBAC compliance.
"""

import asyncio
import json
import logging
import uuid

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _investigate_and_store(alert_id: str) -> None:
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.alert import Alert
    from app.services.llm_agent_service import AlertInvestigationAgent

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Alert).where(Alert.id == uuid.UUID(alert_id))
        )
        alert = result.scalar_one_or_none()
        if not alert:
            logger.warning("LLM investigation: alert %s not found", alert_id)
            return

        agent = AlertInvestigationAgent(db)
        try:
            report = await agent.investigate(alert_id)
        except Exception as exc:
            logger.error(
                "LLM investigation failed for alert %s: %s", alert_id, exc, exc_info=True
            )
            # Store error state so the UI can show why investigation failed
            alert.investigation_report = json.dumps({"error": str(exc)})
            await db.commit()
            return

        alert.investigation_report = json.dumps({
            "summary": report.summary,
            "typology_match": report.typology_match,
            "risk_factors": report.risk_factors,
            "mitigating_factors": report.mitigating_factors,
            "recommendation": report.recommendation,
            "recommended_actions": report.recommended_actions,
            "narrative_fr": report.narrative_fr,
            "model_used": report.model_used,
            "generated_at": report.generated_at,
        })
        await db.commit()
        logger.info(
            "LLM investigation complete for alert %s: recommendation=%s",
            alert_id, report.recommendation,
        )


@celery_app.task(
    name="app.tasks.llm_investigation.run_alert_investigation",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def run_alert_investigation(self, alert_id: str) -> None:
    """Investigate an alert using the Claude API and store the report.

    Args:
        alert_id: UUID string of the Alert to investigate.
    """
    try:
        _run_async(_investigate_and_store(alert_id))
    except Exception as exc:
        logger.error("run_alert_investigation task error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
