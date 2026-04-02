# Agent Network Monitoring Guide

This guide explains how the WeBank AML system monitors agent operators and detects agent-specific fraud typologies.

## 1. WeBank Agent Model

Agents are licensed operators who perform cash-in and cash-out transactions on behalf of customers. Unlike customers, agents legitimately handle 50–200+ transactions per day as part of their normal business operations.

This high transaction volume means standard customer velocity thresholds would produce an unacceptable false-positive rate for agents. Instead, the system computes **per-agent behavioral baselines** using a 30-day rolling window. These baselines are stored in the `agent_profiles` table and updated nightly by the Celery task `update_agent_profiles`.

Agent rules only fire when `actor_type == "agent"` is present in the webhook payload. The BFF must populate this field from Keycloak token claims before forwarding events.

---

## 2. Agent Behavioral Profile

Each agent has a profile in the `agent_profiles` table with the following fields:

| Field | Description |
|-------|-------------|
| `avg_daily_tx_count_30d` | Average number of transactions per day over 30 days |
| `avg_daily_volume_30d` | Average daily transaction volume (XAF) over 30 days |
| `std_daily_volume_30d` | Standard deviation of daily volume — used to detect anomalous volume spikes |
| `typical_float_ratio` | Normal ratio of deposits to withdrawals over 30 days |
| `served_customer_count_30d` | Number of distinct customers served in 30 days |
| `p95_tx_amount_30d` | 95th percentile transaction amount — used to detect outlier amounts |

The nightly `update_agent_profiles` Celery task recomputes all fields for active agents and stores the updated profile.

---

## 3. Agent-Specific Rules

All rules in this section are gated on `actor_type == "agent"`. They will not fire for customer or merchant actors.

| Rule | Trigger | Severity |
|------|---------|----------|
| `agent_structuring` | ≥5 deposits just below the 5M XAF CTR threshold from the same agent within 1 hour | **0.85** |
| `agent_customer_collusion` | Agent A deposits for Customer X; Customer X withdraws via a different agent within 60 minutes | **0.80** |
| `agent_float_anomaly` | Float ratio >0.95 or <0.05 over a 24-hour period (all cash-in or all cash-out), compared against the agent's `typical_float_ratio` | **0.60** |
| `agent_account_farming` | >8 deposits for brand-new accounts (KYC level 1, account age <7 days) within 24 hours | **0.75** |

### Rule Details

**agent_structuring**: Structuring by agent is distinct from customer structuring — the agent is the instrument used to split deposits, not the account holder. The 1-hour window and 5-transaction minimum are calibrated to reduce false positives for agents handling legitimate high-frequency transactions.

**agent_customer_collusion**: This pattern suggests a coordinated split between an agent and a known customer to move funds without triggering a single-agent CTR. The 60-minute window is configurable.

**agent_float_anomaly**: Legitimate agents maintain a roughly balanced float (cash in ≈ cash out). A 24-hour period of exclusively one-directional flow is a strong signal of either agent compromise or use of the agent as a layering conduit. The comparison is made against the agent's own `typical_float_ratio`, not a system-wide threshold.

**agent_account_farming**: Depositing into many newly created, low-KYC accounts is associated with mule account seeding operations. The "brand new" condition (KYC level 1 + account <7 days) is required to distinguish this from legitimate onboarding activity.

---

## 4. False Positive Suppression

Agent rules require `actor_type == "agent"` in the webhook payload. Without this field:

- Agent-specific rules do not evaluate.
- The transaction is scored against standard customer thresholds.

**Responsibility**: The BFF must extract `actor_type` from the authenticated Keycloak JWT token claims and include it in every webhook payload. Failure to do so will cause agent transactions to be evaluated as customer transactions, potentially generating false positives for high-volume agents and missing agent-specific fraud patterns.

Additionally, the `agent_float_anomaly` rule uses the per-agent `typical_float_ratio` from `agent_profiles`, so new agents (fewer than 30 days of history) will have insufficient baseline data. For agents with no profile, this rule is suppressed to avoid false positives.

---

## 5. Network Typology Rules (AMLSim-Inspired)

These rules apply at the network level and are not gated by `actor_type`. They detect structural patterns in the transaction graph consistent with IBM AMLSim typologies.

| Rule | Trigger | Severity |
|------|---------|----------|
| `scatter_gather` | ≥8 unique senders to a single account + a single large outbound transfer within a 7-day window | **0.85** |
| `bipartite_layering` | ≥5 unique senders AND ≥5 unique recipients through a single intermediary account within 7 days | **0.90** |
| `stacking` | ≥3 sequential transfers within 30 minutes where each amount is 80–120% of the prior transfer amount | **0.80** |

### Rule Details

**scatter_gather**: Classic "smurfing into a collection account" pattern. Many small incoming flows aggregate before exiting. The 8-sender minimum and 7-day window balance sensitivity and specificity for the WeBank transaction volume profile.

**bipartite_layering**: The account acts as a pure intermediary — receiving from a diverse source set and distributing to a diverse destination set. This is the hallmark of a layering node in a money laundering network. Severity is set highest (0.90) among network rules because legitimate intermediary patterns (e.g., payroll distribution) typically have predictable recipient sets.

**stacking**: Rapid proportional forwarding mimics the "stacking" typology in AMLSim. The 80–120% amount tolerance accounts for small fees taken at each hop. The 30-minute window ensures this only captures clearly structured rapid chains, not coincidental sequential transfers.
