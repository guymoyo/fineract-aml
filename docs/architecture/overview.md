# Architecture Overview

## System Design

Fineract AML is a standalone microservice that integrates with Apache Fineract via webhooks. It receives transaction events, scores them for fraud risk, screens counterparties against sanctions lists, auto-generates regulatory reports, and provides a compliance dashboard for human review.

### Design Principles

1. **Event-driven** — Transactions flow in via webhooks, analysis is async via Celery
2. **Defense in depth** — Four detection layers: rules → anomaly detection → supervised ML → graph analysis
3. **Human-in-the-loop** — Analyst decisions feed back into model training
4. **Separation of concerns** — Decoupled from Fineract; communicates only via webhook API
5. **Explainability** — Every alert includes per-feature score explanations for SAR filings
6. **Regulatory-first** — Sanctions screening, CTR generation, KYC/EDD, and audit trails built in

## Components

### 1. Webhook Consumer (`app/api/webhook.py`)

Receives HTTP POST events from Fineract when a transaction occurs. Supports all Fineract transaction types:

- deposit, withdrawal, transfer
- loan_disbursement, loan_repayment
- share_purchase, share_redemption
- fixed_deposit, recurring_deposit
- charge, fee, other (catch-all)

Security features:
- **HMAC-SHA256 signature verification** (mandatory in production)
- **Rate limiting** — 100 requests/minute per source IP
- **Idempotency** — duplicate webhooks are detected and skipped
- **Startup validation** — blocks launch if secrets are still defaults

### 2. Analysis Pipeline (`app/tasks/analysis.py`)

Runs asynchronously via Celery for every transaction:

```
Transaction
    ├── Feature Extraction → 22 numerical features (with account history)
    ├── Rule Engine → 10 deterministic checks (severity scores)
    ├── Anomaly Detector → unsupervised scoring (Isolation Forest)
    ├── Fraud Classifier → supervised scoring (XGBoost, if trained + validated)
    ├── Score Combination → final risk score
    ├── Score Explanation → per-feature JSON for regulatory explainability
    ├── Sanctions Screening → counterparty name vs OFAC/EU/UN/PEP watchlists
    ├── CTR Generation → auto-file if amount ≥ 5M XAF (configurable)
    └── Alert Creation → if score ≥ 0.5
```

**Score combination strategy:**

- **With trained ML model**: `final = 0.5×ML + 0.3×anomaly + 0.2×rules`
- **Without ML model (early stage)**: `final = 0.5×anomaly + 0.5×rules`
- **No models at all**: `final = rules` (pure rule engine)

### 3. Rule Engine (`app/rules/engine.py`)

10 deterministic rules that catch known AML patterns:

| Rule | What it detects |
|------|----------------|
| `large_amount` | Transactions above configurable threshold |
| `structuring` | Amounts just below reporting limits (smurfing) |
| `rapid_transactions` | Too many transactions in a short window |
| `round_number` | Suspiciously round amounts |
| `unusual_hours` | Transactions between 2-5 AM |
| `high_velocity_volume` | High cumulative volume in time window |
| `new_ip_address` | IP not seen for this account in 24h |
| `circular_transfer` | A→B→A transfer pattern (layering) |
| `new_counterparty_transfer` | First transfer to unknown account |
| `rapid_pair_transfers` | ≥3 transfers with same counterparty in 24h |

Rules are configurable via environment variables.

### 4. ML Models (`app/ml/`)

**Anomaly Detector (Isolation Forest)** — `anomaly_detector.py`
- Unsupervised — works from day one, no labels needed
- Contamination rate: 1% (configurable via `AML_ANOMALY_CONTAMINATION`)
- Retrained daily on recent transactions
- Drift baseline saved after each retraining

**Fraud Classifier (XGBoost)** — `fraud_classifier.py`
- Supervised — activated once ≥200 fraud labels and ≥1000 total labels exist
- Validation gate: only deployed if CV AUC ≥ 0.80 and std ≤ 0.05
- Retrained weekly, metrics logged to MLflow
- Atomic file writes prevent corruption during retraining

**Graph Analyzer (NetworkX)** — `graph_analyzer.py`
- Builds directed transaction graph (accounts = nodes, transfers = edges)
- Detects: multi-hop cycles (A→B→C→A), fan-out/fan-in patterns, high-centrality nodes
- Computes 6 network features per account (PageRank, degree, cycle membership)

**Drift Detector (PSI)** — `drift_detector.py`
- Population Stability Index on feature and score distributions
- Warning at PSI ≥ 0.10, critical at PSI ≥ 0.25
- Checked during retraining, baselines saved after each training run

**Credit Scoring** — `credit_scorer.py`
- Rule-based weighted scoring (7 components, sum to 1.0)
- K-Means clustering for segment validation
- 5 tiers (A-E) with configurable credit limits

### 5. Sanctions & Watchlist Screening (`app/services/sanctions_service.py`)

Screens transaction counterparties against global sanctions/PEP lists:

| Source | URL | Refresh |
|--------|-----|---------|
| OFAC SDN | `sanctionslistservice.ofac.treas.gov/.../SDN.XML` | Every 6 hours |
| EU Sanctions | `webgate.ec.europa.eu/.../xmlFullSanctionsList` | Every 6 hours (planned) |
| UN Sanctions | `scsanctions.un.org/.../consolidated.xml` | Every 6 hours (planned) |
| PEP | Custom entries | Manual upload |

