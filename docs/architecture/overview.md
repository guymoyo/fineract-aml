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
    ├── Feature Extraction → 36 numerical features (with account history)
    ├── Rule Engine → 19 deterministic checks (severity scores)
    ├── Anomaly Detector → unsupervised scoring (Isolation Forest [+ One-Class SVM if ensemble enabled])
    ├── Shadow Model Scoring → shadow scores logged only, never affect decisions
    ├── Fraud Classifier → supervised scoring (XGBoost, if trained + validated)
    ├── Score Combination → final risk score
    ├── Score Explanation → per-feature JSON for regulatory explainability
    ├── Sanctions Screening → counterparty name vs OFAC/EU/UN/PEP watchlists
    ├── Adverse Media Screening → NewsAPI negative keyword check (if score ≥ threshold)
    ├── CTR Generation → auto-file if amount ≥ 5M XAF (configurable)
    ├── Loan Watch Creation → LoanDisbursementWatch for LOAN_DISBURSEMENT transactions
    ├── LLM Investigation Trigger → auto-investigate HIGH/CRITICAL alerts (if enabled)
    ├── Alert Creation → if score ≥ 0.5
    └── Prometheus Metrics → latency, score distribution, rule hit counts
```

**Score combination strategy:**

- **With trained ML model**: `final = 0.5×ML + 0.3×anomaly + 0.2×rules`
- **Without ML model (early stage)**: `final = 0.5×anomaly + 0.5×rules`
- **No models at all**: `final = rules` (pure rule engine)

### 3. Rule Engine (`app/rules/engine.py`)

19 deterministic rules (including 4 agent, 2 merchant, 3 network typology) that catch known AML patterns:

**Standard rules (10):**

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

**Agent-specific rules (4)** — only fire when `actor_type == "agent"`:

| Rule | What it detects |
|------|----------------|
| `agent_structuring` | ≥5 sub-threshold deposits from same agent within 1 hour |
| `agent_float_anomaly` | Float ratio >0.95 or <0.05 over 24 hours vs. agent baseline |
| `agent_account_farming` | >8 deposits into new KYC-level-1 accounts within 24 hours |
| `agent_customer_collusion` | Deposit via agent + withdrawal via different agent within 60 minutes |

**Merchant rules (2)** — only fire when `actor_type == "merchant"`:

| Rule | What it detects |
|------|----------------|
| `merchant_collection_account` | Merchant account receiving from an unusually diverse set of payers |
| `high_value_anonymous_payment` | High-value transaction with no KYC data on payer |

**Network typology rules (3)** — apply at graph level, actor-type-agnostic:

| Rule | What it detects |
|------|----------------|
| `scatter_gather` | ≥8 unique senders converging into one account + single large outbound within 7 days |
| `bipartite_layering` | ≥5 unique senders AND ≥5 unique recipients through single intermediary within 7 days |
| `stacking` | ≥3 sequential transfers within 30 minutes where each amount is 80–120% of the prior |

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

36 numerical features per transaction:

- **Transaction-level (11)**: amount, log(amount), type (one-hot), hour, day_of_week, weekend, night, round_hundred, round_thousand
- **Account-level / 24h window (11)**: tx_count_1h/24h, total_amount_1h/24h, avg/max_amount_24h, amount_vs_avg_ratio, unique_counterparties_24h, same_type_ratio_24h, is_new_ip_for_account, unique_ips_24h
- **Extended 7d window (10)**: tx_count_7d, total/avg/max_amount_7d, unique_counterparties_7d, amount_vs_7d_avg_ratio, tx_velocity_trend, receiver_diversity_7d, geo_distance_from_usual, has_loan_disbursement_7d
- **Actor context (4)**: is_agent, is_merchant, kyc_level_norm, is_new_kyc

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

## WeBank Actor Model

The AML system differentiates between three actor types, each with distinct behavioral profiles and rule sets. The `actor_type` field in the webhook payload drives which rules are applied.

| Actor | Description | Behavioral Baseline |
|-------|-------------|---------------------|
| **Customer** | Mobile wallet end-users | Standard velocity thresholds |
| **Agent** | Licensed cash-in/cash-out operators with float | Per-agent 30-day rolling baseline stored in `agent_profiles` |
| **Merchant** | QR payment merchants | Monitored for collection account patterns |

The BFF must populate `actor_type` from Keycloak token claims before forwarding events to `/webhook/fineract`. Without this field, agent-specific and merchant-specific rules will not fire.

---

## Synchronous Scoring Path

`POST /api/v1/score` provides real-time risk scoring without persisting anything to the database. It is designed for BFF pre-screening or front-end blocking decisions where sub-400ms latency is required.

```
BFF → POST /api/v1/score
    → ScoringService
        ├── DB history fetch (7d + 24h + 1h) — timeout: 200ms
        │     └── on timeout → degraded_mode=true, skip velocity/ML features
        ├── FeatureExtractor (36 features)
        ├── RuleEngine (19 rules)
        ├── AnomalyDetector (Isolation Forest)
        └── FraudClassifier (XGBoost, if ready)
    → JSON response (rule_score, anomaly_score, ml_score, risk_score, triggered_rules, recommendation, latency_ms, degraded_mode)
    < 400ms p99
