"""Rule engine — deterministic AML detection rules.

These rules run on every transaction before ML scoring. They catch
obvious suspicious patterns that don't need machine learning:
- Large transactions
- Rapid successive transactions (structuring)
- Round-number transactions just below reporting thresholds
- New accounts with high activity
- Unusual transaction times
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.config import settings
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


@dataclass
class RuleResult:
    """Result from a single rule evaluation."""

    rule_name: str
    category: str
    triggered: bool
    severity: float  # 0.0 to 1.0
    details: str


@dataclass
class RuleEngineResult:
    """Aggregated result from all rules."""

    results: list[RuleResult] = field(default_factory=list)

    @property
    def triggered_rules(self) -> list[RuleResult]:
        return [r for r in self.results if r.triggered]

    @property
    def max_severity(self) -> float:
        triggered = self.triggered_rules
        return max(r.severity for r in triggered) if triggered else 0.0

    @property
    def combined_score(self) -> float:
        """Weighted combination of all triggered rule severities."""
        triggered = self.triggered_rules
        if not triggered:
            return 0.0
        # Use a weighted average that increases with more triggered rules
        base_score = sum(r.severity for r in triggered) / len(triggered)
        rule_count_bonus = min(len(triggered) * 0.05, 0.2)
        return min(base_score + rule_count_bonus, 1.0)

    @property
    def rule_names(self) -> list[str]:
        return [r.rule_name for r in self.triggered_rules]


class RuleEngine:
    """Evaluates a transaction against all AML detection rules."""

    def evaluate(
        self,
        transaction: Transaction,
        account_history: list[Transaction],
    ) -> RuleEngineResult:
        """Run all rules against a transaction."""
        result = RuleEngineResult()

        result.results.append(self._check_large_amount(transaction))
        result.results.append(self._check_structuring(transaction))
        result.results.append(self._check_rapid_transactions(transaction, account_history))
        result.results.append(self._check_round_number(transaction))
        result.results.append(self._check_unusual_hours(transaction))
        result.results.append(self._check_velocity(transaction, account_history))
        result.results.append(self._check_new_ip(transaction, account_history))

        if result.triggered_rules:
            logger.info(
                "Transaction %s triggered %d rules: %s",
                transaction.fineract_transaction_id,
                len(result.triggered_rules),
                result.rule_names,
            )

        return result

    def _check_large_amount(self, tx: Transaction) -> RuleResult:
        """Flag transactions above the configured threshold."""
        triggered = tx.amount >= settings.max_transaction_amount
        severity = min(tx.amount / (settings.max_transaction_amount * 2), 1.0) if triggered else 0.0
        return RuleResult(
            rule_name="large_amount",
            category="amount",
            triggered=triggered,
            severity=severity,
            details=f"Amount {tx.currency} {tx.amount:,.2f} exceeds threshold "
            f"{tx.currency} {settings.max_transaction_amount:,.2f}",
        )

    def _check_structuring(self, tx: Transaction) -> RuleResult:
        """Detect structuring — amounts just below the reporting threshold.

        Criminals split large transactions into smaller ones to avoid
        regulatory reporting thresholds (e.g., $10K in the US).
        """
        threshold = settings.structuring_threshold
        upper = settings.max_transaction_amount
        triggered = threshold <= tx.amount < upper
        severity = 0.7 if triggered else 0.0
        return RuleResult(
            rule_name="structuring",
            category="pattern",
            triggered=triggered,
            severity=severity,
            details=f"Amount {tx.currency} {tx.amount:,.2f} is between "
            f"{tx.currency} {threshold:,.2f} and {tx.currency} {upper:,.2f} "
            f"(potential structuring)",
        )

    def _check_rapid_transactions(
        self, tx: Transaction, history: list[Transaction]
    ) -> RuleResult:
        """Flag accounts with too many transactions in a short window."""
        count = len(history)
        triggered = count >= settings.rapid_transaction_count
        severity = min(count / (settings.rapid_transaction_count * 2), 1.0) if triggered else 0.0
        return RuleResult(
            rule_name="rapid_transactions",
            category="velocity",
            triggered=triggered,
            severity=severity,
            details=f"Account has {count} transactions in the last "
            f"{settings.rapid_transaction_window_minutes} minutes "
            f"(threshold: {settings.rapid_transaction_count})",
        )

    def _check_round_number(self, tx: Transaction) -> RuleResult:
        """Flag round-number transactions (e.g., exactly $5000, $1000).

        Legitimate transactions tend to have odd amounts; round numbers
        can indicate manufactured transactions.
        """
        is_round = tx.amount >= 1000 and tx.amount % 1000 == 0
        return RuleResult(
            rule_name="round_number",
            category="pattern",
            triggered=is_round,
            severity=0.3 if is_round else 0.0,
            details=f"Round-number transaction: {tx.currency} {tx.amount:,.2f}",
        )

    def _check_unusual_hours(self, tx: Transaction) -> RuleResult:
        """Flag transactions outside normal business hours (2-5 AM local)."""
        tx_hour = tx.transaction_date.hour if isinstance(tx.transaction_date, datetime) else 12
        is_unusual = 2 <= tx_hour <= 5
        return RuleResult(
            rule_name="unusual_hours",
            category="timing",
            triggered=is_unusual,
            severity=0.4 if is_unusual else 0.0,
            details=f"Transaction at {tx_hour}:00 (unusual hours: 2-5 AM)",
        )

    def _check_velocity(
        self, tx: Transaction, history: list[Transaction]
    ) -> RuleResult:
        """Flag high cumulative volume in the time window."""
        total_volume = sum(t.amount for t in history) + tx.amount
        threshold = settings.max_transaction_amount * 3
        triggered = total_volume >= threshold
        severity = min(total_volume / (threshold * 2), 1.0) if triggered else 0.0
        return RuleResult(
            rule_name="high_velocity_volume",
            category="velocity",
            triggered=triggered,
            severity=severity,
            details=f"Cumulative volume {tx.currency} {total_volume:,.2f} in "
            f"{settings.rapid_transaction_window_minutes} minutes "
            f"(threshold: {tx.currency} {threshold:,.2f})",
        )

    def _check_new_ip(
        self, tx: Transaction, history: list[Transaction]
    ) -> RuleResult:
        """Flag transactions from an IP address not previously seen for this account."""
        current_ip = getattr(tx, "ip_address", None)
        if not current_ip:
            return RuleResult(
                rule_name="new_ip_address",
                category="geographic",
                triggered=False,
                severity=0.0,
                details="No IP address available",
            )
        known_ips = {
            getattr(t, "ip_address", None)
            for t in history
            if getattr(t, "ip_address", None)
        }
        is_new = current_ip not in known_ips and len(known_ips) > 0
        return RuleResult(
            rule_name="new_ip_address",
            category="geographic",
            triggered=is_new,
            severity=0.5 if is_new else 0.0,
            details=f"IP {current_ip} {'is new' if is_new else 'is known'} for account "
            f"(known IPs: {len(known_ips)})",
        )
