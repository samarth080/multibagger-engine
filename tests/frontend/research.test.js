"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM, VirtualConsole } = require("jsdom");

const root = path.resolve(__dirname, "../..");

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
