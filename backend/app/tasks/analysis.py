"""Transaction analysis tasks — triggered for every incoming transaction.

Pipeline:
1. Extract features from the transaction + account history
2. Run rule engine (deterministic checks)
3. Run anomaly detector (unsupervised ML — no labels needed)
4. Run fraud classifier (supervised ML — only if trained model exists)
5. Combine scores and create alert if threshold exceeded
"""

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _analyze(transaction_id: str):
    """Core analysis logic."""
    from datetime import timedelta

    from sqlalchemy import select
    from uuid import UUID

    from app.core.database import async_session
    from app.features.extractor import FeatureExtractor
    from app.ml.anomaly_detector import AnomalyDetector
    from app.ml.fraud_classifier import FraudClassifier
    from app.models.alert import AlertSource
    from app.models.rule_match import RuleMatch
    from app.models.transaction import Transaction
    from app.rules.engine import RuleEngine
    from app.services.transaction_service import TransactionService

    tx_uuid = UUID(transaction_id)

    async with async_session() as db:
        # 1. Load the transaction
        result = await db.execute(
            select(Transaction).where(Transaction.id == tx_uuid)
        )
        transaction = result.scalar_one_or_none()
        if not transaction:
            logger.error("Transaction %s not found", transaction_id)
            return

        service = TransactionService(db)

        # 2. Get account history for feature extraction
        history_1h = await service.get_account_history(
            transaction.fineract_account_id, window_minutes=60
        )
        history_24h = await service.get_account_history(
            transaction.fineract_account_id, window_minutes=1440
        )

        # 3. Extract features
        features = FeatureExtractor.extract(transaction, history_1h, history_24h)

        # 4. Run rule engine (uses 24h history for IP-based rules)
        rule_engine = RuleEngine()
        rule_result = rule_engine.evaluate(transaction, history_1h, history_24h)

        # Store rule matches
        for match in rule_result.triggered_rules:
            rule_match = RuleMatch(
                transaction_id=transaction.id,
                rule_name=match.rule_name,
                rule_category=match.category,
                severity=match.severity,
                details=match.details,
            )
            db.add(rule_match)

        # 5. Run anomaly detector
        anomaly_detector = AnomalyDetector()
        anomaly_score = anomaly_detector.predict(features)

        # 6. Run fraud classifier (only if trained)
        fraud_classifier = FraudClassifier()
        ml_score = 0.0
        model_version = None
        if fraud_classifier.is_ready:
            ml_score, model_version = fraud_classifier.predict(features)

        # 7. Combine scores
        # Priority: ML model > anomaly detection > rules
        if fraud_classifier.is_ready:
            final_score = ml_score * 0.5 + anomaly_score * 0.3 + rule_result.combined_score * 0.2
        else:
            # No ML model yet — rely more on rules + anomaly detection
            final_score = anomaly_score * 0.5 + rule_result.combined_score * 0.5

        # 8. Update transaction risk score
        await service.update_risk_score(
            transaction.id,
            risk_score=final_score,
            anomaly_score=anomaly_score,
            model_version=model_version,
        )

        # 9. Create alert if needed
        source = AlertSource.ML_MODEL if fraud_classifier.is_ready else AlertSource.ANOMALY_DETECTION
        if rule_result.triggered_rules and not fraud_classifier.is_ready:
            source = AlertSource.RULE_ENGINE

        await service.create_alert_if_needed(
            transaction,
            risk_score=final_score,
            source=source,
            triggered_rules=rule_result.rule_names if rule_result.triggered_rules else None,
        )

        await db.commit()

        logger.info(
            "Analysis complete for %s: rule_score=%.2f, anomaly=%.2f, ml=%.2f, final=%.2f",
            transaction.fineract_transaction_id,
            rule_result.combined_score,
            anomaly_score,
            ml_score,
            final_score,
        )


@celery_app.task(name="app.tasks.analysis.analyze_transaction", bind=True, max_retries=3)
def analyze_transaction(self, transaction_id: str):
    """Analyze a transaction for AML/fraud indicators."""
    try:
        _run_async(_analyze(transaction_id))
    except Exception as exc:
        logger.exception("Failed to analyze transaction %s", transaction_id)
        self.retry(exc=exc, countdown=10)
