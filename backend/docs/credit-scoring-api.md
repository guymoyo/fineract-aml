# Credit Scoring API Reference

All endpoints require a valid JWT token passed via the `Authorization: Bearer <token>` header.

Base URL: `/api/v1`

---

## Credit Profiles

### List Credit Profiles

```
GET /credit/profiles?page=1&page_size=25&segment=tier_a
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int | 25 | Items per page (max 100) |
| `segment` | string | — | Filter by segment: `tier_a`, `tier_b`, `tier_c`, `tier_d`, `tier_e` |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "id": "uuid",
      "fineract_client_id": "CLI-001",
      "credit_score": 0.82,
      "segment": "tier_a",
      "max_credit_amount": 5000000.0,
      "score_components": "{\"deposit_consistency\": 0.88, ...}",
      "ml_cluster_id": 2,
      "ml_segment_suggestion": "tier_a",
      "scoring_method": "hybrid",
      "last_computed_at": "2026-03-19T02:00:00Z",
      "is_active": true,
      "created_at": "2026-03-01T10:00:00Z",
      "updated_at": "2026-03-19T02:00:00Z"
    }
  ],
  "total": 15,
  "page": 1,
  "page_size": 25
}
```

### Get Credit Profile by Client ID

```
GET /credit/profiles/{client_id}
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `client_id` | string | Fineract client ID (e.g. `CLI-001`) |

**Response** `200 OK`: Single `CreditProfile` object (same schema as list item above).

**Errors:**
- `404 Not Found` — No credit profile exists for this client.

### Refresh Credit Profile

Re-computes the credit score for a specific client on demand.

```
POST /credit/profiles/{client_id}/refresh
```

**Response** `200 OK`: Updated `CreditProfile` object.

**Notes:**
- This triggers synchronous re-scoring (feature extraction → rule-based score → ML score if model is trained).
- Useful after a large new transaction or before reviewing a credit request.

---

## Credit Requests

### Submit Credit Request

Creates a new credit request. The system automatically:
1. Refreshes the client's credit profile
2. Generates a recommendation (`approve`, `review_carefully`, `reject`)
3. Sets the status to `pending_review`

```
POST /credit/request
```

**Request Body:**
```json
{
  "fineract_client_id": "CLI-001",
  "requested_amount": 500000.0
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fineract_client_id` | string | ✅ | Fineract client ID |
| `requested_amount` | float | ✅ | Amount requested in XAF |

**Response** `201 Created`:
```json
{
  "id": "uuid",
  "fineract_client_id": "CLI-001",
  "requested_amount": 500000.0,
  "credit_score_at_request": 0.72,
  "segment_at_request": "tier_b",
  "max_credit_at_request": 2000000.0,
  "recommendation": "approve",
  "status": "pending_review",
  "reviewer_notes": null,
  "assigned_to": null,
  "reviewed_at": null,
  "reviewed_by": null,
  "created_at": "2026-03-19T12:00:00Z",
  "updated_at": "2026-03-19T12:00:00Z"
}
```

**Errors:**
- `400 Bad Request` — Client has fewer than `credit_min_transactions` transactions.

### List Credit Requests

```
GET /credit/requests?page=1&page_size=25&status=pending_review
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 25 | Items per page |
| `status` | string | — | Filter: `pending_review`, `approved`, `rejected`, `expired` |

**Response** `200 OK`: Paginated list of `CreditRequest` objects.

### Get Credit Request

```
GET /credit/requests/{request_id}
```

**Response** `200 OK`: Single `CreditRequest` object.

### Review Credit Request (Approve / Reject)

```
PUT /credit/requests/{request_id}/review
```

**Request Body:**
```json
{
  "status": "approved",
  "reviewer_notes": "Client has consistent deposit history and low risk."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | ✅ | `approved` or `rejected` |
| `reviewer_notes` | string | — | Analyst notes explaining the decision |

**Response** `200 OK`: Updated `CreditRequest` with `reviewed_at` and `reviewed_by` populated.

**Notes:**
- The request must currently have `status: pending_review` to be reviewed.
- The `reviewed_by` field is set to the authenticated user's ID.

---

## Credit Analytics

### Get Analytics Overview

```
GET /credit/analytics
```

**Response** `200 OK`:
```json
{
  "segment_distribution": [
    {
      "segment": "tier_a",
      "count": 3,
      "avg_score": 0.87,
      "avg_max_amount": 5000000.0
    },
    {
      "segment": "tier_b",
      "count": 5,
      "avg_score": 0.71,
      "avg_max_amount": 2000000.0
    }
  ],
  "total_profiles": 15,
  "avg_credit_score": 0.65,
  "total_pending_requests": 4,
  "total_approved": 12,
  "total_rejected": 3
}
```

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error description message"
}
```

| Status Code | Meaning |
|-------------|---------|
| 400 | Bad request (e.g., insufficient transaction history) |
| 401 | Missing or invalid authentication token |
| 404 | Resource not found |
| 500 | Internal server error |
