"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { TextDecoder, TextEncoder } = require("node:util");
const { JSDOM, VirtualConsole } = require("jsdom");

const root = path.resolve(__dirname, "../..");
const wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const response = (data, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => data });

async function application() {
  const virtualConsole = new VirtualConsole(); const errors = [];
  virtualConsole.on("jsdomError", error => errors.push(error));
  const dom = new JSDOM(fs.readFileSync(path.join(root, "site/screener.html"), "utf8"), {
    runScripts: "outside-only", url: "http://127.0.0.1:8765/screener.html",
    pretendToBeVisual: true, virtualConsole,
  });
  const { window } = dom;
  window.TextEncoder = TextEncoder; window.TextDecoder = TextDecoder;
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  window.HTMLElement.prototype.scrollIntoView = function scrollIntoView() {};
  window.HTMLDialogElement.prototype.showModal = function showModal() { this.setAttribute("open", ""); };
  window.HTMLDialogElement.prototype.close = function close() { this.removeAttribute("open"); };
  window.navigator.clipboard = { writeText: async () => {} };
  window.fetch = async input => {
    const url = new URL(String(input), window.location.href);
    if (url.pathname.startsWith("/api/v1/screener/") && !url.pathname.endsWith(".json")) return response({}, 503);
    if (url.pathname.endsWith(".json")) return response(JSON.parse(fs.readFileSync(path.join(root, "site", url.pathname.slice(1)), "utf8")));
    return response({}, 404);
  };
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/app.js"), "utf8"));
  window.eval(fs.readFileSync(path.join(root, "src/mbe/frontend/assets/screener.js"), "utf8"));
  window.document.dispatchEvent(new window.Event("DOMContentLoaded", { bubbles: true }));
  await wait(120);
  return { dom, window, errors };
}

test("generated screener falls back to the full static build and completes the primary journey", async () => {
  const { dom, window, errors } = await application(); const document = window.document;
  assert.match(document.querySelector("[data-screener-mode]").textContent, /Static snapshot/);
  assert.match(document.querySelector("[data-screener-count]").textContent, /250 companies/);
  assert.equal(document.querySelectorAll("[data-screener-rows] tr[data-instrument-id]").length, 25);

  const field = document.querySelector("[data-field-select]"); field.value = "multibagger_score"; field.dispatchEvent(new window.Event("change", { bubbles: true }));
  const operator = document.querySelector("[data-operator-select]"); operator.value = "gte"; operator.dispatchEvent(new window.Event("change", { bubbles: true }));
  document.querySelector('[data-condition-value="value"]').value = "70";
  document.querySelector("[data-condition-form]").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await wait(40);
  assert.match(document.querySelector("[data-condition-list]").textContent, /Multibagger Score is at least 70/);
  assert.ok(Number(document.querySelector("[data-screener-count]").textContent.match(/\d+/)[0]) < 250);
  assert.ok(new URL(window.location.href).searchParams.get("screen"));

  const sort = document.querySelector("[data-screener-sort]"); sort.value = "confidence"; sort.dispatchEvent(new window.Event("change", { bubbles: true }));
  const direction = document.querySelector("[data-screener-direction]"); direction.value = "desc"; direction.dispatchEvent(new window.Event("change", { bubbles: true })); await wait(35);
  assert.equal(document.querySelector('th[data-field="confidence"]').getAttribute("aria-sort"), "descending");

  const details = document.querySelector("[data-screener-rows] tr[data-instrument-id] .row-action"); details.click();
  assert.match(document.querySelector("[data-match-for]").textContent, /Passed/);
  document.querySelector("[data-share-screen]").click(); await wait(5);
  assert.match(document.querySelector("[data-share-screen]").textContent, /copied/i);

  document.querySelector("[data-clear-conditions]").click(); await wait(35);
  assert.match(document.querySelector("[data-screener-count]").textContent, /250 companies/);
  assert.equal(document.querySelector("[data-filter-panel]").hasAttribute("open"), true);
  assert.deepEqual(errors, []);
  dom.window.close();
});

test("screener builder remains keyboard-native and mobile-collapsible", async () => {
  const { dom, window, errors } = await application(); const document = window.document;
  const summary = document.querySelector("[data-filter-panel] summary");
  summary.focus(); summary.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  assert.equal(summary.tabIndex >= 0, true);
  const preset = document.querySelector("[data-preset-list] button"); preset.focus(); preset.click(); await wait(35);
  assert.ok(document.querySelectorAll("[data-condition-list] .condition-item").length >= 1);
  const firstAction = document.querySelector("[data-screener-rows] tr[data-instrument-id] a, [data-screener-rows] tr[data-instrument-id] button"); firstAction.focus(); firstAction.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
  assert.notEqual(document.activeElement, firstAction);
  assert.deepEqual(errors, []);
  dom.window.close();
});
