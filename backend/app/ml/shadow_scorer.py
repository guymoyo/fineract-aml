"""Shadow/canary ML model runner.

Implements a shadow deployment pattern for ML models:
- The "production" model drives real decisions
- A "shadow" (challenger) model scores every transaction in parallel
- Shadow scores are logged but don't affect alerts
- When the shadow model outperforms production consistently (AUC delta > 0.02
  for 7 days), it can be promoted via the `promote_shadow_model` task

Inspired by Medium article on CI/CD for ML models.
"""

import logging
from pathlib import Path

import joblib
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


class ShadowScorer:
    """Runs a challenger model alongside the production model.

    Usage:
        scorer = ShadowScorer()
        shadow_score = scorer.predict(features)  # returns None if no shadow model
    """

    def __init__(self):
        self.model = None
        self.scaler = None
        model_dir = Path(settings.model_path)
        self._model_path = model_dir / "model_shadow.joblib"
        self._scaler_path = model_dir / "model_shadow_scaler.joblib"
        self._loaded = False

    @property
    def is_ready(self) -> bool:
        if not self._loaded:
            self._load()
        return self.model is not None

    def predict(self, features: np.ndarray) -> float | None:
        """Score a transaction with the shadow model.

        Returns None if no shadow model is available, so callers can
        safely ignore the result without changing production behavior.
        """
        if not self.is_ready:
            return None
        try:
            scaled = self.scaler.transform(features.reshape(1, -1))
            raw = self.model.predict_proba(scaled)[0, 1]
            return float(np.clip(raw, 0.0, 1.0))
        except Exception as exc:
            logger.debug("Shadow scorer predict failed: %s", exc)
            return None

    def save_as_shadow(self, model, scaler) -> None:
        """Write a newly trained model as the shadow challenger (not production)."""
        model_dir = Path(settings.model_path)
        model_dir.mkdir(parents=True, exist_ok=True)
        tmp_m = self._model_path.with_suffix(".joblib.tmp")
        tmp_s = self._scaler_path.with_suffix(".joblib.tmp")
        joblib.dump(model, tmp_m)
        joblib.dump(scaler, tmp_s)
        tmp_m.replace(self._model_path)
        tmp_s.replace(self._scaler_path)
        logger.info("Shadow model saved to %s", self._model_path)
        # Reset so next predict() call reloads from disk
        self._loaded = False
        self.model = None
        self.scaler = None

    def promote_to_production(self, production_model_path: str, production_scaler_path: str) -> None:
        """Overwrite the production model with the shadow model.

        Called after validation confirms the shadow model outperforms production.
        """
        import shutil

        if not self._model_path.exists():
            raise FileNotFoundError("No shadow model to promote")

        shutil.copy2(self._model_path, production_model_path)
        shutil.copy2(self._scaler_path, production_scaler_path)
        logger.info(
            "Shadow model promoted to production: %s → %s",
            self._model_path, production_model_path,
        )

    def _load(self):
        if self._model_path.exists() and self._scaler_path.exists():
            try:
                self.model = joblib.load(self._model_path)
                self.scaler = joblib.load(self._scaler_path)
                logger.debug("Shadow model loaded from %s", self._model_path)
            except Exception as exc:
                logger.warning("Failed to load shadow model: %s", exc)
                self.model = None
                self.scaler = None
        self._loaded = True
