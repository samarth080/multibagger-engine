import pytest

from mbe.data.cache import DiskCache
from mbe.data.provider import ProviderError
from mbe.data.universe_nse import NSE_SOURCES, fetch_universe, parse_constituents_csv

CSV_FIXTURE = """Company Name,Industry,Symbol,Series,ISIN Code
ABB India Ltd.,Capital Goods,ABB,EQ,INE117A01022
ACC Ltd.,Construction Materials,ACC,EQ,INE012A01025
Affle 3i Ltd.,Information Technology,AFFLE,EQ,INE00WC01027
"""


def test_parse_constituents_csv():
    assert parse_constituents_csv(CSV_FIXTURE) == ["ABB.NS", "ACC.NS", "AFFLE.NS"]


def test_parse_rejects_garbage():
    with pytest.raises(ProviderError):
        parse_constituents_csv("<html>blocked</html>")


def test_unknown_universe_raises():
    with pytest.raises(KeyError):
        fetch_universe("nifty-nonsense", cache=None, fetcher=lambda url: CSV_FIXTURE)


def test_fetch_universe_uses_fetcher_and_caches(tmp_path):
    cache = DiskCache(tmp_path, ttl_hours=24)
    calls = []

    def fake_fetcher(url: str) -> str:
        calls.append(url)
        return CSV_FIXTURE

    name = next(iter(NSE_SOURCES))
    first = fetch_universe(name, cache=cache, fetcher=fake_fetcher)
    second = fetch_universe(name, cache=cache, fetcher=fake_fetcher)
    assert first == second == ["ABB.NS", "ACC.NS", "AFFLE.NS"]
    assert len(calls) == 1  # second call served from cache


def test_fetch_failure_is_loud():
    def broken(url: str) -> str:
        raise OSError("connection refused")

    name = next(iter(NSE_SOURCES))
    with pytest.raises(ProviderError):
        fetch_universe(name, cache=None, fetcher=broken)
