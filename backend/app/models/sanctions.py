"""Sanctions screening models — watchlist entries and screening results."""

import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WatchlistSource(str, enum.Enum):
    OFAC_SDN = "ofac_sdn"
    EU_SANCTIONS = "eu_sanctions"
    UN_SANCTIONS = "un_sanctions"
    PEP = "pep"
    CUSTOM = "custom"


class ScreeningStatus(str, enum.Enum):
    CLEAR = "clear"
    POTENTIAL_MATCH = "potential_match"
    CONFIRMED_MATCH = "confirmed_match"
    FALSE_POSITIVE = "false_positive"


class WatchlistEntry(Base, TimestampMixin):
    """A sanctions/PEP watchlist entry loaded from external sources."""

    __tablename__ = "watchlist_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[WatchlistSource] = mapped_column(
        Enum(WatchlistSource, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    entity_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # individual, entity, vessel
    country: Mapped[str | None] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    aliases: Mapped[str | None] = mapped_column(Text)  # JSON list of aliases
    identifiers: Mapped[str | None] = mapped_column(Text)  # JSON: passport, national_id, etc.
    program: Mapped[str | None] = mapped_column(String(255))  # e.g. "SDGT", "UKRAINE-EO13661"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_watchlist_source_name", "source", "entity_name"),
    )


class ScreeningResult(Base, TimestampMixin):
    """Result of screening a transaction counterparty against watchlists."""

    __tablename__ = "screening_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    screened_name: Mapped[str] = mapped_column(String(500), nullable=False)
    matched_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    matched_name: Mapped[str | None] = mapped_column(String(500))
    match_score: Mapped[float | None] = mapped_column(Float)  # 0-1 similarity
    source: Mapped[WatchlistSource | None] = mapped_column(
        Enum(WatchlistSource, values_callable=lambda e: [x.value for x in e])
    )
    status: Mapped[ScreeningStatus] = mapped_column(
        Enum(ScreeningStatus, values_callable=lambda e: [x.value for x in e]),
        default=ScreeningStatus.CLEAR,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_screening_status", "status"),
    )
