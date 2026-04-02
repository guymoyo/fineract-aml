# Regulatory Compliance Guide

This guide explains how the Fineract AML system meets regulatory requirements for Anti-Money Laundering compliance in the CEMAC/COBAC zone (XAF currency) and internationally.

## 1. Sanctions & PEP Screening

### How It Works

Every transfer transaction with a counterparty name is automatically screened against global sanctions and PEP (Politically Exposed Persons) watchlists.

```
Transfer arrives → counterparty_name extracted
    → SanctionsScreeningService.screen_transaction()
    → Fuzzy match against all active watchlist_entries
    → similarity ≥ 0.85 → POTENTIAL_MATCH (alert + manual review required)
    → similarity < 0.85 → CLEAR
```

### Watchlist Sources

| Source | Description | Download URL | Format |
|--------|-------------|-------------|--------|
| **OFAC SDN** | US Treasury Specially Designated Nationals | `sanctionslistservice.ofac.treas.gov/.../SDN.XML` | XML |
| **EU Sanctions** | European Union Consolidated List | `webgate.ec.europa.eu/.../xmlFullSanctionsList` | XML |
| **UN Sanctions** | UN Security Council Consolidated List | `scsanctions.un.org/.../consolidated.xml` | XML |
| **PEP** | Politically Exposed Persons | Custom/manual upload | JSON |

### Download Frequency

Watchlists are automatically refreshed **every 6 hours** via the Celery Beat task `sync_all_watchlists`. This exceeds the industry standard of daily refresh.

OFAC can update the SDN list multiple times per day without prior notice (e.g., after new designations, Executive Orders, or de-listings). The 6-hour cadence ensures we catch same-day updates.

To trigger a manual refresh:
```bash
celery -A app.tasks.celery_app call app.tasks.watchlist_sync.sync_all_watchlists
```

### OFAC SDN List Structure

The SDN list is published as XML. Each entry contains:

```xml
<sdnEntry>
  <uid>12345</uid>
  <sdnType>Individual</sdnType>         <!-- Individual, Entity, Vessel, Aircraft -->
  <lastName>DOE</lastName>
  <firstName>John</firstName>
  <programList>
    <program>SDGT</program>              <!-- Specially Designated Global Terrorist -->
    <program>IRAN</program>
  </programList>
  <akaList>                              <!-- Aliases -->
    <aka>
      <lastName>AL-DOE</lastName>
      <firstName>Yahya</firstName>
    </aka>
  </akaList>
  <addressList>
    <address>
      <country>Iran</country>
      <city>Tehran</city>
    </address>
  </addressList>
  <idList>                               <!-- Identification documents -->
    <id>
      <idType>Passport</idType>
      <idNumber>A12345678</idNumber>
      <idCountry>Iran</idCountry>
    </id>
  </idList>
  <nationalityList>
    <nationality><country>Iran</country></nationality>
  </nationalityList>
</sdnEntry>
```

### Example Watchlist Entries

Here are the types of entries found on the OFAC SDN list:

| Type | Example | Programs | Description |
|------|---------|----------|-------------|
| **Entity** | ISLAMIC REVOLUTIONARY GUARD CORPS (IRGC) | IRAN, IRGC | Iranian military organization |
| **Entity** | HIZBALLAH | SDGT | Designated terrorist organization |
| **Entity** | BANCO DELTA ASIA | NPWMD | Bank facilitating North Korean WMD transactions |
| **Individual** | (Names redacted — real entries include full names, DOB, passport numbers) | Various | Individuals associated with sanctioned programs |
| **Vessel** | Named vessels | DPRK, IRAN | Ships involved in sanctions evasion |

