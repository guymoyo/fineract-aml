# Fraud Detection Guide

This guide explains every fraud-detection mechanism in the system — how each works, what typology it catches, and why it matters for AML compliance in a WeBank mobile-money context.

---

## Detection Architecture

Every transaction passes through three layers in sequence. All layers run on every transaction; their scores are combined into a single final risk score.

```
Transaction arrives via webhook
          │
          ▼
┌─────────────────────────────┐   always on, instant
│  Layer 1 — Rule Engine       │   19 deterministic checks
│  (app/rules/engine.py)       │   severity score → 0.0–1.0
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐   always on, no labels needed
│  Layer 2 — Anomaly Detector  │   Isolation Forest [+ One-Class SVM]
│  (app/ml/anomaly_detector.py)│   anomaly score → 0.0–1.0
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐   active once ≥200 confirmed fraud cases exist
│  Layer 3 — Fraud Classifier  │   XGBoost supervised model
│  (app/ml/fraud_classifier.py)│   fraud probability → 0.0–1.0
└──────────────┬──────────────┘
               │
               ▼
         Score combination
   With ML:    final = 0.5×ML + 0.3×anomaly + 0.2×rules
   Without ML: final = 0.5×anomaly + 0.5×rules
   No models:  final = rules only
               │
    final ≥ 0.5 → Alert created
    final ≥ 0.8 → HIGH risk
    final = 1.0 → CRITICAL risk
```

### Score combination rationale

The ML model gets the highest weight (0.5) because it has learned from real analyst-labeled fraud. The anomaly detector gets the second-highest weight (0.3) because it catches novel patterns the rules haven't seen. Rules (0.2) provide a hard floor — a transaction that triggers multiple rules is never ignored even if ML scores it low.

---

## Layer 1 — Rule Engine (19 rules)

Rules are deterministic, always running, and require no training data. They encode regulatory thresholds and known AML typologies directly.

The combined rule score uses a weighted-average with a multi-rule bonus:

```
combined = mean(triggered_severities) + min(triggered_count × 0.05, 0.20)
```

A transaction triggering 4 rules at 0.7 severity each scores `0.7 + 0.20 = 0.90`.

---

### General rules (applied to all transactions)

| Rule | Env var threshold | Severity | What it detects |
|---|---|---|---|
| `large_amount` | `AML_MAX_TRANSACTION_AMOUNT` (10,000 XAF) | 0.5–1.0 | Transactions at or above the CTR reporting threshold. Required by COBAC for Currency Transaction Report auto-filing |
| `structuring` | `AML_STRUCTURING_THRESHOLD` (9,500 XAF) | 0.7 | Amounts in the 9,500–10,000 XAF band. Criminals deliberately stay just below the reporting threshold to avoid CTR filing — this is the definition of structuring |
| `rapid_transactions` | `AML_RAPID_TRANSACTION_COUNT` (10 in 60 min) | 0.5–1.0 | More than 10 transactions from the same account within 60 minutes. Signals automated fraud, compromised account, or coordinated cash-out |
| `high_velocity_volume` | `AML_MAX_TRANSACTION_AMOUNT × 3` | 0.5–1.0 | Cumulative volume > 30,000 XAF in 60 minutes. Catches high-speed fund sweeping that individual-amount structuring misses |
| `round_number` | Fixed (≥1,000, multiple of 1,000) | 0.3 | Exact multiples of 1,000 XAF. Real-world transactions have odd amounts (merchant totals, fees, etc.). Perfectly round numbers suggest manufactured transactions |
| `unusual_hours` | Fixed (2–5 AM) | 0.4 | Transactions between 2:00–5:00 AM local time. Mobile money fraud spikes at night when victims are asleep and cannot respond to OTP prompts |
| `new_ip_address` | None | 0.5 | Transaction from an IP address never seen before for this account. Primary signal for account takeover — fraudster logs in from a new device |

---

### Transfer-specific rules

These rules only fire when `transaction_type == "transfer"`.

| Rule | Severity | What it detects |
|---|---|---|
| `circular_transfer` | 0.7 | Account A transfers to Account B, and Account B has previously transferred back to Account A within 24h. Classic two-party layering loop — money bouncing between accomplice accounts to manufacture a transaction history |
| `new_counterparty_transfer` | 0.4 | First-ever transfer to an account not seen in the last 24h history. Signals sudden transfer to a mule account. Lower severity because first-time transfers are common for legitimate users too — escalated only with other signals |
| `rapid_pair_transfers` | 0.5–1.0 | 3 or more transfers between the same pair of accounts within 24 hours. Normal users don't need to send money to the same person multiple times in a day; repeated micro-transfers indicate siphoning or layering |

---

### Agent-specific rules

