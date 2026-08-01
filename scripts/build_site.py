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
from mbe.data.news_rss import POLICY_TERMS, company_news, sector_policy
from mbe.data.universe_nse import CACHE_TTL_HOURS
from mbe.data.yahoo import YahooProvider
from mbe.pipeline import screen
from mbe.publish import TOP_N, build_data, diff_weeks, render_site
from mbe.storage import RunStore
from mbe.universe import get_universe
from mbe.models.instrument import stable_instrument_id
from mbe.versioning import build_manifest

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
    build_started = time.monotonic()
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
    master_meta = json.loads(
        Path("universes/nifty-smallcap250-instruments.json").read_text()
    )
    canonical_records = {
        row["provider_symbols"]["yahoo"]: row for row in master_meta["records"]
    }
    if set(canonical_records) != set(tickers):
        missing = sorted(set(tickers) - set(canonical_records))
        extra = sorted(set(canonical_records) - set(tickers))
        raise SystemExit(
            f"canonical master/universe mismatch — missing={missing[:5]} extra={extra[:5]}"
        )
    source_date = master_meta.get("source_version")
    built_at = datetime.now(timezone.utc)
    manifest = build_manifest(
        universe_name=UNIVERSE, tickers=tickers, built_at=built_at,
        source_date=source_date, attempted=len(tickers), scored=len(result.ranked),
        failed=len(result.failures), duration_seconds=time.monotonic() - build_started,
    )
    instrument_ids = {
        ticker: stable_instrument_id(
            exchange_code="NSE" if ticker.endswith(".NS") else "BSE",
            symbol=ticker.removesuffix(".NS").removesuffix(".BO"),
            isin=canonical_records[ticker].get("isin"),
        )
        for ticker in tickers
    }
    if set(instrument_ids) != set(tickers) or len(set(instrument_ids.values())) != len(tickers):
        raise SystemExit("canonical instrument mapping collision — refusing to publish")
    RunStore("data/mbe.duckdb").save_run(
        result, UNIVERSE, build_id=manifest.build_id, instrument_ids=instrument_ids,
    )

    news = {
        b.card.ticker: company_news(
            canonical_records[b.card.ticker].get("company_name")
            or b.info.name
            or b.card.ticker,
            b.card.ticker,
            cache=cache,
            exchange=b.info.exchange or "NSE",
            industry=b.info.industry,
        )
        for b in result.ranked[:TOP_N]
    }
    industries = {
        b.info.industry or b.info.sector
        for b in result.ranked[:TOP_N]
        if (b.info.industry or b.info.sector)
    }
    policy = [
        item
        for key in sorted(industries)
        for item in sector_policy(None, key, cache=cache)
    ]
    with_news = sum(1 for v in news.values() if v)
    # "N items across K sectors" would read as coverage of all K queried; most
    # industries have no policy headline in any given week. Report the sectors
    # that actually returned something — overstating this line is the exact
    # failure that let the dead PIB path look healthy for months.
    covered = len({s for p in policy for s in p.sectors})
    print(
        f"news for {with_news}/{TOP_N} picks | {len(policy)} policy items "
        f"from {covered}/{len(industries)} sectors queried",
        flush=True,
    )
    # POLICY_TERMS maps a Yahoo industry label to the regulator Indian policy
    # journalism names it by; an unmapped industry still searches (on the raw
    # label) but scored ~57% relevant in testing against ~84% mapped. Printed
    # so the table's staleness is visible as the universe drifts.
    unmapped = sorted(i for i in industries if i not in POLICY_TERMS)
    if unmapped:
        print(
            f"  {len(unmapped)} industries have no POLICY_TERMS entry "
            f"(searching the raw label, lower relevance): {', '.join(unmapped)}",
            flush=True,
        )

    prev_path = SITE / "data.json"
    prev = json.loads(prev_path.read_text()) if prev_path.exists() else None
    previous_screener_path = SITE / "api" / "v1" / "screener.json"
    previous_screener_envelope = (
        json.loads(previous_screener_path.read_text())
        if previous_screener_path.exists() else {}
    )
    previous_screener = previous_screener_envelope.get("data", {}).get("rows", [])
    data = build_data(
        result, news, policy, built_at=built_at, manifest=manifest,
        instrument_ids=instrument_ids, canonical_records=canonical_records,
        previous_screener_rows=previous_screener,
    )
    previous_build = previous_screener_envelope.get("meta", {}).get("build") or {}
    if previous_build.get("build_id") and previous_build.get("build_id") != manifest.build_id:
        data["_previous_model_build"] = previous_build
    changes = diff_weeks(prev, data)
    render_site(data, changes, result, SITE)
    print(
        f"site built: {SITE}/index.html | entered {changes['entered']} | "
        f"exited {changes['exited']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