Common OFAC programs:
- **SDGT** — Specially Designated Global Terrorist
- **IRAN** — Iran-related sanctions
- **DPRK** — North Korea (Democratic People's Republic of Korea)
- **UKRAINE-EO13661** — Russia/Ukraine-related sanctions
- **CYBER2** — Malicious cyber activities
- **NPWMD** — Non-Proliferation of Weapons of Mass Destruction

### Matching Algorithm

We use fuzzy string matching (`SequenceMatcher`) to handle:
- Transliteration variations (e.g., "Muhammad" vs "Mohammed" vs "Mohamed")
- Partial name matches
- Alias lookups (each entry's aliases are also checked)

Threshold: **0.85** (configurable via `AML_SANCTIONS_MATCH_THRESHOLD`)

All screening results are stored in the `screening_results` table for audit purposes.

## 2. Currency Transaction Reports (CTR)

### Regulatory Requirement

CEMAC/COBAC regulations require automatic reporting of transactions exceeding a monetary threshold. Our system auto-generates CTRs.

### Configuration

```env
AML_CTR_THRESHOLD=5000000.0  # 5,000,000 XAF (configurable)
```

### How It Works

```
Transaction amount ≥ CTR threshold
    → CurrencyTransactionReport auto-created (status: PENDING)
    → Compliance officer reviews in dashboard
    → Files report with regulator → status: FILED
    → Regulator acknowledges → status: ACKNOWLEDGED
```

Each CTR records:
- Transaction ID, client ID, account ID
- Amount, currency, transaction type
- Reference number (from regulator)
- Filed by (compliance officer name)
- Filing notes

## 3. KYC/KYB (Know Your Customer / Know Your Business)

### Customer Data Model

The `customers` table caches KYC data from Fineract's client API:

| Field | Description |
|-------|-------------|
| full_name | Client display name |
| customer_type | `individual` or `entity` (business) |
| nationality, country_of_residence | ISO 3166-1 alpha-2 codes |
| id_type, id_number, id_expiry | Identification document |
| beneficial_owners | JSON list (for entities) |
| is_pep | Politically Exposed Person flag |
| is_sanctioned | Sanctions match flag |
| risk_level | LOW / MEDIUM / HIGH |

### Enhanced Due Diligence (EDD) Triggers

EDD is automatically required when any of these risk factors are present:

| Risk Factor | EDD Trigger | Risk Level |
|-------------|-------------|------------|
| PEP status | Yes | MEDIUM+ |
| Sanctions match | Yes | HIGH |
| FATF high-risk nationality | Yes | MEDIUM+ |
| FATF high-risk residence | Yes | MEDIUM+ |
| Entity without beneficial owners | Yes | MEDIUM+ |
| 2+ risk factors combined | Yes | HIGH |

### FATF High-Risk Countries

Countries on the FATF grey/black list that trigger EDD:

| Code | Country |
|------|---------|
| AF | Afghanistan |
| MM | Myanmar |
| KP | North Korea |
| IR | Iran |
| YE | Yemen |
| SY | Syria |
| SS | South Sudan |
| LY | Libya |
| SO | Somalia |
| HT | Haiti |

This list is maintained in `app/services/kyc_service.py` and should be updated when FATF issues new guidance.

### Fineract Integration

Customer data is synced from Fineract's REST API:
```
GET {FINERACT_BASE_URL}/clients/{client_id}
```

Sync happens:
- On first transaction from a new client
- On demand via `KYCService.sync_customer_from_fineract()`

## 4. Suspicious Activity Reports (SAR)

### Filing Workflow

```
Alert created → Analyst reviews
    → Decision: "Confirmed Fraud"
    → Check "SAR Filed" checkbox
    → Enter SAR reference number
    → Review stored with: decision, notes, evidence, sar_filed, sar_reference
```

### Score Explanation for SARs

Every transaction has a `score_explanation` JSON that documents exactly why it was flagged:

```json
{
  "final_score": 0.87,
  "components": {
    "rule_score": 0.7,
    "anomaly_score": 0.65,
    "ml_score": 0.92
  },
  "triggered_rules": [
    {"name": "structuring", "category": "pattern", "severity": 0.7},
    {"name": "rapid_transactions", "category": "velocity", "severity": 0.6}
  ],
  "top_features": {
    "amount": 9800.0,
    "tx_count_1h": 8.0,
    "amount_vs_avg_ratio": 4.2
  }
}
```

This satisfies FATF Recommendation 20 — SARs must include the rationale for suspicion.

## 5. Audit Trail

### What Is Logged

| Action | When | Details Captured |
|--------|------|------------------|
| `alert_reviewed` | Analyst submits review | decision, sar_filed, reviewer, IP |
| `user_created` | New user registered | new_username, role, created_by |
| `watchlist_sync` | Watchlist refreshed | entries_loaded, source_url |
| `retention_check` | Monthly retention scan | eligible_count, cutoff_date |
| `retention_purge` | Data purged | purged_count, retention_years |

### Accessing Audit Logs

Audit logs are stored in the `audit_logs` table. They are immutable — once written, they cannot be modified or deleted.

## 6. Data Retention

| Data Type | Retention Period | Action After Expiry |
|-----------|-----------------|---------------------|
| Transactions | 7 years | Flagged for archival (manual approval required) |
| SAR records | 7 years | Same as transactions |
| Clear screening results | 5 years | Auto-purged |
| Potential match screenings | 7 years | Manual review required before purging |
| Audit logs | 10 years | Never auto-purged |

The retention task runs monthly via Celery Beat. All purge actions are audit-logged.

## 7. RBAC (Role-Based Access Control)

| Role | Review Alerts | File SARs | Manage Cases | Create Users | View Analytics |
|------|:---:|:---:|:---:|:---:|:---:|
| analyst | ✓ | ✓ | ✓ | ✗ | ✓ |
| senior_analyst | ✓ | ✓ | ✓ | ✗ | ✓ |
| compliance_officer | ✓ | ✓ | ✓ | ✓ | ✓ |
| admin | ✓ | ✓ | ✓ | ✓ | ✓ |

## 8. Configuration Reference

All settings are configurable via environment variables with the `AML_` prefix:

---

## 9. COBAC SAR Filing Workflow

The system automates SAR preparation end-to-end, from detection through narrative drafting and export.

```
Alert flagged HIGH or CRITICAL
    → Case created (or analyst groups alerts into a case)
    → EscalationService monitors open cases hourly
        → Auto-escalates to ESCALATED status after 30 days if not resolved
        → Notifies compliance officers of approaching deadlines
    → LLM agent generates French SAR narrative (Claude API)
        [gated by AML_LLM_INVESTIGATION_ENABLED=true]
    → Compliance officer reviews at GET /api/v1/cases/{id}/sar/pdf
    → Exports to XML for electronic filing: GET /api/v1/cases/{id}/sar/xml
```

**SLA**: 30 days from escalation. `EscalationService` (run by the hourly Celery task) enforces this SLA automatically and notifies compliance officers of approaching deadlines.

### SAR Document Formats

| Endpoint | Format | Purpose |
|----------|--------|---------|
| `GET /api/v1/cases/{id}/sar/xml` | COBAC-compliant XML | Electronic filing with the regulator |
| `GET /api/v1/cases/{id}/sar/pdf` | French PDF | Compliance officer review and physical submission |

The SAR narrative is drafted in French by the LLM investigation agent and embedded in both export formats. If the alert already has a `narrative_fr` in its `investigation_report`, it is used directly; otherwise Claude is called on demand with the full case context.

---

## 10. Tiered Country Risk (FATF-Based)

Country risk is now tiered across three levels, replacing the previous binary FATF high-risk list.

### Critical — FATF Black List

Countries subject to a Call for Action (highest risk). Mandatory Enhanced Due Diligence (EDD) and automatic HIGH risk assignment.

| Code | Country |
|------|---------|
| KP | North Korea |
| IR | Iran |
| MM | Myanmar |

### High — FATF Grey List

Countries under Increased Monitoring. EDD required; assigned MEDIUM risk.

| Code | Country |
|------|---------|
| AF | Afghanistan |
| YE | Yemen |
| SY | Syria |
| SS | South Sudan |
| LY | Libya |
| SO | Somalia |
| HT | Haiti |
| PA | Panama |
| PH | Philippines |
| VN | Vietnam |
| ML | Mali |
| SN | Senegal |
| CF | Central African Republic |
| CD | Democratic Republic of Congo |
| MZ | Mozambique |
| TZ | Tanzania |
| NG | Nigeria |
| SD | Sudan |

### Elevated — EU Non-Cooperative Jurisdictions

Additional score penalty applied. If the current risk level is LOW it is automatically raised to MEDIUM.

| Code | Country |
|------|---------|
| RU | Russia |
| BY | Belarus |
| CU | Cuba |
| VE | Venezuela |
| ZW | Zimbabwe |

---

## 11. Adverse Media Screening

Counterparty names are screened against recent news articles for negative associations.

**Configuration:**
```env
ADVERSE_MEDIA_ENABLED=true
ADVERSE_MEDIA_API_KEY=<NewsAPI key>
ADVERSE_MEDIA_MIN_RISK_SCORE=0.6   # Only screen when final_score >= this value
```

- Screens against NewsAPI using 16 negative keywords (fraud, money laundering, corruption, sanctions, etc.)
- Only triggered when `final_score >= ADVERSE_MEDIA_MIN_RISK_SCORE` (default 0.6) to limit unnecessary API calls
- Results are logged to the screening results table
- Future: alerts will be raised when a match is found with sufficient confidence

---

## 12. AML Typologies Covered

The system detects the following typologies through dedicated deterministic rules. All 9 new rules are in addition to the original 10 standard rules.

### IBM AMLSim Network Typologies (3 rules)

| Rule Name | Trigger | Severity |
|-----------|---------|----------|
| `scatter_gather` | ≥8 unique senders to a single account + a single large outbound transfer within 7 days | 0.85 |
| `bipartite_layering` | ≥5 unique senders AND ≥5 unique recipients through a single intermediary within 7 days | 0.90 |
| `stacking` | ≥3 sequential transfers within 30 minutes where each amount is 80–120% of the prior transfer | 0.80 |

### Agent-Specific Typologies (4 rules)

All agent rules require `actor_type == "agent"` in the webhook payload.

| Rule Name | Trigger | Severity |
|-----------|---------|----------|
| `agent_structuring` | ≥5 deposits just below the 5M XAF CTR threshold from same agent within 1 hour | 0.85 |
| `agent_float_anomaly` | Float ratio >0.95 or <0.05 over 24 hours vs. agent's own `typical_float_ratio` baseline | 0.60 |
| `agent_account_farming` | >8 deposits into brand-new KYC-level-1 accounts (age <7 days) within 24 hours | 0.75 |
| `agent_customer_collusion` | Deposit via agent A for customer X + withdrawal via different agent within 60 minutes | 0.80 |

### Merchant-Specific Typologies (2 rules)

All merchant rules require `actor_type == "merchant"` in the webhook payload.

| Rule Name | Trigger | Severity |
|-----------|---------|----------|
| `merchant_collection_account` | Merchant account receiving from an unusually diverse set of payers (structuring via merchant QR) | 0.75 |
| `high_value_anonymous_payment` | High-value transaction with no KYC data on the payer side | 0.70 |

```env
# Sanctions
AML_SANCTIONS_SCREENING_ENABLED=true
AML_SANCTIONS_MATCH_THRESHOLD=0.85

# CTR
AML_CTR_THRESHOLD=5000000.0  # XAF

# Risk thresholds
AML_RISK_SCORE_HIGH=0.8     # Alert as HIGH risk
AML_RISK_SCORE_MEDIUM=0.5   # Alert as MEDIUM risk

# ML
AML_ANOMALY_CONTAMINATION=0.01  # Expected fraud rate

# Auth
AML_ACCESS_TOKEN_EXPIRE_MINUTES=30
AML_CORS_ORIGINS=https://dashboard.example.com
```
