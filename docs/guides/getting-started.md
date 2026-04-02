# Getting Started — Local Setup Guide

This guide walks you through running the full Fineract AML stack locally, loading test data, and testing the compliance dashboard.

---

## Prerequisites

**Required:**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)

**Only needed for local development without Docker:**
- Python 3.12+
- Node.js 20+

Everything else (PostgreSQL, Redis, MLflow, the API, Celery workers, and the dashboard) runs inside Docker containers.

---

## Quick Start (under 5 minutes)

```bash
# 1. Clone the repository
git clone https://github.com/ADORSYS-GIS/fineract-aml.git
cd fineract-aml

# 2. Copy the environment file
cp .env.example .env

# 3. Start all services, run migrations, and seed test data
make setup
```

That's it. When `make setup` finishes you'll see:

```
Setup complete! Login with admin / admin123
Dashboard: http://localhost:3000
```

Open **http://localhost:3000** and log in.

---

## Demo Credentials

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin123` | Admin — full access |
| `analyst1` | `analyst123` | Analyst — review alerts and cases |
| `senior_analyst` | `senior123` | Senior Analyst — escalations and SAR filing |

---

## Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Compliance Dashboard | http://localhost:3000 | Main analyst UI |
| AML API | http://localhost:8000 | FastAPI backend |
| Swagger / OpenAPI | http://localhost:8000/docs | Interactive API documentation |
| ReDoc | http://localhost:8000/redoc | API reference (read-only) |
| MLflow UI | http://localhost:5000 | ML experiment tracking and model registry |

---

## What the Seed Data Creates

Running `make seed` (included in `make setup`) populates the database with:

| Data | Count | Details |
|------|-------|---------|
| Users | 3 | Admin, Analyst, Senior Analyst — see credentials above |
| Transactions | ~600 | 500 general + ~96 loan transactions |
| Clients | 15 | `CLI-001` through `CLI-015` |
| Accounts | 20 | `ACC-001` through `ACC-020` |
| Loan histories | 8 clients | 1–3 disbursements each with repayments |
| Suspicious patterns | 6 transfers | Circular transfers + rapid pair transfers |

**Injected fraud patterns** (to trigger alerts):
- **Structuring** — transactions at 9,500–9,999 (just below the 10,000 reporting threshold)
- **Round-amount transfers** — exactly 5,000, 10,000, or 20,000
- **Night transactions** — activity between 2–5 AM
- **Circular transfers** — `CLI-001` sends to `CLI-002` who immediately sends back
- **Rapid pair transfers** — 4 transfers between the same two accounts within 6 hours

Alerts are generated automatically when transactions pass through the analysis pipeline during seeding.

---

## Trigger ML Model Training

ML models train on a daily/weekly schedule via Celery Beat. To populate the **Model Health** page and **Credit Profiles** immediately after setup, trigger training manually:

```bash
# Anomaly Detector (Isolation Forest) — requires ≥100 transactions
docker compose exec api python -c \
  "from app.tasks.training import retrain_anomaly_detector; retrain_anomaly_detector.delay()"

# Credit Scores (rule-based nightly batch) — populates the Credit Profiles page
docker compose exec api python -c \
  "from app.tasks.credit_scoring import compute_all_credit_scores; compute_all_credit_scores.delay()"
```

Wait ~30 seconds, then check:
- **http://localhost:3000/model-health** — Anomaly Detector card with AUC/PSI metrics
- **http://localhost:3000/credit-profiles** — Scored profiles for all 15 clients

### ML Training Schedule

| Model | Schedule | Minimum Data Required | Notes |
|-------|----------|-----------------------|-------|
| Anomaly Detector (Isolation Forest) | Daily | ≥100 transactions | Unsupervised — no labels needed |
| Fraud Classifier (XGBoost) | Weekly | ≥200 confirmed fraud labels | Inactive until analysts label enough alerts |
| Credit Cluster Model (K-Means) | Weekly | ≥1 credit profile | Validates rule-based tier assignments |
| Credit Scores (rule-based) | Daily (nightly) | ≥5 transactions per client | Always runs regardless of ML model status |

Celery Beat starts automatically with `docker compose up`. You can monitor scheduled task execution:

```bash
docker compose logs -f celery-beat    # See when tasks fire
docker compose logs -f celery-worker  # See task execution and results
```

---

## Navigating the Dashboard

After `make setup` + ML training trigger, here's what you'll find on each page:

| Page | URL | What to expect |
|------|-----|----------------|
| Dashboard | `/` | Transaction stats, pending alert count, credit segment pie chart |
| Alerts | `/alerts` | Alerts generated from the seeded suspicious patterns |
| Alert Detail | `/alerts/{id}` | Transaction details, triggered rules, AI report placeholder, sanctions section |
| Transactions | `/transactions` | ~600 seeded transactions (click any row to open detail) |
| Transaction Detail | `/transactions/{id}` | All fields, risk score bars |
| Cases | `/cases` | Empty — create one from the UI using the "New Case" button |
| Case Detail | `/cases/{id}` | Description, status update dropdown |
| Credit Profiles | `/credit-profiles` | 15 profiles after scoring task runs (click row for detail) |
| Credit Profile Detail | `/credit-profiles/{clientId}` | Score breakdown bars, ML cluster, Refresh Score button |
| Credit Requests | `/credit-requests` | Empty — submit via API or Swagger UI |
| Credit Analytics | `/credit-analytics` | Segment distribution, request stats |
| Model Health | `/model-health` | Anomaly Detector card after training task runs |

---

## Checking Container Status

```bash
# See all 7 containers and their status
docker compose ps

