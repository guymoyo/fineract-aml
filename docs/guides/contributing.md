# Contributing Guide

## Development Setup

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Node.js 20+ (for dashboard)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Start infrastructure
docker compose up -d postgres redis

# Run migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload --port 8000

# Start Celery worker (separate terminal)
celery -A app.tasks.celery_app worker --loglevel=info

# Start Celery beat (separate terminal)
celery -A app.tasks.celery_app beat --loglevel=info
```

### Running Tests

```bash
cd backend

# Run all tests
pytest -v

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_rules.py -v

# Run specific test
pytest tests/test_rules.py::TestRuleEngine::test_large_amount_triggers -v
```

### Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check
ruff check .

# Fix auto-fixable issues
ruff check --fix .

# Format
ruff format .
```

## Project Structure

```
backend/app/
├── api/          # FastAPI route handlers (thin — delegate to services)
├── core/         # Configuration, database, security
├── features/     # Feature engineering for ML
├── ml/           # ML models (anomaly detection, fraud classification)
├── models/       # SQLAlchemy ORM models
├── rules/        # Deterministic rule engine
├── schemas/      # Pydantic request/response schemas
├── services/     # Business logic (where the real work happens)
└── tasks/        # Celery async tasks
```

### Architecture Layers

```
API (routes) → Services (business logic) → Models (database)
                    ↓
              Rules / ML (scoring)
```

- **API layer**: Request validation, auth, response formatting
- **Service layer**: Business logic, orchestration
- **Model layer**: Database access, ORM
- **Rules/ML**: Scoring engines (stateless, testable)

## Adding a New Rule

1. Open `app/rules/engine.py`
2. Add a new method:

```python
def _check_my_new_rule(self, tx: Transaction) -> RuleResult:
    triggered = <your condition>
    return RuleResult(
        rule_name="my_new_rule",
        category="pattern",  # amount, pattern, velocity, timing
        triggered=triggered,
        severity=0.5 if triggered else 0.0,
        details="Description of what was detected",
    )
```

3. Call it from `evaluate()`:

```python
result.results.append(self._check_my_new_rule(transaction))
```

4. Add tests in `tests/test_rules.py`

## Adding a New Feature

1. Add the name to `FEATURE_NAMES` in `app/features/extractor.py`
2. Add extraction logic in `extract()`
3. Both anomaly detector and fraud classifier automatically use the new feature
4. Add tests in `tests/test_features.py`
5. After deployment, retrain both models to use the new feature

## Adding a New API Endpoint

1. Create or edit a router in `app/api/`
2. Add service methods in `app/services/`
3. Add Pydantic schemas in `app/schemas/`
4. Register the router in `app/main.py` if it's a new file
5. Add tests in `tests/`
6. Update `docs/api/endpoints.md`

## Branch Strategy

- `main` — production-ready code
- `develop` — integration branch
- `feature/*` — feature branches
- `fix/*` — bug fix branches

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(rules): add high-frequency counterparty rule
fix(ml): handle edge case when account has no history
docs(api): add case management endpoint docs
test(features): add weekend flag extraction test
```
