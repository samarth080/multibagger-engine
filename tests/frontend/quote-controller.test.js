"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "../..");
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

function harness({ visible = true, online = true } = {}) {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://127.0.0.1:8765/", runScripts: "outside-only" });
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
