"""Lightweight (non-research) company payload.

For a search-universe company without a research page — every NSE company
outside the current 250-name Nifty Smallcap research/ranking universe. Shows
identity and a live quote only. Never fabricates a score, rank, explanation,
strength, risk, checklist or score history: those sections simply do not
exist for a company the model has not evaluated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mbe.universal.cache import read_cached_report

RANKING_UNIVERSE_BADGE = "Not currently included in the Multibagger ranking universe."
SCORING_DISCLOSURE = "This company has not yet been evaluated by the Multibagger scoring model."

_UNIVERSAL_ARTIFACTS_DIR = Path("site/api/v1/universal-scores")


def _universal_for(instrument_id: str) -> dict | None:
    """Reads the pre-warmed Universal Research Score artifact for
    instrument_id, if one exists. Never computes live — a missing artifact
    simply means None (rendered as "not yet refreshed"). Shared by the
    static, incremental-rebuild and DB-backed dynamic research builders so
    all three read the exact same prewarmed-artifact directory the same way."""
    cached = read_cached_report(_UNIVERSAL_ARTIFACTS_DIR / f"{instrument_id}.json")
    return cached.get("report") if cached else None


def build_lightweight_research(
    record: dict, quote: dict | None, *, now: datetime | None = None,
) -> dict:
    if record.get("research_available"):
        raise ValueError(
            "build_lightweight_research refuses a research_available record — "
            "that company has a full research page and must not be downgraded."
        )
    now = now or datetime.now(timezone.utc)
    listing_status = record.get("listing_status", "active")
    is_inactive = listing_status not in {"active", "unknown"}
    return {
        "identity": {
            "instrument_id": record["instrument_id"],
            "display_name": record["display_name"],
            "legal_name": record.get("legal_name"),
            "symbol": record["symbol"],
            "exchange": record.get("exchange", "NSE"),
            "primary_exchange": record.get("primary_exchange") or record.get("exchange", "NSE"),
            "isin": record.get("isin"),
            "bse_code": record.get("bse_code"),
            "sector": record.get("sector"),
            "sector_source": record.get("sector_source"),
            "industry": record.get("industry"),
            "industry_source": record.get("industry_source"),
            "listing_status": listing_status,
            "is_sme": record.get("is_sme"),
            "listings": record.get("listings") or [],
        },
        "quote": quote,
        "quote_state": "available" if quote else "unavailable",
        "ranking_universe_badge": RANKING_UNIVERSE_BADGE,
        "scoring_disclosure": SCORING_DISCLOSURE,
        "is_inactive": is_inactive,
        "listing_status_disclosure": (
            f"This listing's status is {listing_status} — it may not be actively tradable."
            if is_inactive else None
        ),
        "canonical_url": record.get("report_url") or f"/company/{record['instrument_id']}.html",
        "generated_at": now.isoformat(),
    }
