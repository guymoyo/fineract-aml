# Fineract AML — Anti-Money Laundering Detection Service

Real-time Anti-Money Laundering (AML) and fraud detection service for [Apache Fineract](https://fineract.apache.org/). Consumes transaction events via webhooks, applies rule-based and ML-powered analysis, and provides a compliance analyst dashboard for investigation and case management.

## Architecture

```
┌─────────────┐     Webhook      ┌──────────────┐     Celery      ┌────────────────┐
│   Fineract  │ ──────────────▶  │   FastAPI     │ ─────────────▶  │  Analysis       │
│   (Core     │  POST /webhook   │   (API)       │   async task    │  Pipeline       │
│   Banking)  │                  │               │                 │                 │
└─────────────┘                  └──────┬───────┘                 │  1. Rules       │
                                        │                          │  2. Anomaly     │
                                        │ REST API                 │  3. XGBoost     │
                                        ▼                          └───────┬────────┘
                                 ┌──────────────┐                         │
                                 │  Compliance   │      Alerts            │
                                 │  Dashboard    │ ◀──────────────────────┘
                                 │  (React)      │
                                 └──────────────┘
                                   │
                                   │  Analyst reviews alerts
                                   │  (human-in-the-loop)
                                   ▼
                              Labeled data → Model retraining
```

## Key Features

### Fraud Detection
- **Rule Engine** — 19 deterministic AML rules covering general patterns, agent network fraud, merchant fraud, and IBM AMLSim network typologies (scatter-gather, bipartite layering, stacking)
- **Anomaly Detection** — Isolation Forest (+ optional One-Class SVM ensemble) detects unusual transactions without any labeled data
- **Fraud Classifier** — XGBoost supervised model trained on analyst-labeled data; shadow/canary deployment with AUC-gated promotion
- **36-feature vector** — transaction-level, 24h window, 7-day window, and WeBank actor-context features
- **Agent network monitoring** — structuring detection, float anomaly, account farming, and agent-customer collusion rules
- **Merchant fraud** — collection-account detection and anonymous high-value payment alerts
- **Post-disbursement loan monitoring** — detects loan-and-run, immediate cash-out, structuring, and cross-agent dispersal
- **Sanctions screening** — OFAC SDN, EU, UN, PEP watchlists refreshed every 6 hours; fuzzy-match at 85% similarity
- **Adverse media screening** — NewsAPI keyword search for high-risk counterparties (optional)
- **LLM investigation agent** — Claude-powered automated investigation reports and French SAR narrative drafts (optional)

### Credit Scoring
- **20 behavioral features** — deposit consistency, net flow, savings rate, loan repayment, fraud history, geographic stability, and more
- **Round-trip gaming detection** — identifies circular wash transactions used to artificially inflate deposit history
- **5-tier segmentation** (A–E) with configurable score thresholds and XAF credit limits
- **K-Means cluster validation** — weekly ML model validates rule-based tiers against natural behavioral segments
- **Real-time re-scoring** — credit requests trigger fresh scoring, not stale nightly batch scores

### Compliance Operations
- **Webhook Consumer** — receives all Fineract transaction types in real-time via HMAC-SHA256 authenticated webhooks
- **Compliance Dashboard** — review alerts, investigate cases, label transactions for model training
- **Human-in-the-Loop** — analyst decisions feed directly into fraud classifier retraining
- **Case Management** — group related suspicious transactions into investigation cases
- **CTR auto-filing** — transactions above 5,000,000 XAF auto-generate COBAC Currency Transaction Reports
- **Escalation engine** — unresolved cases auto-escalate after 30 days; unassigned alerts re-queue after 24 hours
- **Audit trail** — every action logged for COBAC compliance
- **MLflow Integration** — model versioning, experiment tracking, drift detection (PSI)

## Quick Start

```bash
git clone https://github.com/ADORSYS-GIS/fineract-aml.git
cd fineract-aml
cp .env.example .env
make setup
```

Open **http://localhost:3000** and log in with `admin` / `admin123`.

> For full setup instructions, test data details, ML training, troubleshooting, and manual setup steps see the **[Getting Started Guide](docs/guides/getting-started.md)**.

| Service | URL |
|---------|-----|
| Compliance Dashboard | http://localhost:3000 |
| AML API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| MLflow UI | http://localhost:5000 |

### Local Development

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Celery worker (separate terminal)
celery -A app.tasks.celery_app worker --loglevel=info

# Celery beat (separate terminal)
celery -A app.tasks.celery_app beat --loglevel=info
```

### Run Tests

```bash
cd backend
pytest -v
pytest --cov=app --cov-report=html
```

## Project Structure

```
fineract-aml/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── api/               # REST API endpoints
│   │   │   ├── webhook.py     # Fineract webhook consumer
│   │   │   ├── alerts.py      # Alert management
│   │   │   ├── transactions.py# Transaction queries
│   │   │   ├── cases.py       # Case management
│   │   │   ├── credit.py      # Credit scoring & requests
│   │   │   └── auth.py        # Authentication
│   │   ├── core/              # Config, database, security
│   │   ├── features/          # Feature engineering for ML
│   │   ├── ml/                # ML models
│   │   │   ├── anomaly_detector.py  # Isolation Forest (unsupervised)
│   │   │   ├── fraud_classifier.py  # XGBoost (supervised)
│   │   │   └── credit_scorer.py    # Credit scoring + K-Means clustering
│   │   ├── models/            # SQLAlchemy database models
│   │   ├── rules/             # Deterministic rule engine
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── services/          # Business logic layer
│   │   └── tasks/             # Celery async tasks
│   ├── alembic/               # Database migrations
│   ├── tests/                 # Test suite
│   ├── Dockerfile
│   └── requirements.txt
├── dashboard/                  # React compliance dashboard
├── ml/                        # ML experiments & training notebooks
├── k8s/                       # Kubernetes deployment manifests
├── docs/                      # Documentation
├── docker-compose.yml
└── .env.example
```

## Credit Scoring

The system computes credit scores for customers based on their transaction behavior, segments them into tiers (A–E), and provides compliance-reviewed credit request workflows.

**How it works:**
1. Every night, the system looks at each customer's last 180 days of transactions and computes 19 behavioral features (deposit consistency, savings rate, loan repayment rate, fraud history, etc.)
2. A **weighted formula** turns those features into a single credit score (0–1). Biggest factors: deposit consistency (20%), net cash flow (20%), loan repayment (15%), savings rate (15%)
3. The score determines the customer's **tier** and maximum borrowable amount:

| Score | Tier | Max Credit (XAF) |
|-------|------|-------------------|
| ≥ 80% | A - Excellent | 50,000 |
| ≥ 65% | B - Good | 20,000 |
| ≥ 50% | C - Fair | 10,000 |
| ≥ 35% | D - Poor | 1,000 |
| < 35% | E - Very Poor | 0 |

4. A **K-Means ML model** (trained weekly) groups customers into 5 clusters to validate the rule-based tiers
5. When a customer applies for a loan, the system **re-scores them in real-time** and generates a recommendation (approve / review carefully / reject)
6. A **compliance analyst** reviews and makes the final decision — the system never auto-approves

**Quick start:**
```bash
# Run nightly scoring
docker compose exec api python -c "from app.tasks.credit_scoring import compute_all_credit_scores; compute_all_credit_scores.delay()"

# Submit a credit request
curl -X POST http://localhost:8000/api/v1/credit/request \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fineract_client_id":"CLI-001","requested_amount":15000}'
```

**Detailed documentation:**
- [Credit Scoring API Reference](backend/docs/credit-scoring-api.md)
- [Architecture & Scoring Methodology](backend/docs/credit-scoring-architecture.md)
- [Operations Guide & Configuration](backend/docs/credit-scoring-operations.md)

## Documentation

| Guide | Description |
|---|---|
| [Getting Started](docs/guides/getting-started.md) | Local setup, test data, ML training, troubleshooting |
| [Architecture Overview](docs/architecture/overview.md) | System design, components, analysis pipeline |
| [Fraud Detection Guide](docs/guides/fraud-detection.md) | All 19 rules, detection layers, supporting systems, configuration |
| [Credit Scoring Guide](docs/guides/credit-scoring.md) | 20 features, score formula, tiers, gaming detection |
| [ML Pipeline Guide](docs/ml/pipeline.md) | 36-feature table, XGBoost config, drift monitoring, shadow deployment |
| [Regulatory Compliance Guide](docs/guides/regulatory-compliance.md) | COBAC SAR workflow, CTR filing, sanctions screening |
| [Agent Network Monitoring](docs/guides/agent-network-monitoring.md) | Agent fraud patterns and investigation workflow |
| [Loan Monitoring Guide](docs/guides/loan-monitoring.md) | Post-disbursement fraud detection lifecycle |
| [LLM Investigation Agent](docs/guides/llm-agents.md) | Claude-powered alert investigation and SAR drafting |
| [API Reference](docs/api/endpoints.md) | REST endpoints with request/response schemas |
| [Credit Scoring API](backend/docs/credit-scoring-api.md) | Credit request and profile endpoints |
| [Fineract Webhook Setup](docs/guides/fineract-webhook-setup.md) | Configuring Fineract to send events to this service |
| [Deployment Guide](docs/guides/deployment.md) | Docker, Kubernetes, environment configuration |
| [Contributing](docs/guides/contributing.md) | Development setup, testing, pull request process |

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API | Python 3.12, FastAPI | REST API with async support, auto-generated Swagger docs |
| ORM | SQLAlchemy 2.0 (async) | Database models with async PostgreSQL driver (asyncpg) |
| Database | PostgreSQL 16 | Permanent transaction storage, credit profiles, alerts, cases |
| Task Queue | Celery + Redis | Background analysis, nightly scoring, weekly ML retraining |
| ML | scikit-learn, XGBoost, MLflow | 4 ML models (see below) with experiment tracking |
| Dashboard | React, TanStack Router, TanStack Query | Compliance analyst UI with file-based routing |
| Auth | JWT (PyJWT) | Token-based authentication for API and dashboard |
| Validation | Pydantic v2 | Request/response schemas and config management |
| Containers | Docker, Docker Compose, Kubernetes | Development and production deployment |

### ML Models

The system uses 5 complementary models — 4 for AML fraud detection and 1 for credit scoring:

| Model | Type | Library | Purpose | Training |
|-------|------|---------|---------|----------|
| **Rule Engine** | Deterministic | Custom Python | 19 rules covering general AML patterns, agent/merchant fraud, and network typologies (scatter-gather, bipartite layering, stacking) | No training — rules configured via environment variables |
| **Isolation Forest** | Unsupervised | scikit-learn | Anomaly detection — flags statistically unusual transactions without labeled data. Optional One-Class SVM ensemble adds a second detection perspective | Daily retraining via Celery Beat |
| **XGBoost Classifier** | Supervised | XGBoost | Fraud classification — learns from analyst-labeled data (fraud vs. legitimate). Inactive until ≥200 confirmed fraud cases; shadow/canary deployment with AUC gate | Weekly retraining; new model deployed only if CV AUC ≥ 0.80 |
| **Graph Analyzer** | Graph analytics | NetworkX | Builds directed transaction graph to find multi-hop cycles, fan-out/fan-in accounts, and high-PageRank mule nodes | On-demand and nightly |
| **K-Means Clustering** | Unsupervised | scikit-learn | Credit tier validation — groups customers into 5 behavioral clusters to cross-validate the rule-based credit tiers | Weekly retraining via Celery Beat |

**How they work together:**
- For **AML**: Every transaction passes through Rule Engine → Anomaly Detector → XGBoost (if trained). Scores are combined: `0.5×ML + 0.3×anomaly + 0.2×rules`. Final score ≥ 0.5 generates an alert.
- For **Credit**: A rule-based weighted formula scores 20 behavioral features. K-Means independently groups customers to validate those scores. When both agree, confidence is higher.

### Transaction Storage

All transactions are stored **permanently** in PostgreSQL. The credit scoring system uses a **180-day sliding window** — it looks at each customer's last 6 months of transactions to compute their credit score. This means scores automatically reflect recent behavior changes without losing historical data.

## License

Apache License 2.0
