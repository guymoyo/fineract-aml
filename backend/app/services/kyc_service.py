"""KYC/KYB service — syncs customer data from Fineract and manages due diligence.

Pulls client details from Fineract's REST API, caches them locally,
and determines Enhanced Due Diligence (EDD) requirements based on
risk factors (PEP status, high-risk country, sanctions matches).
"""

import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.customer import Customer, CustomerRiskLevel, CustomerType

logger = logging.getLogger(__name__)

# ISO 3166-1 alpha-2 codes for FATF high-risk jurisdictions (2024 list)
HIGH_RISK_COUNTRIES = {
    "AF",  # Afghanistan
    "MM",  # Myanmar
    "KP",  # North Korea
    "IR",  # Iran
    "YE",  # Yemen
    "SY",  # Syria
    "SS",  # South Sudan
    "LY",  # Libya
    "SO",  # Somalia
    "HT",  # Haiti
}


class KYCService:
    """Manages customer KYC/KYB data and due diligence workflows."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_customer_from_fineract(self, client_id: str) -> Customer:
        """Fetch client data from Fineract API and sync to local DB.

        Args:
            client_id: Fineract client ID.

        Returns:
            The synced Customer record.
        """
        fineract_data = await self._fetch_fineract_client(client_id)

        # Upsert customer
        result = await self.db.execute(
            select(Customer).where(Customer.fineract_client_id == client_id)
        )
        customer = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if fineract_data:
            fields = self._map_fineract_to_customer(fineract_data)
            if customer:
                for key, value in fields.items():
                    setattr(customer, key, value)
                customer.last_synced_at = now
            else:
                customer = Customer(
                    fineract_client_id=client_id,
                    **fields,
                    last_synced_at=now,
                )
                self.db.add(customer)
        elif not customer:
            # Fineract unreachable — create stub record
            customer = Customer(
                fineract_client_id=client_id,
                full_name=f"Client {client_id}",
                customer_type=CustomerType.INDIVIDUAL,
                risk_level=CustomerRiskLevel.MEDIUM,  # Unknown = medium risk
            )
            self.db.add(customer)

        # Assess risk level and EDD requirements
        self._assess_risk(customer)

        await self.db.flush()
        logger.info("Customer %s synced: risk=%s, edd=%s", client_id, customer.risk_level.value, customer.edd_required)
        return customer

    async def get_customer(self, client_id: str) -> Customer | None:
        """Get a customer by Fineract client ID."""
        result = await self.db.execute(
            select(Customer).where(Customer.fineract_client_id == client_id)
        )
        return result.scalar_one_or_none()

    async def get_or_sync_customer(self, client_id: str) -> Customer:
        """Get a customer, syncing from Fineract if not cached."""
        customer = await self.get_customer(client_id)
        if not customer:
            customer = await self.sync_customer_from_fineract(client_id)
        return customer

    def _assess_risk(self, customer: Customer) -> None:
        """Determine customer risk level and EDD requirements.

        High risk triggers:
        - PEP (Politically Exposed Person)
        - Sanctioned entity
        - High-risk country (FATF grey/black list)
        - Entity without beneficial ownership info
        """
        edd_reasons = []

        if customer.is_pep:
            edd_reasons.append("PEP status")
        if customer.is_sanctioned:
            edd_reasons.append("Sanctions match")
        if customer.nationality in HIGH_RISK_COUNTRIES:
            edd_reasons.append(f"High-risk nationality: {customer.nationality}")
        if customer.country_of_residence in HIGH_RISK_COUNTRIES:
            edd_reasons.append(f"High-risk residence: {customer.country_of_residence}")
        if (
            customer.customer_type == CustomerType.ENTITY
            and not customer.beneficial_owners
        ):
            edd_reasons.append("Entity without beneficial ownership data")

        if customer.is_sanctioned:
            customer.risk_level = CustomerRiskLevel.HIGH
        elif len(edd_reasons) >= 2:
            customer.risk_level = CustomerRiskLevel.HIGH
        elif edd_reasons:
            customer.risk_level = CustomerRiskLevel.MEDIUM
        else:
            customer.risk_level = CustomerRiskLevel.LOW

        customer.edd_required = len(edd_reasons) > 0
        customer.edd_reason = "; ".join(edd_reasons) if edd_reasons else None

    async def _fetch_fineract_client(self, client_id: str) -> dict | None:
        """Fetch client data from Fineract REST API."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                response = await client.get(
                    f"{settings.fineract_base_url}/clients/{client_id}",
                    headers={"Fineract-Platform-TenantId": "default"},
                )
                if response.status_code == 200:
                    return response.json()
                logger.warning(
                    "Fineract client fetch returned %d for %s",
                    response.status_code, client_id,
                )
        except httpx.RequestError as e:
            logger.debug("Cannot reach Fineract API: %s", e)
        return None

    @staticmethod
    def _map_fineract_to_customer(data: dict) -> dict:
        """Map Fineract client JSON to Customer model fields."""
        # Build full name from Fineract fields
        first = data.get("firstname", "")
        middle = data.get("middlename", "")
        last = data.get("lastname", "")
        display = data.get("displayName", "")
        full_name = display or " ".join(filter(None, [first, middle, last])) or "Unknown"

        # Parse activation date as DOB proxy if available
        dob = None
        if "dateOfBirth" in data and data["dateOfBirth"]:
            parts = data["dateOfBirth"]
            if isinstance(parts, list) and len(parts) == 3:
                dob = datetime(parts[0], parts[1], parts[2])

        # Determine customer type
        is_entity = data.get("legalForm", {})
        customer_type = CustomerType.ENTITY if is_entity and is_entity.get("id") == 2 else CustomerType.INDIVIDUAL

        return {
            "full_name": full_name,
            "customer_type": customer_type,
            "date_of_birth": dob,
            "email": data.get("emailAddress"),
            "phone": data.get("mobileNo"),
        }
