# API Reference

Base URL: `http://localhost:8000/api/v1`

Interactive docs: `http://localhost:8000/docs` (Swagger UI)

## Authentication

All endpoints except `/webhook/fineract` and `/auth/login` require a JWT Bearer token.

```bash
# Login
curl -X POST /api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# Response
{"access_token": "eyJ...", "token_type": "bearer"}

# Use token in subsequent requests
curl -H "Authorization: Bearer eyJ..." /api/v1/transactions
```

---

## Webhook

### POST `/webhook/fineract`

Receives transaction events from Fineract. No authentication required (uses HMAC signature verification).

**Headers:**
- `X-Webhook-Signature` — HMAC-SHA256 signature of the request body

**Request Body:**
```json
{
  "transaction_id": "TX-12345",
  "account_id": "ACC-001",
  "client_id": "CLI-001",
  "transaction_type": "deposit",
  "amount": 5000.00,
  "currency": "USD",
  "transaction_date": "2025-06-15T14:30:00Z",
  "counterparty_account_id": "ACC-002",
  "counterparty_name": "John Doe",
  "description": "Wire transfer",
  "actor_type": "agent",
  "agent_id": "AGT-001",
  "branch_id": "BRN-001",
  "merchant_id": null,
  "device_id": "d3f4...",
  "kyc_level": 2
}
```

