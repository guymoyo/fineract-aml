"""Credit scoring models — rule-based scorer and ML clustering.

Two scoring approaches run in parallel:

1. **CreditScorer** (rule-based, always available):
   Applies a weighted formula to customer-level features to produce a
   credit score (0-1). The score maps to a segment tier (A-E) with
   configurable thresholds, which determines the max credit amount.

2. **CreditClusterModel** (ML, trained weekly):
   Uses K-Means clustering to discover natural customer segments from
   feature space. Clusters are mapped to tiers by sorting centroids
   by average rule-based score. This validates and may refine the
   rule-based segmentation over time.
"""

import logging
from pathlib import Path

import joblib
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from app.core.config import settings
from app.models.credit_profile import CreditSegment

logger = logging.getLogger(__name__)

# Ordered tiers from best to worst
SEGMENT_ORDER = [
    CreditSegment.TIER_A,
    CreditSegment.TIER_B,
    CreditSegment.TIER_C,
    CreditSegment.TIER_D,
    CreditSegment.TIER_E,
]


class CreditScorer:
    """Rule-based credit scorer using weighted feature formula.

    Always available — no training required. Uses configurable weights
    from application settings.
    """

    def __init__(self):
        self.weights = self._load_weights()
        self.tier_thresholds = [
            (settings.credit_tier_a_min_score, CreditSegment.TIER_A),
            (settings.credit_tier_b_min_score, CreditSegment.TIER_B),
            (settings.credit_tier_c_min_score, CreditSegment.TIER_C),
            (settings.credit_tier_d_min_score, CreditSegment.TIER_D),
        ]
        self.tier_amounts = {
            CreditSegment.TIER_A: settings.credit_tier_a_max_amount,
            CreditSegment.TIER_B: settings.credit_tier_b_max_amount,
            CreditSegment.TIER_C: settings.credit_tier_c_max_amount,
            CreditSegment.TIER_D: settings.credit_tier_d_max_amount,
            CreditSegment.TIER_E: settings.credit_tier_e_max_amount,
        }

    def _load_weights(self) -> dict[str, float]:
        """Load scoring weights from settings."""
        return {
            "deposit_consistency": settings.credit_weight_deposit_consistency,
            "net_flow": settings.credit_weight_net_flow,
            "savings_rate": settings.credit_weight_savings_rate,
            "tx_frequency": settings.credit_weight_tx_frequency,
            "account_age": settings.credit_weight_account_age,
            "repayment_rate": settings.credit_weight_repayment_rate,
            "fraud_history": settings.credit_weight_fraud_history,
        }

    def score(self, features: np.ndarray) -> tuple[float, dict]:
        """Compute credit score from feature vector.

        Args:
            features: 1D array from CreditFeatureExtractor.extract().

        Returns:
            (score, components) where score is 0-1 and components is a
            dict of individual component scores for explainability.
        """
        from app.features.credit_extractor import CREDIT_FEATURE_NAMES

        # Create feature dict for easy access
        feat = dict(zip(CREDIT_FEATURE_NAMES, features))

        components = {}

        # 1. Deposit consistency (already 0-1)
        components["deposit_consistency"] = float(feat["deposit_consistency"])

        # 2. Net flow score: sigmoid-normalize net monthly flow
        net_flow = feat["net_monthly_flow"]
        components["net_flow"] = float(_sigmoid_normalize(net_flow, scale=50000))

        # 3. Savings rate (already 0-1)
        components["savings_rate"] = float(feat["savings_rate"])

        # 4. Transaction frequency: normalize (higher = better, caps at ~30/month)
        components["tx_frequency"] = float(min(feat["transaction_frequency"] / 30.0, 1.0))

        # 5. Account age: normalize (caps at 365 days)
        components["account_age"] = float(min(feat["account_age_days"] / 365.0, 1.0))

        # 6. Loan repayment rate (already 0-1, 1.0 = perfect or no loans)
        components["repayment_rate"] = float(feat["loan_repayment_rate"])

        # 7. Fraud history: penalize fraud alerts
        fraud_alerts = feat["total_fraud_alerts"]
        days_since = feat["days_since_last_fraud_alert"]
        # Score: 1.0 if no alerts, decreases with more alerts / more recent
        fraud_penalty = max(0.0, 1.0 - (fraud_alerts * 0.2))
        recency_factor = min(days_since / 365.0, 1.0)
        components["fraud_history"] = float(fraud_penalty * recency_factor)

        # Weighted combination
        total_score = 0.0
        for key, weight in self.weights.items():
            total_score += components.get(key, 0.0) * weight

        # Clamp to [0, 1]
        total_score = max(0.0, min(1.0, total_score))

        return total_score, components

    def classify_segment(self, score: float) -> CreditSegment:
        """Map a credit score to a segment tier.

        Args:
            score: Credit score between 0 and 1.

        Returns:
            The appropriate CreditSegment tier.
        """
        for threshold, segment in self.tier_thresholds:
            if score >= threshold:
                return segment
        return CreditSegment.TIER_E

    def compute_max_amount(self, segment: CreditSegment) -> float:
        """Get the maximum credit amount for a segment tier.

        Args:
            segment: The customer's credit segment.

        Returns:
            Maximum borrowable amount in default currency.
        """
        return self.tier_amounts.get(segment, 0.0)

    def recommend(
        self, score: float, segment: CreditSegment, requested_amount: float, max_amount: float
    ) -> str:
        """Generate a recommendation for a credit request.

        Args:
            score: Customer's credit score (0-1).
            segment: Customer's segment tier.
            requested_amount: Amount the customer wants to borrow.
            max_amount: Max amount for their tier.

        Returns:
            One of: "approve", "review_carefully", "reject".
        """
        from app.models.credit_request import CreditRecommendation

        if segment == CreditSegment.TIER_E or score < settings.credit_tier_d_min_score:
            return CreditRecommendation.REJECT

        if requested_amount > max_amount:
            return CreditRecommendation.REJECT

        if requested_amount <= max_amount * 0.5 and score >= settings.credit_tier_b_min_score:
            return CreditRecommendation.APPROVE

        return CreditRecommendation.REVIEW_CAREFULLY


