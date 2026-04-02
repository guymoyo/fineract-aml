"""Sanctions and PEP screening service.

Screens transaction counterparties against watchlist entries using
fuzzy name matching. Integrates with OFAC SDN, EU, UN sanctions lists.
"""

import json
import logging

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sanctions import (
    ScreeningResult,
    ScreeningStatus,
    WatchlistEntry,
    WatchlistSource,
)

logger = logging.getLogger(__name__)

# Minimum similarity score to flag as a potential match
# With rapidfuzz multi-algorithm scoring, 0.82 balances precision vs recall
# for transliteration tolerance while token_sort handles name-order reversal.
MATCH_THRESHOLD = 0.82


def _name_similarity(name1: str, name2: str) -> float:
    """Multi-algorithm name similarity for sanctions screening.

    Handles reversed names, transliterations, and partial matches.
    Returns a score between 0.0 and 1.0.
    """
    if not name1 or not name2:
        return 0.0

    # Normalize: lowercase, strip diacritics via ASCII encoding
    import unicodedata

    def normalize(s: str) -> str:
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower().strip()

    n1 = normalize(name1)
    n2 = normalize(name2)

    # Token sort ratio handles reversed name order (best for sanctions)
    token_sort = fuzz.token_sort_ratio(n1, n2) / 100.0

    # WRatio handles transliterations and prefix variations
    jaro = fuzz.WRatio(n1, n2) / 100.0

    # Partial ratio handles names with extra titles/middle names
    partial = fuzz.partial_ratio(n1, n2) / 100.0

    # Take the maximum across algorithms
    return max(token_sort, jaro, partial)


class SanctionsScreeningService:
    """Screen names against watchlist entries."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def screen_name(
        self,
        name: str,
        transaction_id: str,
        sources: list[WatchlistSource] | None = None,
    ) -> ScreeningResult:
        """Screen a name against active watchlist entries.

        Args:
            name: The name to screen (counterparty, client, etc.).
            transaction_id: Associated transaction UUID.
            sources: Optional filter to specific watchlist sources.

        Returns:
            ScreeningResult with match details.
        """
        query = select(WatchlistEntry).where(WatchlistEntry.is_active.is_(True))
        if sources:
            query = query.where(WatchlistEntry.source.in_(sources))

        result = await self.db.execute(query)
        entries = result.scalars().all()

        best_match: WatchlistEntry | None = None
        best_score = 0.0

        for entry in entries:
            # Check main name
            score = _name_similarity(name, entry.entity_name)
            if score > best_score:
                best_score = score
                best_match = entry

            # Check aliases
            if entry.aliases:
                try:
                    aliases = json.loads(entry.aliases)
                    for alias in aliases:
                        alias_score = _name_similarity(name, alias)
                        if alias_score > best_score:
                            best_score = alias_score
                            best_match = entry
                except (json.JSONDecodeError, TypeError):
                    pass

        # Determine screening status
        if best_score >= MATCH_THRESHOLD and best_match:
            status = ScreeningStatus.POTENTIAL_MATCH
            logger.warning(
                "Potential sanctions match: '%s' ~ '%s' (score=%.2f, source=%s)",
                name,
                best_match.entity_name,
                best_score,
                best_match.source.value,
            )
        else:
            status = ScreeningStatus.CLEAR

        screening = ScreeningResult(
            transaction_id=transaction_id,
            screened_name=name,
            matched_entry_id=best_match.id if best_match and best_score >= MATCH_THRESHOLD else None,
            matched_name=best_match.entity_name if best_match and best_score >= MATCH_THRESHOLD else None,
            match_score=best_score if best_score >= MATCH_THRESHOLD else None,
            source=best_match.source if best_match and best_score >= MATCH_THRESHOLD else None,
            status=status,
        )
        self.db.add(screening)
        return screening

    async def screen_transaction(
        self,
        transaction_id: str,
        counterparty_name: str | None,
        counterparty_account_id: str | None,
    ) -> list[ScreeningResult]:
        """Screen all names associated with a transaction."""
        results = []

        if counterparty_name:
            result = await self.screen_name(counterparty_name, transaction_id)
            results.append(result)

        return results

    async def load_ofac_sdn_entries(self, entries: list[dict]) -> int:
        """Bulk load OFAC SDN entries into the watchlist.

        Args:
            entries: List of dicts with keys: name, entity_type, country, aliases, program

        Returns:
            Number of entries loaded.
        """
        count = 0
        for entry in entries:
            watchlist_entry = WatchlistEntry(
                source=WatchlistSource.OFAC_SDN,
                entity_name=entry["name"],
                entity_type=entry.get("entity_type", "individual"),
                country=entry.get("country"),
                aliases=json.dumps(entry.get("aliases", [])),
                identifiers=json.dumps(entry.get("identifiers", {})),
                program=entry.get("program"),
            )
            self.db.add(watchlist_entry)
            count += 1

        await self.db.flush()
        logger.info("Loaded %d OFAC SDN entries", count)
        return count
