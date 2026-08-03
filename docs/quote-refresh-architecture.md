# Dynamic quote-refresh architecture (Phase 11 Milestone 2B)

This document describes how company report pages and the rankings table keep
their market price current without a static rebuild, and how that runtime
behavior is kept strictly separate from the frozen research layer built by
Milestone 2A's coverage architecture (see
[`coverage-architecture.md`](coverage-architecture.md)).

> **Naming note:** `coverage-architecture.md`'s own "Milestone 2B
> recommendation" section refers to a *different*, still-unimplemented
> workstream (a broader financial-data source and broader index-membership
> import). That name predates this document and describes unrelated future
> work — it is not this milestone. This inconsistency is called out here so a
> future reader isn't misled by the collision; renumbering that section is
> left to whoever picks up either piece of work next.

## Runtime market layer vs. frozen research layer

Every company page draws from two layers that must never be conflated:

**Runtime market layer** (refreshed on a bounded schedule, client-side only):
current price, previous close, absolute change, percentage change, open, day
high/low, volume, currency, exchange, market status, provider timestamp,
retrieval timestamp, delay, staleness, failure state.

**Frozen research layer** (updated only by an explicit offline build):
Multibagger Score, rank, confidence, risk, investability, financial analysis,
the technical state feeding the model, strengths, risks, score history, peer
comparison, model explanations.

A quote refresh only ever touches DOM elements inside a page's
`[data-company-quote]` block (or, on the rankings table, a row's
`[data-quote]` cell). It never recalculates or rewrites anything else. This is
enforced structurally, not by convention alone: the shared quote-refresh
controller (`quote-controller.js`) is DOM-agnostic — it holds no reference to
score/rank markup at all, so there is no code path by which a quote tick could
touch it. Every quote-refresh test in `tests/frontend/*.test.js` that checks
this explicitly (see e.g. `research.test.js`'s "without touching score DOM"
assertion) is asserting a symptom of that separation, not the whole guarantee.

User-facing language keeps the two layers visibly distinct: a company page's
quote block reads "Market Price · Updated HH:MM IST" (plus a stale/delayed
badge and market-status text) — never "last updated," which the milestone's
brief explicitly forbids as ambiguous. The separate "Trust panel" (Level 3
pages) and build-line already state "Model … · Build … · Cutoff …" — a
distinct, pre-existing timestamp this milestone does not touch.

## Refresh policy

| Condition | Behavior |
|---|---|
| Market open (any refreshed instrument reports `market_status: "open"`) | Refresh every 90 seconds |
| Market closed (all refreshed instruments report closed/pre/post) | Refresh every 15 minutes — bounded, not "never," so a page left open across a market-open transition self-corrects without a full reload |
| Tab hidden (`document.hidden`) | Pending timer cleared, no requests. On visibility restore: immediate refresh if the last interval has already elapsed, otherwise the remaining wait is resumed |
| Offline (`navigator.onLine === false` / `offline` event) | Timer cleared, no requests. `online` event triggers an immediate refresh |
| Fetch failure (the whole request rejects — not a single instrument missing from a batch response) | Exponential backoff: `min(5000 × 2^(failures−1), 300000)` ms. After 5 consecutive failures, automatic retries stop entirely and a manual "Retry" control appears |
| Manual retry click | Bypasses the stopped gate, fetches immediately, resets the failure counter on success, always announces its own outcome |
| Two overlapping triggers (a timer firing at the same moment as a manual retry, or two rapid manual clicks) | The controller holds one in-flight promise per instance; a second trigger reuses it rather than issuing a duplicate request |

These constants live in `src/mbe/frontend/assets/quote-controller.js`'s
`DEFAULTS` object and are the same for every consumer (company page, rankings
table); nothing lowers them for convenience — the only place a shorter
interval is ever used is inside test harnesses, injected explicitly through
`create()`'s options.

## The refresh state machine

