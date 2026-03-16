"""Feature engineering — transforms raw transactions into ML-ready features.

Features are the numerical representations that ML models use to
make predictions. Good features are the #1 driver of model performance.

Feature categories:
1. Transaction-level: amount, time, type
2. Account-level: history, patterns, age
3. Behavioral: deviations from normal patterns
"""

import logging
from datetime import datetime, timezone

import numpy as np

from app.models.transaction import Transaction, TransactionType

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "amount",
    "amount_log",
    "is_deposit",
    "is_withdrawal",
    "is_transfer",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "is_night",  # 10PM-6AM
    "is_round_hundred",
    "is_round_thousand",
    "tx_count_1h",
    "tx_count_24h",
    "total_amount_1h",
    "total_amount_24h",
    "avg_amount_24h",
    "max_amount_24h",
    "amount_vs_avg_ratio",
    "unique_counterparties_24h",
    "same_type_ratio_24h",
    "is_new_ip_for_account",
    "unique_ips_24h",
]


class FeatureExtractor:
    """Extracts numerical features from a transaction and its context."""

    @staticmethod
    def extract(
        transaction: Transaction,
        account_history_1h: list[Transaction],
        account_history_24h: list[Transaction],
    ) -> np.ndarray:
        """Extract features for a single transaction.

        Args:
            transaction: The transaction to score.
            account_history_1h: Same account's transactions in last 1 hour.
            account_history_24h: Same account's transactions in last 24 hours.

        Returns:
            Feature vector as numpy array.
        """
        features = []

        # --- Transaction-level features ---
        features.append(transaction.amount)
        features.append(np.log1p(transaction.amount))

        # Transaction type one-hot
        features.append(1.0 if transaction.transaction_type == TransactionType.DEPOSIT else 0.0)
        features.append(1.0 if transaction.transaction_type == TransactionType.WITHDRAWAL else 0.0)
        features.append(1.0 if transaction.transaction_type == TransactionType.TRANSFER else 0.0)

        # Time features
        tx_dt = transaction.transaction_date
        if isinstance(tx_dt, datetime):
            hour = tx_dt.hour
            dow = tx_dt.weekday()
        else:
            hour = 12
            dow = 0

        features.append(float(hour))
        features.append(float(dow))
        features.append(1.0 if dow >= 5 else 0.0)  # weekend
        features.append(1.0 if hour >= 22 or hour <= 6 else 0.0)  # night

        # Round number flags
        features.append(1.0 if transaction.amount >= 100 and transaction.amount % 100 == 0 else 0.0)
        features.append(1.0 if transaction.amount >= 1000 and transaction.amount % 1000 == 0 else 0.0)

        # --- Account-level features (1h window) ---
        features.append(float(len(account_history_1h)))
        features.append(float(len(account_history_24h)))

        total_1h = sum(t.amount for t in account_history_1h)
        total_24h = sum(t.amount for t in account_history_24h)
        features.append(total_1h)
        features.append(total_24h)

        # Statistical features from 24h history
        if account_history_24h:
            amounts = [t.amount for t in account_history_24h]
            avg_24h = np.mean(amounts)
            max_24h = np.max(amounts)
            features.append(float(avg_24h))
            features.append(float(max_24h))
            features.append(transaction.amount / max(avg_24h, 1.0))
        else:
            features.append(0.0)
            features.append(0.0)
            features.append(1.0)

        # Unique counterparties in 24h
        counterparties = {
            t.counterparty_account_id
            for t in account_history_24h
            if t.counterparty_account_id
        }
        features.append(float(len(counterparties)))

        # Same transaction type ratio in 24h
        if account_history_24h:
            same_type = sum(
                1
                for t in account_history_24h
                if t.transaction_type == transaction.transaction_type
            )
            features.append(same_type / len(account_history_24h))
        else:
            features.append(0.0)

        # --- IP-based features ---
        known_ips = {
            t.ip_address for t in account_history_24h if getattr(t, "ip_address", None)
        }
        current_ip = getattr(transaction, "ip_address", None)
        # Is the IP new for this account (not seen in 24h history)?
        features.append(1.0 if current_ip and current_ip not in known_ips else 0.0)
        # Number of unique IPs used by account in 24h
        features.append(float(len(known_ips)))

        return np.array(features, dtype=np.float64)

    @staticmethod
    def get_feature_names() -> list[str]:
        return FEATURE_NAMES
