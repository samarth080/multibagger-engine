"""Vercel serverless function: live full-report analysis for any ticker.

Unlike api/quotes.py, this needs the real analysis engine (pandas, numpy,
yfinance, pydantic) — see /requirements.txt. It bundles src/mbe/** (see
vercel.json includeFiles) and imports it via a sys.path shim rather than a
package-install step.

No caching at all — YahooProvider(cache=None). DiskCache.set_df() writes
parquet, which needs a parquet engine (pyarrow/fastparquet) that isn't in
the deliberately minimal requirements.txt; adding one just for a
best-effort, warm-instance-only cache isn't worth the extra deployment
weight, so every search is a fresh Yahoo fetch. No prediction-ledger
persistence either (that needs a real database, which stateless serverless
doesn't have) — this is an honest one-shot report: full thesis, critique,
evidence, same validation footer as everywhere else, just no history.
"""

import json
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mbe.data.provider import ProviderError  # noqa: E402
from mbe.data.yahoo import YahooProvider  # noqa: E402
from mbe.pipeline import analyze_ticker  # noqa: E402
from mbe.publish import render_error_page, render_report_page  # noqa: E402

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,15}\Z")


def _log(event: str, **fields) -> None:
    print(json.dumps({
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
    }, default=str))


def _default_provider():
    return YahooProvider(cache=None)


def render_analysis(ticker: str, provider=None) -> tuple[int, str]:
    """Returns (http_status, html). Pure function, no request/response
    coupling — directly unit-testable with a stub provider.

    Error pages render via publish.render_error_page (jinja, autoescape on):
    ticker/reason are passed RAW and escaped by the template engine.
    _TICKER_RE only constrains a VALID ticker — the 400 branch is reached
    exactly when it does NOT match, so the rejected raw string still flows
    into the page and must never be trusted as pre-sanitized."""
    if not ticker:
        return 400, render_error_page(
            "", "No ticker given — try ?ticker=RELIANCE.NS"
        )
    if not _TICKER_RE.match(ticker):
        return 400, render_error_page(ticker, "Not a valid ticker format.")
    if provider is None:
        provider = _default_provider()
    try:
        bundle = analyze_ticker(ticker, provider)
    except ProviderError as exc:
        _log("analysis_provider_failure", ticker=ticker, error_type=type(exc).__name__)
        return 404, render_error_page(ticker, str(exc))
    except Exception as exc:  # honest error page; real detail stays server-side
        _log("analysis_unexpected_failure", ticker=ticker, error_type=type(exc).__name__)
        return 500, render_error_page(
            ticker, "Unexpected error analyzing this ticker."
        )
    return 200, render_report_page(bundle, back_href="/")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        ticker = qs.get("ticker", [""])[0].strip()
        status, body = render_analysis(ticker)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body.encode())
