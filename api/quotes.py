"""Vercel serverless function: delayed (~15 min) quotes for published tickers.

Whitelist = tickers in site/data.json (bundled via vercel.json includeFiles)
— this is not an open proxy: .NS symbols only, whitelist-filtered, capped at
30. If data.json is unavailable the whitelist fails OPEN to regex+cap only
(any well-formed .NS symbol) — deliberate: quotes are public delayed data. Stdlib only; the mbe package is not installed in this runtime."""

import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?interval=1d&range=1d"
)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
_SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]{1,20}\.NS\Z")
_MAX_SYMBOLS = 30


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


def parse_chart(payload: dict) -> dict | None:
    try:
        meta = payload["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
    except (KeyError, IndexError, TypeError):
        return None
    if price is None:
        return None
    out = {"price": price}
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if prev:
        out["day_change_pct"] = round((price / prev - 1) * 100, 2)
    return out


def fetch_quote(symbol: str) -> dict | None:
    req = urllib.request.Request(
        CHART_URL.format(symbol=symbol), headers={"User-Agent": _UA}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return parse_chart(json.loads(resp.read()))
    except Exception:
        return None


def build_response(symbols: list[str], whitelist: set[str], fetch=fetch_quote) -> dict:
    wanted = [
        s for s in symbols
        if _SYMBOL_RE.match(s) and (not whitelist or s in whitelist)
    ][:_MAX_SYMBOLS]
    quotes: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for sym, q in zip(wanted, pool.map(fetch, wanted)):
            if q:
                quotes[sym] = q
    return {"quotes": quotes, "delayed": "~15 min"}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        symbols = [
            s for chunk in qs.get("symbols", []) for s in chunk.split(",") if s
        ]
        body = json.dumps(build_response(symbols, load_whitelist())).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(body)
