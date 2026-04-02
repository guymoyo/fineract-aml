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

**Target**: Accumulate ≥200 confirmed fraud + ≥1000 total labeled transactions.

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

### Features Used (36 total)

The full feature vector used by both the anomaly detector and the fraud classifier:

| # | Feature Name | Category | Description |
|---|-------------|----------|-------------|
| 0 | `amount` | Transaction | Raw transaction amount |
| 1 | `amount_log` | Transaction | log1p(amount) — compresses skewed distribution |
| 2 | `is_deposit` | Transaction | 1 if transaction type is DEPOSIT |
| 3 | `is_withdrawal` | Transaction | 1 if transaction type is WITHDRAWAL |
| 4 | `is_transfer` | Transaction | 1 if transaction type is TRANSFER |
| 5 | `hour_of_day` | Transaction | Hour of day (0–23) |
| 6 | `day_of_week` | Transaction | Day of week (0=Monday, 6=Sunday) |
| 7 | `is_weekend` | Transaction | 1 if Saturday or Sunday |
| 8 | `is_night` | Transaction | 1 if hour is 22:00–06:00 |
| 9 | `is_round_hundred` | Transaction | 1 if amount is a multiple of 100 |
| 10 | `is_round_thousand` | Transaction | 1 if amount is a multiple of 1000 |
| 11 | `tx_count_1h` | 24h window | Number of transactions from this account in last 1 hour |
| 12 | `tx_count_24h` | 24h window | Number of transactions from this account in last 24 hours |
| 13 | `total_amount_1h` | 24h window | Total transaction volume in last 1 hour |
| 14 | `total_amount_24h` | 24h window | Total transaction volume in last 24 hours |
| 15 | `avg_amount_24h` | 24h window | Average transaction amount in last 24 hours |
| 16 | `max_amount_24h` | 24h window | Maximum transaction amount in last 24 hours |
| 17 | `amount_vs_avg_ratio` | 24h window | Current amount / 24h average (deviation signal) |
| 18 | `unique_counterparties_24h` | 24h window | Distinct counterparty accounts in last 24 hours |
| 19 | `same_type_ratio_24h` | 24h window | Fraction of 24h transactions with same type |
| 20 | `is_new_ip_for_account` | 24h window | 1 if IP not seen for this account in last 24 hours |
| 21 | `unique_ips_24h` | 24h window | Count of distinct IP addresses in last 24 hours |
| 22 | `tx_count_7d` | 7d window | Transaction count over last 7 days |
| 23 | `total_amount_7d` | 7d window | Total volume over last 7 days |
| 24 | `avg_amount_7d` | 7d window | Average transaction amount over 7 days |
| 25 | `max_amount_7d` | 7d window | Maximum transaction amount over 7 days |
| 26 | `unique_counterparties_7d` | 7d window | Distinct counterparty accounts in last 7 days |
| 27 | `amount_vs_7d_avg_ratio` | 7d window | Current amount / 7d average (behavioral deviation) |
| 28 | `tx_velocity_trend` | 7d window | 24h tx count / (7d tx count / 7) — acceleration signal |
| 29 | `receiver_diversity_7d` | 7d window | Unique recipients / total 7d transactions |
| 30 | `geo_distance_from_usual` | 7d window | 1.0 if current country differs from 7d modal country |
| 31 | `has_loan_disbursement_7d` | 7d window | 1 if any loan disbursement occurred in last 7 days |
| 32 | `is_agent` | Actor context | 1 if actor_type == "agent" |
| 33 | `is_merchant` | Actor context | 1 if actor_type == "merchant" |
| 34 | `kyc_level_norm` | Actor context | kyc_level / 4.0 (unknown → 0.5 default) |
| 35 | `is_new_kyc` | Actor context | 1 if kyc_level == 1 (brand-new / unverified) |

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

## Implemented Enhancements

### Graph-Based Network Analysis (`app/ml/graph_analyzer.py`)

Builds a directed transaction graph (accounts = nodes, transfers = edges) using NetworkX:

