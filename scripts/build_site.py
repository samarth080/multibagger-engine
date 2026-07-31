"""Weekly site build: screen nifty-smallcap250, pull news/policy, write site/.

Run locally or from GitHub Actions (.github/workflows/weekly.yml).
Env: MBE_CACHE_TTL_HOURS (default 24; CI sets 144 so the restored Actions
cache is actually reused), MBE_THROTTLE_SECS (default 0; CI sets ~0.8 to be
polite to Yahoo from datacenter IPs). Refuses to publish a degraded ranking
(<100 names analyzed) — a rate-limited half-universe must fail loudly, not
ship as if it were the real ranking."""

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from mbe.data.cache import DiskCache
from mbe.data.news_rss import company_news, policy_items
from mbe.data.universe_nse import CACHE_TTL_HOURS
from mbe.data.yahoo import YahooProvider
from mbe.pipeline import screen
from mbe.publish import TOP_N, build_data, diff_weeks, render_site
from mbe.storage import RunStore
from mbe.universe import get_universe

SITE = Path("site")
UNIVERSE = "nifty-smallcap250"
MIN_ANALYZED = 100


def _with_retry(call, attempts: int = 3, base_sleep: float = 20.0):
    """Retry transient rate-limit failures with linear backoff; anything
    else (or the final attempt) re-raises so screen() records the failure."""
    for i in range(attempts):
        try:
            return call()
        except Exception as exc:
            transient = "429" in str(exc) or "Too Many" in str(exc)
            if not transient or i == attempts - 1:
                raise
            time.sleep(base_sleep * (i + 1))


class ThrottledProvider:
    """Politeness wrapper: jittered sleep at the start of each ticker's
    fetch chain (get_info is always the first call per ticker), plus
    backoff-retries on 429s from datacenter IPs."""

    def __init__(self, inner, secs: float):
        self.inner, self.secs = inner, secs

    def get_info(self, ticker):
        if self.secs:
            time.sleep(self.secs * (0.5 + random.random()))
        return _with_retry(lambda: self.inner.get_info(ticker))

    def get_financials(self, ticker):
        return _with_retry(lambda: self.inner.get_financials(ticker))

    def get_prices(self, ticker, years: int = 3):
        return _with_retry(lambda: self.inner.get_prices(ticker, years=years))

    def benchmark_ticker(self, ticker):
        return self.inner.benchmark_ticker(ticker)


def main() -> None:
    ttl = float(os.environ.get("MBE_CACHE_TTL_HOURS", "24"))
    throttle = float(os.environ.get("MBE_THROTTLE_SECS", "0"))
    cache = DiskCache("data/cache", ttl_hours=ttl)
    provider = ThrottledProvider(YahooProvider(cache), throttle)

    universe_cache = DiskCache("data/cache", ttl_hours=max(ttl, CACHE_TTL_HOURS))
    tickers = get_universe(UNIVERSE, cache=universe_cache)
    print(f"screening {len(tickers)} (ttl={ttl}h throttle={throttle}s)...", flush=True)
    result = screen(tickers, provider)
    print(f"analyzed {len(result.ranked)} | failed {len(result.failures)}", flush=True)
    if len(result.ranked) < MIN_ANALYZED:
        raise SystemExit(
            f"only {len(result.ranked)} analyzed (< {MIN_ANALYZED}) — refusing "
            f"to publish a degraded ranking. Failures: "
            f"{list(result.failures.items())[:5]}"
        )
    RunStore("data/mbe.duckdb").save_run(result, UNIVERSE)

    news = {
        b.card.ticker: company_news(
            b.info.name or b.card.ticker, b.card.ticker, cache=cache
        )
        for b in result.ranked[:TOP_N]
    }
    policy = policy_items([s.name for s in result.sector_scores], cache=cache)
    with_news = sum(1 for v in news.values() if v)
    tagged = sum(1 for p in policy if p.sectors)
    print(
        f"news for {with_news}/{TOP_N} picks | {len(policy)} policy items "
        f"({tagged} tagged to a sector)",
        flush=True,
    )
    if policy and not tagged:
        # Known broken as of 2026-07-31, and it fails silently, which is why
        # this warning exists. PIB's RSS at PIB_RSS_URL serves Hindi headlines
        # (Lang= and Regid= variants all return Hindi or an empty feed), while
        # POLICY_KEYWORDS matches lowercase English. Nothing has ever tagged.
        # The page therefore prints untitled-for-purpose Hindi items under a
        # "Government policy" heading with no sector relevance behind them.
        # Fixing it needs an English-language source, not a parameter tweak.
        print(
            "  WARNING: 0 policy items tagged to any sector — the PIB feed is "
            "Hindi and POLICY_KEYWORDS is English, so tagging cannot match. "
            "Policy relevance on the site is not real.",
            flush=True,
        )

    prev_path = SITE / "data.json"
    prev = json.loads(prev_path.read_text()) if prev_path.exists() else None
    data = build_data(result, news, policy, built_at=datetime.now(timezone.utc))
    changes = diff_weeks(prev, data)
    render_site(data, changes, result, SITE)
    print(
        f"site built: {SITE}/index.html | entered {changes['entered']} | "
        f"exited {changes['exited']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