# Expected output — all should show "Up" or "running"
# aml-api          running
# aml-celery-worker running
# aml-celery-beat  running
# aml-postgres     running (healthy)
# aml-redis        running (healthy)
# aml-mlflow       running
# aml-dashboard    running
```

---

## Common Issues

### Port already in use

If a port is already bound on your machine, the container will fail to start.

| Default port | Service | How to change |
|-------------|---------|---------------|
| 3000 | Dashboard | Edit `ports` in `docker-compose.yml` for `dashboard` service |
| 8000 | API | Edit `ports` for `api` service |
| 5000 | MLflow | Edit `ports` for `mlflow` service |
| 5433 | PostgreSQL | Edit `ports` for `postgres` service (also update `AML_DATABASE_URL` in `.env`) |
| 6380 | Redis | Edit `ports` for `redis` service (also update `AML_REDIS_URL` in `.env`) |

### Database not ready

If migrations fail with a connection error, the API started before Postgres was healthy. Wait a few seconds and retry:

```bash
make migrate
```

### Dashboard shows "Network Error" or blank data

The dashboard container serves the pre-built static files and proxies API calls to the `api` container. If the API isn't ready yet:

```bash
docker compose logs api | tail -20   # Check for startup errors
```

### Credit Profiles page is empty

The credit scoring task has not run yet. Trigger it manually:

```bash
docker compose exec api python -c \
  "from app.tasks.credit_scoring import compute_all_credit_scores; compute_all_credit_scores.delay()"
```

### Model Health page is empty

The anomaly detector has not been trained yet. Trigger it manually:

```bash
docker compose exec api python -c \
  "from app.tasks.training import retrain_anomaly_detector; retrain_anomaly_detector.delay()"
```

### Fraud Classifier shows "Collecting labels"

This is expected. The XGBoost classifier only activates after analysts have confirmed ≥200 fraud alerts. Use the seed data alerts as a starting point — review them in the dashboard and mark suspicious ones as "Confirmed Fraud".

---

## Reset Everything

To wipe all data and start fresh:

```bash
make down-clean   # Stop containers and delete all volumes (DB, Redis, MLflow artifacts)
make setup        # Recreate and reseed from scratch
```

---

## Manual Setup (without Make)

If you don't have `make`, run the equivalent commands directly:

```bash
# Start all services
docker compose up -d

# Wait for containers to be healthy (~10 seconds)
docker compose ps

# Run database migrations
docker compose exec api alembic upgrade head

# Seed test data (creates users, transactions, alerts)
docker compose exec api python -m app.scripts.seed_data

# (Optional) Create a custom admin user interactively
docker compose exec api python -m app.scripts.create_admin

# Trigger ML training
docker compose exec api python -c \
  "from app.tasks.training import retrain_anomaly_detector; retrain_anomaly_detector.delay()"
docker compose exec api python -c \
  "from app.tasks.credit_scoring import compute_all_credit_scores; compute_all_credit_scores.delay()"
```

---

## Next Steps

Once the system is running, explore these guides:

- [Fraud Detection Guide](fraud-detection.md) — all 19 AML rules and detection layers
- [Credit Scoring Guide](credit-scoring.md) — how customer scores and tiers work
- [API Reference](../api/endpoints.md) — all REST endpoints
- [Contributing Guide](contributing.md) — how to add rules, features, and endpoints
- [Deployment Guide](deployment.md) — Docker, Kubernetes, and production configuration
