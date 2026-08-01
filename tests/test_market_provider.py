from datetime import datetime, timezone

from mbe.data.market import QuoteRequest, YahooChartQuoteProvider, normalize_yahoo_chart
from mbe.data.registry import ProviderRegistry
from mbe.models.instrument import FreshnessState


def _payload(**meta_updates):
    meta = {
        "regularMarketPrice": 110,
        "chartPreviousClose": 100,
        "regularMarketTime": 1_700_000_000,
        "exchangeDataDelayedBy": 15,
        "marketState": "REGULAR",
        "currency": "INR",
        "exchangeName": "NSI",
        "regularMarketOpen": 102,
        "regularMarketDayHigh": 112,
        "regularMarketDayLow": 99,
        "regularMarketVolume": 12345,
    }
    meta.update(meta_updates)
    return {"chart": {"result": [{"meta": meta, "timestamp": [1_700_000_000]}]}}


def test_yahoo_quote_normalization_preserves_lineage_and_ohlcv():
    request = QuoteRequest(instrument_id="instrument-a", provider_symbol="ALPHA.NS")
    quote = normalize_yahoo_chart(_payload(), request, now_ts=1_700_000_600)
    assert quote.instrument_id == "instrument-a"
    assert quote.provider_symbol == "ALPHA.NS"
    assert quote.last_price == 110 and quote.previous_close == 100
    assert quote.absolute_change == 10 and quote.percentage_change == 10
    assert quote.open == 102 and quote.day_high == 112 and quote.day_low == 99
    assert quote.volume == 12345
    assert quote.freshness_state == FreshnessState.DELAYED


def test_stale_market_open_and_market_closed_behavior():
    request = QuoteRequest(instrument_id="a", provider_symbol="A.NS")
    stale = normalize_yahoo_chart(_payload(exchangeDataDelayedBy=0), request, now_ts=1_700_004_000)
    assert stale.freshness_state == FreshnessState.STALE
    closed = normalize_yahoo_chart(
        _payload(marketState="CLOSED", exchangeDataDelayedBy=0), request,
        now_ts=1_700_004_000,
    )
    assert closed.market_status == "closed"
    assert closed.freshness_state == FreshnessState.FRESH


def test_malformed_and_timeout_become_safe_partial_failures():
    requests = [QuoteRequest(instrument_id="a", provider_symbol="A.NS")]
    malformed = YahooChartQuoteProvider(fetcher=lambda _: {"chart": {"result": []}})
    result = malformed.get_quotes(requests)[0]
    assert result.error_code == "provider_unavailable"
    assert "timeout" not in (result.error_message or "").lower()

    def timeout(_):
        raise TimeoutError("secret provider detail")

    result = YahooChartQuoteProvider(fetcher=timeout).get_quotes(requests)[0]
    assert result.error_code == "provider_unavailable"
    assert "secret" not in (result.error_message or "")


def test_yahoo_quote_normalization_carries_52_week_range_for_lightweight_company_pages():
    """Lightweight (non-research) company pages show 52-week high/low; the
    normalized quote contract must carry it through additively — existing
    consumers that ignore the field are unaffected."""
    request = QuoteRequest(instrument_id="instrument-a", provider_symbol="ALPHA.NS")
    quote = normalize_yahoo_chart(
        _payload(fiftyTwoWeekHigh=150, fiftyTwoWeekLow=80), request, now_ts=1_700_000_600,
    )
    assert quote.week52_high == 150
    assert quote.week52_low == 80


def test_yahoo_quote_normalization_tolerates_missing_52_week_range():
    request = QuoteRequest(instrument_id="instrument-a", provider_symbol="ALPHA.NS")
    quote = normalize_yahoo_chart(_payload(), request, now_ts=1_700_000_600)
    assert quote.week52_high is None
    assert quote.week52_low is None


def test_registry_supports_mock_substitution_and_unsupported_operations():
    class Mock:
        def health(self):
            return {"status": "ok"}

    registry = ProviderRegistry()
    registry.register("quotes", "mock", Mock(), default=True)
    assert isinstance(registry.get("quotes"), Mock)
    assert registry.health()[0]["default"] is True
