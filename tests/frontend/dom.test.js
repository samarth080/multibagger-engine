"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM, VirtualConsole } = require("jsdom");

const root = path.resolve(__dirname, "../..");
const wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

function response(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
}

async function application() {
  const virtualConsole = new VirtualConsole();
  const errors = [];
  virtualConsole.on("jsdomError", error => errors.push(error));
  const dom = new JSDOM(fs.readFileSync(path.join(root, "site/index.html"), "utf8"), {
    runScripts: "outside-only",
    url: "http://127.0.0.1:8765/",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const { window } = dom;
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  window.HTMLElement.prototype.scrollIntoView = function scrollIntoView() {};
  window.HTMLDialogElement.prototype.showModal = function showModal() { this.setAttribute("open", ""); };
  window.HTMLDialogElement.prototype.close = function close() { this.removeAttribute("open"); };
  window.navigator.clipboard = { writeText: async () => {} };
  window.fetch = async input => {
    const url = new URL(String(input), window.location.href);
    if (url.pathname === "/api/v1/status" || url.pathname === "/api/v1/rankings") return response({}, 503);
    if (url.pathname === "/api/quotes") return response({}, 503);
    if (url.pathname.endsWith(".json")) {
      const file = path.join(root, "site", url.pathname.replace(/^\//, ""));
      return response(JSON.parse(fs.readFileSync(file, "utf8")));
    }
    return response({}, 404);
  };
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/app.js"), "utf8"));
  window.document.dispatchEvent(new window.Event("DOMContentLoaded", { bubbles: true }));
  await wait(80);
  return { dom, window, errors };
}

test("generated shell falls back to static rankings and supports URL-state interactions", async () => {
  const { dom, window, errors } = await application();
  const document = window.document;
  assert.match(document.querySelector("[data-mode-badge]").textContent, /Static snapshot/);
  assert.equal(document.querySelectorAll("[data-ranking-rows] tr[data-instrument-id]").length, 25);

  document.querySelector("#score-filter").value = "75";
  document.querySelector("[data-filter-form]").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await wait(40);
  assert.equal(new URL(window.location.href).searchParams.get("minScore"), "75");
  assert.ok(document.querySelectorAll("[data-ranking-rows] tr[data-instrument-id]").length < 25);
  assert.match(document.querySelector("[data-filter-chips]").textContent, /Score ≥ 75/);

  document.querySelector('[data-sort="confidence"]').click();
  await wait(40);
  assert.equal(new URL(window.location.href).searchParams.get("sort"), "confidence");
  assert.equal(document.querySelector('[data-sort="confidence"]').closest("th").getAttribute("aria-sort"), "descending");

  const density = document.querySelector("[data-density]");
  density.value = "compact";
  density.dispatchEvent(new window.Event("change", { bubbles: true }));
  assert.equal(document.querySelector("[data-rankings-table]").dataset.density, "compact");
  assert.deepEqual(errors, []);
  dom.window.close();
});

test("search, theme and mobile navigation remain keyboard-operable", async () => {
  const { dom, window, errors } = await application();
  const document = window.document;
  document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }));
  const search = document.querySelector("#instrument-search");
  assert.equal(search.hasAttribute("open"), true);
  assert.equal(document.activeElement, document.querySelector("[data-search-input]"));

  const input = document.querySelector("[data-search-input]");
  input.value = "BLS";
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
  await wait(240);
  assert.ok(document.querySelectorAll("#search-results [role=option]").length >= 1);
  assert.match(document.querySelector("[data-search-status]").textContent, /match/i);
  document.querySelector("[data-close-search]").click();
  assert.equal(search.hasAttribute("open"), false);

  document.querySelector("[data-theme-toggle]").click();
  assert.equal(document.documentElement.dataset.theme, "light");
  assert.equal(window.localStorage.getItem("mbe-theme"), "light");

  const menuButton = document.querySelector("[data-open-menu]");
  menuButton.click();
  const menu = document.querySelector("#mobile-navigation");
  assert.equal(menu.hasAttribute("open"), true);
  assert.equal(menuButton.getAttribute("aria-expanded"), "true");
  menu.dispatchEvent(new window.Event("cancel", { cancelable: true }));
  assert.equal(menu.hasAttribute("open"), false);
  assert.equal(menuButton.getAttribute("aria-expanded"), "false");
  assert.deepEqual(errors, []);
  dom.window.close();
});

test("search results render a compact match-evidence line", async () => {
  const { dom, window, errors } = await application();
  const document = window.document;
  document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }));
  const input = document.querySelector("[data-search-input]");
  input.value = "BLS";
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
  await wait(240);
  const evidenceLines = document.querySelectorAll("[data-search-results] .search-evidence");
  assert.ok(evidenceLines.length >= 1);
  assert.match(evidenceLines[0].textContent, /symbol|name|match/i);
  assert.deepEqual(errors, []);
  dom.window.close();
});

test("published legacy route exposes an accessible canonical financial summary", () => {
  const html = fs.readFileSync(path.join(root, "site/reports/KFINTECH_NS.html"), "utf8");
  const dom = new JSDOM(html);
  const document = dom.window.document;
  const section = document.querySelector("[aria-labelledby='canonical-financials']");
  assert.ok(section);
  assert.match(section.textContent, /Yahoo compatibility|compatibility fallback/i);
  assert.match(section.textContent, /Fallback source.+not an official filing/is);
  assert.match(section.textContent, /Revenue CAGR \(3y\)/);
  assert.ok(section.querySelectorAll("table thead th[scope='col']").length >= 3);
  assert.ok(section.querySelector("a[href*='methodology.html#financial-methodology']"));
  assert.ok(section.querySelector("details.source-lineage > summary"));
  assert.equal(section.querySelector("details.source-lineage").hasAttribute("open"), false);
  dom.window.close();
});
