"""Curated starter universes (v0.1). v0.2 replaces these with full exchange
lists ingested from NSE/BSE indices. Liquid names across sectors, chosen for
coverage breadth, not as recommendations."""

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


def get_universe(name: str, cache=None) -> list[str]:
    """Curated list, or a dynamic NSE index universe (downloaded + cached)."""
    if name in UNIVERSES:
        return UNIVERSES[name]
    from mbe.data.universe_nse import NSE_SOURCES, fetch_universe

    if name in NSE_SOURCES:
        return fetch_universe(name, cache=cache)
    from mbe.data.universe_us import WIKI_SOURCES, fetch_us_sample

    if name in WIKI_SOURCES:
        return fetch_us_sample(name, cache=cache)
    all_names = sorted(UNIVERSES) + sorted(NSE_SOURCES) + sorted(WIKI_SOURCES)
    raise KeyError(f"unknown universe {name!r}; available: {', '.join(all_names)}")