```

**Degraded mode**: If the account history DB query times out, scoring falls back to rules-only mode. The response is still returned immediately with `degraded_mode: true` so the BFF can choose how to handle the reduced confidence.

---

## Shadow/Canary ML Deployment

After each successful training run, the new model is also written to a **shadow slot** (separate model file path). The shadow model runs on every transaction in parallel with the production model, but its scores are logged only — they never affect risk decisions or alerts.

```
Transaction → Production model → final risk decision
           ↘ Shadow model     → score logged to model_health table only
```

The `promote_shadow_model` Celery task promotes the shadow model to production after:
- The shadow model has been running for at least `AML_SHADOW_MODEL_PROMOTION_DAYS` days (default: 7)
- Shadow AUC exceeds production AUC by at least `AML_SHADOW_MODEL_PROMOTION_AUC_DELTA` (default: 0.02)

Enable shadow deployment via `AML_SHADOW_MODEL_ENABLED=true`.

---

## New Components (Phase 5-6)

### LLM Investigation Agent (`app/services/llm_agent.py`)

Automatically investigates HIGH and CRITICAL alerts when `LLM_INVESTIGATION_ENABLED=true`. Uses the Claude API (claude-opus-4-6) with agentic tool use (transaction history, customer profile, related alerts, agent profile, credit profile). Generates French COBAC SAR narratives stored in `alert.investigation_report`.

### SAR Service (`app/services/sar_service.py`)

Generates COBAC-compliant SAR documents:
- **XML**: Machine-readable format for electronic filing (`GET /api/v1/cases/{id}/sar/xml`)
- **PDF**: Human-readable French-language report for compliance officer review (`GET /api/v1/cases/{id}/sar/pdf`)

### Synchronous Scoring API (`app/api/score.py`)

`POST /api/v1/score` — real-time risk scoring without a DB write. Target: < 400 ms (p99).

Synchronous path:
```
BFF → POST /api/v1/score → ScoringService → {RuleEngine + AnomalyDetector + ML} → response < 400ms
```

### Graph Visualization API (`app/api/graph.py`)

Serves D3/Cytoscape-compatible transaction network graphs for account-level (`/graph/account/{id}`) and case-level (`/graph/case/{id}`) views. Results cached for 15 minutes.

### Model Health API (`app/api/model_health.py`)

Exposes PSI drift scores and AUC metrics per model at `/api/v1/model-health` and `/api/v1/model-health/drift`. Historical snapshots available at `/api/v1/model-health/history/{model_name}`.

### Prometheus Metrics

Metrics endpoint at `GET /metrics` exposes request counts, latency histograms, alert volumes, ML inference latencies, and Celery queue depths for scraping by a Prometheus/Grafana stack.

---

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
