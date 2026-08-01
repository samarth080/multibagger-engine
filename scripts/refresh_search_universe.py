"""Refresh the pinned NSE search-universe snapshot.

Downloads the official main-board and SME listed-security CSVs and writes a
combined, versioned snapshot to ``universes/nse-search-universe.json``. This
mirrors how ``universes/nifty-smallcap250-instruments.json`` is pinned for the
ranking universe, but covers every listed NSE security rather than only index
constituents — the search universe is intentionally the larger of the two.

Usage: python scripts/refresh_search_universe.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mbe.data.nse_search_master import NSE_SEARCH_SOURCES, NseListedSecurityProvider  # noqa: E402

OUT_PATH = Path("universes/nse-search-universe.json")


def _to_master_record(row: dict) -> dict:
    return {
        "source_record_id": row["source_record_id"],
        "company_name": row["company_name"],
        "symbol": row["symbol"],
        "exchange": row["exchange"],
        "exchange_segment": row.get("exchange_segment"),
        "series": row.get("series"),
        "isin": row["isin"],
        "bse_code": None,
        "industry": None,
        "sector": None,
        "listing_status": row.get("listing_status", "active"),
        "listing_date": row["listing_date"].isoformat() if row.get("listing_date") else None,
        "delisting_date": None,
        "is_sme": row.get("is_sme"),
        "security_type": "equity",
        "provider_symbols": row.get("provider_symbols", {}),
        "aliases": [],
    }


def main() -> None:
    combined: list[dict] = []
    source_versions = []
    for segment in NSE_SEARCH_SOURCES:
        snapshot = NseListedSecurityProvider(segment).fetch_instruments()
        combined.extend(_to_master_record(row) for row in snapshot.records)
        source_versions.append(f"{segment}:{snapshot.source_version}")

    seen_isin = set()
    deduped = []
    for record in combined:
        if record["isin"] in seen_isin:
            continue
        seen_isin.add(record["isin"])
        deduped.append(record)
    deduped.sort(key=lambda r: r["symbol"])

    payload = {
        "source": "nse_listed_securities:combined",
        "source_url": "; ".join(v["url"] for v in NSE_SEARCH_SOURCES.values()),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_version": "; ".join(source_versions),
        "universe": "nse-search-universe",
        "n": len(deduped),
        "records": deduped,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"wrote {len(deduped)} records to {OUT_PATH}")


if __name__ == "__main__":
    main()