Actor context fields are populated by the BFF from Keycloak token claims before forwarding. See the [Updated Webhook Payload Schema](#updated-webhook-payload-schema) section for field details.

**Response (202 Accepted):**
```json
{
  "status": "accepted",
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Transaction queued for AML analysis"
}
```

---

## Transactions

### GET `/transactions`

List transactions with optional filtering and pagination.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 50 | Items per page (max 100) |
| `risk_level` | enum | — | Filter: `low`, `medium`, `high`, `critical` |

### GET `/transactions/stats`

Dashboard statistics summary.

**Response:**
```json
{
  "total_transactions": 15234,
  "total_flagged": 127,
  "total_confirmed_fraud": 23,
  "total_false_positives": 89,
  "average_risk_score": 0.23,
  "transactions_today": 342,
  "alerts_pending": 15
}
```

### GET `/transactions/{id}`

Get a single transaction by UUID.

---

## Alerts

### GET `/alerts`

List alerts sorted by risk score (highest first).

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 50 | Items per page (max 100) |
| `status` | enum | — | Filter: `pending`, `under_review`, `confirmed_fraud`, `false_positive`, `escalated`, `dismissed` |
| `assigned_to` | UUID | — | Filter by assigned analyst |

### GET `/alerts/{id}`

Get a single alert with transaction details and reviews.

### PATCH `/alerts/{id}/assign`

Assign an alert to a compliance analyst.

```json
{"assigned_to": "550e8400-e29b-41d4-a716-446655440000"}
```

### PATCH `/alerts/{id}/status`

Update alert status.

```json
{"status": "under_review"}
```

### POST `/alerts/{id}/review`

Submit an analyst review decision. **This is the key endpoint that builds labeled training data.**

```json
{
  "decision": "confirmed_fraud",
  "notes": "Multiple structuring transactions from same source",
  "evidence": "Linked to known fraud ring reference #FR-2025-001",
  "sar_filed": true,
  "sar_reference": "SAR-2025-0042"
}
```

Decision values:
- `confirmed_fraud` — Transaction is fraudulent (label = 1 for ML training)
- `legitimate` — False positive (label = 0 for ML training)
- `suspicious` — Needs further investigation (escalated, not used for training)

---

## Cases

### POST `/cases`

Create an investigation case.

```json
{
  "title": "Suspected structuring — Client CLI-001",
  "description": "Multiple sub-threshold deposits over 3 days",
  "fineract_client_id": "CLI-001",
  "transaction_ids": ["uuid1", "uuid2", "uuid3"]
}
```

### GET `/cases`

List cases with optional status filter.

### GET `/cases/{id}`

Get case details.

### PATCH `/cases/{id}/status`

Update case status: `open`, `investigating`, `escalated`, `closed_legitimate`, `closed_fraud`, `sar_filed`.

### PATCH `/cases/{id}/assign`

Assign a case to an analyst.

---

## Auth

### POST `/auth/login`

Authenticate and receive JWT token.

### POST `/auth/register`

Register a new analyst (requires authentication).

### GET `/auth/me`

Get current user profile.

---

## Health

### GET `/health`

Health check endpoint (no auth required).

```json
{"status": "healthy", "service": "Fineract AML Service", "version": "0.1.0"}
```

---

## Scoring

### POST `/api/v1/score`

Synchronous risk scoring without a database write. Designed for BFF pre-screening or real-time decisioning where sub-400ms latency is required.

**Request body**: Same JSON schema as `POST /webhook/fineract` (including all actor context fields).

**Response:**
```json
{
  "risk_score": 0.74,
  "risk_level": "HIGH",
  "rule_score": 0.65,
  "anomaly_score": 0.71,
  "ml_score": 0.82,
  "triggered_rules": ["structuring", "rapid_transactions"],
  "recommendation": "ESCALATE",
  "latency_ms": 187,
  "degraded_mode": false
}
```

| Field | Description |
|-------|-------------|
| `risk_score` | Final combined risk score (0.0–1.0) |
| `risk_level` | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` |
| `rule_score` | Score contribution from the deterministic rule engine |
| `anomaly_score` | Score from the unsupervised anomaly detector |
| `ml_score` | Score from the supervised fraud classifier (null if model not ready) |
| `triggered_rules` | List of rule names that fired |
| `recommendation` | `ALLOW` / `MONITOR` / `ESCALATE` / `BLOCK` |
| `latency_ms` | End-to-end scoring latency in milliseconds |
| `degraded_mode` | `true` when DB history fetch timed out; rules-only fallback was used |

- `degraded_mode: true` indicates the 7d/24h account history fetch timed out. Scoring fell back to rules-only mode (no ML, no velocity features). The response is still valid but less precise.
- Target latency: **< 400 ms** (p99).

---

## Graph Visualization

### GET `/graph/account/{account_id}?days=30&depth=2`

Returns a 2-hop transaction network graph suitable for D3 or Cytoscape rendering.

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `days` | int | 30 | Lookback window in days |
| `depth` | int | 2 | Hop depth from the root account |

**Response:** `{nodes: [...], edges: [...]}` — cached for 15 minutes.

### GET `/graph/case/{case_id}`

Returns the transaction network subgraph for all accounts and transactions linked to a given case.

---

## Model Health

### GET `/model-health`

Returns the latest health snapshot for each active ML model, including AUC and PSI drift score.

### GET `/model-health/drift`

Returns PSI-based drift summaries per feature, with per-model status (`stable` | `warning` | `drift`) and recommended actions.

### GET `/model-health/history/{model_name}?limit=20`

Returns historical training snapshots for the named model (e.g., `fraud_classifier`, `anomaly_detector`).

**Query Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 20 | Maximum number of historical snapshots to return |

---

## SAR Export

### GET `/cases/{id}/sar/xml`

Exports the SAR (Suspicious Activity Report) for a case as COBAC-compliant XML, ready for electronic filing with the regulator.

### GET `/cases/{id}/sar/pdf`

Exports the SAR as a PDF document in French, formatted for COBAC submission. The narrative is generated or reviewed by the LLM Investigation Agent.

---

## Observability

### GET `/metrics`

Prometheus metrics endpoint. Exposes request counts, latency histograms, alert volumes, model inference latencies, and Celery queue depths.

---

## Updated Webhook Payload Schema

The following fields have been added to the existing `/webhook/fineract` payload in Phase 1 to support the WeBank actor model:

| Field | Type | Description |
|-------|------|-------------|
| `actor_type` | `string\|null` | Actor category: `"customer"`, `"agent"`, or `"merchant"` |
| `agent_id` | `string\|null` | Fineract office/staff ID for the transacting agent |
| `branch_id` | `string\|null` | Branch or office ID |
| `merchant_id` | `string\|null` | Merchant account ID (QR payment merchants) |
| `device_id` | `string\|null` | SHA-256 device fingerprint hash |
| `kyc_level` | `int\|null` | Customer KYC level 1–4 |

The BFF is responsible for populating `actor_type` from Keycloak token claims before forwarding the webhook.
