# Architecture Overview

## System Design

Fineract AML is a standalone microservice that integrates with Apache Fineract via webhooks. It receives transaction events, scores them for fraud risk, and provides a compliance dashboard for human review.

### Design Principles

1. **Event-driven** — Transactions flow in via webhooks, analysis is async via Celery
2. **Defense in depth** — Three detection layers: rules → anomaly detection → supervised ML
3. **Human-in-the-loop** — Analyst decisions feed back into model training
4. **Separation of concerns** — Decoupled from Fineract; communicates only via webhook API
5. **Explainability** — Every alert includes which rules triggered and why

## Components

### 1. Webhook Consumer (`app/api/webhook.py`)

Receives HTTP POST events from Fineract when a transaction occurs (deposit, withdrawal, transfer). The webhook payload includes:

- Transaction ID, account ID, client ID
- Amount, currency, date
- Transaction type
- Counterparty information (for transfers)

After ingestion, the transaction is queued for async analysis.

### 2. Analysis Pipeline (`app/tasks/analysis.py`)

Runs asynchronously via Celery for every transaction:

```
Transaction
    ├── Feature Extraction → numerical feature vector
    ├── Rule Engine → deterministic checks (severity scores)
    ├── Anomaly Detector → unsupervised scoring (Isolation Forest)
    ├── Fraud Classifier → supervised scoring (XGBoost, if trained)
    └── Score Combination → final risk score + alert creation
```

**Score combination strategy:**

- **With trained ML model**: `final = 0.5×ML + 0.3×anomaly + 0.2×rules`
- **Without ML model (early stage)**: `final = 0.5×anomaly + 0.5×rules`

### 3. Rule Engine (`app/rules/engine.py`)

Deterministic rules that catch known AML patterns:

| Rule | What it detects |
|------|----------------|
| `large_amount` | Transactions above configurable threshold |
| `structuring` | Amounts just below reporting limits (smurfing) |
| `rapid_transactions` | Too many transactions in a short window |
| `round_number` | Suspiciously round amounts ($5000, $10000) |
| `unusual_hours` | Transactions between 2-5 AM |
| `high_velocity_volume` | High cumulative volume in time window |

Rules are configurable via environment variables.

### 4. ML Models (`app/ml/`)

**Anomaly Detector (Isolation Forest)**
- Unsupervised — works from day one, no labels needed
- Learns what "normal" transactions look like
- Flags deviations as anomalies
- Retrained daily on recent transactions

**Fraud Classifier (XGBoost)**
- Supervised — activated once ≥50 fraud labels and ≥200 total labels exist
- Trained on analyst-reviewed data
- Provides fraud probability and feature importance
- Retrained weekly

### 5. Feature Engineering (`app/features/extractor.py`)

Transforms raw transactions into 20 numerical features:

- **Transaction-level**: amount, log(amount), type, time
- **Pattern**: round numbers, night transactions, weekend
- **Velocity**: transaction count/volume in 1h and 24h windows
- **Behavioral**: amount vs average ratio, counterparty diversity

### 6. Compliance Dashboard

React-based UI for compliance analysts:

- **Alert Queue** — prioritized by risk score
- **Transaction Detail** — full context, rule matches, risk breakdown
- **Review Workflow** — mark as fraud/legitimate/suspicious
- **Case Management** — group related alerts into investigations
- **Analytics** — trends, volumes, false positive rates

### 7. Data Flow for ML Training

```
Analyst reviews alert
    → Decision: "confirmed fraud" or "false positive"
    → Label stored in database (reviews table)
    → Weekly Celery beat triggers retraining
    → New XGBoost model trained on all labeled data
    → Model versioned in MLflow
    → New model used for future scoring
```

## Database Schema

```
transactions ──┐
               ├──▶ alerts ──▶ reviews (labeled data)
rule_matches ──┘               │
                               ▼
cases ◀── case_transactions    Training pipeline
              │
              └──▶ transactions
```

Key tables:
- `transactions` — every transaction from Fineract
- `alerts` — flagged transactions requiring review
- `reviews` — analyst decisions (training labels)
- `rule_matches` — which rules each transaction triggered
- `cases` — investigation cases grouping related alerts
- `users` — compliance team members

## Deployment Architecture

```
Kubernetes Cluster
├── namespace: fineract         # Existing Fineract deployment
│   └── fineract-server ─── webhook POST ──┐
│                                           │
├── namespace: aml                          │
│   ├── aml-api (FastAPI) ◀────────────────┘
│   ├── aml-celery-worker (analysis tasks)
│   ├── aml-celery-beat (scheduled retraining)
│   ├── aml-dashboard (React)
│   ├── aml-postgres (separate database)
│   ├── aml-redis (task queue broker)
│   └── aml-mlflow (model tracking)
```

- Same cluster as Fineract for low-latency webhook delivery
- Separate namespace for isolation (RBAC, network policies)
- Separate database — no shared tables with Fineract
- Shared PVC for ML models (accessible by API + workers)