These rules fire only when `actor_type == "agent"`. WeBank agents are licensed field operators who handle cash-in and cash-out for customers. Their transaction patterns are fundamentally different from customer wallets.

#### How agent fraud differs from customer fraud

A customer committing fraud acts alone — they have one wallet. A corrupt agent has access to multiple customers' wallets and can orchestrate fraud at scale. These rules detect that scale.

| Rule | Threshold | Severity | What it detects |
|---|---|---|---|
| `agent_structuring` | `AML_AGENT_STRUCTURING_MIN_COUNT` (5 deposits in 1h) | 0.6–1.0 | Agent processes 5 or more customer deposits all in the 9,500–10,000 XAF structuring range within 1 hour. Unlike the general structuring rule (single account), here we look at **all deposits the agent processed** — a hallmark of smurfing where an agent orchestrates multiple clients to each deposit sub-threshold amounts to avoid CTR filing |
| `agent_float_anomaly` | `AML_AGENT_FLOAT_IMBALANCE_THRESHOLD` (95%) | 0.6 | Agent's deposits or withdrawals exceed 95% of their total daily volume. Legitimate agents have a balanced float — they collect cash from some customers and disburse to others. An agent who only collects (pure deposit-heavy) is acting as a placement vehicle for dirty cash. An agent who only disburses (pure withdrawal-heavy) is draining float abnormally |
| `agent_account_farming` | `AML_AGENT_NEW_ACCOUNT_THRESHOLD` (8 new accounts in 24h) | 0.5–0.9 | Agent serves 8 or more brand-new KYC Level 1 accounts in a single day. Legitimate agents onboard 1–2 new customers per day during normal operations. Mass onboarding of new accounts through a single agent is a strong indicator of synthetic identity fraud — registering fake wallets to layer illicit funds |
| `agent_customer_collusion` | `AML_AGENT_COLLUSION_WINDOW_MINUTES` (60 min) | 0.8 | Customer deposits with Agent A, then withdraws the same funds via a **different** Agent B within 60 minutes. This two-agent pattern is used to move cash while obscuring the source — Agent A's branch records show an inflow, Agent B's records show an outflow, and neither alone looks suspicious |

---

### Merchant-specific rules

These rules fire only when `actor_type == "merchant"`. WeBank merchants accept QR payments for goods and services.

| Rule | Threshold | Severity | What it detects |
|---|---|---|---|
| `merchant_collection_account` | Volume > 5× max transaction amount with zero outgoing transfers in 7 days | 0.7 | Merchant receives large inflows from many payers but makes no outgoing transfers or withdrawals over 7 days. Legitimate merchants pay suppliers, make withdrawals, and settle accounts. A merchant account that only receives payments and never spends is being used as a collection bucket — gathering funds from multiple sources to later move in bulk |
| `high_value_anonymous_payment` | `AML_ANONYMOUS_PAYMENT_ALERT_THRESHOLD` (100,000 XAF) | 0.5 | Anonymous payment of 100,000 XAF or more to a merchant. WeBank allows customers to opt into payment anonymity (no counterparty name or account ID sent). This is legitimate for small purchases, but large anonymous payments can mask illicit fund flows into the merchant ecosystem |

---

### Network typology rules

These rules require 7-day transaction history. They are based on patterns documented in IBM AMLSim research and are specific to money laundering networks (not single-account fraud).

#### `scatter_gather` — N→1 collection

**Pattern:** An account receives funds from many unique senders over 7 days (scatter phase), then makes a single large outbound transfer (gather phase).

**How it works in practice:** Criminal A recruits 10 "mules" who each send small amounts to a collector account. Once enough accumulates, the collector sweeps it all out in one transfer to a layering account.

| Parameter | Default |
|---|---|
| `AML_SCATTER_GATHER_MIN_SENDERS` | 8 unique deposit sources in 7 days |
| Severity | 0.6 + 0.03 per sender above threshold (max 1.0) |

---

#### `bipartite_layering` — many-in, many-out

**Pattern:** The same account shows both fan-in (many unique deposit sources) AND fan-out (many unique transfer recipients) in a 7-day window.

**How it works in practice:** This is the layering sandwich. Money collected from many dirty sources passes through a single intermediary account that then distributes it to many clean-looking destinations. Both collection and distribution happening on the same account simultaneously is a very strong signal — the account is acting as a laundering node.

| Parameter | Default |
|---|---|
| `AML_BIPARTITE_FAN_THRESHOLD` | 5 unique sources AND 5 unique recipients |
| Severity | 0.9 (highest of all network rules) |

---

#### `stacking` — proportional chain hops

**Pattern:** 3 or more sequential transfers within a short time window where each transfer's amount is 80–120% of the previous one.

**How it works in practice:** A→B→C→D where each leg moves roughly the same amount within 30 minutes. Used to create an artificial transaction trail across multiple hops to obscure the original source. The proportional amounts make each individual transfer look like a normal follow-on payment.

