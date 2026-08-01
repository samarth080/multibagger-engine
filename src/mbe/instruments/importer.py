"""Idempotent, collision-reporting instrument-master synchronization."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from mbe.db.models import (
    CompanyRow, DataSourceRow, ExchangeRow, FreshnessRow, ImportIssueRow, ImportRunRow,
    IndexMembershipRow, IndexRow, IndustryRow, InstrumentAliasRow,
    InstrumentListingRow, InstrumentRow, ProviderSymbolRow, SectorRow,
)
from mbe.models.instrument import (
    IDENTITY_NAMESPACE, normalize_name, normalize_symbol, stable_company_id,
    stable_instrument_id,
)


class SourceInstrumentRow(BaseModel):
    source_record_id: str | None = None
    company_name: str | None = None
    symbol: str
    exchange: str = "NSE"
    exchange_segment: str | None = None
    series: str | None = None
    isin: str | None = None
    bse_code: str | None = None
    industry: str | None = None
    sector: str | None = None
    listing_status: str = "active"
    listing_date: date | None = None
    delisting_date: date | None = None
    is_sme: bool | None = None
    security_type: str = "equity"
    provider_symbols: dict[str, str] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)

    @field_validator("symbol")
    @classmethod
    def valid_symbol(cls, value: str) -> str:
        value = normalize_symbol(value.removesuffix(".NS").removesuffix(".BO"))
        if not value or len(value) > 40:
            raise ValueError("invalid exchange symbol")
        return value

    @field_validator("isin")
    @classmethod
    def valid_isin(cls, value: str | None) -> str | None:
        if not value:
            return None
        value = normalize_symbol(value)
        if len(value) != 12 or not value[:2].isalpha() or not value[-1].isdigit():
            raise ValueError("invalid ISIN")
        return value


class ImportSummary(BaseModel):
    import_run_id: str
    source: str
    source_version: str | None = None
    source_records_read: int = 0
    instruments_created: int = 0
    instruments_updated: int = 0
    records_unchanged: int = 0
    symbols_added: int = 0
    symbols_changed: int = 0
    aliases_added: int = 0
    duplicate_candidates: int = 0
    ambiguous_records: int = 0
    invalid_records: int = 0
    cross_listings_added: int = 0
    active_listings: int = 0
    inactive_listings: int = 0
    index_memberships_added: int = 0
    index_memberships_closed: int = 0
    duration_seconds: float = 0
    dry_run: bool = False


def parse_nifty_instrument_csv(text: str) -> list[dict[str, Any]]:
    """Retain the official index CSV identity fields the old loader discarded."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    required = {"Company Name", "Industry", "Symbol", "Series", "ISIN Code"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError(
            f"instrument CSV missing columns {sorted(required - set(reader.fieldnames or []))}"
        )
    return [
        {
            "source_record_id": row.get("ISIN Code") or row.get("Symbol"),
            "company_name": row.get("Company Name") or None,
            "symbol": row.get("Symbol", ""),
            "exchange": "NSE",
            "series": row.get("Series") or None,
            "isin": row.get("ISIN Code") or None,
            "industry": row.get("Industry") or None,
            "listing_status": "active",
            "provider_symbols": {"yahoo": f"{row.get('Symbol', '').strip()}.NS"},
        }
        for row in reader
    ]


def pinned_universe_rows(tickers: Iterable[str]) -> list[dict[str, Any]]:
    """Compatibility import where the pinned source exposes symbols only."""
    rows = []
    for ticker in tickers:
        symbol = ticker.removesuffix(".NS")
        rows.append({
            "source_record_id": f"NSE:{symbol}",
            "symbol": symbol,
            "exchange": "NSE",
            "listing_status": "active",
            "provider_symbols": {"yahoo": ticker},
        })
    return rows


def _source(session: Session, code: str) -> DataSourceRow:
    row = session.scalar(select(DataSourceRow).where(DataSourceRow.code == code))
    if row:
        return row
    row = DataSourceRow(
        code=code, name=code.replace("_", " ").title(), source_type="instrument_master",
        is_official=code.startswith("nifty_indices") or code.startswith("nse"),
    )
    session.add(row)
    session.flush()
    return row