- **Cycle detection**: Finds multi-hop money laundering chains (A→B→C→D→A) up to 5 hops
- **Fan-out/fan-in**: Identifies accounts sending to or receiving from many counterparties
- **PageRank**: Identifies important nodes in the money flow network (potential mules)
- **Network features**: 6 per-account features (out_degree, in_degree, total_sent, total_received, pagerank, is_in_cycle)

### Model Drift Detection (`app/ml/drift_detector.py`)

Uses Population Stability Index (PSI) to detect when ML models degrade:

- **Baselines**: Saved after each retraining with feature and score distributions
- **Checking**: Compares current distributions against baseline during retraining
- **Thresholds**: PSI < 0.10 (OK), 0.10-0.25 (warning), ≥ 0.25 (critical — retrain immediately)
- **Integration**: Automatically runs during the retraining pipeline

### Model Validation Gate (`app/ml/fraud_classifier.py`)

New models are only deployed if they meet quality thresholds:

- CV AUC ≥ 0.80 (mean across 5 folds)
- CV AUC std ≤ 0.05 (stable across folds)
- If validation fails, the previous model is kept

### MLflow Integration (`app/tasks/training.py`)

Training metrics (AUC, precision, recall, F1, sample counts) are logged to MLflow after each retraining run. Access at `http://localhost:5000`.

### Atomic Model Writes

Model files are written to a temporary file first, then renamed atomically. This prevents read corruption when API pods load a model file while a Celery worker is retraining.

## Feature Set (36 Features — Phase 7.1)

