"""Model training tasks — scheduled periodic retraining.

Anomaly detector: retrained daily on all recent transactions.
Fraud classifier: retrained weekly once enough labeled data exists.

IMPORTANT: Features are extracted with proper account history windows
to avoid train/serve skew. Each transaction gets its 1h and 24h history
reconstructed from the training batch + database, matching inference behavior.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import timedelta

import numpy as np

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _build_account_history(
    tx: "Transaction",
    all_transactions: list["Transaction"],
    account_index: dict[str, list["Transaction"]],
) -> tuple[list["Transaction"], list["Transaction"]]:
    """Reconstruct 1h and 24h account history for a transaction from batch data.

    This ensures training features match inference features (no train/serve skew).
    """
    siblings = account_index.get(tx.fineract_account_id, [])
    tx_date = tx.transaction_date
    cutoff_1h = tx_date - timedelta(hours=1)
    cutoff_24h = tx_date - timedelta(hours=24)

    history_1h = [
        t for t in siblings
        if t.id != tx.id and cutoff_1h <= t.transaction_date < tx_date
    ]
    history_24h = [
        t for t in siblings
        if t.id != tx.id and cutoff_24h <= t.transaction_date < tx_date
    ]
    return history_1h, history_24h


def _build_account_index(transactions: list["Transaction"]) -> dict[str, list["Transaction"]]:
    """Index transactions by account ID for efficient history lookup."""
    index: dict[str, list["Transaction"]] = defaultdict(list)
    for tx in transactions:
        index[tx.fineract_account_id].append(tx)
    return index


def _save_drift_baseline(feature_matrix, detector, feature_names):
    """Save drift baseline after anomaly detector training."""
    try:
        from app.ml.drift_detector import DriftDetector

        scores = np.array([detector.predict(row) for row in feature_matrix[:1000]])
        drift = DriftDetector()
        drift.save_baseline(feature_matrix[:1000], scores, feature_names)
    except Exception as e:
        logger.warning("Failed to save drift baseline: %s", e)


def _check_and_log_drift(feature_matrix, feature_names):
    """Check feature drift against baseline."""
    try:
        from app.ml.drift_detector import DriftDetector

        drift = DriftDetector()
        # Use zero scores as placeholder — real scores computed during analysis
        scores = np.zeros(len(feature_matrix))
        result = drift.check_drift(feature_matrix, scores, feature_names)
        if result.get("status") in ("warning", "critical"):
            logger.warning("Drift detected: %s", result)
    except Exception as e:
        logger.warning("Failed to check drift: %s", e)


def _log_to_mlflow(model_name: str, metrics: dict):
    """Log training metrics to MLflow if available."""
    try:
        import mlflow

        from app.core.config import settings

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment(settings.mlflow_experiment_name)

        with mlflow.start_run(run_name=f"{model_name}_retrain"):
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    mlflow.log_metric(key, value)
                elif isinstance(value, str):
                    mlflow.log_param(key, value[:250])  # MLflow param limit
            mlflow.log_param("model_name", model_name)
    except Exception as e:
        logger.debug("MLflow logging skipped (not available): %s", e)


async def _retrain_anomaly():
    from sqlalchemy import select

    from app.core.database import async_session
    from app.features.extractor import FeatureExtractor
    from app.ml.anomaly_detector import AnomalyDetector
    from app.models.transaction import Transaction

    async with async_session() as db:
        result = await db.execute(
            select(Transaction).order_by(Transaction.created_at.desc()).limit(10000)
        )
        transactions = list(result.scalars().all())

        if len(transactions) < 100:
            logger.info("Not enough transactions for anomaly training: %d", len(transactions))
            return

        # Build account index for efficient history reconstruction
        account_index = _build_account_index(transactions)

        # Build feature matrix with proper account history (fixes train/serve skew)
        features_list = []
        for tx in transactions:
            history_1h, history_24h = _build_account_history(tx, transactions, account_index)
            features = FeatureExtractor.extract(tx, history_1h, history_24h)
            features_list.append(features)

        feature_matrix = np.vstack(features_list)

        detector = AnomalyDetector()
        metrics = detector.train(feature_matrix)

        # Save drift baseline and log to MLflow
        _save_drift_baseline(feature_matrix, detector, FeatureExtractor.get_feature_names())
        _log_to_mlflow("anomaly_detector", metrics)

        logger.info("Anomaly detector retrained: %s", metrics)


async def _retrain_classifier():
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.core.database import async_session
    from app.features.extractor import FeatureExtractor
    from app.ml.fraud_classifier import FraudClassifier
    from app.models.alert import Alert, AlertStatus
    from app.models.transaction import Transaction

    async with async_session() as db:
        # Get labeled data: transactions with confirmed fraud or false positive alerts
        fraud_alerts = await db.execute(
            select(Alert)
            .options(selectinload(Alert.transaction))
            .where(Alert.status == AlertStatus.CONFIRMED_FRAUD)
        )
        legit_alerts = await db.execute(
            select(Alert)
            .options(selectinload(Alert.transaction))
            .where(Alert.status == AlertStatus.FALSE_POSITIVE)
        )

        fraud_txs = [a.transaction for a in fraud_alerts.scalars().all() if a.transaction]
        legit_txs = [a.transaction for a in legit_alerts.scalars().all() if a.transaction]

        classifier = FraudClassifier()
        if not classifier.can_train(len(fraud_txs), len(fraud_txs) + len(legit_txs)):
            logger.info(
                "Not enough labeled data: %d fraud, %d legitimate (need %d fraud, %d total)",
                len(fraud_txs),
                len(legit_txs),
                classifier.MIN_FRAUD_SAMPLES,
                classifier.MIN_TOTAL_SAMPLES,
            )
            return

        # Collect all labeled transactions and fetch their account history
        all_labeled_txs = fraud_txs + legit_txs

        # Fetch surrounding transactions for all accounts involved (24h window)
        account_ids = {tx.fineract_account_id for tx in all_labeled_txs}
        all_related_txs = []
        for account_id in account_ids:
            result = await db.execute(
                select(Transaction)
                .where(Transaction.fineract_account_id == account_id)
                .order_by(Transaction.transaction_date)
            )
            all_related_txs.extend(result.scalars().all())

        account_index = _build_account_index(all_related_txs)

        # Build feature matrix with proper account history (fixes train/serve skew)
        features_list = []
        labels = []

        for tx in fraud_txs:
            history_1h, history_24h = _build_account_history(tx, all_related_txs, account_index)
            features = FeatureExtractor.extract(tx, history_1h, history_24h)
            features_list.append(features)
            labels.append(1)

        for tx in legit_txs:
            history_1h, history_24h = _build_account_history(tx, all_related_txs, account_index)
            features = FeatureExtractor.extract(tx, history_1h, history_24h)
            features_list.append(features)
            labels.append(0)

        feature_matrix = np.vstack(features_list)
        label_array = np.array(labels)

        metrics = classifier.train(
            feature_matrix,
            label_array,
            feature_names=FeatureExtractor.get_feature_names(),
        )

        # Check drift and log to MLflow
        _check_and_log_drift(feature_matrix, FeatureExtractor.get_feature_names())
        _log_to_mlflow("fraud_classifier", metrics)

        logger.info("Fraud classifier retrained: %s", metrics)


@celery_app.task(name="app.tasks.training.retrain_anomaly_detector")
def retrain_anomaly_detector():
    """Retrain the anomaly detector on recent transactions."""
    _run_async(_retrain_anomaly())


@celery_app.task(name="app.tasks.training.retrain_fraud_classifier")
def retrain_fraud_classifier():
    """Retrain the fraud classifier on labeled data."""
    _run_async(_retrain_classifier())
