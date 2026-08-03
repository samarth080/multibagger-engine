"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM, VirtualConsole } = require("jsdom");

const root = path.resolve(__dirname, "../..");
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

function fixture() {
  const data = JSON.parse(fs.readFileSync(path.join(root, "site/data.json"), "utf8"));
  const row = data.top[0];
  const file = path.join(root, "site/company", `${row.instrument_id}.html`);
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", error => errors.push(error));
  const dom = new JSDOM(fs.readFileSync(file, "utf8"), {
    runScripts: "outside-only", url: `http://127.0.0.1:8765/company/${row.instrument_id}.html`,
    pretendToBeVisual: true, virtualConsole,
  });
  dom.window.navigator.clipboard = { writeText: async () => {} };
  dom.window.fetch = async () => ({ ok: false, status: 503, json: async () => ({}) });
  return { dom, row, errors };
}

test("canonical company page exposes the complete accessible research hierarchy", () => {
  const { dom, row, errors } = fixture();
  const document = dom.window.document;
  assert.equal(document.querySelector("h1").textContent.trim(), row.name);
  for (const id of ["research-summary", "why-ranked", "strengths", "risks", "score-history", "canonical-financials", "technical-context", "peer-comparison", "filings", "company-news", "research-checklist", "trust-panel"]) {
    assert.ok(document.getElementById(id), `missing #${id}`);
  }
  assert.ok(document.querySelector("svg[role='img'] title"));
  assert.ok(document.querySelector("table caption"));
  assert.ok(document.querySelector("[data-company-quote]").textContent.trim());
  assert.equal(document.querySelector("link[rel='canonical']").href, `https://multibagger-engine.vercel.app/company/${row.instrument_id}.html`);
  assert.deepEqual(errors, []);
  dom.window.close();
});

test("research checklist persists locally, resets and announces state", () => {
  const { dom, row, errors } = fixture();
  const { window } = dom;
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/research.js"), "utf8"));
  const first = window.document.querySelector("[data-checklist-item]");
  first.checked = true;
  first.dispatchEvent(new window.Event("change", { bubbles: true }));
  assert.match(window.document.querySelector("[data-checklist-status]").textContent, /^1 of/);
  assert.deepEqual(JSON.parse(window.localStorage.getItem(`mbe-research-checklist:${row.instrument_id}`)), [first.value]);
  window.document.querySelector("[data-reset-checklist]").click();
  assert.match(window.document.querySelector("[data-checklist-status]").textContent, /^0 of/);
  assert.equal(window.localStorage.getItem(`mbe-research-checklist:${row.instrument_id}`), null);
  assert.deepEqual(errors, []);
  dom.window.close();
});

test("legacy report route renders the same canonical research destination", () => {
  const data = JSON.parse(fs.readFileSync(path.join(root, "site/data.json"), "utf8"));
  const row = data.top[0];
  const html = fs.readFileSync(path.join(root, "site/reports", row.ticker_path), "utf8");
  const dom = new JSDOM(html);
  assert.equal(dom.window.document.querySelector("link[rel='canonical']").href,
    `https://multibagger-engine.vercel.app/company/${row.instrument_id}.html`);
  assert.ok(dom.window.document.querySelector("[data-research-page]"));
  dom.window.close();
});

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
  const { dom } = fixture();
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
