"""Model training tasks — scheduled periodic retraining.

Anomaly detector: retrained daily on all recent transactions.
Fraud classifier: retrained weekly once enough labeled data exists.
"""

import asyncio
import logging

import numpy as np

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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

        # Build feature matrix
        features_list = []
        for tx in transactions:
            # Simplified: use transaction-level features only for batch training
            features = FeatureExtractor.extract(tx, [], [])
            features_list.append(features)

        feature_matrix = np.vstack(features_list)

        detector = AnomalyDetector()
        metrics = detector.train(feature_matrix)
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
                50,
                200,
            )
            return

        # Build feature matrix and labels
        features_list = []
        labels = []

        for tx in fraud_txs:
            features = FeatureExtractor.extract(tx, [], [])
            features_list.append(features)
            labels.append(1)

        for tx in legit_txs:
            features = FeatureExtractor.extract(tx, [], [])
            features_list.append(features)
            labels.append(0)

        feature_matrix = np.vstack(features_list)
        label_array = np.array(labels)

        metrics = classifier.train(
            feature_matrix,
            label_array,
            feature_names=FeatureExtractor.get_feature_names(),
        )
        logger.info("Fraud classifier retrained: %s", metrics)


@celery_app.task(name="app.tasks.training.retrain_anomaly_detector")
def retrain_anomaly_detector():
    """Retrain the anomaly detector on recent transactions."""
    _run_async(_retrain_anomaly())


@celery_app.task(name="app.tasks.training.retrain_fraud_classifier")
def retrain_fraud_classifier():
    """Retrain the fraud classifier on labeled data."""
    _run_async(_retrain_classifier())
