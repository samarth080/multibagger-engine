"""Vercel serverless function: the canonical company page for a search-
universe instrument that is NOT in the research universe.

Phase 10A production fix. The 250 research-universe companies still get a
real static file at /company/{id}.html (see mbe.publish.render_site) —
Vercel serves an existing static file before checking rewrites, so this
function only runs for instrument IDs without one: every other NSE-listed
company a user can find via search (Reliance, TCS, HDFC Bank, ...). It
bundles the versioned search-index snapshot (site/api/v1/search-index.json,
see vercel.json includeFiles) for identity lookup and fetches a live quote
on demand — never a fabricated score, rank or research content.
"""

import json
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mbe.data.market import QuoteRequest, YahooChartQuoteProvider, normalize_yahoo_chart  # noqa: E402
from mbe.publish import render_lightweight_company_page  # noqa: E402

_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,80}\Z")
_ROOT = Path(__file__).resolve().parent.parent
SEARCH_INDEX_PATHS = (
    _ROOT / "site" / "api" / "v1" / "search-index.json",
    Path("site/api/v1/search-index.json"),
)


def _log(event: str, **fields) -> None:
    print(json.dumps({
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
    }, default=str))


def _load_index() -> list[dict]:
    for candidate in SEARCH_INDEX_PATHS:
        try:
            return json.loads(candidate.read_text())["data"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
    return []


def _quote_dict(payload: dict, provider_symbol: str) -> dict | None:
    normalized = normalize_yahoo_chart(
        payload, QuoteRequest(instrument_id="lightweight", provider_symbol=provider_symbol),
    )
    if normalized is None:
        return None
    return {
        "price": normalized.last_price,
        "currency": normalized.currency,
        "market_status": normalized.market_status,
        "day_change_pct": normalized.percentage_change,
        "week52_high": normalized.week52_high,
        "week52_low": normalized.week52_low,
    }


def _fetch_quote(provider_symbol: str | None, fetcher) -> dict | None:
    if not provider_symbol:
        return None
    try:
        return _quote_dict(fetcher(provider_symbol), provider_symbol)
    except Exception as exc:
        _log("company_quote_failure", symbol=provider_symbol, error_type=type(exc).__name__)
        return None


def render_company(
    instrument_id: str, *, index: list[dict] | None = None, quote_fetcher=None,
) -> tuple[int, str]:
    """Returns (http_status, html). Pure function — directly unit-testable
    with an injected index and quote fetcher, same shape as api/analyze.py."""
    if not instrument_id or not _ID_RE.match(instrument_id):
        return 400, "<h1>Invalid instrument ID</h1>"
    records = index if index is not None else _load_index()
    record = next((row for row in records if row.get("instrument_id") == instrument_id), None)
    if record is None:
        return 404, "<h1>No matching listed company.</h1>"
    if record.get("research_available"):
        # Static routing should have served the real research page already;
        # reaching here means the static build is out of sync. Fail honestly
        # rather than silently downgrading a modeled company's page.
        _log("company_fallback_hit_modeled_instrument", instrument_id=instrument_id)
        return 404, "<h1>This company's research page is temporarily unavailable. Please retry.</h1>"
    fetcher = quote_fetcher or YahooChartQuoteProvider()._fetch
    quote = _fetch_quote(record.get("provider_symbol"), fetcher)
    html = render_lightweight_company_page(record, quote)
    return 200, html


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        instrument_id = qs.get("id", [""])[0].strip()
        status, body = render_company(instrument_id)
        _log("company_request", instrument_id=instrument_id, status=status)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(body.encode())
