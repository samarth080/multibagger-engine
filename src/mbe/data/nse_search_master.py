"""Search-universe source: official NSE listed-securities master.

The search universe is deliberately independent from the ranking universe
(``NiftyIndexInstrumentProvider`` / ``nifty-smallcap250``). It exists so a user
can find *any* NSE-listed company — Reliance, TCS, HAL — even though those
companies are not currently scored by the Multibagger model.

Sources are the same public, documented NSE archive CSVs already trusted for
official filings (``nsearchives.nseindia.com``), not a paid provider and not
an uncontrolled scrape. Series is restricted to ``EQ``/``BE``/``BZ`` (ordinary
equity) plus the SME board's ``ST`` series; other listed instrument types
(ETFs, debt, etc.) are out of scope for company search.
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import date, datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel

from mbe.data.provider import ProviderError
from mbe.data.universe_nse import default_http

# Documented public archive endpoints. Main-board and SME lists are separate
# files with slightly different column names; both are handled below.
NSE_SEARCH_SOURCES: dict[str, dict[str, str]] = {
    "nse_equity": {
        "url": "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
        "segment": "main",
    },
    "nse_sme": {
        "url": "https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv",
        "segment": "sme",
    },
}

_MAIN_SERIES = {"EQ", "BE", "BZ"}
_SME_SERIES = {"ST", "SM"}


def _strip_keys(row: dict[str, str]) -> dict[str, str]:
    return {(key or "").strip(): (value or "").strip() for key, value in row.items()}


def _parse_listing_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def parse_nse_listed_security_csv(text: str, *, is_sme: bool = False) -> list[dict[str, Any]]:
    """Parse the official NSE main-board or SME listed-security CSV.

    Fails closed (``ProviderError``) on a missing symbol column or an empty
    result — a reshaped/empty source must never look like a working run with
    zero rows, since that would silently collapse the search universe.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    fieldnames = {name.strip() for name in (reader.fieldnames or [])}
    if "SYMBOL" not in fieldnames:
        raise ProviderError(
            f"NSE listed-security CSV missing 'SYMBOL' column (got {sorted(fieldnames)})"
        )
    allowed_series = _SME_SERIES if is_sme else _MAIN_SERIES
    rows: list[dict[str, Any]] = []
    for raw in reader:
        row = _strip_keys(raw)
        symbol = row.get("SYMBOL", "")
        name = row.get("NAME OF COMPANY") or row.get("NAME_OF_COMPANY") or ""
        series = (row.get("SERIES") or row.get("SERIES", "")).upper()
        isin = row.get("ISIN NUMBER") or row.get("ISIN_NUMBER") or ""
        listing_date = row.get("DATE OF LISTING") or row.get("DATE_OF_LISTING") or ""
        if not symbol or not name or not isin:
            continue
        if allowed_series and series and series not in allowed_series:
            continue
        rows.append({
            "source_record_id": isin or symbol,
            "company_name": name,
            "symbol": symbol,
            "exchange": "NSE",
            "exchange_segment": "SME" if is_sme else None,
            "series": series or None,
            "isin": isin,
            "listing_status": "active",
            "listing_date": _parse_listing_date(listing_date),
            "is_sme": bool(is_sme),
            "provider_symbols": {"yahoo": f"{symbol}.NS"},
        })
    if not rows:
        raise ProviderError("NSE listed-security CSV parsed to an empty list")
    return rows


class SearchMasterSnapshot(BaseModel):
    source: str
    source_url: str
    source_version: str
    retrieved_at: datetime
    records: list[dict[str, Any]]


class NseListedSecurityProvider:
    """Official main-board or SME listed-security CSV as a search-universe source.

    Distinct from ``NiftyIndexInstrumentProvider``: that adapter feeds the
    *ranking* universe (index constituents only). This one feeds the *search*
    universe (every listed security NSE publishes on the segment), so a user
    can find companies the ranking model has not modelled yet.
    """

    name = "nse_search_master"

    def __init__(self, segment: str = "nse_equity", fetcher: Callable[[str], str] = default_http):
        if segment not in NSE_SEARCH_SOURCES:
            raise KeyError(f"unsupported NSE search segment {segment!r}")
        self.segment = segment
        self.url = NSE_SEARCH_SOURCES[segment]["url"]
        self.is_sme = NSE_SEARCH_SOURCES[segment]["segment"] == "sme"
        self.fetcher = fetcher

    def fetch_instruments(self) -> SearchMasterSnapshot:
        try:
            payload = self.fetcher(self.url)
            records = parse_nse_listed_security_csv(payload, is_sme=self.is_sme)
        except Exception as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(f"search-master fetch failed for {self.segment}") from exc
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return SearchMasterSnapshot(
            source=f"nse_listed_securities:{self.segment}", source_url=self.url,
            source_version=f"sha256:{digest}", retrieved_at=datetime.now(timezone.utc),
            records=records,
        )

    def health(self) -> dict:
        return {
            "provider": self.name, "status": "configured",
            "capability": "search_universe", "segment": self.segment,
        }
