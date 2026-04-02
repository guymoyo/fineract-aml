# LLM Agents Guide (Claude API Integration)

This guide explains the three LLM-powered automation features in the WeBank AML system, all of which use the Anthropic Claude API.

## 1. Alert Investigation Agent

### Trigger

The investigation agent is automatically invoked for every alert with a risk level of HIGH or CRITICAL when `AML_LLM_INVESTIGATION_ENABLED=true`. The minimum risk level threshold is configurable via `AML_LLM_INVESTIGATION_MIN_RISK_LEVEL`. The agent can also be triggered manually by a compliance analyst from the alert detail view.

### Model

`claude-opus-4-6` with agentic tool use (multi-turn tool calling, up to 10 tool-use rounds per investigation).

### Available Tools

| Tool | Data Returned |
|------|--------------|
| `get_transaction_history` | Last 30 days of transactions for the account |
| `get_customer_profile` | KYC data, risk level, nationality, PEP/sanctions flags |
| `get_related_alerts` | Other open or recent alerts for the same account |
| `get_agent_profile` | Agent behavioral baseline (if `actor_type == "agent"`) |
| `get_credit_profile` | Credit score, tier, active loans (if available) |

### Output: InvestigationReport

The agent produces a structured `InvestigationReport` object, stored in `alert.investigation_report` as JSON:

| Field | Description |
|-------|-------------|
| `summary` | 2–3 sentence plain-language description of why this alert was raised |
| `typology_match` | The closest FATF money laundering typology (e.g., "structuring", "layering", "loan fraud") |
| `risk_factors` | List of factors that increase suspicion |
| `mitigating_factors` | List of factors that argue against fraud (context for dismissal decisions) |
| `recommendation` | One of: `"dismiss"`, `"monitor"`, `"escalate"`, `"file_sar"` |
| `recommended_actions` | Ordered list of next steps for the reviewing analyst |
| `narrative_fr` | Full SAR-ready narrative in French, formatted for COBAC submission |

### Usage Notes

- The investigation runs asynchronously via Celery and is typically available within 30–90 seconds of alert creation.
- If the agent cannot reach a confident conclusion (e.g., insufficient transaction history), it will set `recommendation = "monitor"` and explain the data gap in `summary`.
- Analysts should treat the report as a starting point, not a final decision. The `recommended_actions` list is designed to guide the analyst toward the information needed to make a final call.

---

## 2. SAR Narrative Drafter

### Trigger

When a case is exported via `GET /api/v1/cases/{id}/sar/xml` or `GET /api/v1/cases/{id}/sar/pdf`, the system first checks whether any linked alert already has a `narrative_fr` in its `investigation_report`.

- **If a narrative exists**: It is used directly in the SAR document.
- **If no narrative exists**: Claude is called directly with the case details and all linked transaction data to draft the narrative in French.

### Output

A COBAC-compliant French SAR narrative covering:
- Subject identification (name, account, nationality)
- Transaction pattern description (dates, amounts, counterparties)
- Typology classification
- Basis for suspicion
- Recommended regulatory action

The narrative is embedded in both the XML and PDF export formats.

---

## 3. Credit Decision Explainer

### Trigger

For each new `CreditRequest`, when `AML_LLM_INVESTIGATION_ENABLED=true`, Claude generates a dual-audience explanation before the request is surfaced to analysts.

### Output

Stored in `CreditRequest.explanation_text` as JSON with two keys:

**`customer_fr`** — Customer-facing explanation in French:
- Plain-language description of the score outcome
- Primary factors that helped or hurt the score
- Concrete, actionable improvement tips
- Tone is constructive and appropriate for direct customer communication

**`compliance_en`** — Compliance-facing technical explanation in English:
- Weighted factor breakdown
- `score_inflation_flag` status and the inflation ratio if flagged
- Any recommendation overrides applied
- Rationale summary for the review file

---

## 4. Configuration

All LLM configuration variables use the `AML_` prefix:

```env
AML_ANTHROPIC_API_KEY=sk-ant-...
AML_LLM_INVESTIGATION_ENABLED=true
AML_LLM_MODEL=claude-opus-4-6
AML_LLM_INVESTIGATION_MIN_RISK_LEVEL=HIGH
```

| Variable | Description |
|----------|-------------|
| `AML_ANTHROPIC_API_KEY` | Anthropic API key (required for all LLM features) |
| `AML_LLM_INVESTIGATION_ENABLED` | Master switch — set to `false` to disable all LLM calls |
| `AML_LLM_MODEL` | Model ID to use (default: `claude-opus-4-6`) |
| `AML_LLM_INVESTIGATION_MIN_RISK_LEVEL` | Minimum alert risk level to trigger auto-investigation (`HIGH` or `CRITICAL`). Set to `CRITICAL` to further reduce API costs. |

---

## 5. Privacy Considerations

The following data is sent to the Claude API during alert investigations:

- Transaction amounts, dates, types, and counterparty names
- Customer full name, nationality, and risk level
- Alert risk scores and triggered rule names
- Agent behavioral baseline metrics (for agent alerts)

The following data is **never** sent to the Claude API:

- Raw account credentials or passwords
- Full account numbers (only masked or internal IDs are used)
- Device identifiers or raw IP addresses

Before enabling LLM features in production, verify that your organization's data processing agreement and privacy policy cover the use of third-party AI APIs for processing personal financial data. In the CEMAC zone, this requires compliance with CEMAC Regulation No. 01/03/CEMAC/UMAC/COBAC on data protection for financial institutions.

---

## 6. Cost Management

Each alert investigation makes **1 API session** with up to **10 tool-use rounds** (agentic loop).

| Scenario | Estimated Cost |
|----------|---------------|
| Simple alert (few tools needed) | ~$0.05 USD |
| Complex alert (full tool use, long history) | ~$0.20 USD |

**Cost control recommendations:**

1. **Gate by risk level**: Keep `AML_LLM_INVESTIGATION_MIN_RISK_LEVEL=HIGH` (the default). This prevents investigation of MEDIUM and LOW alerts that rarely require SAR filing.
2. **Monitor via Prometheus**: The `aml_llm_api_calls_total` and `aml_llm_api_cost_usd_total` metrics are exposed at `/metrics`.
3. **Review monthly**: Check the Prometheus dashboard for cost trends. If costs spike, check whether the minimum risk level filter is still correctly configured or whether a rule change has produced more HIGH-level alerts.
4. **Disable for batch testing**: Set `AML_LLM_INVESTIGATION_ENABLED=false` when running load tests or replaying historical data to avoid unnecessary API charges.