| Parameter | Default |
|---|---|
| `AML_STACKING_WINDOW_MINUTES` | 30 minutes |
| `AML_STACKING_AMOUNT_RATIO_MIN` | 0.80 (each hop ≥ 80% of prior) |
| `AML_STACKING_AMOUNT_RATIO_MAX` | 1.20 (each hop ≤ 120% of prior) |
| Severity | 0.8 (chain length ≥ 3) |

---

## Layer 2 — Anomaly Detector

The anomaly detector catches fraud patterns the rules don't know about yet. It learns what "normal" looks like from historical transactions and flags deviations.

### Default: Isolation Forest

**How it works:** Random decision trees partition the feature space. Anomalous transactions — rare, unusual, different — can be isolated in fewer splits than normal ones. Score = how quickly the transaction gets isolated.

**Why this works for fraud:** Fraudulent transactions are statistically unusual (wrong time, wrong amount profile, wrong counterparty pattern). They don't require labels to detect.

**Training:** Daily on the last 10,000 transactions. Assumes ~1% contamination (configurable via `AML_ANOMALY_CONTAMINATION`).

### Optional ensemble: + One-Class SVM

When `AML_ANOMALY_ENSEMBLE_ENABLED=true`, a second model (One-Class SVM with RBF kernel) is trained alongside Isolation Forest. The two scores are blended:

```
anomaly_score = 0.6 × IsolationForest + 0.4 × OneClassSVM
```

The SVM catches anomalies in **dense regions** of feature space where tree-based methods are less sensitive — different mathematical assumptions catch different fraud patterns.

### Score interpretation

Both models output a score where `0.0 = perfectly normal` and `1.0 = highly anomalous`. The sigmoid transformation maps the raw decision function to this range.

---

## Layer 3 — Fraud Classifier (XGBoost)

A supervised gradient-boosted tree model trained directly on analyst-labeled data.

### Activation condition

The classifier only becomes active once:
- ≥ 200 confirmed fraud cases exist in the `alerts` table (status = `CONFIRMED_FRAUD`)
- ≥ 1,000 total labeled records (fraud + legitimate combined)

Until then, the system runs on layers 1 and 2 only. The **IBM AML import adapter** (`app/scripts/import_ibm_aml_data.py`) can pre-load labeled IBM dataset records to satisfy this threshold during setup.

### Validation gate

After training, the new model is only deployed to production if:
- 5-fold cross-validation AUC ≥ 0.80
- Cross-validation AUC standard deviation ≤ 0.05 (stable across folds)

If the new model fails these gates, the previous production model is kept.

### Class imbalance handling

Fraud is rare. The model automatically compensates:

```
scale_pos_weight = n_legitimate / n_fraud
```

If the training set has 1,000 legitimate and 200 fraud examples, `scale_pos_weight = 5.0`, making the model 5× more sensitive to fraud misclassification.

### Shadow deployment

After each successful training:
1. The new model is written to production (atomic file rename)
2. A copy is also written to the shadow slot
3. The shadow model scores every transaction **in parallel** but its scores are only logged — never used for decisions
4. After `AML_SHADOW_MODEL_PROMOTION_DAYS` days (default: 7), if the shadow model's AUC exceeds production by `AML_SHADOW_MODEL_PROMOTION_AUC_DELTA` (default: 0.02), it is promoted to production automatically

---

## The 36-feature vector

Both the anomaly detector and fraud classifier use the same 36-number representation of each transaction. See [ML Pipeline Guide](../ml/pipeline.md) for the full indexed table.

### Feature groups summary

| Group | Count | Key signals |
|---|---|---|
| Transaction-level | 11 | Amount magnitude, transaction type, time-of-day, round-number flags |
| 24h account window | 11 | Velocity (count, volume), amount deviation vs average, IP novelty, counterparty breadth |
| 7-day window | 10 | Medium-term behavioral baseline, velocity trend (acceleration), geographic displacement, receiver diversity |
| Actor context | 4 | Agent/merchant flags, KYC level, new-account flag |

---

## Supporting systems

### Sanctions screening

Every counterparty name is fuzzy-matched against four watchlists using token-sort ratio similarity:

| Watchlist | Source | Refresh |
|---|---|---|
| OFAC SDN | US Treasury Specially Designated Nationals | Every 6 hours |
| EU Sanctions | European Union Consolidated List | Every 6 hours |
| UN Sanctions | UN Security Council List | Every 6 hours |
| PEP | Politically Exposed Persons | Every 6 hours |

Match threshold: 85% similarity (configurable via `AML_SANCTIONS_MATCH_THRESHOLD`). A potential match triggers a mandatory manual review alert regardless of the transaction's risk score.

### Adverse media screening

