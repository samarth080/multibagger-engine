"""Provider-neutral quote contract and the current Yahoo chart adapter."""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field

from mbe.data.provider import ProviderError
from mbe.models.instrument import FreshnessState, QualityStatus


class QuoteRequest(BaseModel):
    instrument_id: str
    provider_symbol: str
    exchange: str | None = None


class NormalizedQuote(BaseModel):
    instrument_id: str
    provider: str
    provider_symbol: str
    exchange: str | None = None
    currency: str | None = None
    last_price: float | None = None
    previous_close: float | None = None
    absolute_change: float | None = None
    percentage_change: float | None = None
    open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None
    volume: int | None = Field(default=None, ge=0)
    market_status: str = "unknown"
    provider_timestamp: datetime | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reported_delay_minutes: int | None = Field(default=None, ge=0)
    freshness_state: FreshnessState = FreshnessState.UNKNOWN
    staleness_reason: str | None = None
    quality_status: QualityStatus = QualityStatus.UNKNOWN
    error_code: str | None = None
    error_message: str | None = None


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _market_status(meta: dict, now_ts: int) -> str:
    provider_state = meta.get("marketState")
    if isinstance(provider_state, str) and provider_state:
        normalized = provider_state.lower()
        return "open" if normalized in {"regular", "open"} else normalized
    periods = meta.get("currentTradingPeriod") or {}
    for state in ("regular", "pre", "post"):
        period = periods.get(state) or {}
        start, end = period.get("start"), period.get("end")
        if isinstance(start, int) and isinstance(end, int) and start <= now_ts < end:
            return "open" if state == "regular" else state
    return "closed"


def normalize_yahoo_chart(
    payload: dict, request: QuoteRequest, *, now_ts: int | None = None,
) -> NormalizedQuote | None:
    now_ts = now_ts or int(time.time())
    try:
        result = payload["chart"]["result"][0]
        meta = result["meta"]
    except (KeyError, IndexError, TypeError):
        return None
    price = _number(meta.get("regularMarketPrice"))
    if price is None or price <= 0:
        return None

    quote_ts = meta.get("regularMarketTime")
    timestamps = result.get("timestamp") or []
    if not isinstance(quote_ts, int) and timestamps:
        quote_ts = timestamps[-1]
    quote_ts = quote_ts if isinstance(quote_ts, int) else None
    market_status = _market_status(meta, now_ts)
    delay = meta.get("exchangeDataDelayedBy")
    delay = delay if isinstance(delay, int) and delay >= 0 else None
    state = FreshnessState.FRESH
    reason = None
    if quote_ts is None:
        state, reason = FreshnessState.UNKNOWN, "quote timestamp unavailable"
    else:
        age_seconds = now_ts - quote_ts
        if age_seconds < -300:
            state, reason = FreshnessState.STALE, "quote timestamp is in the future"
        elif market_status == "open":
            allowed = max((delay or 0) + 15, 30) * 60
            if age_seconds > allowed:
                state, reason = (
                    FreshnessState.STALE,
                    "quote is older than expected while market is open",
                )
            elif delay:
                state = FreshnessState.DELAYED
        elif age_seconds > 5 * 24 * 3600:
            state, reason = FreshnessState.STALE, "last quote is more than five days old"
        elif delay:
            state = FreshnessState.DELAYED

    previous = _number(meta.get("chartPreviousClose")) or _number(meta.get("previousClose"))
    return NormalizedQuote(
        instrument_id=request.instrument_id,
        provider="yahoo",
        provider_symbol=request.provider_symbol,
        exchange=meta.get("exchangeName") or request.exchange,
        currency=meta.get("currency"),
        last_price=price,
        previous_close=previous,
        absolute_change=round(price - previous, 2) if previous and previous > 0 else None,
        percentage_change=(
            round((price / previous - 1) * 100, 2) if previous and previous > 0 else None
        ),
        open=_number(meta.get("regularMarketOpen")),
        day_high=_number(meta.get("regularMarketDayHigh")),
        day_low=_number(meta.get("regularMarketDayLow")),
        week52_high=_number(meta.get("fiftyTwoWeekHigh")),
        week52_low=_number(meta.get("fiftyTwoWeekLow")),
        volume=(int(v) if (v := _number(meta.get("regularMarketVolume"))) is not None and v >= 0 else None),
        market_status=market_status,
        provider_timestamp=(
            datetime.fromtimestamp(quote_ts, timezone.utc) if quote_ts is not None else None
        ),
        reported_delay_minutes=delay,
        freshness_state=state,
        staleness_reason=reason,
        quality_status=QualityStatus.VALID if state != FreshnessState.STALE else QualityStatus.WARNING,
    )


class YahooChartQuoteProvider:
    name = "yahoo"
    chart_url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        "?interval=1d&range=5d"
    )

    def __init__(self, fetcher: Callable[[str], dict] | None = None):
        self.fetcher = fetcher or self._fetch

    @staticmethod
    def _fetch(symbol: str) -> dict:
        safe_symbol = urllib.parse.quote(symbol, safe="")
        req = urllib.request.Request(
            YahooChartQuoteProvider.chart_url.format(symbol=safe_symbol),
            headers={"User-Agent": "Mozilla/5.0 (compatible; MultibaggerEngine/1.0)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read())
        except Exception as exc:
            raise ProviderError(f"quote fetch failed for {symbol}") from exc

    def get_quotes(self, mappings: list[QuoteRequest]) -> list[NormalizedQuote]:
        def one(mapping: QuoteRequest) -> NormalizedQuote:
            try:
                quote = normalize_yahoo_chart(self.fetcher(mapping.provider_symbol), mapping)
                if quote is None:
                    raise ProviderError("provider returned no usable quote")
                return quote
            except Exception:
                return NormalizedQuote(
                    instrument_id=mapping.instrument_id,
                    provider=self.name,
                    provider_symbol=mapping.provider_symbol,
                    exchange=mapping.exchange,
                    freshness_state=FreshnessState.FAILED,
                    quality_status=QualityStatus.INVALID,
                    error_code="provider_unavailable",
                    error_message="Quote provider returned no usable quote.",
                )

        # Yahoo's chart route is one-symbol-per-request. Bound concurrency so a
        # 30-ID API batch does not become 30 serial network round trips.
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(mappings)))) as pool:
            return list(pool.map(one, mappings))

    def health(self) -> dict:
        return {"provider": self.name, "status": "configured", "capability": "quotes"}
