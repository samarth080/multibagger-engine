"""Curated starter universes (v0.1). v0.2 replaces these with full exchange
lists ingested from NSE/BSE indices. Liquid names across sectors, chosen for
coverage breadth, not as recommendations.

Downloaded universes (NSE indices, Wikipedia-derived US samples) are refetched
on a cache TTL, so their membership drifts as indices rebalance. That is right
for production screening — you want today's index — and wrong for evidence: two
ablation runs a week apart silently compare different companies, which makes
every recorded verdict impossible to re-derive or challenge. `pinned=True`
reads a version-controlled snapshot instead, and refuses rather than falling
back, so a run is either reproducible or loudly not.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

PINNED_DIR = Path(__file__).resolve().parents[2] / "universes"

UNIVERSES: dict[str, list[str]] = {
    "india-largecap": [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
        "HINDUNILVR.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "MARUTI.NS",
    ],
    "india-midsmall": [
        # capital goods / manufacturing
        "AIAENG.NS", "GRINDWELL.NS", "SKFINDIA.NS", "TIMKEN.NS", "KSB.NS",
        # chemicals / materials
        "DEEPAKNTR.NS", "NAVINFLUOR.NS", "VINATIORGA.NS", "GALAXYSURF.NS",
        # consumer / retail
        "VGUARD.NS", "RELAXO.NS", "CERA.NS", "LAOPALA.NS",
        # IT / digital
        "PERSISTENT.NS", "KPITTECH.NS", "TATAELXSI.NS", "AFFLE.NS",
        # healthcare
        "LALPATHLAB.NS", "POLYMED.NS", "AJANTPHARM.NS",
        # financials
        "CDSL.NS", "CAMS.NS", "MCX.NS",
        # infra / defence / rail
        "ASTRAL.NS", "POLYCAB.NS",
    ],
    "us-tech": [
        "AAPL", "MSFT", "GOOGL", "NVDA", "AMD", "CRWD", "DDOG", "NET",
    ],
    "us-largecap60": [
        # tech / communication
        "AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "CRM", "ADBE", "ORCL",
        "CSCO", "TXN", "INTU", "NFLX", "DIS",
        # health care
        "JNJ", "UNH", "PFE", "MRK", "ABBV", "TMO", "DHR", "LLY",
        # financials
        "JPM", "BAC", "GS", "MS", "SCHW", "BLK", "V", "MA", "AXP",
        # consumer
        "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "COST", "WMT", "PG", "KO",
        "PEP", "TGT",
        # industrials / energy / materials
        "CAT", "DE", "HON", "GE", "UPS", "UNP", "LMT", "BA", "XOM", "CVX",
        "COP", "LIN", "SHW",
        # utilities / real estate / misc
        "NEE", "DUK", "AMT", "PLD",
    ],
}


def _fetch_universe(name: str, cache=None) -> list[str]:
    """Live membership: curated constant, NSE index, or Wikipedia-derived US sample."""
    if name in UNIVERSES:
        return UNIVERSES[name]
    from mbe.data.universe_nse import NSE_SOURCES, fetch_universe

    if name in NSE_SOURCES:
        return fetch_universe(name, cache=cache)
    from mbe.data.universe_us import WIKI_SOURCES, fetch_us_sample

    if name in WIKI_SOURCES or (name.endswith("2") and name[:-1] in WIKI_SOURCES):
        return fetch_us_sample(name, cache=cache)
    all_names = sorted(UNIVERSES) + sorted(NSE_SOURCES) + sorted(WIKI_SOURCES)
    raise KeyError(f"unknown universe {name!r}; available: {', '.join(all_names)}")


def get_universe(name: str, cache=None, pinned: bool = False) -> list[str]:
    """Universe membership.

    `pinned=False` (default) returns live membership — correct for the weekly
    screen, which should track today's index. `pinned=True` returns the
    version-controlled snapshot and raises if there isn't one: an ablation that
    quietly fell back to a live fetch would look reproducible while comparing a
    different set of companies, which is the failure this exists to prevent.
    """
    if not pinned or name in UNIVERSES:
        return _fetch_universe(name, cache=cache)
    snapshot = PINNED_DIR / f"{name}.json"
    if not snapshot.exists():
        raise KeyError(
            f"no pinned snapshot for {name!r} at {snapshot} — "
            f"run `mbe.universe.pin_universe({name!r})` to create one"
        )
    return json.loads(snapshot.read_text())["tickers"]


def pin_universe(name: str, cache=None) -> Path:
    """Freeze today's membership to a version-controlled snapshot."""
    tickers = _fetch_universe(name, cache=cache)
    PINNED_DIR.mkdir(parents=True, exist_ok=True)
    path = PINNED_DIR / f"{name}.json"
    path.write_text(json.dumps(
        {"pinned_at": date.today().isoformat(), "n": len(tickers), "tickers": tickers},
        indent=1,
    ) + "\n")
    return path
