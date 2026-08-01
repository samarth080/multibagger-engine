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
  async function loadQuote() {
    const node = root.querySelector("[data-company-quote]"); if (!node || !validId) return;
    const apiMode = document.body.dataset.dataMode === "api";
    const url = apiMode ? `/api/v1/quotes?instrument_ids=${encodeURIComponent(instrumentId)}` : `/api/quotes?symbols=${encodeURIComponent(symbol + (exchange === "BSE" ? ".BO" : ".NS"))}`;
    try {
      const response = await global.fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
      if (!response.ok) throw new Error("quote unavailable"); const payload = await response.json();
      const quote = apiMode ? payload.data?.quotes?.[0] : payload.quotes?.[symbol + (exchange === "BSE" ? ".BO" : ".NS")];
      if (!quote) throw new Error("quote unavailable");
      const price = apiMode ? quote.last_price : quote.price; const change = apiMode ? quote.percentage_change : quote.day_change_pct;
      node.textContent = Number.isFinite(price) ? `₹${Number(price).toLocaleString("en-IN", { maximumFractionDigits: 2 })}${Number.isFinite(change) ? ` · ${change >= 0 ? "+" : ""}${Number(change).toFixed(2)}%` : ""}` : "Unavailable";
      const note = document.createElement("small"); note.textContent = `${quote.market_status || "Market status unavailable"}${(apiMode ? quote.freshness_state === "stale" : quote.is_stale) ? " · stale" : ""}`; node.append(note);
    } catch (_) { /* Keep the honest server-rendered build-close/unavailable state. */ }
  }
  loadQuote();
})(/** @type {Window & typeof globalThis} */ (globalThis));
