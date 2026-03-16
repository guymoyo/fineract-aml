"""Tests for feature extraction."""

from datetime import datetime, timezone

import numpy as np
import pytest

from app.features.extractor import FEATURE_NAMES, FeatureExtractor
from app.models.transaction import TransactionType
from tests.conftest import FakeTransaction


class TestFeatureExtractor:
    def test_output_shape(self):
        tx = FakeTransaction()
        features = FeatureExtractor.extract(tx, [], [])
        assert isinstance(features, np.ndarray)
        assert features.shape == (len(FEATURE_NAMES),)

    def test_feature_names_match(self):
        names = FeatureExtractor.get_feature_names()
        assert names == FEATURE_NAMES
        assert len(names) == 20

    def test_deposit_one_hot(self):
        tx = FakeTransaction(transaction_type=TransactionType.DEPOSIT)
        features = FeatureExtractor.extract(tx, [], [])
        assert features[2] == 1.0  # is_deposit
        assert features[3] == 0.0  # is_withdrawal
        assert features[4] == 0.0  # is_transfer

    def test_withdrawal_one_hot(self):
        tx = FakeTransaction(transaction_type=TransactionType.WITHDRAWAL)
        features = FeatureExtractor.extract(tx, [], [])
        assert features[2] == 0.0
        assert features[3] == 1.0
        assert features[4] == 0.0

    def test_weekend_flag(self):
        # 2025-06-14 is Saturday
        tx = FakeTransaction(
            transaction_date=datetime(2025, 6, 14, 10, 0, tzinfo=timezone.utc)
        )
        features = FeatureExtractor.extract(tx, [], [])
        assert features[7] == 1.0  # is_weekend

    def test_night_flag(self):
        tx = FakeTransaction(
            transaction_date=datetime(2025, 6, 15, 3, 0, tzinfo=timezone.utc)
        )
        features = FeatureExtractor.extract(tx, [], [])
        assert features[8] == 1.0  # is_night

    def test_history_features(self):
        tx = FakeTransaction(amount=1000.0)
        history = [FakeTransaction(amount=200.0) for _ in range(5)]
        features = FeatureExtractor.extract(tx, history, history)
        assert features[11] == 5.0  # tx_count_1h
        assert features[12] == 5.0  # tx_count_24h
        assert features[13] == 1000.0  # total_amount_1h (5*200)

    def test_all_features_are_finite(self):
        tx = FakeTransaction()
        features = FeatureExtractor.extract(tx, [], [])
        assert np.all(np.isfinite(features))
