# Credit Scoring Guide

This guide explains how the credit scoring system works — how customer creditworthiness is measured, what each feature captures, how the score is computed, how gaming is detected, and how credit and fraud detection interact.

---

## Overview

The credit scoring system computes a single score (0–1) for each customer based on their last 180 days of transaction behavior. This score maps to a credit tier (A–E) that determines their maximum borrowable amount.

Two approaches run in parallel and cross-validate each other:

| Approach | Always available? | Description |
|---|---|---|
| **Rule-based scorer** | Yes — no training needed | Weighted formula over 20 behavioral features |
| **K-Means cluster model** | After first weekly training run | Groups customers into 5 natural segments to validate rule-based tiers |

The rule-based score drives all credit decisions. The cluster model is used as a validation signal — if the two approaches disagree, it flags the case for closer review.

---

## How it runs

```
Nightly Celery job (compute_all_credit_scores)
    │
    ▼
For each active customer:
    1. Fetch last 180 days of transactions
    2. Count confirmed fraud alerts + days since last fraud alert
    3. CreditFeatureExtractor.extract() → 20-number feature vector
    4. CreditScorer.score() → credit_score (0–1) + component breakdown
    5. classify_segment() → Tier A/B/C/D/E
    6. compute_max_amount() → max borrowable XAF
    7. Save CustomerCreditProfile to database

Weekly Celery job (retrain_credit_cluster_model)
    │
    ▼
    1. Load all CustomerCreditProfile records
    2. CreditClusterModel.train() → K-Means on 20-feature matrix
    3. Map clusters to tiers by average rule-based score
    4. Save cluster model to disk
```

When a customer submits a credit request, the system re-runs steps 1–6 in real-time (not waiting for the nightly batch) to get a fresh score.

---

## The 20 credit features

These are computed from a customer's transaction history, not from a single transaction. All features look back up to 180 days.

### Deposit patterns

| Feature | What it measures | Creditworthiness signal |
|---|---|---|
| `avg_monthly_deposits` | Average total deposits per month | Raw income capacity — higher = more ability to repay |
| `deposit_consistency` | `1 - coefficient_of_variation` across monthly deposit totals | Regular monthly income (salary, business revenue) scores near 1.0. Erratic or one-time deposits score near 0.0. Consistency predicts future income reliability better than the average alone |

**Deposit consistency formula:**
```
cv = std(monthly_totals) / mean(monthly_totals)
deposit_consistency = max(0.0, 1.0 - cv)
```
A customer who deposits exactly 50,000 XAF every month: `cv = 0`, `consistency = 1.0`.
A customer with wild swings (10K one month, 200K the next): high `cv`, low consistency score.

### Spending patterns

| Feature | What it measures | Creditworthiness signal |
|---|---|---|
| `avg_monthly_withdrawals` | Average total withdrawals per month | Spending level — used to compute net flow |
| `max_single_withdrawal` | Largest single withdrawal in 180 days | Signals the customer's largest known expense — relevant for sizing individual loan amounts |

### Net flow and savings

| Feature | What it measures | Creditworthiness signal |
|---|---|---|
| `net_monthly_flow` | `avg_monthly_deposits - avg_monthly_withdrawals` | Positive = saving money. Negative = spending more than earning. The sigmoid normalization maps this to 0–1 with 50,000 XAF as the midpoint |
| `savings_rate` | `net_monthly_flow / avg_monthly_deposits` (clamped 0–1) | What fraction of income is retained. 0.30 = saves 30 XAF per 100 XAF earned. Higher is better |

### Activity

| Feature | What it measures | Creditworthiness signal |
|---|---|---|
| `transaction_frequency` | Average transactions per month | Actively used accounts are better credit risks. An account with 0 transactions for 6 months provides no behavioral data |
| `account_age_days` | Days since first transaction | Longer history = more predictive data = more confidence in the score. Normalizes to 1.0 at 365 days |
| `max_single_deposit` | Largest single deposit in 180 days | Indicates capacity for large inflows (e.g., business contract payment, salary lump sum) |

### Loan behavior

| Feature | What it measures | Creditworthiness signal |
|---|---|---|
| `loan_repayment_rate` | `total_repaid / total_disbursed` (capped at 1.0) | Prior loan behavior is the **strongest single predictor** of future repayment. 1.0 = has repaid all prior loans. 0.5 = half repaid. 0.0 = has outstanding unpaid loans. Customers with no prior loans default to 1.0 (neutral — not penalized for never borrowing) |

### Risk history

| Feature | What it measures | Creditworthiness signal |
|---|---|---|
| `total_fraud_alerts` | Count of `CONFIRMED_FRAUD` alerts for this customer | Each confirmed fraud event reduces the `fraud_history` component by 0.2. Caps at 5 alerts (score → 0.0) |
| `days_since_last_fraud_alert` | Days since most recent confirmed fraud alert | Recency matters — fraud from 3 years ago should count less than fraud last month. Score recovers toward 1.0 as time passes. No fraud history → 365 days (full credit) |

