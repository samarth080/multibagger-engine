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
}


def get_universe(name: str) -> list[str]:
    if name not in UNIVERSES:
        raise KeyError(
            f"unknown universe {name!r}; available: {', '.join(sorted(UNIVERSES))}"
        )
    return UNIVERSES[name]
