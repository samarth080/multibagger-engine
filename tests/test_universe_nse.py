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


WIKI_HTML = """
<html><body>
<table id="constituents" class="wikitable">
<tr><th>Symbol</th><th>Company</th><th>GICS Sector</th></tr>
<tr><td>AAON</td><td>AAON Inc</td><td>Industrials</td></tr>
<tr><td>ABCB</td><td>Ameris Bancorp</td><td>Financials</td></tr>
<tr><td>BRK.B</td><td>Weird Unit</td><td>Financials</td></tr>
</table>
</body></html>
"""


def test_parse_sp600_symbols():
    from mbe.data.universe_us import parse_wiki_constituents

    tickers = parse_wiki_constituents(WIKI_HTML)
    assert "AAON" in tickers and "ABCB" in tickers
    assert "BRK.B" not in tickers  # dotted share classes excluded (Yahoo mismatch)


def test_sample_universe_deterministic():
    from mbe.data.universe_us import sample_evenly

    pool = [f"T{i}" for i in range(100)]
    a = sample_evenly(pool, 10)
    b = sample_evenly(pool, 10)
    assert a == b
    assert len(a) == 10
    assert a[0] == "T0" and a[-1] == "T90"  # even coverage, not the head


def test_sample_offset_produces_disjoint_replication_set():
    from mbe.data.universe_us import sample_evenly

    pool = [f"T{i}" for i in range(600)]
    primary = sample_evenly(pool, 80)
    replication = sample_evenly(pool, 80, offset_fraction=0.5)
    assert len(replication) == 80
    assert set(primary).isdisjoint(set(replication))