**Fraud history component formula:**
```
fraud_penalty = max(0.0, 1.0 - total_fraud_alerts × 0.2)
recency_factor = min(days_since_last_fraud / 365.0, 1.0)
fraud_history_score = fraud_penalty × recency_factor
```

### Diversity

| Feature | What it measures | Creditworthiness signal |
|---|---|---|
| `unique_counterparties` | Number of distinct people/accounts transacted with | Broad financial relationships indicate economic integration. A customer who only transacts with 1–2 accounts in 6 months is harder to profile |
| `geographic_stability` | `1 - (unique_countries / total_transactions)` | Frequent country-hopping correlates with both higher credit risk and AML risk. A customer who always transacts in Cameroon scores near 1.0 |

### Trends (recent vs historical)

| Feature | What it measures | Creditworthiness signal |
|---|---|---|
| `deposit_trend` | `(30d average daily deposits) / (90d average daily deposits)` | > 1.0 means income is growing recently — a positive signal. < 1.0 means income is declining |
| `withdrawal_trend` | `(30d average daily withdrawals) / (90d average daily withdrawals)` | < 1.0 means spending is decreasing recently — a positive signal |

### Transfer behavior

| Feature | What it measures | Creditworthiness signal |
|---|---|---|
| `incoming_transfer_ratio` | `incoming_transfer_amount / total_deposit_amount` | High ratio means income arrives primarily via transfers rather than direct deposits. Slightly higher risk — transfer income is less stable than regular deposits |
| `unique_transfer_senders_30d` | Distinct counterparties who sent money to this account in the last 30 days | Diverse income sources reduce concentration risk — if one source stops, total income doesn't collapse |
| `outgoing_transfer_ratio` | `outgoing_transfer_amount / total_withdrawal_amount` | What proportion of spending goes to other accounts (vs cash withdrawal). High ratio means money leaves via traceable transfers — slightly positive |

### Gaming detection

| Feature | What it measures | Creditworthiness signal |
|---|---|---|
| `round_trip_score` | Fraction of inflows that returned to the same counterparty within 48 hours | Detects circular/wash transactions used to artificially inflate apparent deposit volume. Score near 1.0 = nearly all money going in immediately comes back out — strong signal of credit score manipulation |

#### How round-trip detection works

```
For each outgoing transfer/withdrawal to counterparty CP:
    Look back 48h for incoming deposits/transfers FROM CP
    round_trip_amount += min(outgoing_amount, incoming_from_CP_in_48h)

round_trip_score = round_trip_amount / total_inflow
```

**Example:** Customer receives 100,000 XAF from "Alice" on Monday, then sends 100,000 XAF back to "Alice" on Tuesday. `round_trip_score = 1.0`. The deposits look real on paper but serve only to temporarily inflate the account balance before a credit application.

A high `round_trip_score` heavily penalizes the final credit score, neutralizing the inflated deposit figures.

---

## Credit score formula

The 7 components and their weights (configurable via environment variables):

| Component | Feature(s) used | Default weight | Env var |
|---|---|---|---|
| `deposit_consistency` | `deposit_consistency` | 20% | `AML_CREDIT_WEIGHT_DEPOSIT_CONSISTENCY` |
| `net_flow` | `net_monthly_flow` (sigmoid-normalized) | 20% | `AML_CREDIT_WEIGHT_NET_FLOW` |
| `savings_rate` | `savings_rate` | 15% | `AML_CREDIT_WEIGHT_SAVINGS_RATE` |
| `tx_frequency` | `transaction_frequency / 30` | 10% | `AML_CREDIT_WEIGHT_TX_FREQUENCY` |
| `account_age` | `account_age_days / 365` | 10% | `AML_CREDIT_WEIGHT_ACCOUNT_AGE` |
| `repayment_rate` | `loan_repayment_rate` | 15% | `AML_CREDIT_WEIGHT_REPAYMENT_RATE` |
| `fraud_history` | `total_fraud_alerts`, `days_since_last_fraud_alert` | 10% | `AML_CREDIT_WEIGHT_FRAUD_HISTORY` |

```
credit_score = Σ (component_score × weight)   [clamped to 0.0–1.0]
```

The net flow component uses sigmoid normalization to handle both positive and negative values:
```
net_flow_score = 1 / (1 + exp(-net_monthly_flow / 50000))
```
A customer saving 50,000 XAF/month gets a net flow score of 0.73.
A customer spending 50,000 XAF/month more than they earn gets 0.27.

---

## Credit tiers

| Tier | Min Score | Max Loan (XAF) | Auto-recommendation |
|---|---|---|---|
| A — Excellent | ≥ 0.80 | 50,000 | Approve if request ≤ 50% of limit and score ≥ Tier B threshold |
| B — Good | ≥ 0.65 | 20,000 | Review carefully |
| C — Fair | ≥ 0.50 | 10,000 | Review carefully |
| D — Poor | ≥ 0.35 | 1,000 | Review carefully |
| E — Very Poor | < 0.35 | 0 | Reject |

Thresholds are configurable via `AML_CREDIT_TIER_*_MIN_SCORE` and `AML_CREDIT_TIER_*_MAX_AMOUNT`.

### Recommendation logic

