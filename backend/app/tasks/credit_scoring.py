"""Credit scoring tasks — nightly batch scoring and weekly model retraining.

Pipeline:
1. Nightly: compute_all_credit_scores iterates all active clients,
   extracts credit features, and upserts CustomerCreditProfile records.
2. Weekly: retrain_credit_cluster_model trains K-Means on all customer
   feature vectors to discover natural segments.
3. On-demand: evaluate_credit_request_task re-scores a specific client
   when a credit request is submitted.
"""

import asyncio
import logging

import numpy as np

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _compute_all_scores():
    """Batch-compute credit scores for all active clients."""
    from sqlalchemy import distinct, select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.models.transaction import Transaction
    from app.services.credit_service import CreditService

    # Fresh engine per task to avoid fork-safety issues with asyncpg
    task_engine = create_async_engine(settings.database_url, pool_size=5, max_overflow=2)
    task_session = async_sessionmaker(task_engine, class_=AsyncSession, expire_on_commit=False)

    async with task_session() as db:
        # Get all distinct client IDs
        result = await db.execute(
            select(distinct(Transaction.fineract_client_id))
        )
        client_ids = [row[0] for row in result.all()]

        logger.info("Computing credit scores for %d clients", len(client_ids))

        service = CreditService(db)
        scored = 0
        errors = 0

        for i, client_id in enumerate(client_ids):
            try:
                await service.compute_credit_profile(client_id)
                scored += 1
            except Exception:
                logger.exception("Failed to score client %s", client_id)
                errors += 1

            # Commit in batches
            if (i + 1) % settings.credit_scoring_batch_size == 0:
                await db.commit()
                logger.info("Progress: %d/%d clients scored", scored, len(client_ids))

        await db.commit()
        logger.info(
            "Credit scoring complete: %d scored, %d errors out of %d clients",
            scored, errors, len(client_ids),
        )

    await task_engine.dispose()


async def _retrain_cluster_model():
    """Retrain the K-Means clustering model on all customer feature vectors."""
    from sqlalchemy import distinct, select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.features.credit_extractor import CreditFeatureExtractor
    from app.ml.credit_scorer import CreditClusterModel, CreditScorer
    from app.models.transaction import Transaction
    from app.services.credit_service import CreditService

    task_engine = create_async_engine(settings.database_url, pool_size=5, max_overflow=2)
    task_session = async_sessionmaker(task_engine, class_=AsyncSession, expire_on_commit=False)

    async with task_session() as db:
        # Get all distinct client IDs
        result = await db.execute(
            select(distinct(Transaction.fineract_client_id))
        )
        client_ids = [row[0] for row in result.all()]

        if len(client_ids) < 10:
            logger.info("Not enough clients for clustering: %d (need 10)", len(client_ids))
            await task_engine.dispose()
            return

        service = CreditService(db)
        scorer = CreditScorer()

        feature_list = []
        score_list = []

        for client_id in client_ids:
            try:
                transactions = await service.get_client_transactions(client_id, days=180)
                if len(transactions) < settings.credit_min_transactions:
                    continue

                fraud_count, days_since_fraud = await service.get_fraud_alert_info(client_id)
                account_age = await service.get_account_age_days(client_id)

                features = CreditFeatureExtractor.extract(
                    transactions, fraud_count, days_since_fraud, account_age
                )
                rule_score, _ = scorer.score(features)

                feature_list.append(features)
                score_list.append(rule_score)
            except Exception:
                logger.exception("Failed to extract features for client %s", client_id)

        if len(feature_list) < 10:
            logger.info("Not enough feature vectors for clustering: %d", len(feature_list))
            await task_engine.dispose()
            return

        feature_matrix = np.vstack(feature_list)
        score_array = np.array(score_list)

        cluster_model = CreditClusterModel()
        metrics = cluster_model.train(feature_matrix, score_array)
        logger.info("Credit cluster model retrained: %s", metrics)

    await task_engine.dispose()


async def _evaluate_request(credit_request_id: str):
    """Re-score a specific client for a credit request."""
    from uuid import UUID

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.models.credit_request import CreditRequest
    from app.services.credit_service import CreditService

    task_engine = create_async_engine(settings.database_url, pool_size=5, max_overflow=2)
    task_session = async_sessionmaker(task_engine, class_=AsyncSession, expire_on_commit=False)

    async with task_session() as db:
        request_uuid = UUID(credit_request_id)
        result = await db.execute(
            select(CreditRequest).where(CreditRequest.id == request_uuid)
        )
        credit_request = result.scalar_one_or_none()
        if not credit_request:
            logger.error("Credit request %s not found", credit_request_id)
            await task_engine.dispose()
            return

        service = CreditService(db)
        profile = await service.compute_credit_profile(
            credit_request.fineract_client_id
        )

        # Update request with fresh scores
        from app.ml.credit_scorer import CreditScorer
        scorer = CreditScorer()
        credit_request.credit_score_at_request = profile.credit_score
        credit_request.segment_at_request = profile.segment
        credit_request.max_credit_at_request = profile.max_credit_amount
        credit_request.recommendation = scorer.recommend(
            score=profile.credit_score,
            segment=profile.segment,
            requested_amount=credit_request.requested_amount,
            max_amount=profile.max_credit_amount,
        )

        await db.commit()
        logger.info(
            "Credit request %s re-evaluated: score=%.2f, recommendation=%s",
            credit_request_id,
            profile.credit_score,
            credit_request.recommendation.value,
        )

    await task_engine.dispose()


@celery_app.task(name="app.tasks.credit_scoring.compute_all_credit_scores")
def compute_all_credit_scores():
    """Nightly task: compute credit scores for all active clients."""
    _run_async(_compute_all_scores())


@celery_app.task(name="app.tasks.credit_scoring.retrain_credit_cluster_model")
def retrain_credit_cluster_model():
    """Weekly task: retrain K-Means clustering model."""
    _run_async(_retrain_cluster_model())


@celery_app.task(
    name="app.tasks.credit_scoring.evaluate_credit_request",
    bind=True,
    max_retries=3,
)
def evaluate_credit_request(self, credit_request_id: str):
    """On-demand task: re-evaluate a specific credit request."""
    try:
        _run_async(_evaluate_request(credit_request_id))
    except Exception as exc:
        logger.exception("Failed to evaluate credit request %s", credit_request_id)
        self.retry(exc=exc, countdown=10)
