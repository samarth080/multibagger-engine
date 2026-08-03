/* Shared DOM-agnostic quote-refresh state machine. Reused, unmodified, by the
 * company-research page (research.js) and the rankings table (app.js); each
 * consumer supplies its own fetchQuotes adapter that normalizes its wire
 * shape (v1 API `NormalizedQuote` or the legacy `/api/quotes` dict) into a
 * common { price, marketStatus, freshnessState, error, ... } shape before
 * handing it here. This module never touches DOM beyond registering a
 * visibilitychange listener on the injected document — all rendering
 * happens through the apply callbacks passed to register(). */
/** @param {Window & typeof globalThis} global */
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

  function noop() {}

  function numberOr(value, fallback) {
    return typeof value === "number" && Number.isFinite(value) ? value : fallback;
  }

  /**
   * @typedef {object} MBEQuoteControllerOptions
   * @property {(ids: string[]) => Promise<Map<string, object|null>>} fetchQuotes
   * @property {(message: string) => void} [onAnnounce]
   * @property {(state: string) => void} [onStateChange]
   * @property {() => number} [now]
   * @property {Document} [document]
   * @property {Window & typeof globalThis} [window]
   * @property {typeof globalThis.setTimeout} [setTimeout]
   * @property {typeof globalThis.clearTimeout} [clearTimeout]
   * @property {number} [openIntervalMs]
   * @property {number} [closedIntervalMs]
   * @property {number} [baseBackoffMs]
   * @property {number} [maxBackoffMs]
   * @property {number} [maxConsecutiveFailures]
   * @property {number} [maxBatch]
   */

  /**
   * Creates one quote-refresh controller instance. Every option is optional
   * except `fetchQuotes`; numeric config falls back to the Milestone 2B
   * defaults documented in the design doc.
   * @param {MBEQuoteControllerOptions} options
   */
  function create(options) {
    const opts = /** @type {MBEQuoteControllerOptions} */ (options || {});
    if (typeof opts.fetchQuotes !== "function") throw new Error("MBEQuoteController.create requires a fetchQuotes function");
    const win = /** @type {Window & typeof globalThis} */ (opts.window || global);
    const doc = /** @type {Document | undefined} */ (opts.document || win.document);
    const fetchQuotes = opts.fetchQuotes;
    const onAnnounce = typeof opts.onAnnounce === "function" ? opts.onAnnounce : noop;
    const onStateChange = typeof opts.onStateChange === "function" ? opts.onStateChange : noop;
    const now = typeof opts.now === "function" ? opts.now : Date.now;
    const setTimer = typeof opts.setTimeout === "function" ? opts.setTimeout : win.setTimeout.bind(win);
    const clearTimer = typeof opts.clearTimeout === "function" ? opts.clearTimeout : win.clearTimeout.bind(win);
    const openIntervalMs = numberOr(opts.openIntervalMs, DEFAULTS.openIntervalMs);
    const closedIntervalMs = numberOr(opts.closedIntervalMs, DEFAULTS.closedIntervalMs);
    const baseBackoffMs = numberOr(opts.baseBackoffMs, DEFAULTS.baseBackoffMs);
    const maxBackoffMs = numberOr(opts.maxBackoffMs, DEFAULTS.maxBackoffMs);
    const maxConsecutiveFailures = numberOr(opts.maxConsecutiveFailures, DEFAULTS.maxConsecutiveFailures);
    const maxBatch = numberOr(opts.maxBatch, DEFAULTS.maxBatch);

    /** @type {Map<string, Set<(quote: object|null) => void>>} */
    const registry = new Map();
    let state = "idle";
    let timerId = /** @type {ReturnType<typeof setTimeout> | null} */ (null);
    let inFlight = /** @type {Promise<void> | null} */ (null);
    let failures = 0;
    let destroyed = false;
    let lastFetchAt = /** @type {number | null} */ (null);
    let lastScheduledIntervalMs = 0;
    let baselineEstablished = false;
    let prevMarketOpen = false;
    let prevHasError = false;

    function setState(next) {
      if (state === next) return;
      state = next;
      onStateChange(state);
    }

    function clearPendingTimer() {
      if (timerId !== null) { clearTimer(timerId); timerId = null; }
    }

    function schedule(delayMs) {
      clearPendingTimer();
      lastScheduledIntervalMs = delayMs;
      timerId = setTimer(() => { timerId = null; runTick("timer"); }, delayMs);
    }

    function batchIds() {
      return Array.from(registry.keys()).slice(0, maxBatch);
    }

    async function performFetch(trigger) {
      const ids = batchIds();
      setState("fetching");
      try {
        const resultsById = await fetchQuotes(ids);
        if (destroyed) return;
        failures = 0;
        for (const id of ids) {
          const quote = (resultsById && typeof resultsById.get === "function" ? resultsById.get(id) : undefined) || null;
          const callbacks = registry.get(id);
          if (!callbacks) continue;
          callbacks.forEach(apply => {
            try { apply(quote); } catch (_) { /* one bad watcher must not break the others */ }
          });
        }
        const marketOpen = ids.some(id => {
          const quote = resultsById && typeof resultsById.get === "function" ? resultsById.get(id) : undefined;
          return Boolean(quote) && quote.marketStatus === "open";
        });
        const hasError = ids.some(id => {
          const quote = resultsById && typeof resultsById.get === "function" ? resultsById.get(id) : undefined;
          return !quote || Boolean(quote.error);
        });
        lastFetchAt = now();
        const interval = marketOpen ? openIntervalMs : closedIntervalMs;
        if (trigger === "manual") {
          onAnnounce("Quote refreshed.");
        } else if (baselineEstablished && (marketOpen !== prevMarketOpen || hasError !== prevHasError)) {
          onAnnounce(marketOpen ? "The market is now open." : hasError ? "A quote could not be refreshed." : "The market is now closed.");
        }
        baselineEstablished = true;
        prevMarketOpen = marketOpen;
        prevHasError = hasError;
        schedule(interval);
        setState("scheduled");
      } catch (_err) {
        if (destroyed) return;
        failures += 1;
        if (failures >= maxConsecutiveFailures) {
          clearPendingTimer();
          setState("stopped");
          onAnnounce("Quote updates stopped after repeated failures. Use Retry to try again.");
        } else {
          schedule(Math.min(baseBackoffMs * (2 ** (failures - 1)), maxBackoffMs));
          setState("scheduled");
        }
      }
    }

    function runTick(trigger) {
      if (destroyed) return Promise.resolve();
      if (trigger !== "manual" && state === "stopped") return Promise.resolve();
      if (doc && doc.hidden) {
        clearPendingTimer();
        setState("paused");
        return Promise.resolve();
      }
      if (win.navigator && win.navigator.onLine === false) {
        clearPendingTimer();
        setState("offline");
        return Promise.resolve();
      }
      if (inFlight) return inFlight;
      clearPendingTimer();
      inFlight = performFetch(trigger).finally(() => { inFlight = null; });
      return inFlight;
    }

    function onVisibilityChange() {
      if (destroyed || !doc) return;
      if (doc.hidden) {
        clearPendingTimer();
        setState("paused");
        return;
      }
      if (state === "stopped") return;
      const elapsed = lastFetchAt === null ? Infinity : now() - lastFetchAt;
      if (elapsed >= lastScheduledIntervalMs) runTick("visibility");
      else { schedule(lastScheduledIntervalMs - elapsed); setState("scheduled"); }
    }

    function onOffline() {
      if (destroyed) return;
      clearPendingTimer();
      setState("offline");
    }

    function onOnline() {
      if (destroyed || state === "stopped") return;
      runTick("online");
    }

    if (doc && typeof doc.addEventListener === "function") doc.addEventListener("visibilitychange", onVisibilityChange);
    if (win && typeof win.addEventListener === "function") {
      win.addEventListener("offline", onOffline);
      win.addEventListener("online", onOnline);
    }

    return {
      register(instrumentId, applyFn) {
        const id = String(instrumentId);
        let callbacks = registry.get(id);
        if (!callbacks) { callbacks = new Set(); registry.set(id, callbacks); }
        callbacks.add(applyFn);
        return function unregister() {
          const callbacksForId = registry.get(id);
          if (!callbacksForId) return;
          callbacksForId.delete(applyFn);
          if (callbacksForId.size === 0) registry.delete(id);
        };
      },
      start() { return runTick("start"); },
      retry() { return runTick("manual"); },
      destroy() {
        destroyed = true;
        clearPendingTimer();
        if (doc && typeof doc.removeEventListener === "function") doc.removeEventListener("visibilitychange", onVisibilityChange);
        if (win && typeof win.removeEventListener === "function") {
          win.removeEventListener("offline", onOffline);
          win.removeEventListener("online", onOnline);
        }
      },
      getState() { return state; },
    };
  }

  const pure = { create };
  global["MBEQuoteController"] = pure;
  if (typeof module !== "undefined" && module.exports) module.exports = pure;
})(/** @type {Window & typeof globalThis} */ (globalThis));