```
if tier == E or score < tier_D_threshold:       → REJECT
if requested_amount > max_amount_for_tier:       → REJECT
if requested ≤ 50% of limit and score ≥ tier_B: → APPROVE
else:                                             → REVIEW_CAREFULLY
```

A compliance analyst must review and approve all REVIEW_CAREFULLY recommendations. The system never auto-approves REVIEW_CAREFULLY decisions.

---

## K-Means cluster model (weekly validation)

Every week, a K-Means model is trained on the 20-feature matrix of all CustomerCreditProfile records.

**How cluster→tier mapping works:**
1. Each customer is assigned to one of 5 clusters
2. The average rule-based credit score is computed for each cluster
3. Clusters are ranked by average score: best cluster → Tier A, worst → Tier E

This means the ML segmentation always produces the same 5 tiers as the rule-based scorer, just with boundaries discovered from the data rather than configured by rules.

**When the two methods agree:** High confidence in the tier assignment.
**When they disagree:** The customer's profile is flagged for review — either the rule-based formula weights need adjustment, or the customer has unusual behavioral patterns not well captured by the standard features.

**Cluster quality metric:** Silhouette score. Values above 0.5 indicate well-separated clusters. Below 0.3 indicates the 5-cluster structure doesn't fit the data well, which may prompt feature or weight review.

---

## How credit scoring and fraud detection interact

The two systems share data in both directions:

### Fraud → Credit

- `total_fraud_alerts` and `days_since_last_fraud_alert` are direct inputs to the credit score formula
- A customer with 3 confirmed fraud alerts loses 60% of their `fraud_history` component (0.6 penalty)
- That penalty never expires fully — it decays over 365 days but the alert count remains

### Credit → Fraud (round_trip_score)

- The `round_trip_score` feature detects attempts to inflate deposits artificially before a credit application
- A high round-trip score signals wash transactions, which are themselves a form of financial fraud
- A customer who successfully games the deposit features is penalized heavily enough that the inflated `avg_monthly_deposits` no longer helps their score

### Gaming attempt example

```
Customer circular-washes 500,000 XAF:
    Deposits: 500K (from accomplice)
    Withdrawals: 500K (back to accomplice) 24h later

Without round_trip detection:
    avg_monthly_deposits = high  → net_flow looks great → Tier A

With round_trip detection:
    round_trip_score ≈ 1.0
    round_trip_score is fed to CreditScorer as a penalty signal
    The inflated deposits are neutralized → actual tier reflects real behavior
```

Additionally, the circular transfer pattern (`deposit→withdrawal` to the same counterparty within 48h) also triggers the fraud rule engine `circular_transfer` rule, potentially generating a fraud alert that further penalizes the credit score via the `fraud_history` component.

---

## Credit request workflow

```
Customer → POST /api/v1/credit/request
                │
                ▼
         Real-time re-scoring
         (does not wait for nightly batch)
                │
                ▼
         Auto-recommendation generated
         (approve / review_carefully / reject)
                │
         ┌──────┴──────┐
         │             │
      REJECT         APPROVE or
    (returned         REVIEW_CAREFULLY
    immediately)           │
                           ▼
                    Compliance analyst
                    reviews in dashboard
                           │
                    Final APPROVE / REJECT
                    decision recorded
```

All credit decisions are logged to the audit trail with the score, component breakdown, tier, and analyst decision. This audit trail is required for COBAC compliance.

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `AML_CREDIT_TIER_A_MIN_SCORE` | 0.80 | Minimum score for Tier A |
| `AML_CREDIT_TIER_B_MIN_SCORE` | 0.65 | Minimum score for Tier B |
| `AML_CREDIT_TIER_C_MIN_SCORE` | 0.50 | Minimum score for Tier C |
| `AML_CREDIT_TIER_D_MIN_SCORE` | 0.35 | Minimum score for Tier D |
| `AML_CREDIT_TIER_A_MAX_AMOUNT` | 50,000 XAF | Max loan for Tier A |
| `AML_CREDIT_TIER_B_MAX_AMOUNT` | 20,000 XAF | Max loan for Tier B |
| `AML_CREDIT_TIER_C_MAX_AMOUNT` | 10,000 XAF | Max loan for Tier C |
| `AML_CREDIT_TIER_D_MAX_AMOUNT` | 1,000 XAF | Max loan for Tier D |
| `AML_CREDIT_MIN_TRANSACTIONS` | 5 | Minimum transactions before scoring (below this → Tier E) |
| `AML_CREDIT_GAMING_INFLOW_MULTIPLIER` | 3.0 | Flag if inflow in 30d is 3× the 180d monthly average |
| `AML_CREDIT_GAMING_SCORE_PENALTY` | 0.15 | Score penalty applied when gaming pattern detected |

---

## Related documentation

- [Fraud Detection Guide](fraud-detection.md) — fraud detection layers and rules
- [ML Pipeline Guide](../ml/pipeline.md) — XGBoost and Isolation Forest training details
- [Credit Scoring API Reference](../../backend/docs/credit-scoring-api.md) — REST endpoints
- [Credit Scoring Operations](../../backend/docs/credit-scoring-operations.md) — configuration and monitoring
