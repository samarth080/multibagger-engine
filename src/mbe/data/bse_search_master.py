"""Search-universe source: BSE listed-securities master (Phase 10B).

Additive to `mbe.data.nse_search_master`, not a replacement — BSE listings
are cross-linked to the same canonical instrument as an NSE listing when
ISIN matches (see `mbe.instruments.importer.import_instruments`'s
cross-listing branch), never merged by name/symbol alone.

Honesty note: BSE's official endpoints (`api.bseindia.com`,
`www.bseindia.com` downloads) return bot-protection error pages or the
site's client-side app shell when fetched from this repository's
development network — verified during Phase 10B, not assumed. The fetch
path below follows the exact same fail-closed contract as the NSE provider
and is ready for a reachable official feed; the committed pinned snapshot
(`universes/bse-search-universe.json`) is instead a small, explicitly
labeled starter fixture — see `scripts/refresh_bse_search_universe.py` and
docs/search-architecture.md.
"""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel

from mbe.data.provider import ProviderError
from mbe.data.universe_nse import default_http

# Documented shape of a BSE "list of active/all securities" export: Security
# Code (6-digit scrip code), Security Id (short trading symbol), Security
# Name (company name), Status, Group (A/B/T/Z/M/MT...), Face Value, ISIN No
# and Industry. Column names may need adjustment once a live feed is
# reachable and its exact export format can be confirmed.
BSE_SEARCH_SOURCES: dict[str, str] = {
    "main": "https://www.bseindia.com/downloads1/List_Scrips.csv",
}

_STATUS_MAP = {
    "active": "active",
    "suspended": "suspended",
    "delisted": "delisted",
    "inactive": "inactive",
}


def _strip_keys(row: dict[str, str]) -> dict[str, str]:
    return {(key or "").strip(): (value or "").strip() for key, value in row.items()}


def parse_bse_listed_security_csv(text: str) -> list[dict[str, Any]]:
    """Parse a BSE listed-securities export.

    Fails closed (``ProviderError``) on a missing 'Security Code' column or
    an empty result, matching ``mbe.data.nse_search_master``'s discipline.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    fieldnames = {name.strip() for name in (reader.fieldnames or [])}
    if "Security Code" not in fieldnames:
        raise ProviderError(
            f"BSE listed-security CSV missing 'Security Code' column (got {sorted(fieldnames)})"
        )
    rows: list[dict[str, Any]] = []
    for raw in reader:
        row = _strip_keys(raw)
        code = row.get("Security Code", "")
        symbol = row.get("Security Id", "")
        name = row.get("Security Name", "")
        isin = row.get("ISIN No", "")
        status = _STATUS_MAP.get(row.get("Status", "").strip().lower(), "unknown")
        group = row.get("Group", "") or None
        industry = row.get("Industry", "") or None
        if not code or not symbol or not name or not isin:
            continue
        if not (len(code) == 6 and code.isdigit()):
            continue
        rows.append({
            "source_record_id": isin or code,
            "company_name": name,
            "symbol": symbol,
            "exchange": "BSE",
            "exchange_segment": "SME" if group in {"M", "MT"} else None,
            "series": group,
            "isin": isin,
            "bse_code": code,
            "industry": industry,
            "listing_status": status if status != "unknown" else "active",
            "is_sme": group in {"M", "MT"} if group else False,
        })
    if not rows:
        raise ProviderError("BSE listed-security CSV parsed to an empty list")
    return rows


class BseSearchMasterSnapshot(BaseModel):
    source: str
    source_url: str
    source_version: str
    retrieved_at: datetime
    records: list[dict[str, Any]]


class BseListedSecurityProvider:
    """Official BSE listed-security CSV as a search-universe source.

    Mirrors ``mbe.data.nse_search_master.NseListedSecurityProvider``
    exactly: same fail-closed contract, same fetcher-injection seam for
    tests, same snapshot shape. Feeds the search universe only — never the
    ranking universe (no ``index_code`` is ever implied here).
    """

    name = "bse_search_master"

    def __init__(self, segment: str = "main", fetcher: Callable[[str], str] = default_http):
        if segment not in BSE_SEARCH_SOURCES:
            raise KeyError(f"unsupported BSE search segment {segment!r}")
        self.segment = segment
        self.url = BSE_SEARCH_SOURCES[segment]
        self.fetcher = fetcher

    def fetch_instruments(self) -> BseSearchMasterSnapshot:
        try:
            payload = self.fetcher(self.url)
            records = parse_bse_listed_security_csv(payload)
        except Exception as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(f"BSE search-master fetch failed for {self.segment}") from exc
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return BseSearchMasterSnapshot(
            source=f"bse_listed_securities:{self.segment}", source_url=self.url,
            source_version=f"sha256:{digest}", retrieved_at=datetime.now(timezone.utc),
            records=records,
        )

    def health(self) -> dict:
        return {
            "provider": self.name, "status": "configured",
            "capability": "search_universe", "segment": self.segment,
        }