`quote-controller.js` exposes `MBEQuoteController.create(options)`, returning
`{ register, start, retry, destroy, getState }`. States: `idle`, `fetching`,
`scheduled`, `paused` (tab hidden), `offline`, `stopped` (backoff exhausted).
Every page-level consumer (`research.js`, `app.js`) creates exactly one
controller instance, registers one `apply(quote)` callback per instrument ID
it wants refreshed, and calls `start()` once. The controller:

1. Batches every currently-registered instrument ID into a single
   `fetchQuotes(ids)` call per tick, capped at `maxBatch` (default 30,
   matching the existing `/api/v1/quotes` batch limit).
2. Determines the next interval from the aggregate market status across the
   batch's successful results.
3. Silently establishes a baseline on its first successful tick, then only
   announces (via the page's `onAnnounce`, wired to the shared
   `[data-announcer]` node) when the aggregate market-status or error-presence
   category actually changes — never on every tick.
4. On a full fetch rejection, backs off exponentially; once it gives up
   (state `"stopped"`), it calls the page's `onStateChange` callback, which is
   the *only* place either consumer reveals a retry affordance or replaces a
   good last-known price with "Unavailable." A single transient failure never
   touches the DOM — this was a real defect caught during this milestone's own
   review cycle (research.js's first draft called the failure-rendering path
   from inside the fetch's own `catch`, wiping a correct price on the very
   first dropped request) and fixed before merge; the fix is what
   `onStateChange` exists for.

Wire-shape normalization (`NormalizedQuote` from `/api/v1/quotes`, or the
legacy `/api/quotes` dict shape) is handled by
`MBEQuoteController.fromApiQuote`/`.fromLegacyQuote`, shared by both
`research.js` and `app.js` rather than duplicated per page — a real bundle-size
regression (`app.js` briefly exceeded its documented 60 KiB budget once the
rankings table gained its own copy of these adapters) is what surfaced the
duplication and is why it now lives in the one file both pages already load.

## Quote capability

Every company page computes, at render time (server-side, from data the
Milestone 2A coverage policy already exposes — no new backend field was
added), which of these states it's in, and gates client-side refresh
accordingly:

- **Mapped** — `quote_available` true and `listing_status` is `active`/
  `unknown` → attempt refresh normally.
- **Unmapped** — no provider-symbol mapping (`quote_available` false) → never
  call the quotes API; `/api/v1/quotes` already reports this as
  `provider_mapping_missing` for any batch caller, and `assess_coverage()`
  already encodes it as `no_quote_provider_mapping`.
- **Inactive** / **Delisted** — `listing_status` is `inactive`/`suspended` or
  `delisted` → never attempt a live quote at all, per the milestone's explicit
  instruction; the page shows whatever was last rendered server-side and
  nothing more.
- **Unsupported provider** — structurally representable (a mapping whose
  provider isn't one the client fetch path recognizes) but unreachable today,
  since the backend's `default_registry()` only ever registers `"yahoo"`. Not
  tested with a real second provider, since building one is out of scope here.

Runtime freshness (`fresh`/`delayed`/`stale`/`missing`/`failed`/`unknown`) and
`market_status` are never computed client-side — they arrive verbatim on every
successful fetch from the existing `NormalizedQuote`/legacy-dict fields and
are only relabeled for display.

## Caching

`/api/v1/quotes` (like every other successful `mbe.api.app` route) already
carries `Cache-Control: public, max-age=60`, set unconditionally by the
existing request middleware (`src/mbe/api/app.py`) for any 2xx response — this
predates this milestone and required no change. The 90-second (market open)
and 15-minute (market closed) client poll intervals were chosen to sit
comfortably above that 60-second edge/browser cache window rather than fight
it, so a page's own poll and another visitor's overlapping request for the
same instrument within the same minute are very likely served from cache
rather than re-hitting Yahoo. No new caching code was added; this section
documents behavior that already existed.

Deduplication of *simultaneous* requests from the same page is handled
client-side by the controller's single in-flight-promise rule (see the state
machine section above) — this is a different, complementary mechanism to the
server's HTTP cache, and matters even when the HTTP cache is cold (e.g. the
very first fetch on a freshly loaded page, before any cache entry exists).

