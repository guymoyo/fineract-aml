"""Model drift detection using Population Stability Index (PSI).

Monitors feature and score distributions over time to detect when
ML models degrade due to data drift. Alerts when drift exceeds thresholds.

PSI interpretation:
- PSI < 0.10: No significant drift
- 0.10 <= PSI < 0.25: Moderate drift — investigate
- PSI >= 0.25: Significant drift — retrain immediately
"""

import json
import logging
from pathlib import Path

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

PSI_THRESHOLD_WARNING = 0.10
PSI_THRESHOLD_CRITICAL = 0.25


def compute_psi(
    expected: np.ndarray, actual: np.ndarray, n_bins: int = 10
) -> float:
    """Compute Population Stability Index between two distributions.

    Args:
        expected: Reference (training) distribution values.
        actual: Current (production) distribution values.
        n_bins: Number of bins for histogram comparison.

    Returns:
        PSI value. Higher = more drift.
    """
    if len(expected) < n_bins or len(actual) < n_bins:
        return 0.0

    # Create bins from the expected distribution
    breakpoints = np.percentile(expected, np.linspace(0, 100, n_bins + 1))
    breakpoints = np.unique(breakpoints)
    if len(breakpoints) < 2:
        return 0.0

    # Compute proportions in each bin
    expected_counts = np.histogram(expected, bins=breakpoints)[0]
    actual_counts = np.histogram(actual, bins=breakpoints)[0]

    # Add small epsilon to avoid division by zero
    eps = 1e-6
    expected_pct = (expected_counts + eps) / (len(expected) + eps * len(expected_counts))
    actual_pct = (actual_counts + eps) / (len(actual) + eps * len(actual_counts))

    # PSI formula: sum((actual_pct - expected_pct) * ln(actual_pct / expected_pct))
    psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return float(psi)


class DriftDetector:
    """Monitors feature and score distributions for model drift."""

    def __init__(self):
        self._baseline_path = Path(settings.model_path) / "drift_baseline.json"
        self._baseline: dict | None = None

    def save_baseline(
        self,
        feature_matrix: np.ndarray,
        scores: np.ndarray,
        feature_names: list[str],
    ) -> None:
        """Save the current distribution as a baseline for future comparison.

        Call this after model retraining with the training data.
        """
        baseline = {
            "feature_stats": {},
            "score_stats": {
                "mean": float(np.mean(scores)),
                "std": float(np.std(scores)),
                "percentiles": np.percentile(scores, [10, 25, 50, 75, 90]).tolist(),
                "values": scores[:5000].tolist(),  # Store up to 5000 for PSI
            },
            "n_samples": len(scores),
        }

        for i, name in enumerate(feature_names):
            col = feature_matrix[:, i]
            baseline["feature_stats"][name] = {
                "mean": float(np.mean(col)),
                "std": float(np.std(col)),
                "percentiles": np.percentile(col, [10, 25, 50, 75, 90]).tolist(),
                "values": col[:5000].tolist(),
            }

        model_dir = Path(settings.model_path)
        model_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self._baseline_path.with_suffix(".json.tmp")
        with open(tmp_path, "w") as f:
            json.dump(baseline, f)
        tmp_path.replace(self._baseline_path)

        self._baseline = baseline
        logger.info("Drift baseline saved: %d samples, %d features", len(scores), len(feature_names))

    def check_drift(
        self,
        feature_matrix: np.ndarray,
        scores: np.ndarray,
        feature_names: list[str],
    ) -> dict:
        """Compare current distributions against baseline.

        Returns:
            Dict with per-feature PSI values, overall score PSI,
            and drift severity assessment.
        """
        if self._baseline is None:
            self._load_baseline()

        if self._baseline is None:
            return {"status": "no_baseline", "message": "No baseline saved yet"}

        result = {
            "status": "ok",
            "feature_drift": {},
            "score_psi": 0.0,
            "drifted_features": [],
            "critical_features": [],
        }

        # Check score distribution drift
        baseline_scores = np.array(self._baseline["score_stats"]["values"])
        score_psi = compute_psi(baseline_scores, scores)
        result["score_psi"] = round(score_psi, 4)

        # Check each feature
        for i, name in enumerate(feature_names):
            if name not in self._baseline["feature_stats"]:
                continue
            baseline_values = np.array(self._baseline["feature_stats"][name]["values"])
            current_values = feature_matrix[:, i]
            psi = compute_psi(baseline_values, current_values)
            result["feature_drift"][name] = round(psi, 4)

            if psi >= PSI_THRESHOLD_CRITICAL:
                result["critical_features"].append(name)
            elif psi >= PSI_THRESHOLD_WARNING:
                result["drifted_features"].append(name)

        # Overall assessment
        if score_psi >= PSI_THRESHOLD_CRITICAL or len(result["critical_features"]) > 0:
            result["status"] = "critical"
            logger.warning(
                "CRITICAL drift detected: score_psi=%.4f, critical_features=%s",
                score_psi, result["critical_features"],
            )
        elif score_psi >= PSI_THRESHOLD_WARNING or len(result["drifted_features"]) > 0:
            result["status"] = "warning"
            logger.warning(
                "Moderate drift detected: score_psi=%.4f, drifted_features=%s",
                score_psi, result["drifted_features"],
            )

        return result

    def _load_baseline(self) -> None:
        if self._baseline_path.exists():
            with open(self._baseline_path) as f:
                self._baseline = json.load(f)
            logger.info("Drift baseline loaded: %d samples", self._baseline.get("n_samples", 0))
