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

- **Webhook Consumer** — receives deposit/withdrawal events from Fineract in real-time
- **Rule Engine** — deterministic AML rules (large amounts, structuring, velocity, unusual hours)
- **Anomaly Detection** — unsupervised ML (Isolation Forest) that works without labeled data
- **Fraud Classifier** — supervised ML (XGBoost) that trains on analyst-labeled data over time
- **Compliance Dashboard** — review alerts, investigate cases, label transactions
- **Human-in-the-Loop** — analyst decisions become training data for continuous ML improvement
- **Case Management** — group related suspicious transactions into investigation cases
- **Credit Scoring** — rule-based + ML customer credit scoring with tier segmentation
- **Credit Request Review** — compliance workflow for loan applications with auto-recommendations
- **Transfer Fraud Detection** — circular transfer, new counterparty, and rapid pair detection
- **MLflow Integration** — model versioning, experiment tracking, metrics logging

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.12+ (for local development)
- Node.js 20+ (for dashboard development)

### Run with Docker Compose

```bash
# Clone the repository
git clone https://github.com/ADORSYS-GIS/fineract-aml.git
cd fineract-aml

# Copy environment file
cp .env.example .env

# Start all services
docker compose up -d

# Run database migrations
docker compose exec api alembic upgrade head

# Create initial admin user (interactive)
docker compose exec api python -m app.scripts.create_admin
```

Services will be available at:

| Service | URL |
|---------|-----|
| AML API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Docs (ReDoc) | http://localhost:8000/redoc |
| Compliance Dashboard | http://localhost:3000 |
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

- [Architecture Overview](docs/architecture/overview.md)
- [API Reference](docs/api/endpoints.md)
- [Credit Scoring API](backend/docs/credit-scoring-api.md)
- [Fineract Webhook Setup](docs/guides/fineract-webhook-setup.md)
- [ML Pipeline Guide](docs/ml/pipeline.md)
- [Deployment Guide](docs/guides/deployment.md)
- [Contributing](docs/guides/contributing.md)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API | Python 3.12, FastAPI, SQLAlchemy 2.0 |
| Database | PostgreSQL 16 |
| Task Queue | Celery + Redis |
| ML | scikit-learn, XGBoost, MLflow |
| Dashboard | React, TanStack Router, TanStack Query |
| Containers | Docker, Kubernetes |

## License

Apache License 2.0
