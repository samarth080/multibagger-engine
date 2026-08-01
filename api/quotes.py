"""Vercel serverless function: freshness-aware quotes for published tickers.

Whitelist = tickers in site/data.json (bundled via vercel.json includeFiles)
— this is not an open proxy: .NS symbols only, whitelist-filtered, capped at
30. If data.json is unavailable the endpoint fails closed instead of becoming
an unrestricted Yahoo proxy. Quote parsing is delegated to the same normalized
provider adapter used by the versioned API.

Yahoo's exchange-specific delay metadata is returned verbatim. The UI must not
claim a universal 15-minute delay when the provider says otherwise."""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mbe.data.market import (  # noqa: E402
    QuoteRequest,
    YahooChartQuoteProvider,
    normalize_yahoo_chart,
)

_SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]{1,20}\.NS\Z")
_MAX_SYMBOLS = 30


def _log(event: str, **fields) -> None:
    print(json.dumps({
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
    }, default=str))


def load_whitelist() -> set[str]:
    for candidate in (
        Path(__file__).resolve().parent.parent / "site" / "data.json",
        Path("site/data.json"),
    ):
        try:
            data = json.loads(candidate.read_text())
            return {row["ticker"] for row in data.get("top", [])}
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
    return set()


def parse_chart(payload: dict, now_ts: int | None = None) -> dict | None:
    """Phase-0 response compatibility around the canonical quote normalizer."""
    normalized = normalize_yahoo_chart(
        payload, QuoteRequest(instrument_id="legacy", provider_symbol="legacy"),
        now_ts=now_ts,
    )
    if normalized is None:
        return None
    out = {
        "price": normalized.last_price,
        "currency": normalized.currency,
        "exchange": normalized.exchange,
        "market_status": normalized.market_status,
        "as_of": normalized.provider_timestamp.isoformat() if normalized.provider_timestamp else None,
        "delay_minutes": normalized.reported_delay_minutes,
        "is_delayed": (
            normalized.reported_delay_minutes > 0
            if normalized.reported_delay_minutes is not None else None
        ),
        "is_stale": normalized.freshness_state == "stale",
        "stale_reason": normalized.staleness_reason,
        "provider": "Yahoo Finance",
    }
    if normalized.previous_close is not None:
        out["previous_close"] = normalized.previous_close
        out["day_change"] = normalized.absolute_change
        out["day_change_pct"] = normalized.percentage_change
    return out


def fetch_quote(symbol: str) -> dict | None:
    try:
        provider = YahooChartQuoteProvider()
        return parse_chart(provider.fetcher(symbol))
    except Exception as exc:
        _log("quote_provider_failure", symbol=symbol, error_type=type(exc).__name__)
        return None


def build_response(symbols: list[str], whitelist: set[str], fetch=fetch_quote) -> dict:
    generated_at = datetime.now(timezone.utc).isoformat()
    if not whitelist:
        return {
            "quotes": {},
            "errors": {"service": "published-symbol whitelist unavailable"},
            "provider": "Yahoo Finance",
            "generated_at": generated_at,
            "status": "unavailable",
        }
    wanted = list(dict.fromkeys(
        s for s in symbols if _SYMBOL_RE.match(s) and s in whitelist
    ))[:_MAX_SYMBOLS]
    quotes: dict[str, dict] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for sym, q in zip(wanted, pool.map(fetch, wanted)):
            if q:
                quotes[sym] = q
            else:
                errors[sym] = "provider returned no usable quote"
    return {
        "quotes": quotes,
        "errors": errors,
        "provider": "Yahoo Finance",
        "generated_at": generated_at,
        "status": "partial" if errors and quotes else "unavailable" if errors else "ok",
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        symbols = [
            s for chunk in qs.get("symbols", []) for s in chunk.split(",") if s
        ]
        response = build_response(symbols, load_whitelist())
        _log(
            "quote_request",
            requested=len(symbols),
            returned=len(response["quotes"]),
            status=response["status"],
        )
        body = json.dumps(response).encode()
        unavailable = response["status"] == "unavailable" and not response["quotes"]
        self.send_response(503 if unavailable else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=600")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)
