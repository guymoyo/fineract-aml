"""Webank eligibility endpoint schemas."""

from pydantic import BaseModel


class ProductInfo(BaseModel):
    product_id: str
    name: str
    max_amount: int
    durations_days: list[int] | None = None
    durations_months: list[int] | None = None
    interest_rate_pct: float


class EligibilityResponse(BaseModel):
    eligible: bool
    max_amount: int
    score: int
    score_band: str  # NON_ELIGIBLE, LOW, MEDIUM, HIGH, PREMIUM
    available_products: list[ProductInfo]
    ineligibility_reasons: list[str]
    eligible_from: str | None = None
    computed_at: str
