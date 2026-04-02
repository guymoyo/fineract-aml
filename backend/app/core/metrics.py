"""Prometheus metrics for the AML service.

Instruments key pipeline events so the ops team can monitor throughput,
alert rates, scoring latency, and model drift from a single dashboard.
"""

from prometheus_client import Counter, Gauge, Histogram

# ── Transaction pipeline ───────────────────────────────────────────────────────

transactions_analyzed = Counter(
    "aml_transactions_analyzed_total",
    "Total transactions analyzed by the AML pipeline",
    ["risk_level", "actor_type"],
)

# ── Rule engine ────────────────────────────────────────────────────────────────

rules_triggered = Counter(
    "aml_rules_triggered_total",
    "Number of times each rule fired",
    ["rule_name"],
)

# ── Alerts ─────────────────────────────────────────────────────────────────────

alerts_created = Counter(
    "aml_alerts_created_total",
    "Alerts created by source and risk level",
    ["source", "risk_level"],
)

# ── Scoring latency ────────────────────────────────────────────────────────────

scoring_latency = Histogram(
    "aml_scoring_latency_seconds",
    "End-to-end scoring latency (rule engine + ML)",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

# ── Loan monitoring ────────────────────────────────────────────────────────────

loan_watch_active = Gauge(
    "aml_loan_watch_active_count",
    "Number of active post-disbursement loan watches",
)

# ── Model drift ────────────────────────────────────────────────────────────────

model_drift_psi = Gauge(
    "aml_model_drift_psi",
    "Population Stability Index (PSI) per feature — higher means more drift",
    ["feature_name"],
)

# ── Data quality ───────────────────────────────────────────────────────────────

data_quality_rejections = Counter(
    "aml_data_quality_rejections_total",
    "Webhook payloads rejected by data quality validation",
    ["reason"],
)

data_quality_warnings = Counter(
    "aml_data_quality_warnings_total",
    "Webhook payloads that passed with warnings",
    ["warning_type"],
)

# ── LLM investigations ─────────────────────────────────────────────────────────

llm_investigations = Counter(
    "aml_llm_investigations_total",
    "LLM alert investigations completed",
    ["recommendation"],
)

llm_investigation_latency = Histogram(
    "aml_llm_investigation_latency_seconds",
    "Time to complete LLM alert investigation",
    buckets=[1, 5, 10, 20, 30, 60, 120],
)
