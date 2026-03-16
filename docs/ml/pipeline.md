# ML Pipeline Guide

## Overview

The AML ML pipeline evolves through three phases, progressively adding intelligence as data accumulates.

## Phase 1: Rule Engine + Anomaly Detection (Day 1)

**No labeled data required.**

### Rule Engine

Deterministic rules catch known AML patterns immediately:

```
Transaction → Rule Engine → triggered_rules[], combined_score
```

| Rule | Severity | What it catches |
|------|----------|----------------|
| Large amount | 0.5-1.0 | Transactions above $10,000 (configurable) |
| Structuring | 0.7 | Amounts between $9,500-$10,000 (below reporting threshold) |
| Rapid transactions | 0.5-1.0 | >10 transactions per hour from same account |
| Round numbers | 0.3 | Exact multiples of $1,000 |
| Unusual hours | 0.4 | Transactions between 2-5 AM |
| High velocity | 0.5-1.0 | Cumulative volume >$30,000 in 1 hour |

Rules are configurable via environment variables (see `.env.example`).

### Anomaly Detection (Isolation Forest)

Unsupervised model that learns what "normal" looks like:

```python
# How it works:
# 1. Fit on historical transactions (assumed mostly normal)
# 2. For each new transaction, measure how "isolated" it is
# 3. Anomalous transactions are easy to isolate → high score
```

**Why Isolation Forest?**
- Works without any labels
- Efficient on high-dimensional data
- Naturally handles the rarity of fraud (anomalies are isolated quickly)
- Fast inference (milliseconds per transaction)

**Training schedule**: Daily via Celery beat on last 10,000 transactions.

**Score interpretation**: 0.0 = perfectly normal, 1.0 = highly anomalous.

### Score Combination (Phase 1)

```
final_score = 0.5 × anomaly_score + 0.5 × rule_combined_score
```

If `final_score ≥ 0.5` → Alert created → Goes to analyst queue.

## Phase 2: Human-in-the-Loop Labeling

This phase runs alongside Phase 1. Analysts review alerts in the dashboard:

```
Alert (pending) → Analyst opens alert
                → Reviews transaction details, rule matches, risk breakdown
                → Marks decision:
                   • "Confirmed Fraud" → is_fraud = 1
                   • "Legitimate" (false positive) → is_fraud = 0
                   • "Suspicious" → escalated, not used for training
```

### Building the Training Dataset

Every review creates a labeled data point:

```sql
-- Labeled data query (used by training pipeline)
SELECT t.*, r.decision
FROM transactions t
JOIN alerts a ON a.transaction_id = t.id
JOIN reviews r ON r.alert_id = a.id
WHERE r.decision IN ('confirmed_fraud', 'legitimate')
```

**Target**: Accumulate ≥50 confirmed fraud + ≥200 total labeled transactions.

### Tips for Analysts

1. **Be consistent** — Similar transactions should get similar labels
2. **Label false positives too** — The model needs negative examples
3. **Document reasoning** — Use the notes field for context
4. **File SARs when required** — Use the SAR reference field for tracking

## Phase 3: Supervised Classification (XGBoost)

Activated automatically once minimum label thresholds are met.

### Why XGBoost?

| Property | Benefit for AML |
|----------|----------------|
| Handles imbalanced data | Fraud is rare (~0.1-1% of transactions). `scale_pos_weight` compensates |
| Feature importance | Tells you *why* a transaction was flagged — required for regulatory compliance |
| Works with small datasets | Effective with 200+ samples, unlike deep learning |
| Fast inference | Sub-millisecond scoring per transaction |
| Robust to outliers | Built-in regularization prevents overfitting |

### Features Used (20 total)

```
Transaction-level:        amount, log(amount), type (one-hot), hour, day_of_week
Pattern flags:           is_weekend, is_night, is_round_hundred, is_round_thousand
Velocity (1h window):    tx_count_1h, total_amount_1h
Velocity (24h window):   tx_count_24h, total_amount_24h, avg_amount_24h, max_amount_24h
Behavioral:              amount_vs_avg_ratio, unique_counterparties_24h, same_type_ratio_24h
```

### Training Configuration

```python
XGBClassifier(
    n_estimators=300,        # 300 trees (boosting rounds)
    max_depth=6,             # Each tree is at most 6 levels deep
    learning_rate=0.05,      # Conservative learning rate
    scale_pos_weight=~100,   # Auto-calculated: n_legit / n_fraud
    min_child_weight=5,      # Prevents overfitting on rare events
    subsample=0.8,           # Use 80% of data per tree (regularization)
    colsample_bytree=0.8,    # Use 80% of features per tree
)
```

### Score Combination (Phase 3)

```
final_score = 0.5 × ml_score + 0.3 × anomaly_score + 0.2 × rule_score
```

The ML model gets the highest weight because it has learned from real labeled data.

### Retraining Schedule

- **Weekly** via Celery beat
- Uses all labeled data accumulated to date
- 5-fold stratified cross-validation for metrics
- Metrics logged to MLflow (AUC, precision, recall, F1)
- Old model replaced only if new model has better CV AUC

### Monitoring Model Performance

Access MLflow at `http://localhost:5000`:

- **Experiments** → `fineract-aml` → compare model versions
- **Metrics** → track AUC, precision, recall over time
- **Feature importance** → which features drive predictions

Key metrics to watch:
- **AUC ≥ 0.85**: Model is discriminating well
- **Precision ≥ 0.3**: At least 30% of alerts are true positives
- **Recall ≥ 0.8**: Catching at least 80% of actual fraud

## Adding New Features

To add a new feature:

1. Add the feature name to `FEATURE_NAMES` in `app/features/extractor.py`
2. Add the extraction logic in `FeatureExtractor.extract()`
3. The feature is automatically picked up by both anomaly detector and classifier
4. Retrain both models after adding features

## Adding New Rules

To add a new rule:

1. Add a method `_check_my_rule()` in `app/rules/engine.py`
2. Return a `RuleResult` with name, category, severity, and details
3. Call it from `evaluate()`
4. No retraining needed — rules take effect immediately

## Future Enhancements

- **Graph-based analysis** (NetworkX/Neo4j) for detecting circular money flows
- **Real-time feature store** (Feast/Redis) for sub-millisecond feature lookups
- **Ensemble models** — combine XGBoost + LightGBM + CatBoost
- **Concept drift detection** — alert when transaction patterns shift
- **Active learning** — prioritize labeling the most informative samples
