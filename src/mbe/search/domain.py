"""Search-universe types.

The platform tracks three deliberately different universes:

- **Search universe** — everything the platform can identify (currently every
  NSE main-board and SME listed security; see ``mbe.data.nse_search_master``).
- **Research universe** — companies with a deterministic research page
  (currently the 250 Nifty Smallcap companies with a model build).
- **Ranking universe** — companies currently scored by the Multibagger model
  (currently identical to the research universe, but conceptually separate;
  see ``docs/HANDOVER.md`` "Search, research and ranking universes").

``SearchResultType`` tags where a given result sits so the UI can render an
honest badge instead of implying every company has been scored.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class SearchResultType(StrEnum):
    #: Type A — fully modeled: score, research page, ranking, explanations.
    MODELED = "modeled"
    #: Type B — known instrument, identity confirmed, not yet modeled.
    KNOWN = "known"
    #: Type C — instrument exists but only a quote is available (no confirmed
    #: identity match in the search index; reached via a raw symbol probe).
    QUOTE_ONLY = "quote_only"
    #: Type D — no matching listed company.
    UNKNOWN = "unknown"


class ExchangeListing(BaseModel):
    """One exchange's listing of a canonical instrument. A company can have
    an NSE listing, a BSE listing, or both — see the NSE/BSE cross-listing
    bridge in ``mbe.search.catalog.build_search_index`` and
    ``mbe.instruments.importer.import_instruments``."""

    exchange: str
    symbol: str
    bse_code: str | None = None
    isin: str | None = None
    listing_status: str = "active"
    is_primary: bool = True
    is_sme: bool | None = None


class SearchIndexRecord(BaseModel):
    """One entry in the merged search index: identity plus research/ranking
    status. ``instrument_id`` is the immutable canonical ID — identical
    whether or not the company is currently modeled, and identical across
    an NSE/BSE cross-listing sharing one ISIN.

    ``exchange``/``symbol``/``bse_code``/``listing_status``/``is_sme`` mirror
    the *primary* listing for backward compatibility with Phase 10A
    consumers; ``listings`` carries the full multi-exchange detail added in
    Phase 10B."""

    instrument_id: str
    company_id: str | None = None
    display_name: str
    legal_name: str | None = None
    symbol: str
    exchange: str = "NSE"
    primary_exchange: str = "NSE"
    isin: str | None = None
    bse_code: str | None = None
    sector: str | None = None
    sector_source: str | None = None
    industry: str | None = None
    industry_source: str | None = None
    sub_industry: str | None = None
    sub_industry_source: str | None = None
    classification_version: str | None = None
    classification_confidence: float | None = None
    classification_review_status: str | None = None
    classification_selection_reason: str | None = None
    classification_conflict: bool = False
    listing_status: str = "active"
    is_sme: bool | None = None
    market_cap_category: str | None = None
    aliases: list[dict] = []
    provider_symbol: str | None = None
    listings: list[ExchangeListing] = []
    # Verified broad-index memberships only (e.g. "Nifty 50"). Empty on every
    # record today — no broad-index source beyond Nifty Smallcap 250 (already
    # reflected via research_available) is imported yet. See
    # mbe.search.ranking module docstring and docs/search-architecture.md
    # "Search ranking policy version 3".
    index_memberships: list[str] = []

    result_type: SearchResultType
    research_available: bool = False
    rank: int | None = None
    multibagger_score: float | None = None
    confidence: float | None = None
    risk_score: float | None = None
    report_url: str


class SearchCandidate(BaseModel):
    """A ranked search result: the matched record plus why it matched, and
    the Phase 10C Milestone 2 (search ranking policy version 3) evidence
    fields that explain its position — see mbe.search.ranking module
    docstring for the full tier/tie-break policy."""

    record: SearchIndexRecord
    score: float
    matched_by: str
    matched_value: str
    match_tier: str
    matched_field: str
    match_reason: str
    match_confidence: float
    ranking_policy_version: str
    active_listing: bool
    primary_listing: bool
    requested_exchange_matched: bool | None = None
    index_memberships: list[str] = []
    research_available: bool
    ranking_available: bool
    classification_review_status: str | None = None
    classification_conflict: bool = False
    prominence_signals: list[str] = []
    ambiguity_warning: str | None = None
