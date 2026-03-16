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
  "description": "Wire transfer"
}
```

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
