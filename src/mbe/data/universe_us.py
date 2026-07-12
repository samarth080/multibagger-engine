"""US small/mid-cap universes from Wikipedia's S&P constituent tables.

A mechanical universe source: hand-picking small caps from memory would bake
in survivorship and hindsight winners. Current-constituent lists still carry
survivorship bias for backtests (stated in every report), but remove
name-selection bias entirely. Wikipedia is CC-licensed and stable; one
request per week thanks to the cache.
"""

from __future__ import annotations

import io

import pandas as pd

from mbe.data.cache import DiskCache
from mbe.data.provider import ProviderError
from mbe.data.universe_nse import default_http

WIKI_SOURCES = {
    "us-smallcap-sample": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
    "us-midcap-sample": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
}
# replication sets: same source, stride midpoints -> disjoint from the primary
REPLICATION_SUFFIX = "2"
CACHE_TTL_HOURS = 7 * 24
DEFAULT_SAMPLE = 80


def parse_wiki_constituents(html: str) -> list[str]:
    """Symbols from the first table containing a 'Symbol' column."""
    try:
        tables = pd.read_html(io.StringIO(html))
    except ValueError as exc:
        raise ProviderError(f"no tables found in constituents page: {exc}") from exc
    for table in tables:
        if "Symbol" in table.columns:
            symbols = [
                str(s).strip()
                for s in table["Symbol"].tolist()
                # plain symbols only; dotted share classes don't map to Yahoo cleanly
                if str(s).strip().isalpha() and 1 <= len(str(s).strip()) <= 5
            ]
            if symbols:
                return symbols
    raise ProviderError("constituents page had no usable 'Symbol' table")


def sample_evenly(
    pool: list[str], size: int, offset_fraction: float = 0.0
) -> list[str]:
    """Deterministic even-stride sample — reproducible, no head-of-list bias.
    offset_fraction=0.5 picks stride midpoints: a replication set fully
    disjoint from the primary sample."""
    if len(pool) <= size:
        return list(pool)
    stride = len(pool) / size
    return [pool[int((i + offset_fraction) * stride)] for i in range(size)]


def fetch_us_sample(
    name: str,
    cache: DiskCache | None,
    fetcher=default_http,
    size: int = DEFAULT_SAMPLE,
) -> list[str]:
    offset = 0.0
    source = name
    if name.endswith(REPLICATION_SUFFIX) and name[:-1] in WIKI_SOURCES:
        source = name[:-1]
        offset = 0.5
    if source not in WIKI_SOURCES:
        raise KeyError(f"unknown US universe {name!r}")
    key = f"universe_{name}_{size}"
    if cache and (hit := cache.get_json(key)):
        return hit["tickers"]
    try:
        html = fetcher(WIKI_SOURCES[source])
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"constituents download failed for {name}: {exc}") from exc
    tickers = sample_evenly(sorted(parse_wiki_constituents(html)), size, offset)
    if cache:
        cache.set_json(key, {"tickers": tickers})
    return tickers
