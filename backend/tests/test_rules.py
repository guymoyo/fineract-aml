"""Tests for the AML rule engine."""

import uuid
from datetime import datetime, timezone

import pytest

from app.models.transaction import Transaction, TransactionType
from app.rules.engine import RuleEngine


def _make_transaction(**kwargs) -> Transaction:
    """Create a test transaction with defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "fineract_transaction_id": f"TX-{uuid.uuid4().hex[:8]}",
        "fineract_account_id": "ACC-001",
        "fineract_client_id": "CLI-001",
        "transaction_type": TransactionType.DEPOSIT,
        "amount": 500.0,
        "currency": "USD",
        "transaction_date": datetime(2025, 6, 15, 14, 30, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    tx = Transaction.__new__(Transaction)
    for k, v in defaults.items():
        setattr(tx, k, v)
    return tx


class TestRuleEngine:
    def setup_method(self):
        self.engine = RuleEngine()

    def test_normal_transaction_no_triggers(self):
        tx = _make_transaction(amount=500.0)
        result = self.engine.evaluate(tx, [])
        assert len(result.triggered_rules) == 0
        assert result.combined_score == 0.0

    def test_large_amount_triggers(self):
        tx = _make_transaction(amount=15000.0)
        result = self.engine.evaluate(tx, [])
        triggered = [r.rule_name for r in result.triggered_rules]
        assert "large_amount" in triggered

    def test_structuring_triggers(self):
        tx = _make_transaction(amount=9700.0)
        result = self.engine.evaluate(tx, [])
        triggered = [r.rule_name for r in result.triggered_rules]
        assert "structuring" in triggered

    def test_round_number_triggers(self):
        tx = _make_transaction(amount=5000.0)
        result = self.engine.evaluate(tx, [])
        triggered = [r.rule_name for r in result.triggered_rules]
        assert "round_number" in triggered

    def test_unusual_hours_triggers(self):
        tx = _make_transaction(
            amount=500.0,
            transaction_date=datetime(2025, 6, 15, 3, 0, tzinfo=timezone.utc),
        )
        result = self.engine.evaluate(tx, [])
        triggered = [r.rule_name for r in result.triggered_rules]
        assert "unusual_hours" in triggered

    def test_rapid_transactions_triggers(self):
        tx = _make_transaction(amount=500.0)
        history = [_make_transaction(amount=100.0) for _ in range(12)]
        result = self.engine.evaluate(tx, history)
        triggered = [r.rule_name for r in result.triggered_rules]
        assert "rapid_transactions" in triggered

    def test_multiple_rules_increase_score(self):
        # Large + round + structuring-adjacent
        tx = _make_transaction(
            amount=10000.0,
            transaction_date=datetime(2025, 6, 15, 3, 0, tzinfo=timezone.utc),
        )
        result = self.engine.evaluate(tx, [])
        assert len(result.triggered_rules) >= 2
        assert result.combined_score > 0.3

    def test_combined_score_capped_at_1(self):
        tx = _make_transaction(amount=50000.0)
        history = [_make_transaction(amount=20000.0) for _ in range(20)]
        result = self.engine.evaluate(tx, history)
        assert result.combined_score <= 1.0
