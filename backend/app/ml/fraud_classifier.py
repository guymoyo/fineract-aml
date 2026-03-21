"""Supervised fraud classifier — trained on human-labeled data.

This module uses XGBoost to classify transactions as fraud/not-fraud.
It only becomes active once enough labeled data is available (from
analyst reviews in the compliance dashboard).

The training pipeline:
1. Analyst reviews alerts → labeled data (fraud/legitimate)
2. Feature engineering extracts features from transactions
3. XGBoost trains on labeled features
4. Model is versioned and tracked in MLflow
5. New transactions scored in real-time
"""

import logging
from pathlib import Path

import joblib
import numpy as np
import xgboost as xgb
from sklearn.metrics import (
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score

from app.core.config import settings

logger = logging.getLogger(__name__)

# Minimum labeled samples needed before training a supervised model.
# With 22 features and 5-fold CV, we need enough fraud samples to have
# statistically meaningful test folds (~40+ fraud per fold).
MIN_FRAUD_SAMPLES = 200
MIN_TOTAL_SAMPLES = 1000

# Validation gates — new models must meet these thresholds to be deployed
MIN_CV_AUC = 0.80
MAX_CV_AUC_STD = 0.05


class FraudClassifier:
    """XGBoost-based fraud classifier.

    Only activated when sufficient labeled data is available.
    Until then, the system relies on rules + anomaly detection.
    """

    MIN_FRAUD_SAMPLES = MIN_FRAUD_SAMPLES
    MIN_TOTAL_SAMPLES = MIN_TOTAL_SAMPLES

    def __init__(self):
        self.model: xgb.XGBClassifier | None = None
        self.version: str | None = None
        self._model_path = Path(settings.model_path) / "fraud_classifier.joblib"

    @property
    def is_ready(self) -> bool:
        """Whether a trained model is available for scoring."""
        if self.model is not None:
            return True
        self._load()
        return self.model is not None

    def can_train(self, n_fraud: int, n_total: int) -> bool:
        """Check if there's enough labeled data to train."""
        return n_fraud >= MIN_FRAUD_SAMPLES and n_total >= MIN_TOTAL_SAMPLES

    def train(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        feature_names: list[str] | None = None,
    ) -> dict:
        """Train the fraud classifier on labeled data.

        Args:
            features: 2D array (n_samples, n_features).
            labels: 1D binary array (0=legitimate, 1=fraud).
            feature_names: Optional feature names for interpretability.

        Returns:
            Training metrics including AUC, precision, recall, F1.
        """
        n_fraud = int(np.sum(labels == 1))
        n_legit = int(np.sum(labels == 0))
        scale_pos_weight = n_legit / max(n_fraud, 1)

        logger.info(
            "Training fraud classifier: %d samples (%d fraud, %d legitimate)",
            len(labels),
            n_fraud,
            n_legit,
        )

        self.model = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            scale_pos_weight=scale_pos_weight,
            min_child_weight=5,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            eval_metric="aucpr",
            use_label_encoder=False,
        )

        # Cross-validation for robust metrics
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        cv_scores = cross_val_score(
            self.model, features, labels, cv=cv, scoring="roc_auc"
        )

        # Final training on all data
        self.model.fit(features, labels)

        # Training predictions for metrics
        predictions = self.model.predict(features)
        probabilities = self.model.predict_proba(features)[:, 1]

        # Feature importance
        importance = {}
        if feature_names:
            for name, score in zip(feature_names, self.model.feature_importances_):
                importance[name] = float(score)

        cv_auc_mean = float(np.mean(cv_scores))
        cv_auc_std = float(np.std(cv_scores))

        metrics = {
            "version": None,
            "n_samples": len(labels),
            "n_fraud": n_fraud,
            "n_legitimate": n_legit,
            "cv_auc_mean": cv_auc_mean,
            "cv_auc_std": cv_auc_std,
            "train_auc": float(roc_auc_score(labels, probabilities)),
            "train_precision": float(precision_score(labels, predictions)),
            "train_recall": float(recall_score(labels, predictions)),
            "train_f1": float(f1_score(labels, predictions)),
            "feature_importance": importance,
            "classification_report": classification_report(
                labels, predictions, target_names=["legitimate", "fraud"]
            ),
            "deployed": False,
        }

        # Validation gate: only deploy if model meets quality thresholds
        if cv_auc_mean < MIN_CV_AUC or cv_auc_std > MAX_CV_AUC_STD:
            logger.warning(
                "Model failed validation gate: cv_auc=%.4f (min %.2f), cv_std=%.4f (max %.2f). "
                "Keeping previous model.",
                cv_auc_mean,
                MIN_CV_AUC,
                cv_auc_std,
                MAX_CV_AUC_STD,
            )
            # Restore previous model if it existed
            self.model = None
            self._load()
            return metrics

        self.version = f"v{len(labels)}_{n_fraud}f"
        metrics["version"] = self.version
        metrics["deployed"] = True
        self._save()

        logger.info("Fraud classifier trained and deployed: AUC=%.4f", cv_auc_mean)
        return metrics

    def predict(self, features: np.ndarray) -> tuple[float, str]:
        """Score a single transaction.

        Returns:
            (fraud_probability, model_version)
        """
        if not self.is_ready:
            return 0.0, "no_model"

        proba = self.model.predict_proba(features.reshape(1, -1))[0][1]
        return float(proba), self.version or "unknown"

    def _save(self):
        model_dir = Path(settings.model_path)
        model_dir.mkdir(parents=True, exist_ok=True)
        # Atomic write: dump to temp file, then rename to avoid read corruption
        tmp_path = self._model_path.with_suffix(".joblib.tmp")
        joblib.dump(
            {"model": self.model, "version": self.version}, tmp_path
        )
        tmp_path.replace(self._model_path)
        logger.info("Fraud classifier saved: %s", self.version)

    def _load(self):
        if self._model_path.exists():
            data = joblib.load(self._model_path)
            self.model = data["model"]
            self.version = data["version"]
            logger.info("Fraud classifier loaded: %s", self.version)
