# Credit Scoring Architecture

## How It All Works (Plain Language)

### AML (Anti-Money Laundering)

**Transaction Monitoring:** Fineract sends every transaction (deposit, withdrawal, transfer, loan) to our system via a webhook. Each transaction gets analyzed automatically in the background by a Celery worker.

**Rule Engine** checks for suspicious patterns:
- Large amounts → flagged
- Structuring → amounts just under 10,000 (trying to avoid detection)
- Rapid transactions → many transactions in a short window
- Night transactions → activity at unusual hours (2–5 AM)
- Circular transfers → A sends to B, B sends back to A (money laundering pattern)
- Rapid pair transfers → same two accounts exchanging money repeatedly
- New counterparty → first-time transfer to an unknown account

**Risk Score:** Each transaction gets a score from 0% to 100%. If high enough → an Alert is created for compliance analysts to review.

**Alerts & Cases:** Analysts see alerts in the dashboard, review them, and mark as fraud or legitimate. Their decisions become training data for the ML models.

### Credit Scoring

**Feature Extraction:** Every night, the system looks at each customer's last 180 days of transactions and computes 19 features: how regularly they deposit, how much they save, do they repay loans, any fraud history, etc.

**Scoring:** A weighted formula turns those 19 features into a single score (0 to 1). Biggest factors: deposit consistency (20%), net cash flow (20%), loan repayment (15%), savings rate (15%).

**Tier Segmentation:** Score → Tier → Max borrowable amount (in XAF):
- ≥ 80% → Tier A (Excellent) → 50,000 XAF
- ≥ 65% → Tier B (Good) → 20,000 XAF
- ≥ 50% → Tier C (Fair) → 10,000 XAF
- ≥ 35% → Tier D (Poor) → 1,000 XAF
- < 35% → Tier E (Very Poor) → 0 XAF (no credit)

**ML Validation:** Weekly, a K-Means clustering model groups customers into 5 clusters. This validates the rule-based tiers — if both agree, confidence is higher.

**Credit Request Flow:**
1. Customer applies for a loan
2. System re-computes their score in real-time
3. Auto-recommendation generated: approve / review carefully / reject
4. Compliance analyst reviews in the dashboard
5. Analyst approves or rejects (never auto-approved)

### Dashboard Pages

