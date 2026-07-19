# Live Search-Any-Stock — Serverless Analyze Function

**Date:** 2026-07-19 · **Status:** Approved design
**Goal:** A search box on the hosted site that lets a visitor type any ticker
and get the full `mbe analyze` report back, live, without touching the
existing static weekly-picks pipeline. Free Vercel serverless, added
alongside the current site — nothing already deployed changes.

## Scope

Additive only. The static `site/` build (weekly rankings, sector context,
news, policy, delayed quotes) is untouched. This adds:
- `api/analyze.py` — a Python serverless function running the real
  `analyze_ticker()` + `render_report()` pipeline for one ticker per request.
- A search form on `site/index.html` (plain GET, no JS) linking to it.
- `requirements.txt` (new, root) — the minimal dependency set this function
  needs; `api/quotes.py` stays stdlib-only and unaffected.

**Explicitly out of scope for this increment**: the CLI's prediction-ledger
persistence (DuckDB-backed "since last analysis" diffs, calibration-adjusted
confidence) — no persistent disk exists in stateless serverless. The hosted
report is an honest one-shot: full thesis, critique, evidence, same
validation footer everywhere else carries — just no history. Also deferred:
choosing EDGAR/NSE as the fundamentals provider (defaults to Yahoo, matching
the CLI default); sector-momentum context (single-ticker analysis has never
had it, per the P2.4 design — same "n/a, computed in universe screens" line
the CLI already shows).

## Request flow

1. Visitor submits the search form → browser GETs `/api/analyze?ticker=X`.
2. Function validates the ticker format (reject before touching Yahoo).
3. `YahooProvider(DiskCache("/tmp/mbe-cache"))` — ephemeral, best-effort:
   helps a still-warm instance skip re-fetching for a repeat search, no
   cache shared across cold instances or users (accepted tradeoff of the
   free-serverless choice).
4. `analyze_ticker(ticker, provider)` → `render_report(bundle)` → wrapped in
   the same dark report shell `src/mbe/publish.py` already uses for weekly
   report pages (shared, parametrized back-link — `publish.py`'s
   `_REPORT_SHELL` gets a small public wrapper so both call sites use one
   template).
5. Returned directly as `text/html` — a real, shareable, bookmarkable URL.
6. Any failure (bad ticker, no data, provider error) renders a clean error
   page, never a raw 500.

## Packaging

- New root `requirements.txt`: `pandas`, `numpy`, `yfinance`, `pydantic`,
  `jinja2`, `markdown`, `defusedxml`. Deliberately excludes `scipy` (only
  `backtest/harness.py` needs it — not on the `analyze_ticker` path),
  `duckdb`/`pyarrow`/`fastapi`/`uvicorn`/`typer`/`rich` (storage/web/CLI only).
- `vercel.json` gains a `functions."api/analyze.py"` entry: `includeFiles`
  bundling `src/mbe/**`, and a raised `maxDuration` (heavy cold import +
  live multi-call Yahoo fetch + full pipeline compute needs more room than
  the default).
- `api/analyze.py` does a `sys.path` shim to the bundled `src/` at import
  time — no separate package install step, same pattern already proven by
  the sys.path-based test loader for `api/quotes.py`.

## Honesty & safety

- Ticker validated against a strict allow-pattern before any network call.
- Errors render a real page, not a stack trace.
- No real rate-limiting is possible without shared state on the free tier —
  stated plainly, not glossed over. Residual risk: heavy use could get
  Vercel's shared IP range rate-limited by Yahoo; separate from (doesn't
  block) the GitHub Actions weekly build, which runs from different IPs.
- Cold-start latency is a real, stated unknown — heavy imports (pandas/numpy/
  yfinance) plus a live multi-call fetch could be slow on a cold instance.
  First live search tells us which world we're in, same as the weekly
  build's Yahoo-rate-limit unknown was resolved empirically.

## Fallback if this doesn't hold up in practice

If cold starts or execution-time limits make this unreliable, the documented
pivot is the persistent-host option already scoped and declined this round
(small Render/Railway/Fly container running the existing `mbe serve` app).
The core analysis code (`analyze_ticker`, `render_report`) doesn't change
either way — only the hosting wrapper would.

## Testing

Offline: ticker-validation regex tests; error-page rendering with a stub
provider (ProviderError → clean HTML, not a crash); the shared report-shell
wrapper tested once and reused by both call sites. Same importlib
file-path-loading pattern as `tests/test_quotes_fn.py`, since `api/` sits
outside the `mbe` package.
Live: first real search once deployed — watch cold-start time, watch for
Yahoo rate-limit signals, confirm the report renders correctly end-to-end.
