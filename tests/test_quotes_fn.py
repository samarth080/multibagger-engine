"""Offline tests for the Vercel quotes function (loaded from file path —
api/ is deliberately outside the mbe package; it must stay stdlib-only)."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "quotes_fn", Path(__file__).parent.parent / "api" / "quotes.py"
)
quotes_fn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quotes_fn)


def test_parse_chart_extracts_price_and_change():
    payload = {"chart": {"result": [{"meta": {
        "regularMarketPrice": 105.0, "chartPreviousClose": 100.0}}]}}
    q = quotes_fn.parse_chart(payload)
    assert q == {"price": 105.0, "day_change_pct": 5.0}


def test_parse_chart_bad_payload_is_none():
    assert quotes_fn.parse_chart({}) is None
    assert quotes_fn.parse_chart({"chart": {"result": []}}) is None


def test_build_response_filters_symbols():
    whitelist = {"GOOD.NS", "ALSO.NS"}
    fetched: list[str] = []

    def fake_fetch(sym):
        fetched.append(sym)
        return {"price": 10.0}

    out = quotes_fn.build_response(
        ["GOOD.NS", "EVIL.US", "NOTLISTED.NS", "lower.ns"], whitelist, fetch=fake_fetch
    )
    assert set(out["quotes"]) == {"GOOD.NS"}
    assert fetched == ["GOOD.NS"]  # non-whitelisted/malformed never fetched
    assert out["delayed"] == "~15 min"


def test_build_response_open_when_no_whitelist_but_ns_only_and_capped():
    out = quotes_fn.build_response(
        [f"T{i}.NS" for i in range(40)], set(), fetch=lambda s: {"price": 1.0}
    )
    assert len(out["quotes"]) == 30  # hard cap