The feature vector was expanded from 22 to 36 features. See the full feature table in the [Features Used](#features-used-36-total) section under Phase 3.

**Important**: The feature dimension change (22 → 36) invalidates any previously serialized model files. The system falls back to rules-only mode (`is_ready=False`) until models are retrained on the new feature set.

---

## Extended 7-day Window Features (indices 22–31)

These features capture medium-term behavioral patterns that the original 24h window misses. They are extracted from `account_history_7d` passed to `FeatureExtractor.extract()`. If the 7d history is not supplied, the extractor falls back to the 24h list (divided by 7 for rate normalization).

| Index | Feature | Purpose |
|-------|---------|---------|
| 22 | `tx_count_7d` | Baseline transaction count over 7 days — contextualizes 1h/24h velocity |
| 23 | `total_amount_7d` | Total volume baseline over 7 days |
| 24 | `avg_amount_7d` | Average amount baseline used to compute `amount_vs_7d_avg_ratio` |
| 25 | `max_amount_7d` | Maximum single transaction over 7 days — flags outlier amounts |
| 26 | `unique_counterparties_7d` | Counterparty breadth — high diversity may indicate layering |
| 27 | `amount_vs_7d_avg_ratio` | Current amount / 7d average — key behavioral deviation signal |
| 28 | `tx_velocity_trend` | 24h count / (7d count / 7) — acceleration of transaction rate |
| 29 | `receiver_diversity_7d` | Unique recipients / total 7d transactions — mule distribution signal |
| 30 | `geo_distance_from_usual` | 1.0 if current country differs from 7d modal country — geographic outlier |
| 31 | `has_loan_disbursement_7d` | 1 if any loan disbursement occurred in last 7 days — triggers loan monitoring context |

---

## Actor Context Features (indices 32–35)

These four features encode the actor model into the ML feature vector, allowing the models to learn actor-specific behavioral norms without maintaining separate model files per actor type.

| Index | Feature | Description |
|-------|---------|-------------|
| 32 | `is_agent` | 1 if `actor_type == "agent"` — agent operators have very different velocity norms |
| 33 | `is_merchant` | 1 if `actor_type == "merchant"` — merchant collection patterns differ from P2P transfers |
| 34 | `kyc_level_norm` | `kyc_level / 4.0` — normalized KYC level. Unknown/missing → 0.5 (neutral) |
| 35 | `is_new_kyc` | 1 if `kyc_level == 1` (brand-new / unverified account) — high-risk onboarding signal |

---

## One-Class SVM Ensemble

When `AML_ANOMALY_ENSEMBLE_ENABLED=true`, the anomaly detector combines two models:

```
final_anomaly_score = 0.6 × IsolationForest_score + 0.4 × OneClassSVM_score
```

The One-Class SVM uses an RBF kernel and is trained alongside the Isolation Forest on the same data. It catches anomaly patterns in dense regions of feature space where Isolation Forest (a tree-based method) is less sensitive.

Both models are saved atomically and loaded together. If the SVM model file is missing (e.g., first run after enabling), the system falls back to Isolation Forest only and logs a warning.

**Configuration:**
```env
AML_ANOMALY_ENSEMBLE_ENABLED=true  # default: false
```

---

## Shadow/Canary Deployment

After each successful training run, the trained model is also written to a **shadow slot** (a separate file path alongside the production model). The shadow model runs on every transaction in parallel but its scores are only logged — they never influence risk decisions or trigger alerts.

```
Training run completes
    → Production model file updated (atomic rename)
    → Shadow model file also written (same weights, separate path)

Per transaction:
    → Production model → contributes to final_score
    → Shadow model     → score appended to model_health table (shadow_score column)
```

The `promote_shadow_model` Celery task promotes the shadow to production when:
1. Shadow has been running for at least `AML_SHADOW_MODEL_PROMOTION_DAYS` days (default: 7)
2. Shadow AUC exceeds production AUC by at least `AML_SHADOW_MODEL_PROMOTION_AUC_DELTA` (default: 0.02)

**Configuration:**
```env
AML_SHADOW_MODEL_ENABLED=true                  # default: false
AML_SHADOW_MODEL_PROMOTION_DAYS=7              # days before promotion is evaluated
AML_SHADOW_MODEL_PROMOTION_AUC_DELTA=0.02      # minimum AUC improvement required
```

---

## Synthetic Data Generator

Located at `backend/app/scripts/generate_aml_typologies.py`. Generates labeled synthetic transactions covering five IBM AMLSim typologies plus WeBank-specific patterns.

```bash
python -m app.scripts.generate_aml_typologies \
  --n-typologies 100 \
  --fraud-rate 0.05 \
  --output aml_synthetic.csv
```

**Typology generators (one class per typology):**

| Generator Class | Typology | Description |
|----------------|----------|-------------|
| `ScatterGatherGenerator` | Scatter-gather | N→1 collection into a single account + single large disbursement |
| `BipartiteLayeringGenerator` | Bipartite layering | Fan-out then fan-in through an intermediary account layer |
| `StackingGenerator` | Stacking | Rapid proportional sequential hops (each amount 80–120% of prior) |
| `AgentStructuringGenerator` | Agent structuring | Sub-threshold deposits repeated via the same agent to avoid CTR |
| `LoanAndRunGenerator` | Loan-and-run | Rapid extraction of loan proceeds shortly after disbursement |

Use synthetic data to bootstrap model training before sufficient real labeled data is available. Always mix with real data once available — purely synthetic training leads to distribution mismatch.

---

## Model Drift Monitoring

PSI (Population Stability Index) is computed against the feature distribution baseline saved at the last retraining run.

| PSI Range | Status | Recommended Action |
|-----------|--------|-------------------|
| PSI < 0.1 | Stable | No action required |
| 0.1 ≤ PSI < 0.25 | Warning | Monitor closely; consider retraining within 7 days |
| PSI ≥ 0.25 | Drift | Immediate retraining required |

Drift metrics are visible via the Model Health API:
- `GET /api/v1/model-health/drift` — current drift summary with recommendations
- `GET /api/v1/model-health/history/{model_name}` — historical PSI and AUC over time

Drift alerts also appear in Prometheus at `/metrics` (gauge: `aml_model_psi{model="fraud_classifier"}`).

---

## Future Enhancements

- **Real-time feature store** (Feast/Redis) for sub-millisecond feature lookups
- **Ensemble models** — combine XGBoost + LightGBM + CatBoost
- **Active learning** — prioritize labeling the most informative samples
- **Sequence models** (LSTM/Transformer) for temporal pattern detection