def _exchange(session: Session, code: str) -> ExchangeRow:
    code = code.upper()
    row = session.get(ExchangeRow, code)
    if row:
        return row
    defaults = {
        "NSE": ("National Stock Exchange of India", "XNSE"),
        "BSE": ("BSE Limited", "XBOM"),
    }
    name, mic = defaults.get(code, (code, None))
    row = ExchangeRow(
        code=code, name=name, mic=mic, country="IN", currency="INR",
        timezone="Asia/Kolkata",
    )
    session.add(row)
    session.flush()
    return row


def _classification(session: Session, sector: str | None, industry: str | None) -> tuple[int | None, int | None]:
    sector_id = industry_id = None
    if sector:
        sector_row = session.scalar(select(SectorRow).where(SectorRow.name == sector))
        if not sector_row:
            sector_row = SectorRow(name=sector)
            session.add(sector_row)
            session.flush()
        sector_id = sector_row.sector_id
    if industry:
        industry_row = session.scalar(select(IndustryRow).where(
            IndustryRow.name == industry, IndustryRow.sector_id == sector_id,
            IndustryRow.sub_industry.is_(None),
        ))
        if not industry_row:
            industry_row = IndustryRow(name=industry, sector_id=sector_id)
            session.add(industry_row)
            session.flush()
        industry_id = industry_row.industry_id
    return sector_id, industry_id


def _matches(session: Session, row: SourceInstrumentRow) -> list[str]:
    candidate_sets: list[set[str]] = []
    if row.isin:
        candidate_sets.append(set(session.scalars(select(InstrumentListingRow.instrument_id).where(
            InstrumentListingRow.isin == row.isin,
        )).all()))
    for provider, symbol in row.provider_symbols.items():
        matches = set(session.scalars(select(ProviderSymbolRow.instrument_id).where(
            ProviderSymbolRow.provider == provider.casefold(),
            ProviderSymbolRow.provider_symbol == symbol,
            ProviderSymbolRow.valid_to.is_(None),
        )).all())
        if matches:
            candidate_sets.append(matches)
    symbol_matches = set(session.scalars(select(InstrumentListingRow.instrument_id).where(
        InstrumentListingRow.exchange_code == row.exchange.upper(),
        InstrumentListingRow.symbol == row.symbol,
        InstrumentListingRow.valid_to.is_(None),
    )).all())
    if symbol_matches:
        candidate_sets.append(symbol_matches)
    union = set().union(*candidate_sets) if candidate_sets else set()
    return sorted(union)


