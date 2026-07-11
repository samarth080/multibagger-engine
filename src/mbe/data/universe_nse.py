"""NSE index constituent ingestion (niftyindices.com CSV archives).

Universes refresh at most weekly (7-day cache TTL). Failures are loud
(ProviderError) — a screen over a silently-empty universe would look like
a working run with no signal, which is worse than an error.
"""

from __future__ import annotations

import csv
import io
import urllib.request

from mbe.data.cache import DiskCache
from mbe.data.provider import ProviderError

NSE_SOURCES: dict[str, str] = {
    "nifty50": "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
    "nifty500": "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv",
    "nifty-midcap150": "https://niftyindices.com/IndexConstituent/ind_niftymidcap150list.csv",
    "nifty-smallcap250": "https://niftyindices.com/IndexConstituent/ind_niftysmallcap250list.csv",
    "nifty-microcap250": "https://niftyindices.com/IndexConstituent/ind_niftymicrocap250list.csv",
}

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
CACHE_TTL_HOURS = 7 * 24


def default_http(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8-sig")


def parse_constituents_csv(text: str) -> list[str]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "Symbol" not in reader.fieldnames:
        raise ProviderError(
            f"constituent CSV missing 'Symbol' column (got {reader.fieldnames})"
        )
    tickers = [
        f"{row['Symbol'].strip()}.NS"
        for row in reader
        if row.get("Symbol", "").strip()
    ]
    if not tickers:
        raise ProviderError("constituent CSV parsed to an empty list")
    return tickers


def fetch_universe(
    name: str,
    cache: DiskCache | None,
    fetcher=default_http,
) -> list[str]:
    if name not in NSE_SOURCES:
        raise KeyError(
            f"unknown NSE universe {name!r}; available: {', '.join(sorted(NSE_SOURCES))}"
        )
    key = f"universe_{name}"
    if cache and (hit := cache.get_json(key)):
        return hit["tickers"]
    try:
        text = fetcher(NSE_SOURCES[name])
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"universe download failed for {name}: {exc}") from exc
    tickers = parse_constituents_csv(text)
    if cache:
        cache.set_json(key, {"tickers": tickers})
    return tickers