When `AML_ADVERSE_MEDIA_ENABLED=true` and the transaction's risk score is ≥ `AML_ADVERSE_MEDIA_MIN_RISK_SCORE` (default 0.6), the counterparty name is searched via NewsAPI for negative keyword matches (fraud, money laundering, corruption, sanctions, etc.).

Results — article snippets, relevance scores, matched keywords — are stored in `adverse_media_results` and attached to the alert for investigator context. This provides additional evidence for SAR filing without requiring manual news research.

### LLM investigation agent

When `AML_LLM_INVESTIGATION_ENABLED=true` and an alert reaches HIGH or CRITICAL risk level, Claude (model: `AML_LLM_MODEL`) is invoked to produce a structured investigation report:

- Typology identification (which AML pattern best fits the transaction profile)
- Risk factor narrative (plain-language explanation of why this is suspicious)
- SAR filing recommendation with suggested narrative in French (COBAC requirement)
- Similar historical cases from the case database

The report is attached to the alert and visible in the compliance dashboard.

### Post-disbursement loan monitoring

When a `LOAN_DISBURSEMENT` transaction is processed, the system creates a `LoanDisbursementWatch` record and monitors for four fraud patterns over the following 30 days:

| Pattern | Trigger | Signal |
|---|---|---|
| `loan_and_run` | 80%+ of loan withdrawn within 30 days | Borrower never intended to repay — extracted proceeds and defaulted |
| `immediate_cash_out` | Any withdrawal within 30 minutes of disbursement | Automatic extraction of loan funds — often indicates a mule account set up specifically to receive and drain loans |
| `post_disbursement_structuring` | Multiple sub-threshold withdrawals after disbursement | Breaking loan proceeds into smaller amounts to avoid detection, same as general structuring but in the context of loan fraud |
| `cross_agent_dispersal` | Funds sent to 5+ different counterparties via different agents | Loan proceeds are immediately scattered across the agent network — a classic money mule distribution pattern |

### Escalation engine

The escalation engine runs hourly and handles two scenarios:

1. **Stale cases**: Investigation cases open for more than 30 days without resolution are automatically escalated to senior compliance officers
2. **Unassigned alerts**: High-severity alerts with no assigned reviewer after 24 hours are re-queued and flagged

### CTR auto-filing

Transactions above `AML_CTR_THRESHOLD` (default: 5,000,000 XAF) automatically trigger a Currency Transaction Report in the COBAC-required format. CTRs are generated, stored, and can be exported for regulatory submission.

---

## Configuration reference

All fraud detection parameters are configured via environment variables with the `AML_` prefix. See `.env.example` for the full list with defaults.

| Section | Key variables |
|---|---|
| Thresholds | `AML_MAX_TRANSACTION_AMOUNT`, `AML_STRUCTURING_THRESHOLD`, `AML_CTR_THRESHOLD` |
| Velocity | `AML_RAPID_TRANSACTION_WINDOW_MINUTES`, `AML_RAPID_TRANSACTION_COUNT` |
| Agent fraud | `AML_AGENT_STRUCTURING_MIN_COUNT`, `AML_AGENT_FLOAT_IMBALANCE_THRESHOLD`, `AML_AGENT_NEW_ACCOUNT_THRESHOLD`, `AML_AGENT_COLLUSION_WINDOW_MINUTES` |
| Merchant fraud | `AML_ANONYMOUS_PAYMENT_ALERT_THRESHOLD` |
| Network typology | `AML_SCATTER_GATHER_MIN_SENDERS`, `AML_BIPARTITE_FAN_THRESHOLD`, `AML_STACKING_WINDOW_MINUTES` |
| ML models | `AML_ANOMALY_THRESHOLD`, `AML_ANOMALY_CONTAMINATION`, `AML_ANOMALY_ENSEMBLE_ENABLED` |
| Shadow deployment | `AML_SHADOW_MODEL_ENABLED`, `AML_SHADOW_MODEL_PROMOTION_DAYS`, `AML_SHADOW_MODEL_PROMOTION_AUC_DELTA` |
| Risk levels | `AML_RISK_SCORE_HIGH` (0.8), `AML_RISK_SCORE_MEDIUM` (0.5) |

---

## Related documentation

- [ML Pipeline Guide](../ml/pipeline.md) — full 36-feature table, XGBoost training configuration, model drift monitoring
- [Regulatory Compliance Guide](regulatory-compliance.md) — COBAC SAR workflow, CTR filing, sanctions screening operations
- [Agent Network Monitoring Guide](agent-network-monitoring.md) — detailed agent fraud patterns and investigation workflow
- [Loan Monitoring Guide](loan-monitoring.md) — post-disbursement monitoring lifecycle and thresholds
- [LLM Investigation Agent](llm-agents.md) — configuring and interpreting AI-generated investigation reports
