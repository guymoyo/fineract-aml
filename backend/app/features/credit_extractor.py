"""Customer-level credit feature extraction.

Unlike the transaction-level FeatureExtractor (which computes 22 features
per individual transaction), this module aggregates a customer's entire
transaction history into credit-relevant features over 30d/90d/180d windows.

These features feed into the CreditScorer for behavioral credit scoring.

Feature categories:
- Deposit patterns: consistency, volume, trend
- Withdrawal patterns: volume, trend
- Net flow & savings: income vs spending ratio
- Account activity: frequency, age, counterparty diversity
- Loan behavior: repayment rate (when loan transactions exist)
- Risk history: fraud alerts, geographic stability
- Transfer behavior: incoming/outgoing ratios, sender diversity
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np

logger = logging.getLogger(__name__)

CREDIT_FEATURE_NAMES = [
    # Deposit patterns
    "avg_monthly_deposits",
    "deposit_consistency",           # 1 - normalized std dev (higher = more consistent)
    # Withdrawal patterns
    "avg_monthly_withdrawals",
    # Net flow & savings
    "net_monthly_flow",              # deposits - withdrawals per month
    "savings_rate",                  # net_flow / deposits (0-1)
    # Activity
    "transaction_frequency",         # avg transactions per month
    "account_age_days",
    # Extremes
    "max_single_deposit",
    "max_single_withdrawal",
    # Loan behavior
    "loan_repayment_rate",           # repayments / disbursements (1.0 if no loans)
    # Risk history
    "days_since_last_fraud_alert",   # normalized: 365 if none
    "total_fraud_alerts",
    # Diversity
    "unique_counterparties",
    "geographic_stability",          # 1 - (unique_countries / total_txns)
    # Trends (recent vs historical)
    "deposit_trend",                 # 30d avg / 90d avg (>1 = improving)
    "withdrawal_trend",              # 30d avg / 90d avg (<1 = improving)
    # Transfer behavior
    "incoming_transfer_ratio",       # incoming transfers / total deposits
    "unique_transfer_senders_30d",
    "outgoing_transfer_ratio",       # outgoing transfers / total withdrawals
]


class CreditFeatureExtractor:
    """Extract customer-level credit features from transaction history.

    All features are designed so that higher values generally indicate
    better creditworthiness, except for total_fraud_alerts and
    withdrawal_trend where lower is better.
    """

    @staticmethod
    def get_feature_names() -> list[str]:
        """Return ordered list of feature names."""
        return list(CREDIT_FEATURE_NAMES)

    @staticmethod
    def extract(
        transactions: list,
        fraud_alert_count: int,
        days_since_last_fraud: int | None,
        account_age_days: int,
    ) -> np.ndarray:
        """Extract credit features for a single customer.

        Args:
            transactions: All transactions for this customer (up to 180 days).
            fraud_alert_count: Number of CONFIRMED_FRAUD alerts for this client.
            days_since_last_fraud: Days since most recent fraud alert, or None.
            account_age_days: Days since first transaction for this client.

        Returns:
            1D numpy array of shape (len(CREDIT_FEATURE_NAMES),).
        """
        features = []
        now = datetime.now(timezone.utc)

        if not transactions:
            return np.zeros(len(CREDIT_FEATURE_NAMES))

        # Categorize transactions by type
        deposits = []
        withdrawals = []
        loan_disbursements = []
        loan_repayments = []
        incoming_transfers = []
        outgoing_transfers = []

        for tx in transactions:
            tx_type = getattr(tx, "transaction_type", None)
            if tx_type is None:
                continue
            tx_type_val = tx_type.value if hasattr(tx_type, "value") else str(tx_type)
            amount = float(getattr(tx, "amount", 0))
            tx_date = getattr(tx, "transaction_date", now)

            if tx_type_val == "deposit":
                deposits.append((amount, tx_date))
            elif tx_type_val == "withdrawal":
                withdrawals.append((amount, tx_date))
            elif tx_type_val == "loan_disbursement":
                loan_disbursements.append((amount, tx_date))
            elif tx_type_val == "loan_repayment":
                loan_repayments.append((amount, tx_date))
            elif tx_type_val == "transfer":
                # Determine direction: if counterparty_account_id exists, it's outgoing
                # For incoming transfers, the customer's account receives the money
                counterparty = getattr(tx, "counterparty_account_id", None)
                if counterparty:
                    outgoing_transfers.append((amount, tx_date, counterparty))
                else:
                    incoming_transfers.append((amount, tx_date, None))

        # ── Deposit patterns ──────────────────────────────────

        # Group deposits by month
        monthly_deposits = _monthly_totals([a for a, _ in deposits], [d for _, d in deposits], now)
        avg_monthly_dep = float(np.mean(monthly_deposits)) if monthly_deposits else 0.0
        features.append(avg_monthly_dep)

        # Deposit consistency: 1 - coefficient of variation (clamped to [0, 1])
        if len(monthly_deposits) > 1 and avg_monthly_dep > 0:
            cv = float(np.std(monthly_deposits)) / avg_monthly_dep
            deposit_consistency = max(0.0, 1.0 - cv)
        else:
            deposit_consistency = 0.5  # unknown → neutral
        features.append(deposit_consistency)

        # ── Withdrawal patterns ───────────────────────────────

        monthly_withdrawals = _monthly_totals([a for a, _ in withdrawals], [d for _, d in withdrawals], now)
        avg_monthly_wd = float(np.mean(monthly_withdrawals)) if monthly_withdrawals else 0.0
        features.append(avg_monthly_wd)

        # ── Net flow & savings ────────────────────────────────

        net_monthly_flow = avg_monthly_dep - avg_monthly_wd
        features.append(net_monthly_flow)

        savings_rate = net_monthly_flow / avg_monthly_dep if avg_monthly_dep > 0 else 0.0
        savings_rate = max(0.0, min(1.0, savings_rate))
        features.append(savings_rate)

        # ── Activity ──────────────────────────────────────────

        months_active = max(account_age_days / 30.0, 1.0)
        tx_frequency = len(transactions) / months_active
        features.append(tx_frequency)

        features.append(float(account_age_days))

        # ── Extremes ─────────────────────────────────────────

        max_deposit = max((a for a, _ in deposits), default=0.0)
        features.append(float(max_deposit))

        max_withdrawal = max((a for a, _ in withdrawals), default=0.0)
        features.append(float(max_withdrawal))

        # ── Loan behavior ─────────────────────────────────────

        total_disbursed = sum(a for a, _ in loan_disbursements)
        total_repaid = sum(a for a, _ in loan_repayments)
        if total_disbursed > 0:
            repayment_rate = min(total_repaid / total_disbursed, 1.0)
        else:
            repayment_rate = 1.0  # no loans → perfect (neutral)
        features.append(repayment_rate)

        # ── Risk history ──────────────────────────────────────

        days_fraud = float(days_since_last_fraud) if days_since_last_fraud is not None else 365.0
        features.append(days_fraud)
        features.append(float(fraud_alert_count))

        # ── Diversity ─────────────────────────────────────────

        counterparties = set()
        for tx in transactions:
            cp = getattr(tx, "counterparty_account_id", None)
            if cp:
                counterparties.add(cp)
        features.append(float(len(counterparties)))

        countries = set()
        for tx in transactions:
            cc = getattr(tx, "country_code", None)
            if cc:
                countries.add(cc)
        geo_stability = 1.0 - (len(countries) / max(len(transactions), 1))
        geo_stability = max(0.0, geo_stability)
        features.append(geo_stability)

        # ── Trends ────────────────────────────────────────────

        cutoff_30d = now - timedelta(days=30)
        cutoff_90d = now - timedelta(days=90)

        dep_30d = sum(a for a, d in deposits if d >= cutoff_30d)
        dep_90d = sum(a for a, d in deposits if d >= cutoff_90d)
        deposit_trend = (dep_30d / 30.0) / (dep_90d / 90.0) if dep_90d > 0 else 1.0
        features.append(deposit_trend)

        wd_30d = sum(a for a, d in withdrawals if d >= cutoff_30d)
        wd_90d = sum(a for a, d in withdrawals if d >= cutoff_90d)
        withdrawal_trend = (wd_30d / 30.0) / (wd_90d / 90.0) if wd_90d > 0 else 1.0
        features.append(withdrawal_trend)

        # ── Transfer behavior ─────────────────────────────────

        total_deposit_amount = sum(a for a, _ in deposits)
        incoming_amount = sum(a for a, _, _ in incoming_transfers)
        incoming_ratio = incoming_amount / total_deposit_amount if total_deposit_amount > 0 else 0.0
        features.append(incoming_ratio)

        # Unique senders in last 30 days (for incoming transfers, we don't have sender info
        # so we use counterparty from outgoing as a proxy for transfer network diversity)
        recent_senders = set()
        for tx in transactions:
            tx_type = getattr(tx, "transaction_type", None)
            tx_date = getattr(tx, "transaction_date", now)
            cp = getattr(tx, "counterparty_account_id", None)
            if tx_type and hasattr(tx_type, "value") and tx_type.value == "transfer" and cp and tx_date >= cutoff_30d:
                recent_senders.add(cp)
        features.append(float(len(recent_senders)))

        total_withdrawal_amount = sum(a for a, _ in withdrawals)
        outgoing_amount = sum(a for a, _, _ in outgoing_transfers)
        outgoing_ratio = outgoing_amount / total_withdrawal_amount if total_withdrawal_amount > 0 else 0.0
        features.append(outgoing_ratio)

        assert len(features) == len(CREDIT_FEATURE_NAMES), (
            f"Expected {len(CREDIT_FEATURE_NAMES)} features, got {len(features)}"
        )
        return np.array(features, dtype=np.float64)


def _monthly_totals(amounts: list[float], dates: list[datetime], now: datetime) -> list[float]:
    """Group amounts by calendar month and return monthly totals."""
    if not amounts:
        return []
    monthly = defaultdict(float)
    for amount, date in zip(amounts, dates):
        key = (date.year, date.month)
        monthly[key] += amount
    return list(monthly.values())