- **Dashboard** → overview stats (transactions, alerts, system health)
- **Alerts** → review flagged transactions, mark as fraud/legitimate
- **Transactions** → browse all transactions with risk levels
- **Cases** → group related alerts into investigations
- **Credit Profiles** → see every customer's score, tier, max credit
- **Credit Requests** → review queue with approve/reject buttons
- **Credit Analytics** → tier distribution chart, summary stats

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Data Flow                                     │
│                                                                      │
│  Transactions ──▶ Feature Extraction ──▶ Credit Scoring ──▶ Profile  │
│  (180 days)       (19 features)          (rule + ML)       (DB)      │
│                                                                      │
│  Credit Request ──▶ Profile Refresh ──▶ Recommendation ──▶ Review    │
│  (on demand)        (real-time)          (auto-generated)   (human)  │
│                                                                      │
│  Celery Beat ──▶ Nightly Batch Scoring ──▶ All Profiles Updated     │
│                  Weekly ML Retraining ──▶ K-Means Cluster Model      │
└─────────────────────────────────────────────────────────────────────┘
```

## Credit Feature Definitions

Features are extracted per-customer from their transaction history (default: 180 days).

| # | Feature | Description | Range |
|---|---------|-------------|-------|
| 1 | `avg_monthly_deposits` | Average total deposits per month | ≥0 |
| 2 | `deposit_consistency` | 1 − normalized std-dev of monthly deposits | [0, 1] |
| 3 | `avg_monthly_withdrawals` | Average total withdrawals per month | ≥0 |
| 4 | `net_monthly_flow` | Deposits − withdrawals (monthly avg) | any |
| 5 | `savings_rate` | Net flow / deposits (clamped to [0,1]) | [0, 1] |
| 6 | `transaction_frequency` | Average transactions per month | ≥0 |
| 7 | `account_age_days` | Days since account was created | ≥0 |
| 8 | `max_single_deposit` | Largest single deposit | ≥0 |
| 9 | `max_single_withdrawal` | Largest single withdrawal | ≥0 |
| 10 | `loan_repayment_rate` | Repayments ÷ disbursements (1.0 if none) | [0, ∞) |
| 11 | `days_since_last_fraud_alert` | Days since most recent confirmed fraud alert | ≥0 |
| 12 | `total_fraud_alerts` | Count of confirmed fraud alerts | ≥0 |
| 13 | `unique_counterparties` | Distinct transfer counterparties | ≥0 |
| 14 | `geographic_stability` | Fraction of transactions from most common country | [0, 1] |
| 15 | `deposit_trend` | 30-day avg deposits ÷ 90-day avg deposits | ≥0 |
| 16 | `withdrawal_trend` | 30-day avg withdrawals ÷ 90-day avg withdrawals | ≥0 |
| 17 | `incoming_transfer_ratio` | Incoming transfers ÷ total deposits | [0, 1] |
| 18 | `unique_transfer_senders_30d` | Distinct senders of transfers in last 30 days | ≥0 |
| 19 | `outgoing_transfer_ratio` | Outgoing transfers ÷ total withdrawals | [0, 1] |

**Source:** `backend/app/features/credit_extractor.py`

## Scoring Methodology

### Rule-Based Scoring (Primary)

The rule-based scorer computes a weighted sum of normalized feature values:

```
credit_score = Σ (weight_i × normalized_feature_i)
```

**Weights** (configurable via environment variables):

| Weight | Feature | Default |
|--------|---------|---------|
| `credit_weight_deposit_consistency` | Deposit consistency | 0.20 |
| `credit_weight_net_flow` | Net monthly flow (sigmoid-normalized) | 0.20 |
| `credit_weight_savings_rate` | Savings rate | 0.15 |
| `credit_weight_tx_frequency` | Transaction frequency (capped at 50/mo) | 0.10 |
| `credit_weight_account_age` | Account age (capped at 730 days) | 0.10 |
| `credit_weight_repayment_rate` | Loan repayment rate (capped at 1.0) | 0.15 |
| `credit_weight_fraud_history` | Fraud penalty (1 − normalized alerts) | 0.10 |

Final score is clamped to [0.0, 1.0].

### Tier Classification

| Tier | Label | Min Score | Max Credit (XAF) |
|------|-------|-----------|-------------------|
| A | Excellent | ≥ 0.80 | 50,000 |
| B | Good | ≥ 0.65 | 20,000 |
| C | Fair | ≥ 0.50 | 10,000 |
| D | Poor | ≥ 0.35 | 1,000 |
| E | Very Poor | < 0.35 | 0 (no credit) |

### ML Clustering (Validation)

A K-Means clustering model (k=5) is trained weekly on all customer feature vectors:

1. Features are standardized (StandardScaler)
2. K-Means clusters customers into 5 groups
3. Clusters are sorted by average rule-based score of their members
4. Each cluster maps to a tier (best cluster → Tier A, worst → Tier E)

The ML segment is stored as `ml_segment_suggestion` on the credit profile for comparison. When both rule-based and ML scores agree, `scoring_method = "hybrid"`.

**Model persistence:** `models/credit_cluster.joblib` (StandardScaler + KMeans + cluster-to-tier mapping)

### Credit Request Recommendations

When a credit request is submitted, the system generates an automatic recommendation:

| Condition | Recommendation |
|-----------|---------------|
| Score ≥ tier_b threshold AND amount ≤ max credit | `approve` |
| Amount > max credit OR score < tier_d threshold | `reject` |
| Everything else | `review_carefully` |

**Important:** The system never auto-approves. All requests go through compliance review.

## Database Schema

### customer_credit_profiles

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| fineract_client_id | VARCHAR(100) | Unique, indexed |
| credit_score | FLOAT | 0.0 – 1.0 |
| segment | ENUM(creditsegment) | tier_a through tier_e |
| max_credit_amount | FLOAT | XAF amount |
| score_components | TEXT | JSON breakdown of scoring components |
| ml_cluster_id | INT | K-Means cluster assignment (nullable) |
| ml_segment_suggestion | ENUM(ml_credit_segment) | ML-suggested tier (nullable) |
| scoring_method | ENUM(scoringmethod) | rule_based, ml_cluster, hybrid |
| last_computed_at | TIMESTAMP | Last time score was computed |
| is_active | BOOLEAN | Whether profile is active |
| created_at | TIMESTAMP | Auto-set on creation |
| updated_at | TIMESTAMP | Auto-set on update |

### credit_requests

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| fineract_client_id | VARCHAR(100) | Indexed |
| requested_amount | FLOAT | Amount requested |
| credit_score_at_request | FLOAT | Snapshot of score at time of request |
| segment_at_request | ENUM(request_credit_segment) | Snapshot of segment |
| max_credit_at_request | FLOAT | Snapshot of max credit |
| recommendation | ENUM(creditrecommendation) | approve, review_carefully, reject |
| status | ENUM(creditrequeststatus) | pending_review → approved/rejected/expired |
| reviewer_notes | TEXT | Analyst notes |
| assigned_to | UUID FK→users | Assigned compliance analyst |
| reviewed_at | TIMESTAMP | When review was completed |
| reviewed_by | UUID FK→users | Who reviewed it |
| created_at | TIMESTAMP | Auto-set |
| updated_at | TIMESTAMP | Auto-set |

## Celery Task Schedule

| Task | Schedule | Description |
|------|----------|-------------|
| `compute_all_credit_scores` | Every 24 hours (nightly) | Iterates all distinct clients, extracts features, scores, upserts profiles |
| `retrain_credit_cluster_model` | Every 7 days (weekly) | Trains K-Means on all customer feature vectors |
| `evaluate_credit_request` | On demand | Re-scores a specific client for a credit request (with retry) |

All tasks use a fresh `create_async_engine` per invocation for Celery fork-safety (no shared connection pools across forked workers).

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API | Python 3.12, FastAPI | REST API with async support, auto-generated Swagger docs |
| ORM | SQLAlchemy 2.0 (async) | Database models with async PostgreSQL driver (asyncpg) |
| Database | PostgreSQL 16 | Permanent transaction storage, credit profiles, alerts, cases |
| Task Queue | Celery + Redis | Background analysis, nightly scoring, weekly ML retraining |
| ML | scikit-learn, XGBoost, MLflow | 4 ML models with experiment tracking |
| Dashboard | React, TanStack Router, TanStack Query | Compliance analyst UI with file-based routing |
| Auth | JWT (PyJWT) | Token-based authentication |
| Validation | Pydantic v2 | Request/response schemas and config management |
| Containers | Docker, Docker Compose, Kubernetes | Development and production deployment |

## ML Models

The system uses 4 complementary models — 3 for AML fraud detection and 1 for credit scoring:

| Model | Type | Library | Purpose | Training |
|-------|------|---------|---------|----------|
| **Rule Engine** | Deterministic | Custom Python | Checks 7 suspicious patterns (large amounts, structuring, rapid transactions, unusual hours, circular transfers, new counterparties, rapid pairs) | No training — rules configured via env vars |
| **Isolation Forest** | Unsupervised | scikit-learn | Anomaly detection — flags statistically unusual transactions without labeled data | Retrains automatically as data grows |
| **XGBoost Classifier** | Supervised | XGBoost | Fraud classification — learns from analyst decisions to predict fraud probability | Retrains when analysts label enough new data |
| **K-Means Clustering** | Unsupervised | scikit-learn | Credit tier validation — groups customers into 5 clusters to validate rule-based tiers | Weekly via Celery Beat |

### How They Work Together

**For AML detection:** Every transaction passes through three layers:
1. **Rule Engine** — deterministic checks (structuring, velocity, etc.)
2. **Isolation Forest** — statistical anomaly detection (no labels needed)
3. **XGBoost** — learned fraud patterns (trained on analyst decisions)

Each produces a risk score. The highest score determines the overall risk level. High-risk transactions generate alerts for compliance analysts to review.

**For Credit Scoring:** Two approaches run in parallel:
1. **Rule-based scorer** — weighted formula using 19 behavioral features (primary)
2. **K-Means clustering** — independently groups customers into 5 clusters (validation)

When both the rule-based tier and the ML cluster agree, the scoring method is marked as "hybrid" — giving higher confidence in the assessment.

## Transaction Storage

All transactions received from Fineract are stored **permanently** in PostgreSQL. They are never deleted or archived.

The credit scoring system uses a **180-day sliding window** — it looks at each customer's last 6 months of transactions to compute features and scores. This means:
- Scores automatically reflect recent behavior changes
- Historical data is preserved for auditing and compliance
- The window is configurable via the feature extraction parameters

**Source files:**
- Rule Engine: `backend/app/rules/engine.py`
- Isolation Forest: `backend/app/ml/anomaly_detector.py`
- XGBoost Classifier: `backend/app/ml/fraud_classifier.py`
- K-Means Clustering: `backend/app/ml/credit_scorer.py`
- Feature Engineering: `backend/app/features/extractor.py` (AML), `backend/app/features/credit_extractor.py` (Credit)
