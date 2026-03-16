"""Unsupervised anomaly detection — works WITHOUT labeled data.

This module uses Isolation Forest to detect unusual transactions.
The key insight: fraudulent transactions are rare and different from
normal ones, so they're easy to "isolate" in a decision tree.

No labels needed — the model learns what "normal" looks like and
flags anything that deviates.
"""

import logging
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.core.config import settings

logger = logging.getLogger(__name__)


class AnomalyDetector:
    """Isolation Forest-based anomaly detector for transactions.

    Training: fit on historical transactions (all assumed mostly normal).
    Inference: score new transactions — higher score = more anomalous.
    """

    def __init__(self):
        self.model: IsolationForest | None = None
        self.scaler: StandardScaler | None = None
        self._model_path = Path(settings.model_path) / "anomaly_detector.joblib"
        self._scaler_path = Path(settings.model_path) / "anomaly_scaler.joblib"

    def train(self, features: np.ndarray, contamination: float = 0.05) -> dict:
        """Train the anomaly detector on historical transaction features.

        Args:
            features: 2D array of shape (n_transactions, n_features).
            contamination: Expected proportion of anomalies (default 5%).

        Returns:
            Training metrics.
        """
        self.scaler = StandardScaler()
        scaled_features = self.scaler.fit_transform(features)

        self.model = IsolationForest(
            n_estimators=200,
            contamination=contamination,
            max_samples="auto",
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(scaled_features)

        # Get training anomaly scores
        scores = self.model.decision_function(scaled_features)
        predictions = self.model.predict(scaled_features)
        n_anomalies = int(np.sum(predictions == -1))

        self._save()

        metrics = {
            "n_samples": len(features),
            "n_anomalies_detected": n_anomalies,
            "anomaly_rate": n_anomalies / len(features),
            "mean_score": float(np.mean(scores)),
            "std_score": float(np.std(scores)),
        }
        logger.info("Anomaly detector trained: %s", metrics)
        return metrics

    def predict(self, features: np.ndarray) -> float:
        """Score a single transaction. Returns anomaly score between 0 and 1.

        Higher score = more anomalous = more suspicious.
        """
        if self.model is None:
            self._load()

        if self.model is None:
            logger.warning("No trained anomaly model available, returning 0.0")
            return 0.0

        scaled = self.scaler.transform(features.reshape(1, -1))

        # decision_function returns negative for anomalies
        raw_score = self.model.decision_function(scaled)[0]

        # Convert to 0-1 range where 1 = most anomalous
        # Raw scores: negative = anomaly, positive = normal
        # We invert and normalize using sigmoid-like transform
        anomaly_score = 1.0 / (1.0 + np.exp(raw_score * 5))

        return float(np.clip(anomaly_score, 0.0, 1.0))

    def _save(self):
        """Persist model and scaler to disk."""
        model_dir = Path(settings.model_path)
        model_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, self._model_path)
        joblib.dump(self.scaler, self._scaler_path)
        logger.info("Anomaly detector saved to %s", self._model_path)

    def _load(self):
        """Load model and scaler from disk."""
        if self._model_path.exists() and self._scaler_path.exists():
            self.model = joblib.load(self._model_path)
            self.scaler = joblib.load(self._scaler_path)
            logger.info("Anomaly detector loaded from %s", self._model_path)
        else:
            logger.warning("No saved anomaly detector found at %s", self._model_path)
