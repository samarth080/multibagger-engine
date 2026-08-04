"""Bounded, resumable Universal Research Score refresh CLI.

Per-company failure isolation (one bad ticker never aborts the batch, same
pattern as mbe.pipeline.screen), retry-with-backoff on transient provider
failures, a cache-key skip for already-fresh entries (resumable — a rerun
only recomputes what changed or previously failed), and a manifest
recording exactly what happened this run (partial-completion reporting,
per the design doc's "bounded universal analysis refresh" requirement).

Deliberately sequential, not concurrent, despite the design doc's "bounded
concurrency (small worker pool)" language: concurrent Yahoo requests from
one process meaningfully raise rate-limit risk (the same risk the original
2026-07-19 live-search-analyze design flagged: "heavy use could get
Vercel's shared IP range rate-limited by Yahoo"), and this CLI runs from a
single developer/CI machine, not serverless, so there is no per-request
latency budget forcing concurrency. `--limit` plus retry-with-backoff
already satisfy "bounded" and "resilient to transient failure" without
that added risk and complexity; revisit only if refresh throughput
becomes a real bottleneck at larger scale.

Usage:
    .venv/bin/python scripts/build_universal_scores.py \
        --instruments universes/verification-set.json \
        --output site/api/v1/universal-scores \
        --limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mbe.data.provider import DataProvider, ProviderError  # noqa: E402
from mbe.universal.cache import cache_key_for, read_cached_report, write_cached_report  # noqa: E402
from mbe.universal.pipeline import analyze_universal  # noqa: E402
from mbe.universal.policy import UNIVERSAL_SCORE_POLICY_VERSION  # noqa: E402
from mbe.universal.report import build_universal_report  # noqa: E402


@dataclass
class RefreshOutcome:
    succeeded: list[str] = field(default_factory=list)
    skipped_cached: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


class _PrefetchedProviderView:
    """Wraps a provider so a call for the given ticker returns the
    already-fetched (info, fin, prices) without hitting the provider
    again — avoids a redundant second fetch when analyze_universal()
    re-requests the same ticker's data internally. A call for any OTHER
    ticker (e.g., the benchmark index) passes through to the real
    provider untouched. Created fresh per instrument, never shared across
    the batch, so it can't leak into retry logic (which always runs
    against the raw provider) and can't grow memory across a large run."""

    def __init__(self, provider: DataProvider, ticker: str, info, fin, prices):
        self._provider = provider
        self._ticker = ticker
        self._info = info
        self._fin = fin
        self._prices = prices

    def get_info(self, ticker):
        if ticker == self._ticker:
            return self._info
        return self._provider.get_info(ticker)

    def get_financials(self, ticker):
        if ticker == self._ticker:
            return self._fin
        return self._provider.get_financials(ticker)

    def get_prices(self, ticker, years=3):
        if ticker == self._ticker:
            return self._prices
        return self._provider.get_prices(ticker, years=years)

    def benchmark_ticker(self, ticker):
        return self._provider.benchmark_ticker(ticker)


def _fetch_with_retry(provider: DataProvider, ticker: str, *, max_retries: int, backoff_seconds: float):
    """Returns (info, fin, prices) or raises the last ProviderError after
    exhausting retries. A fresh transient failure (e.g. a dropped
    connection) gets up to `max_retries` attempts with linear backoff;
    a systematically bad ticker still fails after the same bounded number
    of attempts, so one bad company can never hang the batch."""
    last_error: ProviderError | None = None
    for attempt in range(1, max_retries + 1):
        try:
            info = provider.get_info(ticker)
            fin = provider.get_financials(ticker)
            prices = provider.get_prices(ticker)
            return info, fin, prices
        except ProviderError as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(backoff_seconds * attempt)
    raise last_error


def run_refresh(
    instruments: list[dict],
    *,
    provider: DataProvider,
    output_dir: Path,
    limit: int | None = None,
    max_retries: int = 3,
    retry_backoff_seconds: float = 2.0,
) -> RefreshOutcome:
    outcome = RefreshOutcome()
    output_dir = Path(output_dir)
    processed = 0
    for record in instruments:
        if limit is not None and processed >= limit:
            break
        processed += 1
        instrument_id = record["instrument_id"]
        ticker = record["provider_symbol"]
        artifact_path = output_dir / f"{instrument_id}.json"

        try:
            info, fin, prices = _fetch_with_retry(
                provider, ticker, max_retries=max_retries, backoff_seconds=retry_backoff_seconds,
            )
        except ProviderError as exc:
            outcome.failed[instrument_id] = str(exc)
            continue

        key = cache_key_for(info, fin, prices, policy_version=UNIVERSAL_SCORE_POLICY_VERSION)
        cached = read_cached_report(artifact_path, expected_cache_key=key)
        if cached is not None:
            outcome.succeeded.append(instrument_id)
            outcome.skipped_cached.append(instrument_id)
            continue

        # Analyze with prefetched view to avoid redundant second fetch when analyze_universal
        # re-requests the same ticker's data. Benchmark (different ticker) passes through to real provider.
        prefetched_view = _PrefetchedProviderView(provider, ticker, info, fin, prices)
        try:
            card = analyze_universal(ticker, prefetched_view, instrument_id=instrument_id)
        except ProviderError as exc:
            outcome.failed[instrument_id] = str(exc)
            continue
        except Exception as exc:  # one bad ticker must never abort the batch
            outcome.failed[instrument_id] = f"unexpected: {exc!r}"
            continue

        generated_at = datetime.now(timezone.utc)
        report = build_universal_report(card, generated_at=generated_at)
        payload = {
            "instrument_id": instrument_id, "cache_key": key,
            "policy_version": UNIVERSAL_SCORE_POLICY_VERSION,
            "generated_at": generated_at.isoformat(), "report": report,
        }
        write_cached_report(artifact_path, payload)
        outcome.succeeded.append(instrument_id)

    manifest = {
        "policy_version": UNIVERSAL_SCORE_POLICY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "succeeded_count": len(outcome.succeeded),
        "skipped_cached_count": len(outcome.skipped_cached),
        "failed_count": len(outcome.failed),
        "failures": outcome.failed,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    return outcome


def _load_instruments(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instruments", type=Path, required=True, help="JSON list of {instrument_id, provider_symbol}")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    from mbe.data.yahoo import YahooProvider
    provider = YahooProvider(cache=None)
    instruments = _load_instruments(args.instruments)
    outcome = run_refresh(instruments, provider=provider, output_dir=args.output, limit=args.limit)
    print(json.dumps({
        "succeeded": len(outcome.succeeded), "skipped_cached": len(outcome.skipped_cached),
        "failed": len(outcome.failed), "failure_detail": outcome.failed,
    }, indent=2))
    return 0 if not outcome.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
