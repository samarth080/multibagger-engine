# Hosted Weekly India Picks — Static Publish Pipeline

**Date:** 2026-07-18 · **Status:** Approved design
**Goal:** A public-URL page (Vercel) showing the weekly NIFTY Smallcap 250
multibagger ranking with sector context, week-over-week changes, headlines,
government-policy items, and delayed quotes — rebuilt automatically every
Monday by GitHub Actions. The engine stays honest: descriptive layers are
displayed, never scored; the model-validation status is printed on the page.

## Architecture split

| Piece | Where | Why |
|---|---|---|
| Weekly ranking compute (~20 min, 250 tickers, DuckDB, disk cache) | GitHub Actions (cron, Monday pre-open IST) | Long batch + persistent-ish cache doesn't fit serverless |
| Site hosting (static HTML/JSON) | Vercel, free tier | Zero servers; redeploy per weekly build |
| Delayed quotes (~25 tickers, page load) | One Vercel serverless function, ~5 min edge cache | Small/fast fits serverless; labeled "delayed ~15 min" |
| On-demand analysis, backtests, ablations | User's Mac (`mbe serve`, CLI) | The lab stays local; the site is its published output |

## The page (`site/` output)

- **Top 25 table**: rank, ticker, name, multibagger + investment score,
  confidence, risk, trend, industry group + sector-momentum rank, theme tags.
- **Changes this week**: entries/exits vs the prior week's Top 25 (computed
  by diffing the previous `data.json`, kept in the repo by the weekly job).
- **Sector momentum table** (descriptive; the ablation demotion note stays).
- **Per-pick expansion**: 3–5 latest headlines; link to the full static
  report page (existing `render_report` markdown rendered to HTML).
- **Policy feed**: recent PIB items mapped to the top sectors.
- **Quotes strip**: current delayed price + move since ranking date, fetched
  client-side from the quotes function.
- **Footer (permanent)**: model-validation status — the same honest text the
  reports carry (IC +0.16/+0.10 India smallcap 2y, survivorship caveats,
  research tooling not investment advice) — plus build timestamp and next
  scheduled update.

## Weekly pipeline (`.github/workflows/weekly.yml` + `scripts/build_site.py`)

1. Restore `data/cache` from Actions cache (reduces Yahoo load; TTLs bumped
   for CI via env var so a warm cache is actually reused).
2. `scripts/build_site.py`: run `screen()` on nifty-smallcap250 → persist to
   DuckDB (artifact-cached) → pull news/policy RSS → write `site/data.json`,
   `site/index.html`, `site/reports/<ticker>.html` → compute week-over-week
   diff vs the committed previous `data.json`.
3. Deploy `site/` to Vercel (CLI + `VERCEL_TOKEN` secret) and commit the new
   `data.json` back to the repo (the next week's diff base).
4. Throttling: jittered sleep between tickers; retry with backoff on 429s.

**Stated risk:** Yahoo rate-limits datacenter IPs. Mitigations above; if GH
runners get blocked outright, the documented fallback is a launchd job on the
user's Mac running the identical `build_site.py` and pushing — same output,
different trigger. First live run tells us which world we're in.

## News & policy module (`src/mbe/data/news_rss.py`)

- Google News RSS per company (`"<company name>" OR <ticker-base>`), 7-day
  window, deduped by title, top 3–5 per pick.
- PIB RSS (Press Information Bureau) for government policy items; mapped to
  top sectors via keyword queries derived from `sector_themes.py` keys.
- Stdlib/feedparser parsing; offline tests with canned RSS fixtures (house
  pattern: every provider is tested offline).
- **Descriptive only, never scored.** Scoring news requires its own
  pre-registered validation (future P2.5/P2.6 territory).

## Quotes function (`api/quotes.py` on Vercel)

Fetches Yahoo quotes for the whitelisted ~25 page tickers only, 5-minute
cache, returns `{ticker: {price, change_pct}}`. No other symbols served
(not an open proxy). Page renders "delayed ~15 min" beside every quote.

## Explicitly deferred

US-market page (same pipeline, second universe — after India is live),
true real-time broker feeds, AI news summaries (needs API key + cost),
news-driven scoring (needs pre-registered validation), on-demand analysis
in the hosted page (needs a persistent backend — revisit only if wanted).

## Testing & verification

- Offline: RSS parsing fixtures; site builder golden test (build from a stub
  `ScreenResult`, assert page contains ranking rows, changes strip, honesty
  footer); quotes function unit test with a stubbed fetch.
- Live: one manual `build_site.py` run locally; first Actions run watched
  end-to-end; Vercel preview checked before the cron takes over.

## Prerequisites (user, one-time)

GitHub account + this repo pushed (private OK; ~130 Actions-min/month used
of 2000 free); Vercel account connected to the repo; `VERCEL_TOKEN` secret.
