"""Service layer for case management."""

import uuid as uuid_mod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseStatus, CaseTransaction
from app.schemas.case import CaseCreate


class CaseService:
    """Handles investigation case management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_case(self, data: CaseCreate) -> Case:
        case_number = f"CASE-{uuid_mod.uuid4().hex[:8].upper()}"
        case = Case(
            case_number=case_number,
            title=data.title,
            description=data.description,
            fineract_client_id=data.fineract_client_id,
        )
        self.db.add(case)
        await self.db.flush()

        for tx_id in data.transaction_ids:
            link = CaseTransaction(case_id=case.id, transaction_id=tx_id)
            self.db.add(link)

        await self.db.flush()
        return case

    async def list_cases(
        self,
        page: int = 1,
        page_size: int = 50,
        status: CaseStatus | None = None,
    ) -> tuple[list[Case], int]:
        query = select(Case)
        count_query = select(func.count(Case.id))

        if status:
            query = query.where(Case.status == status)
            count_query = count_query.where(Case.status == status)

        query = query.order_by(Case.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        cases = list(result.scalars().all())

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        return cases, total

    async def get_case(self, case_id: UUID) -> Case | None:
        result = await self.db.execute(select(Case).where(Case.id == case_id))
        return result.scalar_one_or_none()

    async def update_status(self, case_id: UUID, status: CaseStatus) -> Case:
        result = await self.db.execute(select(Case).where(Case.id == case_id))
        case = result.scalar_one()
        case.status = status
        await self.db.flush()
        return case

    async def assign_case(self, case_id: UUID, user_id: UUID) -> Case:
        result = await self.db.execute(select(Case).where(Case.id == case_id))
        case = result.scalar_one()
        case.assigned_to = user_id
        if case.status == CaseStatus.OPEN:
            case.status = CaseStatus.INVESTIGATING
        await self.db.flush()
        return case

    async def add_transaction(
        self, case_id: UUID, transaction_id: UUID, notes: str | None = None
    ) -> CaseTransaction:
        link = CaseTransaction(
            case_id=case_id, transaction_id=transaction_id, notes=notes
        )
        self.db.add(link)
        await self.db.flush()
        return link
