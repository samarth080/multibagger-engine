"""Merge the search universe with research/ranking status.

This is the join that fixes the Phase 10A regression: the search universe
(every NSE-listed security) is built independently of the research universe
(currently 250 companies) and then annotated — never filtered — by whether a
research page and a current model build exist for it.
"""

from __future__ import annotations

from typing import Any

from datetime import datetime, timezone

from mbe.coverage.policy import assess_coverage
from mbe.data.provider import ProviderError
from mbe.models.instrument import stable_instrument_id
from mbe.research.builder import canonical_company_url
from mbe.search.classification import ClassificationRecord, ClassificationSource, select_canonical
from mbe.search.domain import ExchangeListing, SearchIndexRecord, SearchResultType


def _canonical_id(*, symbol: str, isin: str | None, exchange: str = "NSE") -> str:
    return stable_instrument_id(exchange_code=exchange, symbol=symbol, isin=isin)


def _listing_from_row(row: dict[str, Any], *, is_primary: bool) -> ExchangeListing:
    return ExchangeListing(
        exchange=row.get("exchange", "NSE"), symbol=row["symbol"],
        bse_code=row.get("bse_code"), isin=row.get("isin"),
        listing_status=row.get("listing_status") or "active",
        is_primary=is_primary, is_sme=row.get("is_sme"),
    )


def _classification_record(
    instrument_id: str, data: dict[str, Any], *, source: ClassificationSource,
) -> ClassificationRecord:
    return ClassificationRecord(
        instrument_id=instrument_id, source=source,
        sector=data.get("sector"), industry=data.get("industry"),
        sub_industry=data.get("sub_industry"),
        source_record_id=data.get("source_record_id") or data.get("isin") or data.get("symbol"),
        retrieved_at=datetime.now(timezone.utc),
    )


def build_search_index(
    search_universe_rows: list[dict[str, Any]],
    research_instruments: list[dict[str, Any]] | None = None,
    screener_rows: list[dict[str, Any]] | None = None,
    *,
    bse_rows: list[dict[str, Any]] | None = None,
) -> list[SearchIndexRecord]:
    """Build the full, merged search index.

    ``search_universe_rows`` — the pinned/official NSE listed-security rows
    (``mbe.data.nse_search_master`` / ``mbe.instruments.importer.SourceInstrumentRow``
    shape). Defines the primary (NSE) search universe.

    ``research_instruments`` — canonical instrument records for companies with
    a research page (``mbe.publish._canonical_instruments`` / the static
    ``instruments.json`` shape). Defines the research universe.

    ``screener_rows`` — the current model build's scored rows
    (``item["instrument_id"]`` / ``item["values"]``), used only to attach
    rank/score/confidence/risk to research-universe entries. Defines the
    ranking universe. A company can be in the research universe without a
    current score (e.g. a build failure); it never fabricates one.

    ``bse_rows`` (Phase 10B) — BSE listed-security rows
    (``mbe.data.bse_search_master`` shape). A row whose ISIN matches an
    existing record is folded in as a second ``ExchangeListing`` (the
    NSE/BSE cross-listing bridge — same canonical ``instrument_id`` because
    ``stable_instrument_id`` keys on ISIN alone when present); a row with no
    ISIN match becomes its own BSE-only search result. Never merged by name
    or symbol similarity alone.

    Every row present in any input is included: the research universe is
    authoritative for a company's identity when both sources describe it
    (richer sector/industry/aliases), but must never cause a company to
    disappear from search if a wider source is momentarily missing it.
    """
    if not search_universe_rows and not research_instruments and not bse_rows:
        raise ProviderError("search index build received no candidate rows")

    research_by_id = {row["instrument_id"]: row for row in (research_instruments or [])}
    screener_by_id = {row["instrument_id"]: row["values"] for row in (screener_rows or [])}

    records: dict[str, SearchIndexRecord] = {}
    classification_inputs: dict[str, list[ClassificationRecord]] = {}

    for row in search_universe_rows:
        instrument_id = _canonical_id(symbol=row["symbol"], isin=row.get("isin"), exchange=row.get("exchange", "NSE"))
        research = research_by_id.get(instrument_id)
        values = screener_by_id.get(instrument_id)
        classification_inputs.setdefault(instrument_id, []).append(
            _classification_record(instrument_id, row, source=ClassificationSource.EXCHANGE_MASTER)
        )
        if research:
            classification_inputs[instrument_id].append(
                _classification_record(instrument_id, research, source=ClassificationSource.RESEARCH_UNIVERSE)
            )
        records[instrument_id] = _merge_record(instrument_id, row, research, values)

    for instrument_id, research in research_by_id.items():
        if instrument_id in records:
            continue
        classification_inputs.setdefault(instrument_id, []).append(
            _classification_record(instrument_id, research, source=ClassificationSource.RESEARCH_UNIVERSE)
        )
        values = screener_by_id.get(instrument_id)
        records[instrument_id] = _merge_record(instrument_id, None, research, values)

    for row in (bse_rows or []):
        instrument_id = _canonical_id(symbol=row["symbol"], isin=row.get("isin"), exchange="BSE")
        classification_inputs.setdefault(instrument_id, []).append(
            _classification_record(instrument_id, row, source=ClassificationSource.EXCHANGE_MASTER)
        )
        existing = records.get(instrument_id)
        if existing:
            listing = _listing_from_row(row, is_primary=False)
            existing.listings = [*existing.listings, listing]
            if not existing.bse_code:
                existing.bse_code = row.get("bse_code")
            continue
        research = research_by_id.get(instrument_id)
        values = screener_by_id.get(instrument_id)
        if research:
            classification_inputs[instrument_id].append(
                _classification_record(instrument_id, research, source=ClassificationSource.RESEARCH_UNIVERSE)
            )
        records[instrument_id] = _merge_record(instrument_id, row, research, values)

    for instrument_id, record in records.items():
        candidates = classification_inputs.get(instrument_id, [])
        reconciled = select_canonical(candidates) if candidates else []
        selected = next((r for r in reconciled if r.is_selected_canonical), None)
        record.sector = selected.sector if selected else None
        record.industry = selected.industry if selected else None
        record.sub_industry = selected.sub_industry if selected else None
        record.sector_source = selected.source.value if selected and selected.sector else None
        record.industry_source = selected.source.value if selected and selected.industry else None
        record.sub_industry_source = selected.source.value if selected and selected.sub_industry else None
        record.classification_version = selected.classification_version if selected else (
            reconciled[0].classification_version if reconciled else None
        )
        record.classification_confidence = selected.confidence if selected else None
        record.classification_review_status = (
            selected.review_status.value if selected
            else (reconciled[0].review_status.value if reconciled else None)
        )
        record.classification_selection_reason = selected.selection_reason if selected else (
            reconciled[0].selection_reason if reconciled else None
        )
        record.classification_conflict = any(
            r.review_status.value == "conflict" for r in reconciled
        )

        assessment = assess_coverage(
            record.model_dump(mode="json"),
            has_financial_data=record.research_available,
            has_model_score=record.rank is not None and record.multibagger_score is not None,
            has_full_research_payload=record.research_available,
        )
        record.financial_available = assessment.financial_available

    return list(records.values())


