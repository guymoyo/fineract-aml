# Credit Scoring Operations Guide

## Configuration Reference

All settings use the `AML_` environment variable prefix. For example, `credit_tier_a_min_score` is set via `AML_CREDIT_TIER_A_MIN_SCORE`.

### Tier Thresholds

| Setting | Default | Description |
|---------|---------|-------------|
| `credit_tier_a_min_score` | 0.80 | Minimum score for Tier A (Excellent) |
| `credit_tier_b_min_score` | 0.65 | Minimum score for Tier B (Good) |
| `credit_tier_c_min_score` | 0.50 | Minimum score for Tier C (Fair) |
| `credit_tier_d_min_score` | 0.35 | Minimum score for Tier D (Poor) |

Scores below `tier_d_min_score` fall into Tier E (Very Poor).

### Max Credit Amounts (XAF)

| Setting | Default | Description |
|---------|---------|-------------|
| `credit_tier_a_max_amount` | 5,000,000 | Max credit for Tier A |
| `credit_tier_b_max_amount` | 2,000,000 | Max credit for Tier B |
| `credit_tier_c_max_amount` | 1,000,000 | Max credit for Tier C |
| `credit_tier_d_max_amount` | 500,000 | Max credit for Tier D |
| `credit_tier_e_max_amount` | 0 | Tier E customers cannot borrow |

### Scoring Weights

All weights must sum to 1.0.

| Setting | Default | Feature |
|---------|---------|---------|
| `credit_weight_deposit_consistency` | 0.20 | How regularly the customer deposits |
| `credit_weight_net_flow` | 0.20 | Net income vs. spending |
| `credit_weight_savings_rate` | 0.15 | Ratio saved vs. deposited |
| `credit_weight_tx_frequency` | 0.10 | How active the account is |
| `credit_weight_account_age` | 0.10 | Maturity of the account |
| `credit_weight_repayment_rate` | 0.15 | Loan repayment behavior |
| `credit_weight_fraud_history` | 0.10 | Penalty for past fraud alerts |

### Batch Processing

| Setting | Default | Description |
|---------|---------|-------------|
| `credit_scoring_batch_size` | 500 | Profiles to commit per batch in nightly scoring |
| `credit_min_transactions` | 5 | Minimum transactions required to compute a credit score |

## Common Operations

### Trigger Nightly Scoring Manually

```bash
# Via Docker
docker compose exec api python -c "
from app.tasks.credit_scoring import compute_all_credit_scores
compute_all_credit_scores.delay()
"

# Check task status in Celery worker logs
docker compose logs -f celery-worker --tail=50
```

### Trigger ML Model Retraining

```bash
docker compose exec api python -c "
from app.tasks.credit_scoring import retrain_credit_cluster_model
retrain_credit_cluster_model.delay()
"
```

### Refresh a Single Client's Score

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/credit/profiles/CLI-001/refresh \
  -H "Authorization: Bearer $TOKEN"

# Via Celery task
docker compose exec api python -c "
from app.tasks.credit_scoring import evaluate_credit_request
evaluate_credit_request.delay('CLI-001')
"
```

### Submit a Credit Request (API)

```bash
curl -X POST http://localhost:8000/api/v1/credit/request \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fineract_client_id": "CLI-001", "requested_amount": 500000}'
```

### Approve / Reject a Credit Request

```bash
curl -X PUT http://localhost:8000/api/v1/credit/requests/{request_id}/review \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "approved", "reviewer_notes": "Good payment history."}'
```

### Check Credit Analytics

```bash
curl http://localhost:8000/api/v1/credit/analytics \
  -H "Authorization: Bearer $TOKEN"
```

## Adjusting Tier Thresholds

1. Update the environment variables in `.env`:
   ```env
   AML_CREDIT_TIER_A_MIN_SCORE=0.85
   AML_CREDIT_TIER_B_MIN_SCORE=0.70
   AML_CREDIT_TIER_A_MAX_AMOUNT=6000000
   ```

2. Restart the API and Celery services:
   ```bash
   docker compose restart api celery-worker celery-beat
   ```

3. Trigger a full re-scoring to apply new thresholds:
   ```bash
   docker compose exec api python -c "
   from app.tasks.credit_scoring import compute_all_credit_scores
   compute_all_credit_scores.delay()
   "
   ```

Existing credit requests are NOT retroactively updated — they retain the score/segment snapshot from when they were created.

## Monitoring

### Key Logs to Watch

```bash
# Credit scoring tasks
docker compose logs celery-worker 2>&1 | grep -i "credit"

# API credit endpoints
docker compose logs api 2>&1 | grep "/credit/"
```

### Health Indicators

| Metric | Where to Check | Healthy |
|--------|---------------|---------|
| Nightly scoring ran | Celery worker logs: `"Nightly credit scoring complete"` | Runs every 24h |
| ML model trained | Celery worker logs: `"Credit cluster model retrained"` | Runs every 7d |
| Profiles computed | `GET /credit/analytics` → `total_profiles` | > 0 after first nightly run |
| Pending reviews | `GET /credit/analytics` → `total_pending_requests` | Monitor for buildup |

### Celery Beat Verification

```bash
# Check that beat schedules are registered
docker compose exec celery-beat celery -A app.tasks.celery_app inspect scheduled
```

## Troubleshooting

### "No credit profile found" when submitting a request

**Cause:** The client has fewer transactions than `credit_min_transactions` (default: 5).

**Fix:** Either lower the threshold or ensure the client has sufficient transaction history:
```env
AML_CREDIT_MIN_TRANSACTIONS=3
```

### ML model not training

**Cause:** The weekly task needs sufficient profiles to cluster. K-Means requires at least 5 data points.

**Fix:** Ensure nightly scoring has run first to create profiles, then trigger retraining:
```bash
# Step 1: Run nightly scoring
docker compose exec api python -c "
from app.tasks.credit_scoring import compute_all_credit_scores
compute_all_credit_scores.delay()
"

# Step 2: Wait for completion, then retrain
docker compose exec api python -c "
from app.tasks.credit_scoring import retrain_credit_cluster_model
retrain_credit_cluster_model.delay()
"
```

### Scores seem wrong after config change

**Remember:** Score changes only take effect after re-computation. Either:
1. Wait for the nightly batch job
2. Trigger manual re-scoring (see above)
3. Refresh individual profiles via the API

### asyncpg fork-safety errors in Celery

All credit scoring tasks create a fresh `create_async_engine` per invocation. If you see `InterfaceError: cannot perform operation: another operation is in progress`, check that no credit tasks are importing the shared `async_session` from `app.core.database`.
