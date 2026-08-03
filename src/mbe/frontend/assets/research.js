/* Company-research progressive enhancement: quote, copy, comparison and local checklist. */
/** @param {Window & typeof globalThis} global */
(function researchBootstrap(global) {
  "use strict";
  const document = global.document;
  if (!document) return;
  const root = /** @type {HTMLElement | null} */ (document.querySelector("[data-research-page]"));
  if (!root) return;
  const instrumentId = String(root.dataset.instrumentId || "");
  const symbol = String(root.dataset.symbol || "");
  const exchange = String(root.dataset.exchange || "NSE");
  const validId = /^[A-Za-z0-9-]{1,80}$/.test(instrumentId);
  const storage = (() => { try { return global.localStorage; } catch (_) { return null; } })();
  const announce = message => { const node = document.querySelector("[data-announcer]"); if (node) node.textContent = message; };
  const checklistKey = validId ? `mbe-research-checklist:${instrumentId}` : "";
  const readCodes = () => { if (!checklistKey) return new Set(); try { const parsed = JSON.parse(storage?.getItem(checklistKey) || "[]"); return new Set(Array.isArray(parsed) ? parsed.filter(value => typeof value === "string") : []); } catch (_) { return new Set(); } };
  const boxes = /** @type {HTMLInputElement[]} */ (Array.from(root.querySelectorAll("[data-checklist-item]")));
  let completed = readCodes();
  const updateChecklist = (speak = false) => {
    boxes.forEach(box => { box.checked = completed.has(box.value); });
    const status = root.querySelector("[data-checklist-status]");
    if (status) status.textContent = `${completed.size} of ${boxes.length} complete`;
    if (speak) announce(`${completed.size} of ${boxes.length} research checklist items complete.`);
  };
  boxes.forEach(box => box.addEventListener("change", () => {
    if (box.checked) completed.add(box.value); else completed.delete(box.value);
    if (checklistKey) storage?.setItem(checklistKey, JSON.stringify([...completed].sort())); updateChecklist(true);
  }));
  root.querySelector("[data-reset-checklist]")?.addEventListener("click", () => {
    completed = new Set(); if (checklistKey) storage?.removeItem(checklistKey); updateChecklist(true);
  });
  updateChecklist();
  const copyButton = /** @type {HTMLButtonElement | null} */ (root.querySelector("[data-copy-link]"));
  copyButton?.addEventListener("click", async () => {
    try { await global.navigator.clipboard.writeText(global.location.href); copyButton.textContent = "Link copied"; announce("Canonical company link copied."); global.setTimeout(() => { copyButton.textContent = "Copy link"; }, 1800); }
    catch (_) { announce("Could not copy the company link."); }
  });
  const comparisonButton = /** @type {HTMLButtonElement | null} */ (root.querySelector("[data-add-comparison]"));
  comparisonButton?.addEventListener("click", () => {
    const key = "mbe-comparison-instruments"; let ids = [];
    try { const parsed = JSON.parse(storage?.getItem(key) || "[]"); ids = Array.isArray(parsed) ? parsed : []; } catch (_) {}
    ids = [...new Set([...ids, instrumentId])].filter(id => /^[A-Za-z0-9-]{1,80}$/.test(id)).slice(-8);
    storage?.setItem(key, JSON.stringify(ids)); comparisonButton.textContent = "Added to comparison";
    announce(`${symbol || "Company"} added to the local comparison list.`);
  });
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
  const quoteRoot = /** @type {HTMLElement | null} */ (root.querySelector("[data-company-quote]"));
  // Task 4 (rankings table) may need this same rule; if so it should define
  // its own copy rather than importing from research.js — quote-controller.js
  // is the shared, DOM-agnostic module and this list is a page-level policy.
  const listingStatus = String(root.dataset.listingStatus || "active");
  const priceNode = /** @type {HTMLElement | null | undefined} */ (quoteRoot?.querySelector("[data-quote-price]"));
  const changeNode = /** @type {HTMLElement | null | undefined} */ (quoteRoot?.querySelector("[data-quote-change]"));
  const controllerFactory = /** @type {{ create: Function } | undefined} */ (global["MBEQuoteController"]);
  // priceNode/changeNode are the minimum markup this block can render into
  // (and imply quoteRoot exists, since they're queried from it); without them
  // there is nothing to update, so skip creating (and starting) a controller
  // entirely rather than polling a page that can never show the result.
  if (!priceNode || !changeNode || !validId || ["inactive", "suspended", "delisted"].includes(listingStatus) || !controllerFactory) return;

  const badgeNode = /** @type {HTMLElement | null} */ (quoteRoot.querySelector("[data-quote-status-badge]"));
  const marketStatusNode = /** @type {HTMLElement | null} */ (quoteRoot.querySelector("[data-quote-market-status]"));
  const updatedNode = /** @type {HTMLElement | null} */ (quoteRoot.querySelector("[data-quote-updated]"));
  const retryButton = /** @type {HTMLButtonElement | null} */ (quoteRoot.querySelector("[data-quote-retry]"));
  const apiMode = document.body.dataset.dataMode === "api";
  const legacySymbol = symbol + (exchange === "BSE" ? ".BO" : ".NS");

  const render = common => {
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
  };

  async function fetchAndNormalize(ids) {
    const url = apiMode
      ? `/api/v1/quotes?instrument_ids=${encodeURIComponent(ids.join(","))}`
      : `/api/quotes?symbols=${encodeURIComponent(legacySymbol)}`;
    const response = await global.fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
    if (!response.ok) throw new Error(`http_${response.status}`);
    const payload = await response.json();
    const result = new Map();
    if (apiMode) {
      for (const quote of payload.data?.quotes || []) result.set(String(quote.instrument_id), apiQuoteToCommon(quote));
    } else {
      result.set(instrumentId, legacyQuoteToCommon(payload.quotes?.[legacySymbol]));
    }
    return result;
  }

  const controller = controllerFactory.create({
    onAnnounce: announce,
    // A transient failure (one dropped fetch, one 503) must stay silent and
    // keep showing the last-known-good quote — the controller itself is
    // still auto-retrying with backoff underneath. Only once it gives up
    // (state "stopped", after maxConsecutiveFailures) do we surface
    // "Unavailable" and reveal the retry control.
    onStateChange: state => { if (state === "stopped") render(null); },
    fetchQuotes: fetchAndNormalize,
  });
  controller.register(instrumentId, render);
  controller.start();
  retryButton?.addEventListener("click", () => controller.retry());
})(/** @type {Window & typeof globalThis} */ (globalThis));