def import_instruments(
    session: Session,
    records: Iterable[dict[str, Any] | SourceInstrumentRow],
    *,
    source_code: str,
    source_version: str | None = None,
    source_timestamp: datetime | None = None,
    index_code: str | None = None,
    dry_run: bool = False,
) -> ImportSummary:
    started = time.monotonic()
    run_id = str(uuid.uuid4())
    summary = ImportSummary(
        import_run_id=run_id, source=source_code, source_version=source_version,
        dry_run=dry_run,
    )
    materialized = list(records)
    if not materialized:
        raise ValueError("instrument import source is empty; refusing to modify memberships")
    summary.source_records_read = len(materialized)
    source = _source(session, source_code)
    run = ImportRunRow(
        import_run_id=run_id, source_id=source.source_id, source_version=source_version,
        source_timestamp=source_timestamp, started_at=datetime.now(timezone.utc),
        status="running", source_hash=hashlib.sha256(
            json.dumps([r.model_dump(mode="json") if isinstance(r, BaseModel) else r for r in materialized], sort_keys=True, default=str).encode()
        ).hexdigest(),
    )
    session.add(run)
    session.flush()
    index_row = None
    membership_date = (source_timestamp or datetime.now(timezone.utc)).date()
    if index_code:
        index_row = session.scalar(select(IndexRow).where(IndexRow.code == index_code))
        if not index_row:
            index_row = IndexRow(
                index_id=str(uuid.uuid5(IDENTITY_NAMESPACE, f"index:IN:{index_code}")),
                code=index_code, name=index_code.replace("-", " ").title(),
                provider=source_code, market="IN",
            )
            session.add(index_row)
            session.flush()
    seen_instrument_ids: set[str] = set()

    for index, raw in enumerate(materialized):
        try:
            row = raw if isinstance(raw, SourceInstrumentRow) else SourceInstrumentRow(**raw)
        except ValidationError as exc:
            summary.invalid_records += 1
            session.add(ImportIssueRow(
                import_run_id=run_id, source_record_id=str(index), issue_type="invalid",
                message=str(exc), raw_record=raw if isinstance(raw, dict) else None,
                resolution_status="unresolved",
            ))
            continue
        _exchange(session, row.exchange)
        matches = _matches(session, row)
        conflicting_isins: dict[str, list[str]] = {}
        if row.isin:
            for candidate_id in matches:
                known = set(session.scalars(select(InstrumentListingRow.isin).where(
                    InstrumentListingRow.instrument_id == candidate_id,
                    InstrumentListingRow.isin.is_not(None),
                )).all())
                if known and row.isin not in known:
                    conflicting_isins[candidate_id] = sorted(known)
        if conflicting_isins:
            summary.ambiguous_records += 1
            summary.duplicate_candidates += len(conflicting_isins)
            session.add(ImportIssueRow(
                import_run_id=run_id, source_record_id=row.source_record_id,
                issue_type="conflicting_identity",
                message=f"incoming ISIN {row.isin} conflicts with matched records {conflicting_isins}",
                raw_record=row.model_dump(mode="json"), resolution_status="unresolved",
            ))
            continue
        if len(matches) > 1:
            summary.ambiguous_records += 1
            summary.duplicate_candidates += len(matches)
            session.add(ImportIssueRow(
                import_run_id=run_id, source_record_id=row.source_record_id,
                issue_type="ambiguous_identity",
                message=f"record matches multiple instruments: {', '.join(matches)}",
                raw_record=row.model_dump(mode="json"), resolution_status="unresolved",
            ))
            continue

        sector_id, industry_id = _classification(session, row.sector, row.industry)
        instrument = session.get(InstrumentRow, matches[0]) if matches else None
        changed = False
        if instrument is None:
            instrument_id = stable_instrument_id(
                exchange_code=row.exchange, symbol=row.symbol, isin=row.isin,
                source_record_id=row.source_record_id,
            )
            company_id = stable_company_id(
                country="IN", isin=row.isin, name=row.company_name,
                fallback=f"{row.exchange}:{row.symbol}",
            )
            company = session.get(CompanyRow, company_id)
            if not company:
                company = CompanyRow(
                    company_id=company_id, legal_name=row.company_name,
                    current_legal_name=row.company_name, display_name=row.company_name,
                    country="IN",
                )
                session.add(company)
            instrument = InstrumentRow(
                instrument_id=instrument_id, company_id=company_id,
                security_type=row.security_type, country="IN", currency="INR",
                timezone="Asia/Kolkata", sector_id=sector_id, industry_id=industry_id,
                quality_status="valid" if row.isin and row.company_name else "warning",
            )
            session.add(instrument)
            session.flush()
            session.add(InstrumentListingRow(
                instrument_id=instrument_id, exchange_code=row.exchange.upper(),
                symbol=row.symbol, bse_code=row.bse_code, isin=row.isin,
                exchange_segment=row.exchange_segment, exchange_series=row.series,
                status=row.listing_status, listing_date=row.listing_date,
                delisting_date=row.delisting_date, is_primary=True, is_sme=row.is_sme,
                valid_from=row.listing_date,
            ))
            summary.instruments_created += 1
            summary.symbols_added += 1
            changed = True
        else:
            instrument.updated_at = datetime.now(timezone.utc)
            if sector_id and instrument.sector_id != sector_id:
                instrument.sector_id, changed = sector_id, True
            if industry_id and instrument.industry_id != industry_id:
                instrument.industry_id, changed = industry_id, True
            company = session.get(CompanyRow, instrument.company_id) if instrument.company_id else None
            if company and row.company_name and company.current_legal_name != row.company_name:
                if company.current_legal_name:
                    old_norm = normalize_name(company.current_legal_name)
                    exists = session.scalar(select(InstrumentAliasRow).where(
                        InstrumentAliasRow.instrument_id == instrument.instrument_id,
                        InstrumentAliasRow.alias_type == "former_name",
                        InstrumentAliasRow.normalized_value == old_norm,
                    ))
                    if not exists:
                        session.add(InstrumentAliasRow(
                            instrument_id=instrument.instrument_id, alias_type="former_name",
                            value=company.current_legal_name, normalized_value=old_norm,
                            source_id=source.source_id,
                        ))
                        summary.aliases_added += 1
                company.current_legal_name = row.company_name
                company.display_name = row.company_name
                company.updated_at = datetime.now(timezone.utc)
                changed = True
            current_listing = session.scalar(select(InstrumentListingRow).where(
                InstrumentListingRow.instrument_id == instrument.instrument_id,
                InstrumentListingRow.exchange_code == row.exchange.upper(),
                InstrumentListingRow.valid_to.is_(None),
            ))
            if current_listing and current_listing.symbol != row.symbol:
                old = current_listing.symbol
                current_listing.valid_to = date.today()
                session.add(InstrumentAliasRow(
                    instrument_id=instrument.instrument_id, alias_type="former_symbol",
                    value=old, normalized_value=normalize_name(old), source_id=source.source_id,
                ))
                session.add(InstrumentListingRow(
                    instrument_id=instrument.instrument_id, exchange_code=row.exchange.upper(),
                    symbol=row.symbol, bse_code=row.bse_code, isin=row.isin,
                    exchange_segment=row.exchange_segment, exchange_series=row.series,
                    status=row.listing_status, listing_date=row.listing_date,
                    delisting_date=row.delisting_date, is_primary=True, is_sme=row.is_sme,
                    valid_from=date.today(),
                ))
                summary.symbols_changed += 1
                summary.aliases_added += 1
                changed = True
            elif current_listing:
                mutable = {
                    "exchange_series": row.series,
                    "exchange_segment": row.exchange_segment,
                    "status": row.listing_status,
                    "delisting_date": row.delisting_date,
                    "is_sme": row.is_sme,
                }
                for field, value in mutable.items():
                    if value is not None and getattr(current_listing, field) != value:
                        setattr(current_listing, field, value)
                        changed = True
            else:
                # Instrument already exists (matched via ISIN, provider symbol
                # or same-exchange symbol) but has no listing yet on THIS
                # row's exchange: a new exchange listing (e.g. a BSE row
                # cross-linking to an NSE-created instrument by ISIN), not a
                # symbol change. Never primary — the exchange that first
                # created the instrument keeps that status.
                session.add(InstrumentListingRow(
                    instrument_id=instrument.instrument_id, exchange_code=row.exchange.upper(),
                    symbol=row.symbol, bse_code=row.bse_code, isin=row.isin,
                    exchange_segment=row.exchange_segment, exchange_series=row.series,
                    status=row.listing_status, listing_date=row.listing_date,
                    delisting_date=row.delisting_date, is_primary=False, is_sme=row.is_sme,
                    valid_from=row.listing_date,
                ))
                summary.cross_listings_added += 1
                changed = True
        for provider, provider_symbol in row.provider_symbols.items():
            provider = provider.casefold()
            exists = session.scalar(select(ProviderSymbolRow).where(
                ProviderSymbolRow.instrument_id == instrument.instrument_id,
                ProviderSymbolRow.provider == provider,
                ProviderSymbolRow.provider_symbol == provider_symbol,
                ProviderSymbolRow.valid_to.is_(None),
            ))
            if not exists:
                collision = session.scalar(select(ProviderSymbolRow).where(
                    ProviderSymbolRow.provider == provider,
                    ProviderSymbolRow.provider_symbol == provider_symbol,
                    ProviderSymbolRow.valid_to.is_(None),
                ))
                if collision and collision.instrument_id != instrument.instrument_id:
                    summary.ambiguous_records += 1
                    session.add(ImportIssueRow(
                        import_run_id=run_id, source_record_id=row.source_record_id,
                        issue_type="provider_symbol_collision",
                        message=f"{provider}:{provider_symbol} belongs to {collision.instrument_id}",
                        raw_record=row.model_dump(mode="json"), resolution_status="unresolved",
                    ))
                    continue
                session.add(ProviderSymbolRow(
                    instrument_id=instrument.instrument_id, provider=provider,
                    provider_symbol=provider_symbol, is_primary=True, source_id=source.source_id,
                ))
                changed = True
        for alias in row.aliases:
            norm = normalize_name(alias)
            exists = session.scalar(select(InstrumentAliasRow).where(
                InstrumentAliasRow.instrument_id == instrument.instrument_id,
                InstrumentAliasRow.normalized_value == norm,
            ))
            if not exists:
                session.add(InstrumentAliasRow(
                    instrument_id=instrument.instrument_id, alias_type="common_name",
                    value=alias, normalized_value=norm, source_id=source.source_id,
                ))
                summary.aliases_added += 1
                changed = True
        seen_instrument_ids.add(instrument.instrument_id)
        if index_row:
            membership = session.scalar(select(IndexMembershipRow).where(
                IndexMembershipRow.index_id == index_row.index_id,
                IndexMembershipRow.instrument_id == instrument.instrument_id,
                IndexMembershipRow.effective_to.is_(None),
            ))
            if not membership:
                session.add(IndexMembershipRow(
                    index_id=index_row.index_id,
                    instrument_id=instrument.instrument_id,
                    effective_from=membership_date,
                    source_id=source.source_id,
                ))
                summary.index_memberships_added += 1
        if matches:
            if changed:
                summary.instruments_updated += 1
            else:
                summary.records_unchanged += 1
        if row.listing_status == "active":
            summary.active_listings += 1
        else:
            summary.inactive_listings += 1

    # Only treat absence as an index exit when the complete source validated;
    # a partial/bad download must never remove memberships.
    if index_row and not summary.invalid_records and not summary.ambiguous_records:
        active_memberships = session.scalars(select(IndexMembershipRow).where(
            IndexMembershipRow.index_id == index_row.index_id,
            IndexMembershipRow.effective_to.is_(None),
        )).all()
        for membership in active_memberships:
            if membership.instrument_id not in seen_instrument_ids:
                membership.effective_to = membership_date
                summary.index_memberships_closed += 1

    summary.duration_seconds = round(time.monotonic() - started, 3)
    run.finished_at = datetime.now(timezone.utc)
    run.status = "dry_run" if dry_run else "complete"
    run.summary = summary.model_dump(mode="json")
    freshness = session.scalar(select(FreshnessRow).where(
        FreshnessRow.dataset == "instrument_master",
        FreshnessRow.partition_key == source_code,
    ))
    values = {
        "source_id": source.source_id,
        "import_run_id": run_id,
        "state": "fresh",
        "source_timestamp": source_timestamp,
        "retrieved_at": run.finished_at,
        "normalized_at": run.finished_at,
        "data_version": source_version,
        "quality_status": (
            "warning" if summary.invalid_records or summary.ambiguous_records else "valid"
        ),
        "warning": (
            f"{summary.invalid_records} invalid; {summary.ambiguous_records} ambiguous"
            if summary.invalid_records or summary.ambiguous_records else None
        ),
        "raw_payload_hash": run.source_hash,
    }
    if freshness:
        for field, value in values.items():
            setattr(freshness, field, value)
    else:
        session.add(FreshnessRow(
            dataset="instrument_master", partition_key=source_code, **values,
        ))
    session.flush()
    if dry_run:
        session.rollback()
    else:
        session.commit()
    return summary
