"""Webank eligibility scoring — 6 criteria, 100 points total."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert, AlertStatus
from app.models.transaction import Transaction, TransactionType
from app.schemas.eligibility import EligibilityResponse, ProductInfo

logger = logging.getLogger(__name__)

WEBANK_PRODUCTS = [
    ProductInfo(product_id="WEBANK_SHORT_7", name="Crédit 7 jours", max_amount=0, durations_days=[7], interest_rate_pct=5.0),
    ProductInfo(product_id="WEBANK_SHORT_14", name="Crédit 14 jours", max_amount=0, durations_days=[7, 14], interest_rate_pct=7.0),
    ProductInfo(product_id="WEBANK_SHORT_30", name="Crédit 30 jours", max_amount=0, durations_days=[7, 14, 30], interest_rate_pct=10.0),
    ProductInfo(product_id="WEBANK_INSTALL_2", name="Crédit 2 mois", max_amount=0, durations_months=[2], interest_rate_pct=4.0),
    ProductInfo(product_id="WEBANK_INSTALL_3", name="Crédit 3 mois", max_amount=0, durations_months=[2, 3], interest_rate_pct=4.0),
    ProductInfo(product_id="WEBANK_INSTALL_6", name="Crédit 6 mois", max_amount=0, durations_months=[2, 3, 6], interest_rate_pct=3.5),
    ProductInfo(product_id="WEBANK_LONG_12", name="Crédit 12 mois", max_amount=0, durations_months=[12], interest_rate_pct=3.0),
    ProductInfo(product_id="WEBANK_LONG_24", name="Crédit 24 mois", max_amount=0, durations_months=[12, 24], interest_rate_pct=2.5),
]

# (band_name, min_score, max_score, min_amount, max_amount)
SCORE_BANDS = [
    ("NON_ELIGIBLE", 0, 29, 0, 0),
    ("LOW", 30, 49, 10_000, 25_000),
    ("MEDIUM", 50, 69, 25_000, 100_000),
    ("HIGH", 70, 84, 100_000, 300_000),
    ("PREMIUM", 85, 100, 300_000, 500_000),
]


def _interpolate_amount(score: int, min_s: int, max_s: int, min_a: int, max_a: int) -> int:
    if max_s == min_s:
        return max_a
    ratio = (score - min_s) / (max_s - min_s)
    return int(min_a + ratio * (max_a - min_a))


def _get_band_and_amount(score: int) -> tuple[str, int]:
    for band_name, min_s, max_s, min_a, max_a in SCORE_BANDS:
        if min_s <= score <= max_s:
            return band_name, _interpolate_amount(score, min_s, max_s, min_a, max_a)
    return "NON_ELIGIBLE", 0


async def compute_eligibility(db: AsyncSession, fineract_client_id: str) -> EligibilityResponse:
    """Compute credit eligibility using the PRD's 6-criteria scoring system."""
    now = datetime.now(timezone.utc)
    reasons: list[str] = []

    # Fetch all transactions for this client
    result = await db.execute(
        select(Transaction)
        .where(Transaction.fineract_client_id == fineract_client_id)
        .order_by(Transaction.transaction_date.asc())
    )
    txns = list(result.scalars().all())

    if not txns:
        return EligibilityResponse(
            eligible=False, max_amount=0, score=0, score_band="NON_ELIGIBLE",
            available_products=[], ineligibility_reasons=["NO_TRANSACTION_HISTORY"],
            computed_at=now.isoformat(),
        )

    first_txn_date = txns[0].transaction_date
    account_age_days = (now - first_txn_date).days if first_txn_date else 0

    # Hard blockers
    if account_age_days < 90:
        reasons.append("ACCOUNT_TOO_YOUNG")
    if len(txns) < 10:
        reasons.append("INSUFFICIENT_ACTIVITY")

    # Check active loan
    disbursements = [t for t in txns if t.transaction_type == TransactionType.LOAN_DISBURSEMENT]
    repayments = [t for t in txns if t.transaction_type == TransactionType.LOAN_REPAYMENT]
    if len(disbursements) > len(repayments):
        reasons.append("EXISTING_ACTIVE_LOAN")

    if reasons:
        eligible_from = None
        if "ACCOUNT_TOO_YOUNG" in reasons and first_txn_date:
            eligible_from = (first_txn_date + timedelta(days=90)).isoformat()
        return EligibilityResponse(
            eligible=False, max_amount=0, score=0, score_band="NON_ELIGIBLE",
            available_products=[], ineligibility_reasons=reasons,
            eligible_from=eligible_from, computed_at=now.isoformat(),
        )

    # === 6-criteria scoring ===
    score = 0

    # 1. Account age (max 20 pts)
    if account_age_days >= 365:
        score += 20
    elif account_age_days >= 180:
        score += 14
    elif account_age_days >= 90:
        score += 8

    # 2. Transaction volume in last 90 days (max 20 pts)
    cutoff_90d = now - timedelta(days=90)
    txns_90d = [t for t in txns if t.transaction_date and t.transaction_date >= cutoff_90d]
    vol = len(txns_90d)
    if vol >= 50:
        score += 20
    elif vol >= 25:
        score += 14
    elif vol >= 10:
        score += 8

    # 3. Average balance in last 90 days (max 20 pts) — approximated from txn amounts
    if txns_90d:
        avg_amount = sum(abs(t.amount) for t in txns_90d if t.amount) / len(txns_90d)
        if avg_amount >= 200_000:
            score += 20
        elif avg_amount >= 50_000:
            score += 15
        elif avg_amount >= 10_000:
            score += 10
        elif avg_amount >= 1_000:
            score += 5

    # 4. Regularity — active months in last 12 (max 15 pts)
    cutoff_12m = now - timedelta(days=365)
    recent_txns = [t for t in txns if t.transaction_date and t.transaction_date >= cutoff_12m]
    active_months = len(set(
        (t.transaction_date.year, t.transaction_date.month)
        for t in recent_txns if t.transaction_date
    ))
    if active_months >= 8:
        score += 15
    elif active_months >= 5:
        score += 10
    elif active_months >= 3:
        score += 5

    # 5. Repayment history (max 15 pts)
    if not disbursements:
        score += 5  # neutral — no loan history
    elif len(repayments) >= len(disbursements):
        score += 15  # on-time repayment
    # else: late → 0 points

    # 6. No incidents (max 10 pts)
    txn_ids = [t.id for t in txns]
    incident_count = 0
    if txn_ids:
        result = await db.execute(
            select(func.count(Alert.id)).where(
                and_(
                    Alert.status == AlertStatus.CONFIRMED_FRAUD,
                    Alert.transaction_id.in_(txn_ids),
                )
            )
        )
        incident_count = result.scalar() or 0

    if incident_count == 0:
        score += 10
    elif incident_count == 1:
        score += 5

    # Compute band and max amount
    band, max_amount = _get_band_and_amount(score)
    eligible = band != "NON_ELIGIBLE"

    products = []
    if eligible:
        for p in WEBANK_PRODUCTS:
            products.append(p.model_copy(update={"max_amount": min(max_amount, 500_000)}))

    return EligibilityResponse(
        eligible=eligible,
        max_amount=max_amount,
        score=score,
        score_band=band,
        available_products=products,
        ineligibility_reasons=[],
        computed_at=now.isoformat(),
    )