## Failure behavior

A quote failure — at any layer (network error, provider timeout, invalid
mapping, partial per-instrument failure within an otherwise-successful batch)
— never affects the rest of the report. This holds by construction:
`quote-controller.js` never touches any DOM outside the callbacks a consumer
explicitly registers, and both consumers only ever write into their own
quote-block markup. The static site build path is unaffected in a different,
stronger sense: it doesn't merely tolerate a quote failure, it never attempts
a live quote at all — `render_frontend_only`/`render_site_from_manifest` run
under `deny_network()`, and the quote-refresh JS only ever executes in a
browser, never during the Python build.

## Accessibility behavior

- Visual price/percentage/timestamp updates are silent — no `aria-live`
  announcement fires on an ordinary tick.
- The shared `[data-announcer]` node is used only when the categorical
  market-status or error state changes since the previous tick, or for a
  manual retry's own outcome (always announced, regardless of whether
  anything else changed).
- Price direction is never color-only: every rendered change carries a
  `+`/`−` sign, an `aria-hidden` arrow glyph (▲/▼), and the numeric text
  itself; the `quote-gain`/`quote-loss` CSS classes supply color as a
  secondary cue on top of that, not instead of it.
- The manual retry control is a real `<button type="button">` with visible,
  descriptive text ("Retry quote" / "Retry quotes") — keyboard-operable by
  default, no custom key handling needed.

## Provider limitations

Unchanged from the existing architecture: Yahoo Finance is the sole
registered quote provider (`default_registry()` only wires up `"yahoo"`);
its delay is passed through verbatim from `exchangeDataDelayedBy`, never
invented; and `/api/v1/quotes` carries a standing warning
("Yahoo Finance is an unofficial delayed provider.") on every response. This
milestone adds no second provider and no new abuse-prevention layer beyond
the existing batch cap (`MAX_QUOTE_INSTRUMENTS = 30`) and short cache —
building a dedicated rate limiter was judged out of scope, since nothing in
this milestone's brief required one beyond what already exists.

## Vercel runtime behavior

`api/v1.py` (the FastAPI app, including `/api/v1/quotes`) and the legacy
`api/quotes.py` serverless function are unchanged by this milestone — no new
route, no new `vercel.json` entry. The quote-refresh JS is a static asset
(`quote-controller.js`, copied alongside `app.js`/`research.js` via the
existing `_copy_assets()`), served from Vercel's static asset path with the
existing `Cache-Control: public, max-age=3600, must-revalidate` header
already applied to everything under `/assets/`. All quote *data* requests
still go through the two existing dynamic routes above, at their existing
60-second cache setting — nothing about how Vercel caches either path
changed.

## Milestone 2C prerequisites

Concrete, in priority order:

1. **Screener quote integration** — deliberately deferred this milestone.
   `screener.js` has no existing price/quote column to hook live data into;
   the shared `quote-controller.js` API (`register(instrumentId, applyFn)`)
   is generic enough to support it without modification, but which column and
   which visible-row set count as "the screener's quotes" needs its own design
   pass.
2. **A second quote provider** — the `ProviderRegistry`/`QuoteProvider`
   abstraction is real and already capability-generic (see
   `src/mbe/data/registry.py`, `src/mbe/data/provider.py`); only a second
   adapter implementing `QuoteProvider` and a `registry.register("quotes",
   "<name>", ...)` call are needed. Doing this would also make the
   "unsupported provider" quote-capability state (documented above but
   unreachable today) real.
3. **Watchlists** — out of scope for the whole of Phase 11 per
   `docs/HANDOVER.md`'s standing "Out of scope" list; the controller's
   registration API does not assume a company-page or rankings-page context,
   so a future watchlist page could reuse it directly once the feature itself
   is scoped.
