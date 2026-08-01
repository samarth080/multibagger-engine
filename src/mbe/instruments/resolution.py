"""Conservative ranked identity lookup with explicit match reasons."""

from __future__ import annotations

from difflib import SequenceMatcher

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from mbe.db.models import (
    CompanyRow, IndustryRow, InstrumentAliasRow, InstrumentListingRow,
    InstrumentRow, ProviderSymbolRow, SectorRow,
)
from mbe.models.instrument import normalize_name, normalize_symbol


class ListingMatch(BaseModel):
    """One exchange's current listing of a matched instrument (Phase 10B
    NSE/BSE cross-listing exposure)."""

    exchange: str
    symbol: str
    bse_code: str | None = None
    isin: str | None = None
    listing_status: str | None = None
    is_primary: bool = True
    is_sme: bool | None = None


class MatchCandidate(BaseModel):
    instrument_id: str
    display_name: str | None = None
    symbol: str | None = None
    exchange: str | None = None
    score: float
    matched_by: str
    matched_value: str
    bse_code: str | None = None
    isin: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_category: str | None = None
    listing_status: str | None = None
    is_sme: bool | None = None
    listings: list[ListingMatch] = []


class InstrumentResolver:
    def __init__(self, session: Session):
        self.session = session

    def resolve(self, query: str, *, limit: int = 10) -> list[MatchCandidate]:
        raw = query.strip()
        if not raw or len(raw) > 160:
            return []
        normalized_name = normalize_name(raw)
        normalized_symbol = normalize_symbol(raw)
        rows = self.session.execute(
            select(InstrumentRow, CompanyRow, SectorRow, IndustryRow).outerjoin(
                CompanyRow, CompanyRow.company_id == InstrumentRow.company_id
            ).outerjoin(
                SectorRow, SectorRow.sector_id == InstrumentRow.sector_id
            ).outerjoin(
                IndustryRow, IndustryRow.industry_id == InstrumentRow.industry_id
            )
        ).all()
        listings = self.session.scalars(select(InstrumentListingRow).where(
            InstrumentListingRow.valid_to.is_(None)
        )).all()
        aliases = self.session.scalars(select(InstrumentAliasRow)).all()
        mappings = self.session.scalars(select(ProviderSymbolRow).where(
            ProviderSymbolRow.valid_to.is_(None)
        )).all()
        by_listing: dict[str, list] = {}
        by_alias: dict[str, list] = {}
        by_mapping: dict[str, list] = {}
        for item in listings:
            by_listing.setdefault(item.instrument_id, []).append(item)
        for item in aliases:
            by_alias.setdefault(item.instrument_id, []).append(item)
        for item in mappings:
            by_mapping.setdefault(item.instrument_id, []).append(item)

        candidates: list[MatchCandidate] = []
        for instrument, company, sector, industry in rows:
            best: tuple[float, str, str] | None = None
            for listing in by_listing.get(instrument.instrument_id, []):
                if normalized_symbol in {listing.symbol.upper(), f"{listing.symbol.upper()}.NS"}:
                    best = max(best or (0, "", ""), (100, "exact_nse_symbol", listing.symbol))
                if listing.bse_code and raw == listing.bse_code:
                    best = max(best or (0, "", ""), (98, "exact_bse_code", listing.bse_code))
                if listing.isin and normalized_symbol == listing.isin:
                    best = max(best or (0, "", ""), (97, "exact_isin", listing.isin))
            for mapping in by_mapping.get(instrument.instrument_id, []):
                if normalized_symbol == normalize_symbol(mapping.provider_symbol):
                    best = max(best or (0, "", ""), (96, "exact_provider_symbol", mapping.provider_symbol))
            names = [n for n in (
                company.legal_name if company else None,
                company.current_legal_name if company else None,
                company.display_name if company else None,
            ) if n]
            for name in names:
                norm = normalize_name(name)
                safe_norm = normalize_name(name, strip_suffixes=True)
                if normalized_name in {norm, safe_norm}:
                    best = max(best or (0, "", ""), (95, "exact_company_name", name))
                elif len(normalized_name) >= 3 and norm.startswith(normalized_name):
                    best = max(best or (0, "", ""), (82, "company_name_prefix", name))
                elif len(normalized_name) >= 5:
                    similarity = SequenceMatcher(None, normalized_name, norm).ratio()
                    if similarity >= 0.78:
                        best = max(best or (0, "", ""), (60 + similarity * 20, "fuzzy_company_name", name))
            for alias in by_alias.get(instrument.instrument_id, []):
                if normalized_name == alias.normalized_value:
                    # Short abbreviations stay below a clear exact name/symbol.
                    alias_score = 78 if len(normalized_name) <= 3 else 90
                    best = max(best or (0, "", ""), (alias_score, f"exact_{alias.alias_type}", alias.value))
            if best:
                primary = next((x for x in by_listing.get(instrument.instrument_id, []) if x.is_primary), None)
                current_listings = by_listing.get(instrument.instrument_id, [])
                candidates.append(MatchCandidate(
                    instrument_id=instrument.instrument_id,
                    display_name=company.display_name if company else None,
                    symbol=primary.symbol if primary else None,
                    exchange=primary.exchange_code if primary else None,
                    score=round(best[0], 2), matched_by=best[1], matched_value=best[2],
                    bse_code=primary.bse_code if primary else None,
                    isin=primary.isin if primary else None,
                    sector=sector.name if sector else None,
                    industry=industry.name if industry else None,
                    market_cap_category=instrument.market_cap_category,
                    listing_status=primary.status if primary else None,
                    is_sme=primary.is_sme if primary else None,
                    listings=[ListingMatch(
                        exchange=listing.exchange_code, symbol=listing.symbol,
                        bse_code=listing.bse_code, isin=listing.isin,
                        listing_status=listing.status, is_primary=listing.is_primary,
                        is_sme=listing.is_sme,
                    ) for listing in current_listings],
                ))
        candidates.sort(key=lambda item: (-item.score, item.display_name or "", item.instrument_id))
        return candidates[:limit]
