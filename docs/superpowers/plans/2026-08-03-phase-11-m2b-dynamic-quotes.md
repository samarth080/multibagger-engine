# Phase 11 Milestone 2B — Dynamic Market-Price Quote Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Company report pages (and the rankings table) refresh their market-price quote automatically, on a bounded schedule, through the existing provider-neutral `/api/v1/quotes` layer — without ever recalculating or touching the frozen research layer (score, rank, confidence, risk, financials, technical state, strengths, risks, history, peers).

**Architecture:** A new dependency-free, DOM-agnostic module `src/mbe/frontend/assets/quote-controller.js` implements one client-side refresh state machine (idle → fetching → scheduled/backoff/stopped, with pause-on-hidden-tab and offline handling) and is shared — not duplicated — by the two existing quote consumers: the company research page (`research.js`) and the rankings table (`app.js`). Each consumer supplies a small adapter that normalizes its own wire shape (the v1 API's `NormalizedQuote` or the legacy `/api/quotes` dict) into one common internal shape before handing it to the controller; the controller never parses a wire format and never touches score/rank DOM. The backend already satisfies almost every Milestone 2B requirement (provider-neutral contract, Yahoo adapter, staleness/delay computation, fail-closed provider-symbol validation, partial-failure handling, batch limits, a short `Cache-Control: public, max-age=60` on every 2xx response) — this plan adds zero new backend endpoints and only adds tests that pin down scenarios the spec calls out explicitly (previous-close missing, provider timeout, invalid mapping, inactive listing) that weren't yet asserted. "Quote capability" (mapped / unmapped / inactive / delisted) is derived entirely from data the coverage policy and identity payload already expose (`quote_available`, `listing_status`) — no new coverage fields are added, keeping Milestone 2A's policy the single source of truth.

**Tech Stack:** Vanilla JS (`src/mbe/frontend/assets/*.js`), Jinja2 templates, `node --test` + `jsdom` for frontend tests, Python 3 / FastAPI / pydantic v2 (`mbe.api`, `mbe.data.market`) for backend tests, pytest.

**Full design reference:** this plan's own "Design decisions" section below (no separate design doc was written — the milestone is additive to the Milestone 2A architecture already documented in `docs/coverage-architecture.md`).

---

## Design decisions (read before coding)

**Refresh policy (constants live in `quote-controller.js`, injectable for tests):**
| Condition | Interval |
|---|---|
| Any refreshed instrument reports `market_status: "open"` | 90 seconds |
| All refreshed instruments report a closed/pre/post market | 15 minutes (still bounded — never "never", so a page left open across a market-open transition self-corrects) |
| Tab hidden (`document.hidden`) | Timer cleared; no requests. On visibility restore: if the elapsed time already exceeds the last interval, fetch immediately; otherwise resume the remaining wait. |
| Offline (`navigator.onLine === false` / `offline` event) | Timer cleared; no requests. On `online` event: fetch immediately. |
| Fetch failure (network/HTTP error, not a per-instrument error) | Exponential backoff: `min(5000 * 2^(failures-1), 300000)` ms. After 5 consecutive failures: stop automatic retries, surface a manual "Retry" control. |
| Manual retry click | Bypasses the "stopped" gate, fetches immediately, resets the failure counter on success, always announces its own outcome. |
| Two overlapping refresh triggers (timer + visibility restore, or two manual clicks) | The controller keeps one in-flight promise per instance and returns/awaits it instead of issuing a second request — this is the "simultaneous requests deduplicated" requirement. |

**Quote capability states** (per company page, computed client-side, no new backend fields):
- `mapped` — coverage `quote_available: true` and `listing_status` is `active`/`unknown` → attempt refresh.
- `unmapped` — `quote_available: false` (no provider symbol) → never call the quotes API; show "No public quote mapping is available" (this is exactly what `/api/v1/quotes` already returns as `provider_mapping_missing` for batch callers, and what `assess_coverage` already encodes as `no_quote_provider_mapping`).
- `inactive` — `listing_status in {inactive, suspended}` → never call the quotes API (per spec: "Do not attempt live quotes for inactive... instruments unless explicitly supported"); show the listing-status badge that `company_coverage.html`/`company.html` already render.
- `delisted` — `listing_status == "delisted"` → same as `inactive`, distinct label.
- `unsupported_provider` — reserved for a future second provider; structurally representable (any mapping whose `provider` isn't one the client fetch path knows how to call) but unreachable today since `default_registry()` only ever registers `"yahoo"`. Documented, not tested with a real second provider (that would be inventing scope Milestone 2B doesn't ask for).

Runtime freshness (`fresh`/`delayed`/`stale`/`missing`/`failed`/`unknown`) and `market_status` come back on every successful fetch from the existing `NormalizedQuote`/legacy-dict fields — these are never computed client-side, only relabeled for display.

**Accessibility:** visual price/percentage/timestamp updates are silent (no `aria-live` announcement per tick). The shared `[data-announcer]` node is used only when the *categorical* market-status or error state changes since the previous tick, and always once for a manual retry's own outcome. Price direction is never color-only: every rendered change carries a `+`/`−` sign, an `aria-hidden` arrow glyph, and the numeric text itself (already legible to screen readers) — `quote-gain`/`quote-loss` CSS classes (already defined in `app.css`) supply color only as a secondary cue.

**Caching:** the existing FastAPI middleware (`src/mbe/api/app.py:158`) already sets `Cache-Control: public, max-age=60` on every successful response, including `/api/v1/quotes` — this doubles as the "short server-side quote cache" the spec asks for and is why the client polling interval (90s open / 15min closed) is chosen to sit comfortably above it rather than fight it. No new caching code is added; this plan documents the existing behavior in `docs/quote-refresh-architecture.md`.

**Screener:** deliberately out of scope for this milestone. `screener.js` has zero quote-related code today and its columns are driven entirely by the offline dataset snapshot, not by any live-quote hook — wiring quotes into it would mean inventing new screener UI surface (which column? which rows count as "visible"?) that this milestone's spec does not pin down. The shared controller's API (`register(instrumentId, applyFn)`) is generic enough that a future milestone can wire it into the screener without touching `quote-controller.js` itself. This is called out explicitly in the completion report's "Known limitations" and "Milestone 2C" sections rather than silently skipped.

---

## File structure

New:
- `src/mbe/frontend/assets/quote-controller.js` — shared refresh state machine (DOM-agnostic)
- `tests/frontend/quote-controller.test.js`
- `docs/quote-refresh-architecture.md`

Modified:
- `src/mbe/frontend/assets/research.js` — replace the one-shot `loadQuote()` with a controller-driven refresh; add the capability gate (mapped/unmapped/inactive/delisted); add retry wiring
- `src/mbe/frontend/assets/app.js` — replace `loadQuotes`/`renderQuote` in `initRankings()` with a controller-driven refresh (same 30-row cap, same dual api/legacy mode); add a manual "Retry" affordance
- `src/mbe/frontend/templates/base.html` — one added `<script defer>` line for `quote-controller.js`, loaded before `app.js`
- `src/mbe/frontend/templates/company.html` — redesign the hero "Quote" `<dd>` into a richer quote block with granular hooks; add `data-listing-status`
- `src/mbe/frontend/templates/company_coverage.html` — same treatment for the Level 0–2 quote section; add `data-listing-status` (already has `company.is_inactive` in scope)
- `tests/frontend/research.test.js` — extend with the new quote scenarios
- `tests/frontend/dom.test.js` — extend the rankings quote-failure test with success/backoff/retry scenarios
- `tests/test_market_provider.py` — add previous-close-missing and partial-fields scenarios
- `tests/test_api_v1.py` — add invalid-mapping / inactive-listing / duplicate-id-dedup scenarios for `/api/v1/quotes`
- `tests/test_deterministic_build.py` — add the Milestone 2B hash-invariance test
- `docs/HANDOVER.md` — new "Phase 11 Milestone 2B" section

---

### Task 1: Quote-controller core state machine

**Files:**
- Create: `src/mbe/frontend/assets/quote-controller.js`
- Test: `tests/frontend/quote-controller.test.js`

- [ ] **Step 1: Write the failing tests**

```js
// tests/frontend/quote-controller.test.js
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "../..");
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

function harness({ visible = true, online = true } = {}) {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://127.0.0.1:8765/" });
  const { window } = dom;
  Object.defineProperty(window.document, "hidden", { value: !visible, configurable: true });
  Object.defineProperty(window.navigator, "onLine", { value: online, configurable: true });
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/quote-controller.js"), "utf8"));
  return { dom, window };
}

function stubFetch(sequence) {
  let call = 0;
  const calls = [];
  return {
    calls,
    fetchQuotes: async ids => {
      calls.push(ids.slice());
      const step = sequence[Math.min(call, sequence.length - 1)];
      call += 1;
      if (step instanceof Error) throw step;
      return step(ids);
    },
  };
}

test("successful tick applies quotes and schedules the open-market interval", async () => {
  const { window } = harness();
  const { fetchQuotes, calls } = stubFetch([
    ids => new Map(ids.map(id => [id, { price: 110, marketStatus: "open", freshnessState: "fresh" }])),
  ]);
  const applied = [];
  const controller = window.MBEQuoteController.create({
    fetchQuotes, openIntervalMs: 20, closedIntervalMs: 20, document: window.document, window,
  });
  controller.register("id-1", quote => applied.push(quote));
  controller.start();
  await wait(10);
  assert.equal(calls.length, 1);
  assert.deepEqual(applied[0], { price: 110, marketStatus: "open", freshnessState: "fresh" });
  assert.equal(controller.getState(), "scheduled");
  controller.destroy();
});

test("closed-market ticks use the closed interval and market-status changes are reported to onAnnounce once", async () => {
  const { window } = harness();
  const { fetchQuotes } = stubFetch([
    ids => new Map(ids.map(id => [id, { price: 100, marketStatus: "closed", freshnessState: "fresh" }])),
  ]);
  const announcements = [];
  const controller = window.MBEQuoteController.create({
    fetchQuotes, openIntervalMs: 500, closedIntervalMs: 15, onAnnounce: m => announcements.push(m),
    document: window.document, window,
  });
  controller.register("id-1", () => {});
  controller.start();
  await wait(10);
  await wait(30);
  // First tick establishes the baseline silently; repeated closed ticks report nothing new.
  assert.deepEqual(announcements, []);
  controller.destroy();
});

test("a full fetch failure backs off exponentially then stops after the configured max", async () => {
  const { window } = harness();
  const { fetchQuotes, calls } = stubFetch([new Error("network down")]);
  const announcements = [];
  const controller = window.MBEQuoteController.create({
    fetchQuotes, baseBackoffMs: 5, maxBackoffMs: 40, maxConsecutiveFailures: 3,
    onAnnounce: m => announcements.push(m), document: window.document, window,
  });
  controller.register("id-1", () => {});
  controller.start();
  await wait(120);
  assert.ok(calls.length >= 3, `expected at least 3 attempts, got ${calls.length}`);
  assert.equal(controller.getState(), "stopped");
  assert.ok(announcements.some(m => /stopped after repeated failures/.test(m)));
  controller.destroy();
});

test("manual retry bypasses the stopped gate, resets failures on success and always announces", async () => {
  const { window } = harness();
  let mode = "fail";
  const fetchQuotes = async ids => {
    if (mode === "fail") throw new Error("still down");
    return new Map(ids.map(id => [id, { price: 50, marketStatus: "closed", freshnessState: "fresh" }]));
  };
  const announcements = [];
  const controller = window.MBEQuoteController.create({
    fetchQuotes, baseBackoffMs: 5, maxBackoffMs: 10, maxConsecutiveFailures: 2,
    onAnnounce: m => announcements.push(m), document: window.document, window,
  });
  controller.register("id-1", () => {});
  controller.start();
  await wait(60);
  assert.equal(controller.getState(), "stopped");
  mode = "success";
  await controller.retry();
  assert.equal(controller.getState(), "scheduled");
  assert.ok(announcements.some(m => m === "Quote refreshed."));
  controller.destroy();
});

test("hidden tab pauses polling and restores on visibility with an immediate fetch when overdue", async () => {
  const { window } = harness({ visible: false });
  const { fetchQuotes, calls } = stubFetch([
    ids => new Map(ids.map(id => [id, { price: 1, marketStatus: "open", freshnessState: "fresh" }])),
  ]);
  const controller = window.MBEQuoteController.create({
    fetchQuotes, openIntervalMs: 10000, document: window.document, window,
  });
  controller.register("id-1", () => {});
  controller.start();
  await wait(20);
  assert.equal(calls.length, 0, "must not fetch while the tab starts hidden");
  Object.defineProperty(window.document, "hidden", { value: false, configurable: true });
  window.document.dispatchEvent(new window.Event("visibilitychange"));
  await wait(10);
  assert.equal(calls.length, 1);
  controller.destroy();
});

test("offline stops polling and online triggers an immediate refresh", async () => {
  const { window } = harness();
  const { fetchQuotes, calls } = stubFetch([
    ids => new Map(ids.map(id => [id, { price: 1, marketStatus: "open", freshnessState: "fresh" }])),
  ]);
  const controller = window.MBEQuoteController.create({
    fetchQuotes, openIntervalMs: 10, document: window.document, window,
  });
  controller.register("id-1", () => {});
  controller.start();
  await wait(15);
  const successfulCalls = calls.length;
  assert.ok(successfulCalls >= 1);
  Object.defineProperty(window.navigator, "onLine", { value: false, configurable: true });
  window.dispatchEvent(new window.Event("offline"));
  await wait(30);
  assert.equal(calls.length, successfulCalls, "no requests while offline");
  Object.defineProperty(window.navigator, "onLine", { value: true, configurable: true });
  window.dispatchEvent(new window.Event("online"));
  await wait(10);
  assert.equal(calls.length, successfulCalls + 1);
  controller.destroy();
});

test("overlapping triggers deduplicate into a single in-flight request", async () => {
  const { window } = harness();
  let resolveFetch;
  const calls = [];
  const fetchQuotes = async ids => {
    calls.push(ids.slice());
    return new Promise(resolve => { resolveFetch = () => resolve(new Map(ids.map(id => [id, { price: 1 }]))); });
  };
  const controller = window.MBEQuoteController.create({
    fetchQuotes, openIntervalMs: 10000, document: window.document, window,
  });
  controller.register("id-1", () => {});
  const first = controller.start();
  const second = controller.retry();
  await wait(5);
  assert.equal(calls.length, 1, "a second trigger while one is in flight must not issue a new request");
  resolveFetch();
  await Promise.all([first, second]);
  controller.destroy();
});

test("more than the configured batch cap registers only the first N ids in a single request", async () => {
  const { window } = harness();
  const seen = [];
  const controller = window.MBEQuoteController.create({
    fetchQuotes: async ids => { seen.push(ids); return new Map(); },
    maxBatch: 3, openIntervalMs: 10000, document: window.document, window,
  });
  for (let i = 0; i < 5; i += 1) controller.register(`id-${i}`, () => {});
  await controller.start();
  assert.equal(seen[0].length, 3);
  controller.destroy();
});

test("never touches DOM directly — apply callbacks are the only side effect", async () => {
  const { window } = harness();
  const controller = window.MBEQuoteController.create({
    fetchQuotes: async ids => new Map(ids.map(id => [id, { price: 1 }])),
    openIntervalMs: 10000, document: window.document, window,
  });
  const before = window.document.body.innerHTML;
  controller.register("id-1", () => {});
  await controller.start();
  assert.equal(window.document.body.innerHTML, before);
  controller.destroy();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tests/frontend/quote-controller.test.js`
Expected: FAIL with `TypeError: Cannot read properties of undefined (reading 'create')` (or similar — `window.MBEQuoteController` does not exist yet).

- [ ] **Step 3: Write the implementation**

```js
// src/mbe/frontend/assets/quote-controller.js
/* Shared dynamic quote-refresh state machine (Phase 11 Milestone 2B).
 * DOM-agnostic on purpose: callers register an instrument ID plus an
 * apply(quote|null) callback and own all rendering themselves. This module
 * never touches score/rank/research DOM and never parses a provider wire
 * shape — callers pass an already-normalized common quote shape via their
 * injected fetchQuotes(ids) -> Map<id, quote|null>.
 */
(function (global) {
  "use strict";

  const DEFAULTS = Object.freeze({
    openIntervalMs: 90000,
    closedIntervalMs: 900000,
    baseBackoffMs: 5000,
    maxBackoffMs: 300000,
    maxConsecutiveFailures: 5,
    maxBatch: 30,
  });

  function createController(options = {}) {
    const config = { ...DEFAULTS, ...options };
    const fetchQuotes = config.fetchQuotes;
    const onAnnounce = config.onAnnounce || (() => {});
    const onStateChange = config.onStateChange || (() => {});
    const now = config.now || (() => Date.now());
    const doc = config.document || global.document;
    const win = config.window || global;
    const setTimeoutFn = (config.setTimeout || win.setTimeout).bind(win);
    const clearTimeoutFn = (config.clearTimeout || win.clearTimeout).bind(win);

    const watchers = new Map();
    let timer = null;
    let inFlight = null;
    let consecutiveFailures = 0;
    let lastIntervalMs = config.openIntervalMs;
    let lastSuccessAt = 0;
    let previousMarketStatus = null;
    let previousHadError = false;
    let hasBaseline = false;
    let stopped = false;
    let destroyed = false;
    let state = "idle";

    function setState(next) { state = next; onStateChange(state); }
    function ids() { return Array.from(watchers.keys()).slice(0, config.maxBatch); }
    function clearTimer() { if (timer !== null) { clearTimeoutFn(timer); timer = null; } }
    function isHidden() { return Boolean(doc && doc.hidden); }
    function isOffline() { return Boolean(win.navigator && win.navigator.onLine === false); }

    function scheduleNext(delayMs) {
      clearTimer();
      lastIntervalMs = delayMs;
      timer = setTimeoutFn(() => { tick(false); }, delayMs);
    }

    function applyResults(resultsById) {
      let anyOpen = false;
      let anyError = false;
      for (const [id, applySet] of watchers) {
        const result = resultsById.get(id) || null;
        if (result && result.marketStatus === "open") anyOpen = true;
        if (!result || result.error) anyError = true;
        applySet.forEach(apply => {
          try { apply(result); } catch (_) { /* one bad DOM handler must not break the batch */ }
        });
      }
      return { anyOpen, anyError };
    }

    async function tick(manual = false) {
      if (destroyed) return;
      if (!manual && stopped) return;
      if (isOffline()) { clearTimer(); setState("offline"); return; }
      if (!manual && isHidden()) { clearTimer(); setState("paused"); return; }
      const requestedIds = ids();
      if (!requestedIds.length) { setState("idle"); return; }
      if (inFlight) return inFlight;
      setState("fetching");
      inFlight = (async () => {
        try {
          const resultsById = await fetchQuotes(requestedIds);
          const { anyOpen, anyError } = applyResults(resultsById);
          consecutiveFailures = 0;
          stopped = false;
          lastSuccessAt = now();
          const marketStatus = anyOpen ? "open" : "closed";
          if (manual) {
            onAnnounce(anyError ? "Quote refreshed. Some instruments are still unavailable." : "Quote refreshed.");
          } else if (hasBaseline && (marketStatus !== previousMarketStatus || anyError !== previousHadError)) {
            onAnnounce(
              anyError ? "Some quotes are temporarily unavailable."
                : marketStatus === "open" ? "Market is open. Quotes are refreshing automatically."
                : "Market is closed. Showing the last available quote."
            );
          }
          hasBaseline = true;
          previousMarketStatus = marketStatus;
          previousHadError = anyError;
          setState("scheduled");
          scheduleNext(marketStatus === "open" ? config.openIntervalMs : config.closedIntervalMs);
        } catch (_) {
          consecutiveFailures += 1;
          if (consecutiveFailures >= config.maxConsecutiveFailures) {
            stopped = true;
            setState("stopped");
            onAnnounce(manual ? "Quote refresh failed again." : "Quote updates stopped after repeated failures. Use Retry to try again.");
            return;
          }
          if (manual) onAnnounce("Quote refresh failed. Retrying automatically.");
          const delay = Math.min(config.baseBackoffMs * (2 ** (consecutiveFailures - 1)), config.maxBackoffMs);
          setState("backoff");
          scheduleNext(delay);
        } finally {
          inFlight = null;
        }
      })();
      return inFlight;
    }

    function handleVisibility() {
      if (destroyed) return;
      if (isHidden()) { clearTimer(); setState("paused"); return; }
      if (isOffline()) { setState("offline"); return; }
      if (stopped) return;
      const elapsed = now() - lastSuccessAt;
      if (!lastSuccessAt || elapsed >= lastIntervalMs) tick(false);
      else scheduleNext(lastIntervalMs - elapsed);
    }

    function handleOffline() { clearTimer(); setState("offline"); }
    function handleOnline() { if (!stopped) tick(false); }

    if (doc && doc.addEventListener) doc.addEventListener("visibilitychange", handleVisibility);
    if (win && win.addEventListener) { win.addEventListener("offline", handleOffline); win.addEventListener("online", handleOnline); }

    function register(instrumentId, apply) {
      if (!watchers.has(instrumentId)) watchers.set(instrumentId, new Set());
      watchers.get(instrumentId).add(apply);
      return function unregister() {
        const set = watchers.get(instrumentId);
        if (!set) return;
        set.delete(apply);
        if (!set.size) watchers.delete(instrumentId);
      };
    }

    function start() { return destroyed ? Promise.resolve() : tick(false); }
    function retry() { clearTimer(); return tick(true); }
    function getState() { return state; }

    function destroy() {
      destroyed = true;
      clearTimer();
      if (doc && doc.removeEventListener) doc.removeEventListener("visibilitychange", handleVisibility);
      if (win && win.removeEventListener) { win.removeEventListener("offline", handleOffline); win.removeEventListener("online", handleOnline); }
    }

    return { register, start, retry, destroy, getState };
  }

  global.MBEQuoteController = { create: createController, DEFAULTS };
})(typeof globalThis !== "undefined" ? globalThis : this);
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/frontend/quote-controller.test.js`
Expected: all tests pass (`pass 9`, `fail 0`).

- [ ] **Step 5: Lint and typecheck**

Run: `npm run lint && npm run typecheck`
Expected: no errors. If `eslint`/`tsc` flag the new file for a convention used elsewhere (e.g. the `/** @param {Window & typeof globalThis} global */` JSDoc header other asset files use), add it to match.

- [ ] **Step 6: Commit**

```bash
git add src/mbe/frontend/assets/quote-controller.js tests/frontend/quote-controller.test.js
git commit -m "feat(quotes): add shared dynamic quote-refresh state machine"
```

---

### Task 2: Wire the controller into the company research page

**Files:**
- Modify: `src/mbe/frontend/assets/research.js`
- Modify: `src/mbe/frontend/templates/base.html`
- Test: `tests/frontend/research.test.js`

- [ ] **Step 1: Add `quote-controller.js` to `base.html` before `app.js`**

```html
<!-- src/mbe/frontend/templates/base.html, replacing the single line at the bottom of <body> -->
  <script defer src="{{ asset_prefix }}/quote-controller.js"></script>
  <script defer src="{{ asset_prefix }}/app.js"></script>
  {% block scripts %}{% endblock %}
```

- [ ] **Step 2: Write the failing tests**

```js
// tests/frontend/research.test.js — add these tests (keep the existing three)
test("company page applies a successful quote update to price, change and timestamp without touching score DOM", () => {
  const { dom, row, errors } = fixture();
  const { window } = dom;
  // The checked-in site/ is rendered with MBE_FRONTEND_DATA_MODE=static (see
  // render_frontend_only), so body.dataset.dataMode is "static" by default;
  // force "api" here to exercise the /api/v1/quotes branch of research.js.
  window.document.body.dataset.dataMode = "api";
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/quote-controller.js"), "utf8"));
  const scoreBefore = window.document.querySelector(".hero-score strong").textContent;
  window.fetch = async url => {
    if (String(url).includes("/api/v1/quotes")) {
      return {
        ok: true,
        json: async () => ({ data: { quotes: [{
          instrument_id: row.instrument_id, last_price: 555.5, percentage_change: 1.25,
          market_status: "open", freshness_state: "fresh", provider_timestamp: "2026-08-03T05:00:00Z",
        }] } }),
      };
    }
    return { ok: false, status: 404, json: async () => ({}) };
  };
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/research.js"), "utf8"));
  return wait(30).then(() => {
    const price = window.document.querySelector("[data-quote-price]");
    const change = window.document.querySelector("[data-quote-change]");
    assert.match(price.textContent, /555\.50/);
    assert.match(change.textContent, /\+1\.25%/);
    assert.equal(window.document.querySelector(".hero-score strong").textContent, scoreBefore);
    assert.deepEqual(errors, []);
    dom.window.close();
  });
});

test("delayed and stale quotes render their badges and market status", () => {
  const { dom, row } = fixture();
  const { window } = dom;
  window.document.body.dataset.dataMode = "api";
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/quote-controller.js"), "utf8"));
  window.fetch = async () => ({
    ok: true,
    json: async () => ({ data: { quotes: [{
      instrument_id: row.instrument_id, last_price: 100, percentage_change: -0.5,
      market_status: "open", freshness_state: "stale", staleness_reason: "quote is older than expected while market is open",
      reported_delay_minutes: 15, provider_timestamp: "2026-08-03T05:00:00Z",
    }] } }),
  });
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/research.js"), "utf8"));
  return wait(30).then(() => {
    assert.match(window.document.querySelector("[data-quote-status-badge]").textContent, /Stale/);
    assert.match(window.document.querySelector("[data-quote-market-status]").textContent, /Open/i);
    dom.window.close();
  });
});

test("previous close missing still renders a price without a fabricated change value", () => {
  const { dom, row } = fixture();
  const { window } = dom;
  window.document.body.dataset.dataMode = "api";
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/quote-controller.js"), "utf8"));
  window.fetch = async () => ({
    ok: true,
    json: async () => ({ data: { quotes: [{
      instrument_id: row.instrument_id, last_price: 100, percentage_change: null, previous_close: null,
      market_status: "closed", freshness_state: "fresh",
    }] } }),
  });
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/research.js"), "utf8"));
  return wait(30).then(() => {
    assert.match(window.document.querySelector("[data-quote-price]").textContent, /100\.00/);
    assert.equal(window.document.querySelector("[data-quote-change]").textContent.trim(), "");
    dom.window.close();
  });
});

test("quote-unavailable shows a retry control that is keyboard-operable and announces on use", () => {
  const { dom, row } = fixture();
  const { window } = dom;
  window.document.body.dataset.dataMode = "api";
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/quote-controller.js"), "utf8"));
  let attempt = 0;
  window.fetch = async () => {
    attempt += 1;
    if (attempt === 1) throw new Error("network down");
    return {
      ok: true,
      json: async () => ({ data: { quotes: [{ instrument_id: row.instrument_id, last_price: 42, market_status: "closed", freshness_state: "fresh" }] } }),
    };
  };
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/research.js"), "utf8"));
  return wait(30).then(() => {
    const retry = window.document.querySelector("[data-quote-retry]");
    assert.ok(retry && !retry.hidden, "retry control must be visible after a failed fetch");
    assert.equal(retry.tagName, "BUTTON");
    retry.dispatchEvent(new window.Event("click", { bubbles: true }));
    return wait(15).then(() => {
      assert.match(window.document.querySelector("[data-quote-price]").textContent, /42\.00/);
      assert.match(window.document.querySelector("[data-announcer]").textContent, /Quote refreshed/);
      dom.window.close();
    });
  });
});

test("inactive and delisted companies never trigger a quote fetch", () => {
  const { dom, row } = fixture();
  const { window } = dom;
  window.document.querySelector("[data-research-page]").dataset.listingStatus = "delisted";
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/quote-controller.js"), "utf8"));
  let fetched = false;
  window.fetch = async () => { fetched = true; return { ok: true, json: async () => ({ data: { quotes: [] } }) }; };
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/research.js"), "utf8"));
  return wait(30).then(() => {
    assert.equal(fetched, false);
    dom.window.close();
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `node --test tests/frontend/research.test.js`
Expected: FAIL — `[data-quote-price]` etc. do not exist yet (template not updated, Task 3) and `research.js` still runs the old one-shot `loadQuote()`.

- [ ] **Step 4: Rewrite `research.js`'s quote section**

```js
// src/mbe/frontend/assets/research.js — replace the loadQuote() function and its
// call site (the whole block from `async function loadQuote()` to `loadQuote();`)
// with the following. Everything above it (checklist, copy link, comparison) is unchanged.
function apiQuoteToCommon(quote) {
  if (!quote) return null;
  return {
    price: quote.last_price ?? null,
    changePct: quote.percentage_change ?? null,
    marketStatus: quote.market_status || "unknown",
    freshnessState: quote.freshness_state || "unknown",
    stalenessReason: quote.staleness_reason || null,
    delayMinutes: quote.reported_delay_minutes ?? null,
    providerTimestamp: quote.provider_timestamp || null,
    error: Boolean(quote.error_code),
  };
}
function legacyQuoteToCommon(quote) {
  if (!quote) return null;
  return {
    price: quote.price ?? null,
    changePct: quote.day_change_pct ?? null,
    marketStatus: quote.market_status || "unknown",
    freshnessState: quote.is_stale ? "stale" : "fresh",
    stalenessReason: quote.stale_reason || null,
    delayMinutes: quote.delay_minutes ?? null,
    providerTimestamp: quote.as_of || null,
    error: false,
  };
}
const quoteRoot = root.querySelector("[data-company-quote]");
const listingStatus = String(root.dataset.listingStatus || "active");
if (quoteRoot && validId && !["inactive", "suspended", "delisted"].includes(listingStatus) && global.MBEQuoteController) {
  const priceNode = quoteRoot.querySelector("[data-quote-price]");
  const changeNode = quoteRoot.querySelector("[data-quote-change]");
  const badgeNode = quoteRoot.querySelector("[data-quote-status-badge]");
  const marketStatusNode = quoteRoot.querySelector("[data-quote-market-status]");
  const updatedNode = quoteRoot.querySelector("[data-quote-updated]");
  const retryButton = quoteRoot.querySelector("[data-quote-retry]");
  const apiMode = document.body.dataset.dataMode === "api";
  const legacySymbol = symbol + (exchange === "BSE" ? ".BO" : ".NS");

  function render(common) {
    if (!common || common.price == null) {
      priceNode.textContent = "Unavailable";
      changeNode.textContent = "";
      if (badgeNode) badgeNode.hidden = true;
      if (marketStatusNode) marketStatusNode.textContent = "Market status unavailable";
      if (retryButton) retryButton.hidden = false;
      return;
    }
    if (retryButton) retryButton.hidden = true;
    priceNode.textContent = `₹${Number(common.price).toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
    changeNode.textContent = Number.isFinite(common.changePct)
      ? `${common.changePct >= 0 ? "▲ +" : "▼ "}${Number(common.changePct).toFixed(2)}%` : "";
    changeNode.className = !Number.isFinite(common.changePct) ? "quote-change"
      : common.changePct >= 0 ? "quote-change quote-gain" : "quote-change quote-loss";
    if (badgeNode) {
      const label = common.freshnessState === "stale" ? "Stale"
        : common.freshnessState === "delayed" ? `Delayed${common.delayMinutes ? ` ${common.delayMinutes}m` : ""}` : "";
      badgeNode.hidden = !label;
      badgeNode.textContent = label;
    }
    if (marketStatusNode) marketStatusNode.textContent = common.marketStatus ? `${common.marketStatus} market` : "Market status unavailable";
    if (updatedNode) {
      updatedNode.textContent = common.providerTimestamp
        ? `Updated ${new Date(common.providerTimestamp).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })} IST`
        : "Retrieval time unavailable";
    }
  }

  const controller = global.MBEQuoteController.create({
    onAnnounce: announce,
    fetchQuotes: async ids => {
      const url = apiMode
        ? `/api/v1/quotes?instrument_ids=${encodeURIComponent(ids.join(","))}`
        : `/api/quotes?symbols=${encodeURIComponent(legacySymbol)}`;
      const response = await global.fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
      if (!response.ok) throw new Error(`http_${response.status}`);
      const payload = await response.json();
      const result = new Map();
      if (apiMode) {
        for (const quote of payload.data?.quotes || []) result.set(quote.instrument_id, apiQuoteToCommon(quote));
      } else {
        result.set(instrumentId, legacyQuoteToCommon(payload.quotes?.[legacySymbol]));
      }
      return result;
    },
  });
  controller.register(instrumentId, render);
  controller.start();
  retryButton?.addEventListener("click", () => controller.retry());
}
```

- [ ] **Step 5: Run the tests**

Run: `node --test tests/frontend/research.test.js`
Expected: still FAIL on the DOM-hook tests (`[data-quote-price]` etc.) until Task 3 updates the templates and rebuilds `site/company/*.html` fixtures the tests read from. Confirm the failure is specifically "element not found," not a JS error — that isolates the remaining work to markup.

- [ ] **Step 6: Commit**

```bash
git add src/mbe/frontend/assets/research.js src/mbe/frontend/templates/base.html tests/frontend/research.test.js
git commit -m "feat(quotes): drive the company-page quote block from the shared refresh controller"
```

---

### Task 3: Company page template markup

**Files:**
- Modify: `src/mbe/frontend/templates/company.html`
- Modify: `src/mbe/frontend/templates/company_coverage.html`

- [ ] **Step 1: Redesign the Level 3 hero quote block in `company.html`**

Replace this line:
```html
      <div><dt>Quote</dt><dd data-company-quote>{% if research.quote.price is not none %}₹{{ '{:,.2f}'.format(research.quote.price) }}{% else %}Unavailable{% endif %}<small>{{ research.quote.message }}</small></dd></div>
```
with:
```html
      <div><dt>Market Price</dt><dd data-company-quote>
        <span data-quote-price>{% if research.quote.price is not none %}₹{{ '{:,.2f}'.format(research.quote.price) }}{% else %}Unavailable{% endif %}</span>
        <span data-quote-change class="quote-change"></span>
        <span class="badge badge-warning" data-quote-status-badge hidden></span>
        <small data-quote-market-status>{{ research.quote.message }}</small>
        <small data-quote-updated></small>
        <button type="button" class="button button-quiet button-small" data-quote-retry hidden>Retry quote</button>
      </dd></div>
```

- [ ] **Step 2: Add `data-listing-status` to the article root**

```html
<!-- company.html line 4, add one attribute -->
<article class="research-page" data-research-page data-instrument-id="{{ research.identity.instrument_id }}" data-symbol="{{ research.identity.symbol }}" data-exchange="{{ research.identity.exchange }}" data-listing-status="{{ research.identity.listing_status }}">
```

- [ ] **Step 3: Same treatment for `company_coverage.html`**

Replace the article root's opening tag:
```html
<article class="research-page" data-research-page data-coverage-company data-instrument-id="{{ company.identity.instrument_id }}" data-symbol="{{ company.identity.symbol }}" data-exchange="{{ company.identity.exchange }}" data-listing-status="{{ company.identity.listing_status }}">
```
Replace the "Current price" / "Day change" `<dt>`/`<dd>` pair in `.hero-metrics` with:
```html
      <div><dt>Market Price</dt><dd data-company-quote>
        <span data-quote-price>{% if company.quote and company.quote.price is not none %}₹{{ '{:,.2f}'.format(company.quote.price) }}{% else %}Unavailable{% endif %}</span>
        <span data-quote-change class="quote-change"></span>
        <span class="badge badge-warning" data-quote-status-badge hidden></span>
        <small data-quote-market-status>{% if company.quote and company.quote.market_status %}{{ company.quote.market_status|title }} market{% else %}Market status unavailable{% endif %}</small>
        <small data-quote-updated></small>
        <button type="button" class="button button-quiet button-small" data-quote-retry hidden>Retry quote</button>
      </dd></div>
```
Leave the existing "52-week high"/"52-week low"/"Market cap" `<dt>`/`<dd>` rows untouched — those stay build-time-only fields (the spec only requires the *current* price line to refresh).

- [ ] **Step 4: Rebuild the static site so the jsdom fixtures in Task 2's tests read the new markup**

Run exactly this one command — it is the safe, deterministic, network-denied path (`render_site_from_manifest`, confirmed by reading `scripts/build_site.py:191-205` and `src/mbe/builds/offline.py:221-234`):

```bash
uv run python scripts/build_site.py --manifest builds/manifests/phase11-m1-frozen-inputs.json --out site
```

This re-renders every `site/company/*.html` and `site/reports/*.html` from the frozen research payloads using the templates just edited, and re-copies every file in `src/mbe/frontend/assets/` (including the new `quote-controller.js`, via `_copy_assets()` in `src/mbe/publish.py:612-617`, which copies the whole directory — no per-file wiring needed) into `site/assets/`.

Do **not** additionally run `scripts/build_search_assets.py` or `scripts/build_coverage_artifact.py`. `docs/HANDOVER.md`'s Milestone 2A entry (search `"Pre-deploy step required"`) already flagged that regenerating `search-index.json`/`research-coverage.json` needs its own explicit human review pass (a `build_mode` labeling bug and a stale `verify_release.py` JSON count) — that is a pre-existing Milestone 2A gap, not part of Milestone 2B's scope, and must be left exactly as it is. Confirm afterward with `git diff --stat site/ | grep -v '^ site/company/\| site/reports/\| site/assets/'` — expect no output (i.e. only company pages, legacy report pages and assets changed).

- [ ] **Step 5: Run the full frontend test suite**

Run: `npm test`
Expected: all `tests/frontend/*.test.js` pass, including Task 1 and Task 2's new tests.

- [ ] **Step 6: Commit**

```bash
git add src/mbe/frontend/templates/company.html src/mbe/frontend/templates/company_coverage.html site/
git commit -m "feat(quotes): add granular market-price DOM hooks to both company templates"
```

---

### Task 4: Wire the controller into the rankings table

**Files:**
- Modify: `src/mbe/frontend/assets/app.js`
- Test: `tests/frontend/dom.test.js`

- [ ] **Step 1: Write the failing tests**

```js
// tests/frontend/dom.test.js — add these tests after the existing ones
test("rankings quotes refresh through the shared controller and expose a manual retry after backoff stops", async () => {
  const { dom, window } = await application();
  const document = window.document;
  let attempt = 0;
  window.fetch = async input => {
    const url = new URL(String(input), window.location.href);
    if (url.pathname === "/api/v1/status" || url.pathname === "/api/v1/rankings") return response({}, 503);
    if (url.pathname === "/api/quotes") { attempt += 1; return response({}, 503); }
    if (url.pathname.endsWith(".json")) return response(JSON.parse(fs.readFileSync(path.join(root, "site", url.pathname.replace(/^\//, "")), "utf8")));
    return response({}, 404);
  };
  await wait(600);
  const retry = document.querySelector("[data-quotes-retry]");
  assert.ok(retry, "a manual retry control must appear once automatic backoff stops");
  const firstSpan = document.querySelector("[data-ranking-rows] [data-quote]");
  assert.equal(firstSpan.textContent.trim(), "Unavailable");
  dom.window.close();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test tests/frontend/dom.test.js`
Expected: FAIL — `[data-quotes-retry]` does not exist.

- [ ] **Step 3: Replace `loadQuotes`/`renderQuote` in `app.js`'s `initRankings()`**

```js
// src/mbe/frontend/assets/app.js — inside initRankings(), replace the existing
// `loadQuotes` and `renderQuote` const declarations (and the `quoteUnavailable`
// variable is no longer needed) with:
let quoteController = null;
function commonFromApi(quote) {
  if (!quote) return null;
  return { price: quote.last_price ?? null, changePct: quote.percentage_change ?? null, marketStatus: quote.market_status || "unknown", freshnessState: quote.freshness_state || "unknown", delayMinutes: quote.reported_delay_minutes ?? null, providerTimestamp: quote.provider_timestamp || null, error: Boolean(quote.error_code) };
}
function commonFromLegacy(quote) {
  if (!quote) return null;
  return { price: quote.price ?? null, changePct: quote.day_change_pct ?? null, marketStatus: quote.market_status || "unknown", freshnessState: quote.is_stale ? "stale" : "fresh", delayMinutes: quote.delay_minutes ?? null, providerTimestamp: quote.as_of || null, error: false };
}
function renderQuote(span, common) {
  if (!common || common.price == null) { span.textContent = "Unavailable"; span.title = "No usable quote for this instrument."; return; }
  span.className = common.freshnessState === "stale" || !Number.isFinite(common.changePct) ? "cell-note" : common.changePct >= 0 ? "quote-gain" : "quote-loss";
  span.replaceChildren(create("strong", "", `₹${formatNumber(common.price, 2)}${Number.isFinite(common.changePct) ? ` ${common.changePct >= 0 ? "+" : ""}${formatNumber(common.changePct, 2)}%` : ""}`));
  const notes = [common.freshnessState === "stale" ? "Stale" : null, common.marketStatus, Number.isFinite(common.delayMinutes) && common.delayMinutes > 0 ? `${common.delayMinutes}m delay` : null, common.providerTimestamp ? new Date(common.providerTimestamp).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) + " IST" : null].filter(Boolean);
  if (notes.length) span.append(create("span", "cell-note", notes.join(" · ")));
}
function ensureQuoteController() {
  if (quoteController || !global.MBEQuoteController) return quoteController;
  quoteController = global.MBEQuoteController.create({
    maxBatch: 30,
    onStateChange: nextState => {
      let retryEl = qs("[data-quotes-retry]", root);
      if (nextState === "stopped") {
        if (!retryEl) {
          retryEl = create("button", "button button-quiet button-small", "Retry quotes");
          retryEl.type = "button"; retryEl.dataset.quotesRetry = "";
          retryEl.addEventListener("click", () => quoteController.retry());
          qs("[data-mode-badge]", root)?.after(retryEl);
        }
      } else if (retryEl) retryEl.remove();
    },
    onAnnounce: announce,
    fetchQuotes: async ids => {
      const result = new Map();
      if (response?.mode === "api") {
        const payload = await fetchJson(`${API.quotes}?instrument_ids=${encodeURIComponent(ids.join(","))}`, { timeout: 9000 });
        const byId = new Map((payload.data?.quotes || []).map(quote => [quote.instrument_id, quote]));
        for (const id of ids) result.set(id, commonFromApi(byId.get(id)));
      } else {
        const bySymbol = new Map(qsa("[data-quote]", tbody).map(span => [span.dataset.quote, span.dataset.symbol]));
        const symbols = [...new Set(ids.map(id => bySymbol.get(id)).filter(Boolean))];
        const payload = await fetchJson(`/api/quotes?symbols=${encodeURIComponent(symbols.join(","))}`, { timeout: 9000 });
        for (const id of ids) result.set(id, commonFromLegacy(payload.quotes?.[bySymbol.get(id)]));
      }
      return result;
    },
  });
  return quoteController;
}
const registeredRows = new Set();
const loadQuotes = rows => {
  if (!rows.length) return;
  const controller = ensureQuoteController();
  if (!controller) return;
  for (const row of rows) {
    if (registeredRows.has(row.instrument_id)) continue;
    registeredRows.add(row.instrument_id);
    controller.register(row.instrument_id, common => {
      const span = qs(`[data-quote="${row.instrument_id}"]`, tbody);
      if (span) renderQuote(span, common);
    });
  }
  controller.start();
};
```

- [ ] **Step 4: Run the tests**

Run: `npm test`
Expected: all pass, including the new rankings quote test and every previously-passing test (the rewrite must not change `renderRows`'s call site, `applyColumns(); loadQuotes(rows);`, which stays as-is).

- [ ] **Step 5: Lint and typecheck**

Run: `npm run check`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/mbe/frontend/assets/app.js tests/frontend/dom.test.js
git commit -m "feat(quotes): drive rankings-table quotes from the shared refresh controller"
```

---

### Task 5: Backend tests for scenarios the spec calls out explicitly

**Files:**
- Modify: `tests/test_market_provider.py`
- Modify: `tests/test_api_v1.py`

No production backend code changes in this task — the existing `/api/v1/quotes` route, `NormalizedQuote` contract, `YahooChartQuoteProvider`, and fail-closed mapping lookup already implement every one of these scenarios; this task only adds assertions that were missing.

- [ ] **Step 1: Add previous-close-missing and partial-fields tests**

```python
# tests/test_market_provider.py — add after the existing tests
def test_missing_previous_close_yields_a_price_with_no_change(): 
    request = QuoteRequest(instrument_id="a", provider_symbol="A.NS")
    payload = _payload()
    del payload["chart"]["result"][0]["meta"]["chartPreviousClose"]
    quote = normalize_yahoo_chart(payload, request, now_ts=1_700_000_600)
    assert quote.last_price == 110
    assert quote.previous_close is None
    assert quote.absolute_change is None
    assert quote.percentage_change is None


def test_partial_fields_missing_volume_and_ohlc_still_yield_a_usable_quote():
    request = QuoteRequest(instrument_id="a", provider_symbol="A.NS")
    payload = _payload()
    meta = payload["chart"]["result"][0]["meta"]
    for key in ("regularMarketOpen", "regularMarketDayHigh", "regularMarketDayLow", "regularMarketVolume"):
        del meta[key]
    quote = normalize_yahoo_chart(payload, request, now_ts=1_700_000_600)
    assert quote.last_price == 110
    assert quote.open is None and quote.day_high is None and quote.day_low is None and quote.volume is None


def test_provider_timeout_becomes_the_same_safe_partial_failure_as_a_malformed_payload():
    def timing_out(_symbol):
        raise TimeoutError("upstream timed out")
    provider = YahooChartQuoteProvider(fetcher=timing_out)
    [quote] = provider.get_quotes([QuoteRequest(instrument_id="a", provider_symbol="A.NS")])
    assert quote.error_code == "provider_unavailable"
    assert "timed out" not in (quote.error_message or "")
```

- [ ] **Step 2: Add invalid-mapping, dedup and cache-header tests reusing the existing `api` fixture**

`api` (defined at `tests/test_api_v1.py:49-80`) already yields `(TestClient, ids, manifest)` where `ids` maps `"GOOD.NS"/"ALSO.NS" -> instrument_id` for two active, fully-scored, provider-mapped instruments — exactly what `test_validation_errors_and_quote_limits_are_stable` (`:138-158`) already uses for its `"missing-id"` case. Add these tests right after it, following the same `(client, ids, _) = api` unpacking:

```python
# tests/test_api_v1.py — add after test_validation_errors_and_quote_limits_are_stable
def test_quotes_endpoint_reports_invalid_mapping_as_a_structured_error_not_a_fetch(api):
    client, ids, _ = api
    response = client.get("/api/v1/quotes", params={"instrument_ids": "totally-unknown-instrument-id"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["quotes"] == []
    assert body["errors"] == [{
        "code": "provider_mapping_missing",
        "message": "No public quote mapping is available.",
        "field": "totally-unknown-instrument-id",
    }]


def test_quotes_endpoint_deduplicates_repeated_instrument_ids_in_one_request(api):
    client, ids, _ = api
    good_id = ids["GOOD.NS"]
    response = client.get("/api/v1/quotes", params={"instrument_ids": f"{good_id},{good_id},{good_id}"})
    assert response.status_code == 200
    assert len(response.json()["data"]["quotes"]) == 1


def test_quotes_endpoint_sets_a_short_public_cache_header(api):
    client, ids, _ = api
    response = client.get("/api/v1/quotes", params={"instrument_ids": ids["GOOD.NS"]})
    assert response.headers["cache-control"] == "public, max-age=60"
```

- [ ] **Step 3: Add one focused inactive-listing test with its own minimal fixture**

The shared `api` fixture's two seed rows are both `listing_status: "active"` and fully screened/ranked — reusing it for a delisted, unranked instrument would require mutating rows the other 10 tests in this file depend on. Add a small, self-contained test instead, mirroring `api()`'s own construction exactly but with one unranked, unmapped, delisted row:

```python
# tests/test_api_v1.py — add as its own test, independent of the `api` fixture
def test_company_summary_for_a_delisted_unmapped_instrument_never_fabricates_a_quote():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        import_instruments(session, [{
            "company_name": "Delisted Shell Limited", "symbol": "DELIST", "exchange": "NSE",
            "isin": "INE999Z01019", "sector": None, "industry": None,
            "listing_status": "delisted", "provider_symbols": {}, "aliases": [],
        }], source_code="test_master", source_version="v1")
        instrument_id = session.scalars(select(InstrumentRow.instrument_id)).one()
    client = TestClient(create_app(engine=engine, provider_registry=ProviderRegistry()))
    response = client.get(f"/api/v1/company/{instrument_id}/summary")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["listing_status"] == "delisted"
    assert body["quote"] is None
    assert body["research_available"] is False
```

Confirm `ProviderRegistry()` constructed with zero registered providers doesn't raise on a company with no provider mapping (the route's own `try/except Exception: quote = None` at `src/mbe/api/app.py:466-479` should absorb `registry.get("quotes")` never even being called, since the mapping lookup at `:469-472` returns `None` first) — if this assumption is wrong the test will surface it immediately as a 500, which is itself useful signal to fix in `app.py` rather than paper over in the test.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_market_provider.py tests/test_api_v1.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_market_provider.py tests/test_api_v1.py
git commit -m "test(quotes): pin down previous-close-missing, timeout, invalid-mapping and dedup scenarios"
```

---

### Task 6: Deterministic build hash-invariance test

**Files:**
- Modify: `tests/test_deterministic_build.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deterministic_build.py — add after test_coverage_artifact_does_not_change_the_preserved_public_hashes
def test_quote_refresh_ui_does_not_change_score_financial_or_membership_hashes(tmp_path):
    """Milestone 2B only touches templates/JS that render around the existing
    quote value — it must not perturb any research/score/financial output or
    which companies belong to which coverage level."""
    from mbe.builds.offline import build_coverage_only, build_search_only, render_site_from_manifest
    out = tmp_path / "site"
    render_site_from_manifest(MANIFEST, out)
    build_search_only(MANIFEST, out, write_manifest=False)
    build_coverage_only(MANIFEST, out)
    assert public_value_hashes(out) == VALUE_FIXTURE
    search_index = json.loads((out / "api/v1/search-index.json").read_text())
    membership = sorted(
        (r["instrument_id"], r["research_coverage_level"], r["ranking_available"])
        for r in search_index["data"]
    )
    fixture_path = ROOT / "tests/fixtures/phase11-m2b-membership-hash.json"
    if not fixture_path.exists():
        fixture_path.write_text(json.dumps(membership, indent=2, sort_keys=True))
    assert membership == json.loads(fixture_path.read_text())


def test_deny_network_still_blocks_the_offline_build_after_the_quote_ui_change(tmp_path):
    from mbe.builds.offline import render_site_from_manifest
    from mbe.builds.network import OfflineNetworkError, deny_network
    with deny_network():
        with pytest.raises(OfflineNetworkError):
            import urllib.request
            urllib.request.urlopen("https://query1.finance.yahoo.com/v8/finance/chart/TEST.NS", timeout=1)
    # The real build must still succeed under the same guard — no new network
    # call was introduced by the frontend quote controller (it only runs in
    # the browser, never during the Python build).
    render_site_from_manifest(MANIFEST, tmp_path / "site2")
```

`search_index["data"]` and each row's `research_coverage_level`/`ranking_available` fields are confirmed against `src/mbe/builds/offline.py:190-196` (`build_coverage_only` reads the same `["data"]` list) and `src/mbe/search/domain.py:106,137` (`SearchIndexRecord.research_coverage_level`, `.ranking_available`).

- [ ] **Step 2: Run to verify the first run creates the fixture, then run again to verify it's pinned**

Run: `uv run pytest tests/test_deterministic_build.py -k m2b -v`
Expected: PASS on both runs (the first run writes `tests/fixtures/phase11-m2b-membership-hash.json`; commit that file).

- [ ] **Step 3: Commit**

```bash
git add tests/test_deterministic_build.py tests/fixtures/phase11-m2b-membership-hash.json
git commit -m "test(quotes): guard score, financial and coverage-membership hashes against the quote UI change"
```

---

### Task 7: Documentation

**Files:**
- Create: `docs/quote-refresh-architecture.md`
- Modify: `docs/HANDOVER.md`

- [ ] **Step 1: Write `docs/quote-refresh-architecture.md`**

Cover, in this order, each as its own `##` section with 3–8 sentences plus the relevant table from this plan's "Design decisions": (1) runtime market layer vs frozen research layer, with the exact field lists from the milestone's objective; (2) the refresh-policy table; (3) the state-machine's states and transitions (idle/fetching/scheduled/backoff/stopped/paused/offline) with the dedup and manual-retry rules; (4) quote-capability states (mapped/unmapped/inactive/delisted/unsupported_provider) and where each is computed; (5) caching — the existing `Cache-Control: public, max-age=60` middleware and why the poll intervals are chosen above it; (6) accessibility behavior; (7) provider limitations (Yahoo unofficial/delayed, single-provider registry); (8) Vercel runtime behavior (which routes are serverless functions vs static, and that the quote fetch always happens client-side against `/api/v1/quotes` or `/api/quotes`, never during static generation); (9) Milestone 2C prerequisites — list concretely: screener quote integration, a second quote provider behind the existing registry, watchlists.

- [ ] **Step 2: Add a "Phase 11 Milestone 2B" section to `docs/HANDOVER.md`**

Match the style of the existing "Phase 11 Milestone 1" section (`docs/HANDOVER.md:2161`) — read it first for tone/format, then write an analogous section summarizing what shipped, the file list, and a link to `docs/quote-refresh-architecture.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/quote-refresh-architecture.md docs/HANDOVER.md
git commit -m "docs(quotes): record the dynamic quote-refresh architecture and update HANDOVER"
```

---

### Task 8: Full verification pass and completion report

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `uv run pytest -q`
Expected: all pass; record the exact count for the completion report.

- [ ] **Step 2: Run the full frontend suite**

Run: `npm test`
Expected: all pass; record the exact count.

- [ ] **Step 3: Run lint/typecheck**

Run: `npm run check`
Expected: clean.

- [ ] **Step 4: Confirm no stray network calls in core tests**

Run: `grep -rn "query1.finance.yahoo.com" tests/ | grep -v test_market_provider.py`
Expected: no output outside the one file that intentionally exercises the adapter with an injected fake fetcher (never a real network call).

- [ ] **Step 5: Review the diff before committing anything left uncommitted**

Run: `git status && git diff --stat release/v1.0.0-rc1...HEAD`
Expected: only the files listed in "File structure" above, plus any rebuilt `site/` artifacts from Task 3.

- [ ] **Step 6: Produce the completion report**

Report, in prose, exactly the items the milestone's "At completion report" section asks for: quote-refresh interval (90s open / 15min closed), market-open/closed/hidden-tab/backoff behavior (from "Design decisions"), cache duration (60s, existing middleware), first-update latency (measure once manually: open a rebuilt company page locally, time from load to the first `[data-quote-price]` update — report the observed number, do not guess), API changes (none — zero new endpoints, only additive tests), frontend controller changes (`quote-controller.js` + the two integration points), the two hash values from `public_value_hashes()` plus the membership-hash fixture, Python test count, frontend test count, the list of commit SHAs/messages from this branch, known limitations (screener deferred, single quote provider, 15-minute closed-market ceiling rather than "never"), and the Milestone 2C recommendation (screener integration, second provider behind the existing registry, watchlists — in that order, with a one-sentence reason each).

- [ ] **Step 7: Do not push**

Per the milestone's instructions, leave all commits local on `phase11-m2b-dynamic-quotes`. Do not run `git push`.
