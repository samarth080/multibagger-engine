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
        "regularMarketPrice": 105.0,
        "chartPreviousClose": 100.0,
        "regularMarketTime": 1_700_000_000,
        "exchangeDataDelayedBy": 15,
        "currency": "INR",
        "exchangeName": "NSI",
        "marketState": "CLOSED",
    }}]}}
    q = quotes_fn.parse_chart(payload, now_ts=1_700_000_100)
    assert q is not None
    assert q["price"] == 105.0
    assert q["previous_close"] == 100.0
    assert q["day_change"] == 5.0
    assert q["day_change_pct"] == 5.0
    assert q["currency"] == "INR"
    assert q["market_status"] == "closed"
    assert q["delay_minutes"] == 15
    assert q["is_delayed"] is True
    assert q["is_stale"] is False
    assert q["as_of"].startswith("2023-11-14T")


def test_parse_chart_bad_payload_is_none():
    assert quotes_fn.parse_chart({}) is None
    assert quotes_fn.parse_chart({"chart": {"result": []}}) is None


def test_parse_chart_marks_an_old_open_market_quote_stale():
    payload = {"chart": {"result": [{"meta": {
        "regularMarketPrice": 105.0,
        "regularMarketTime": 1_700_000_000,
        "marketState": "REGULAR",
        "exchangeDataDelayedBy": 15,
    }}]}}
    q = quotes_fn.parse_chart(payload, now_ts=1_700_004_000)
    assert q is not None
    assert q["market_status"] == "open"
    assert q["is_stale"] is True
    assert "market is open" in q["stale_reason"]


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
    assert out["status"] == "ok"
    assert out["provider"] == "Yahoo Finance"
    assert out["errors"] == {}


def test_build_response_fails_closed_when_whitelist_is_missing():
    out = quotes_fn.build_response(
        [f"T{i}.NS" for i in range(40)], set(), fetch=lambda s: {"price": 1.0}
    )
    assert out["quotes"] == {}
    assert out["status"] == "unavailable"
    assert "whitelist" in out["errors"]["service"]


def test_build_response_deduplicates_and_caps_symbols():
    whitelist = {f"T{i}.NS" for i in range(40)}
    requested = ["T0.NS", "T0.NS", *[f"T{i}.NS" for i in range(40)]]
    out = quotes_fn.build_response(
        requested, whitelist, fetch=lambda s: {"price": 1.0}
    )
    assert len(out["quotes"]) == 30