def _merge_record(
    instrument_id: str,
    source_row: dict[str, Any] | None,
    research: dict[str, Any] | None,
    values: dict[str, Any] | None,
) -> SearchIndexRecord:
    provider_symbols = (source_row or {}).get("provider_symbols") or {}
    yahoo_symbol = provider_symbols.get("yahoo") or (
        f"{(research or source_row)['symbol']}.NS" if (research or source_row) else None
    )
    if research:
        primary_exchange = research.get("exchange", "NSE")
        listing = (
            _listing_from_row(source_row, is_primary=True) if source_row
            else ExchangeListing(
                exchange=primary_exchange, symbol=research["symbol"],
                bse_code=research.get("bse_code"), isin=research.get("isin"),
                listing_status=research.get("listing_status") or "active",
                is_primary=True, is_sme=research.get("is_sme"),
            )
        )
        return SearchIndexRecord(
            instrument_id=instrument_id,
            company_id=research.get("company_id"),
            display_name=research.get("display_name") or research["symbol"],
            legal_name=research.get("legal_name"),
            symbol=research["symbol"],
            exchange=primary_exchange,
            primary_exchange=primary_exchange,
            isin=research.get("isin") or (source_row or {}).get("isin"),
            bse_code=research.get("bse_code") or (source_row or {}).get("bse_code"),
            sector=None, sector_source=None, industry=None, industry_source=None,
            listing_status=research.get("listing_status") or "active",
            is_sme=research.get("is_sme"),
            market_cap_category=research.get("market_cap_category"),
            aliases=research.get("aliases") or [],
            provider_symbol=yahoo_symbol,
            listings=[listing],
            result_type=SearchResultType.MODELED if values else SearchResultType.KNOWN,
            research_available=True,
            rank=values.get("rank") if values else None,
            multibagger_score=values.get("multibagger_score") if values else None,
            confidence=values.get("confidence") if values else None,
            risk_score=values.get("risk_score") if values else None,
            report_url=canonical_company_url(instrument_id),
        )
    row = source_row or {}
    primary_exchange = row.get("exchange", "NSE")
    return SearchIndexRecord(
        instrument_id=instrument_id,
        company_id=None,
        display_name=row.get("company_name") or row["symbol"],
        legal_name=row.get("company_name"),
        symbol=row["symbol"],
        exchange=primary_exchange,
        primary_exchange=primary_exchange,
        isin=row.get("isin"),
        bse_code=row.get("bse_code"),
        sector=None, sector_source=None, industry=None, industry_source=None,
        listing_status=row.get("listing_status") or "active",
        is_sme=row.get("is_sme"),
        market_cap_category=None,
        aliases=[],
        provider_symbol=yahoo_symbol,
        listings=[_listing_from_row(row, is_primary=True)],
        result_type=SearchResultType.KNOWN,
        research_available=False,
        rank=None, multibagger_score=None, confidence=None, risk_score=None,
        report_url=canonical_company_url(instrument_id),
    )