- **Matching**: Fuzzy name matching (SequenceMatcher, threshold 0.85)
- **Aliases**: Checks all known aliases for each watchlist entry
- **Results**: CLEAR, POTENTIAL_MATCH, CONFIRMED_MATCH, FALSE_POSITIVE
- **Auto-download**: Celery Beat task `sync_all_watchlists` runs every 6 hours

### 6. KYC/KYB Service (`app/services/kyc_service.py`)

Syncs customer data from Fineract's client API:

- Caches identity, contact, ID documents, beneficial ownership
- Auto-assesses risk level based on:
  - PEP (Politically Exposed Person) status
  - Sanctions matches
  - FATF high-risk country (nationality or residence)
  - Entity without beneficial ownership data
- Triggers Enhanced Due Diligence (EDD) when risk factors present

### 7. Compliance Features

**CTR (Currency Transaction Report)** — `app/models/ctr.py`
- Auto-generated when transaction amount ≥ `AML_CTR_THRESHOLD` (default 5M XAF)
- Status tracking: PENDING → FILED → ACKNOWLEDGED

**Audit Trail** — `app/models/audit_log.py`
- Logs all compliance-critical actions: alert reviews, user creation, data retention purges, watchlist syncs
- Immutable entries with user_id, timestamp, IP, action details

**Data Retention** — `app/tasks/retention.py`
- 7-year transaction retention, 5-year screening retention, 10-year audit log retention
- Monthly enforcement task flags old records, purges clear screenings
- All purge actions are audit-logged

### 8. Feature Engineering (`app/features/extractor.py`)

22 numerical features per transaction:

- **Transaction-level**: amount, log(amount), type (one-hot), time
- **Pattern**: round numbers, night transactions, weekend
- **Velocity**: count/volume in 1h and 24h windows
- **Behavioral**: amount vs average ratio, counterparty diversity
- **IP-based**: new IP detection, unique IP count in 24h

19 customer-level features for credit scoring.

### 9. Compliance Dashboard

React-based UI for compliance analysts:

- **Dashboard** — KPIs: transactions today, pending alerts, confirmed fraud, detection health
- **Alert Queue** — prioritized by risk score, filterable by status
- **Alert Detail** — full context, rule matches, score explanation, review form
- **Transactions** — browse all transactions with risk level filters
- **Cases** — group related alerts into investigations
- **Credit Profiles** — customer scores by tier A-E
- **Credit Requests** — loan applications with compliance review
- **Credit Analytics** — segment distribution, approval/rejection rates

### 10. Authentication & Authorization

- **JWT** — HS256 tokens with 30-minute expiry
- **RBAC** — 4 roles: analyst, senior_analyst, compliance_officer, admin
- **Registration** — only admin/compliance_officer can create users
- **Rate limiting** — login: 5/min, webhook: 100/min, API: per-user limits
- **CORS** — restricted to dashboard origin (configurable)

## Database Schema

```
transactions ──┐
               ├──▶ alerts ──▶ reviews (labeled data → ML training)
rule_matches ──┘               │
                               ▼
cases ◀── case_transactions    Training pipeline
              │
              └──▶ transactions

customers (KYC/KYB from Fineract)
watchlist_entries → screening_results (sanctions/PEP)
currency_transaction_reports (CTR)
customer_credit_profiles → credit_requests
audit_logs (immutable compliance trail)
```

## Scheduled Tasks (Celery Beat)

| Task | Schedule | Description |
|------|----------|-------------|
| `retrain_anomaly_detector` | Daily | Retrain Isolation Forest on last 10K transactions |
| `retrain_fraud_classifier` | Weekly | Retrain XGBoost on labeled data (if enough labels) |
| `compute_all_credit_scores` | Daily (nightly) | Batch credit scoring for all clients |
| `retrain_credit_cluster_model` | Weekly | Retrain K-Means clustering |
| `poll_fineract_transactions` | Every 60s | Fallback polling if webhooks fail |
| `sync_all_watchlists` | Every 6 hours | Download OFAC SDN / EU / UN sanctions lists |
| `enforce_data_retention` | Monthly | Check retention policies, purge expired data |

## Deployment Architecture

```
Kubernetes Cluster
├── namespace: fineract         # Existing Fineract deployment
│   └── fineract-server ─── webhook POST ──┐
│                                           │
├── namespace: aml                          │
│   ├── aml-api (FastAPI, 2 replicas) ◀───┘
│   ├── aml-celery-worker (analysis + training, 2 replicas)
│   ├── aml-celery-beat (scheduled tasks)
│   ├── aml-dashboard (React)
│   ├── aml-postgres (with daily backup CronJob)
│   ├── aml-redis (task queue broker)
│   └── aml-mlflow (model tracking)
```

- Same cluster as Fineract for low-latency webhook delivery
- Separate namespace for isolation (RBAC, network policies)
- Separate database — no shared tables with Fineract
- Shared PVC for ML models (atomic writes prevent corruption)
- Daily pg_dump backup CronJob with 30-day retention
