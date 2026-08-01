"""Refresh the pinned BSE search-universe snapshot.

Tries the official BSE feed first (mbe.data.bse_search_master); BSE's site
was not reachable from this repository's development network as of Phase
10B (bot-protection error page / client-side app shell returned instead of
data — verified, not assumed). When the live fetch fails, this script falls
back to a small, explicitly-labeled CURATED STARTER FIXTURE: long-stable,
extremely well-documented large-cap BSE scrip codes for companies whose
ISIN is already verified against the live-fetched
universes/nse-search-universe.json (Phase 10A). This is not a claim of full
BSE main-board/SME coverage — see docs/search-architecture.md "BSE coverage
and honesty about sourcing". Re-run this script once an official feed is
reachable to replace the fixture with a real pull.

Usage: python scripts/refresh_bse_search_universe.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mbe.data.bse_search_master import BSE_SEARCH_SOURCES, BseListedSecurityProvider  # noqa: E402
from mbe.data.provider import ProviderError  # noqa: E402

OUT_PATH = Path("universes/bse-search-universe.json")

# Curated starter set: long-stable BSE scrip codes for mega-cap companies,
# selected only where confidence in the code is very high (companies that
# have not undergone a demerger/relisting that would have changed it). ISIN
# is cross-checked against universes/nse-search-universe.json at generation
# time, not merely asserted here.
CURATED_STARTER_SET = [
    # (bse_code, security_id, security_name, isin, group, industry)
    ("500325", "RELIANCE", "Reliance Industries Ltd.", "INE002A01018", "A", "Refineries"),
    ("532540", "TCS", "Tata Consultancy Services Ltd.", "INE467B01029", "A", "IT Consulting & Software"),
    ("500209", "INFY", "Infosys Ltd.", "INE009A01021", "A", "IT Consulting & Software"),
    ("500180", "HDFCBANK", "HDFC Bank Ltd.", "INE040A01034", "A", "Banks"),
    ("532174", "ICICIBANK", "ICICI Bank Ltd.", "INE090A01021", "A", "Banks"),
    ("500875", "ITC", "ITC Ltd.", "INE154A01025", "A", "Cigarettes & Tobacco Products"),
    ("500112", "SBIN", "State Bank of India", "INE062A01020", "A", "Banks"),
    ("507685", "WIPRO", "Wipro Ltd.", "INE075A01022", "A", "IT Consulting & Software"),
    ("500510", "LT", "Larsen & Toubro Ltd.", "INE018A01030", "A", "Construction & Engineering"),
    ("532500", "MARUTI", "Maruti Suzuki India Ltd.", "INE585B01010", "A", "Automobiles"),
    ("532215", "AXISBANK", "Axis Bank Ltd.", "INE238A01034", "A", "Banks"),
    ("500247", "KOTAKBANK", "Kotak Mahindra Bank Ltd.", "INE237A01036", "A", "Banks"),
    ("500034", "BAJFINANCE", "Bajaj Finance Ltd.", "INE296A01032", "A", "Finance (NBFC)"),
    ("532454", "BHARTIARTL", "Bharti Airtel Ltd.", "INE397D01024", "A", "Telecom Services"),
    ("500696", "HINDUNILVR", "Hindustan Unilever Ltd.", "INE030A01027", "A", "Personal Products"),
    ("500790", "NESTLEIND", "Nestle India Ltd.", "INE239A01024", "A", "Food Products"),
    ("524715", "SUNPHARMA", "Sun Pharmaceutical Industries Ltd.", "INE044A01036", "A", "Pharmaceuticals"),
    ("500820", "ASIANPAINT", "Asian Paints Ltd.", "INE021A01026", "A", "Paints"),
    ("541154", "HAL", "Hindustan Aeronautics Ltd.", "INE066F01020", "A", "Aerospace & Defense"),
    ("500049", "BEL", "Bharat Electronics Ltd.", "INE263A01024", "A", "Aerospace & Defense"),
]


def _curated_rows() -> list[dict]:
    nse_by_isin = {
        row["isin"]: row["symbol"]
        for row in json.loads(Path("universes/nse-search-universe.json").read_text())["records"]
    }
    rows = []
    for bse_code, security_id, name, isin, group, industry in CURATED_STARTER_SET:
        if isin not in nse_by_isin:
            raise SystemExit(f"curated BSE fixture ISIN {isin} ({security_id}) not found in the verified NSE snapshot")
        rows.append({
            "source_record_id": isin,
            "company_name": name,
            "symbol": security_id,
            "exchange": "BSE",
            "exchange_segment": None,
            "series": group,
            "isin": isin,
            "bse_code": bse_code,
            "industry": industry,
            "listing_status": "active",
            "is_sme": False,
        })
    return rows


def main() -> None:
    live_error: str | None = None
    try:
        snapshot = BseListedSecurityProvider().fetch_instruments()
        records = snapshot.records
        source = snapshot.source
        source_url = snapshot.source_url
        source_version = snapshot.source_version
        coverage_status = "live_official_source"
    except ProviderError as exc:
        live_error = str(exc)
        records = _curated_rows()
        source = "curated_starter_fixture"
        source_url = BSE_SEARCH_SOURCES["main"]
        source_version = "curated:2026-08-01"
        coverage_status = "curated_starter_fixture_pending_live_verification"

    payload = {
        "source": source,
        "source_url": source_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_version": source_version,
        "universe": "bse-search-universe",
        "coverage_status": coverage_status,
        "coverage_note": (
            "Live BSE fetch failed; falling back to a curated starter set of "
            f"{len(records)} long-stable large-cap scrip codes, ISIN-cross-checked "
            f"against the live-fetched NSE snapshot. Live fetch error: {live_error}"
        ) if live_error else "Live official BSE fetch succeeded.",
        "n": len(records),
        "records": records,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"wrote {len(records)} records to {OUT_PATH} ({coverage_status})")


if __name__ == "__main__":
    main()
