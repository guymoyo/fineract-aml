"""RuleMatch model — tracks which rules a transaction triggered."""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class RuleMatch(Base, TimestampMixin):
    """Records when a transaction matches an AML detection rule."""

    __tablename__ = "rule_matches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False
    )

    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[float] = mapped_column(Float, nullable=False)
    details: Mapped[str | None] = mapped_column(Text)

    # Relationships
    transaction: Mapped["Transaction"] = relationship(back_populates="rule_matches")  # noqa: F821