class CreditClusterModel:
    """K-Means clustering model for customer segmentation validation.

    Discovers natural customer segments from feature space. Clusters are
    mapped to credit tiers by sorting centroids by average rule-based
    credit score (best cluster → Tier A, worst → Tier E).

    Follows the same persistence pattern as FraudClassifier.
    """

    def __init__(self):
        self.model: KMeans | None = None
        self.scaler: StandardScaler | None = None
        self.cluster_to_segment: dict[int, CreditSegment] | None = None
        self._model_path = Path(settings.model_path) / "credit_cluster.joblib"
        self._scaler_path = Path(settings.model_path) / "credit_cluster_scaler.joblib"

    @property
    def is_ready(self) -> bool:
        """Whether a trained model is available for prediction."""
        if self.model is not None:
            return True
        self._load()
        return self.model is not None

    def train(
        self,
        features: np.ndarray,
        rule_scores: np.ndarray,
        n_clusters: int = 5,
    ) -> dict:
        """Train K-Means clustering on customer feature matrix.

        Args:
            features: 2D array (n_customers, n_features).
            rule_scores: 1D array of rule-based scores for each customer
                         (used to map clusters to tiers).
            n_clusters: Number of clusters (default 5 = number of tiers).

        Returns:
            Training metrics including silhouette score and cluster stats.
        """
        logger.info("Training credit cluster model: %d customers, %d clusters", len(features), n_clusters)

        self.scaler = StandardScaler()
        scaled = self.scaler.fit_transform(features)

        self.model = KMeans(
            n_clusters=n_clusters,
            random_state=42,
            n_init=10,
            max_iter=300,
        )
        labels = self.model.fit_predict(scaled)

        # Map clusters to tiers by average rule-based score
        cluster_avg_scores = {}
        for cluster_id in range(n_clusters):
            mask = labels == cluster_id
            if mask.any():
                cluster_avg_scores[cluster_id] = float(np.mean(rule_scores[mask]))
            else:
                cluster_avg_scores[cluster_id] = 0.0

        # Sort clusters by score (best first) and map to tiers
        sorted_clusters = sorted(cluster_avg_scores.items(), key=lambda x: x[1], reverse=True)
        self.cluster_to_segment = {}
        for rank, (cluster_id, _) in enumerate(sorted_clusters):
            tier_idx = min(rank, len(SEGMENT_ORDER) - 1)
            self.cluster_to_segment[cluster_id] = SEGMENT_ORDER[tier_idx]

        self._save()

        # Compute metrics
        sil_score = float(silhouette_score(scaled, labels)) if len(set(labels)) > 1 else 0.0
        cluster_sizes = {int(k): int(v) for k, v in zip(*np.unique(labels, return_counts=True))}
        cluster_info = {
            str(cid): {
                "size": cluster_sizes.get(cid, 0),
                "avg_score": cluster_avg_scores.get(cid, 0.0),
                "mapped_tier": self.cluster_to_segment.get(cid, CreditSegment.TIER_E).value,
            }
            for cid in range(n_clusters)
        }

        metrics = {
            "n_customers": len(features),
            "n_clusters": n_clusters,
            "silhouette_score": sil_score,
            "clusters": cluster_info,
        }
        logger.info("Credit cluster model trained: silhouette=%.4f", sil_score)
        return metrics

    def predict(self, features: np.ndarray) -> tuple[int, CreditSegment]:
        """Predict cluster and suggested segment for a customer.

        Args:
            features: 1D array of customer features.

        Returns:
            (cluster_id, suggested_segment).
        """
        if not self.is_ready:
            return -1, CreditSegment.TIER_E

        scaled = self.scaler.transform(features.reshape(1, -1))
        cluster_id = int(self.model.predict(scaled)[0])
        segment = self.cluster_to_segment.get(cluster_id, CreditSegment.TIER_E)
        return cluster_id, segment

    def _save(self):
        model_dir = Path(settings.model_path)
        model_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "cluster_to_segment": self.cluster_to_segment,
            },
            self._model_path,
        )
        joblib.dump(self.scaler, self._scaler_path)
        logger.info("Credit cluster model saved")

    def _load(self):
        if self._model_path.exists() and self._scaler_path.exists():
            data = joblib.load(self._model_path)
            self.model = data["model"]
            self.cluster_to_segment = data["cluster_to_segment"]
            self.scaler = joblib.load(self._scaler_path)
            logger.info("Credit cluster model loaded")


def _sigmoid_normalize(value: float, scale: float = 1.0) -> float:
    """Map any real value to (0, 1) via sigmoid, centered at 0."""
    return 1.0 / (1.0 + np.exp(-value / scale))
