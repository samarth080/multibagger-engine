"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const app = require("../../src/mbe/frontend/assets/app.js");

const instruments = [
  {
    instrument_id: "id-good", display_name: "Good Engineering Limited",
    legal_name: "Good Engineering Limited", symbol: "GOOD", exchange: "NSE",
    isin: "INE000A01018", bse_code: "500001", industry: "Engineering",
    listing_status: "active", aliases: [{ type: "former name", value: "Great Works" }],
    report_url: "/reports/GOOD_NS.html"
  },
  {
    instrument_id: "id-food", display_name: "Good Foods Limited",
    symbol: "GFOOD", exchange: "NSE", isin: "INE000B01017",
    industry: "Foods", listing_status: "active", aliases: [{ type: "abbreviation", value: "GEL" }]
  }
];

test("canonical static search preserves exact-match precedence and reasons", () => {
  assert.equal(app.staticSearch(instruments, "GOOD")[0].matched_by, "exact NSE symbol");
  assert.equal(app.staticSearch(instruments, "500001")[0].matched_by, "exact BSE code");
  assert.equal(app.staticSearch(instruments, "INE000A01018")[0].matched_by, "exact ISIN");
  assert.equal(app.staticSearch(instruments, "Good Engineering Ltd")[0].matched_by, "exact company name");
  assert.equal(app.staticSearch(instruments, "Great Works")[0].matched_by, "exact former name");
  assert.equal(app.staticSearch(instruments, "Good Eng")[0].matched_by, "company-name prefix");
});

test("short aliases remain below clear exact identities", () => {
  const result = app.staticSearch(instruments, "GEL");
  assert.equal(result[0].score, 78);
  assert.equal(result[0].matched_by, "exact abbreviation");
});

test("safe fuzzy matching is gated by length and quality", () => {
  assert.equal(app.staticSearch(instruments, "Good Engneering Limited")[0].instrument_id, "id-good");
  assert.deepEqual(app.staticSearch(instruments, "x"), []);
});

test("ranking URL state validates values and round-trips shareable filters", () => {
  const state = app.parseRankingState("?q=good&minScore=70&minConfidence=90&maxRisk=25&rankMin=2&rankMax=9&sort=confidence&dir=desc&page=2&pageSize=10");
  assert.equal(state.minScore, 70);
  assert.equal(state.minConfidence, 90);
  assert.equal(state.sort, "confidence");
  assert.equal(state.pageSize, 10);
  const roundTrip = app.parseRankingState(`?${app.stateToSearch(state)}`);
  assert.deepEqual(roundTrip, state);
  assert.equal(app.parseRankingState("?minScore=999&page=-2&pageSize=17&sort=unsafe").minScore, 100);
});

const rows = [
  app.rankingRow({ instrument_id: "1", rank: 1, symbol: "GOOD", exchange: "NSE", name: "Good Engineering", sector: "Industrials", industry: "Engineering", multibagger_score: 80, investment_score: 70, confidence: .95, risk_score: 10, technical_trend: "up" }),
  app.rankingRow({ instrument_id: "2", rank: 2, symbol: "FOOD", exchange: "NSE", name: "Food Co", sector: "Consumer", industry: "Foods", multibagger_score: 72, investment_score: 74, confidence: .8, risk_score: 30, technical_trend: "sideways" }),
  app.rankingRow({ instrument_id: "3", rank: 3, symbol: "ALSO", exchange: "NSE", name: "Also Engineering", sector: "Industrials", industry: "Engineering", multibagger_score: 72, investment_score: 60, confidence: .9, risk_score: 20, technical_trend: "up" })
];

test("static ranking filters compose and sorting is stable", () => {
  const state = app.parseRankingState("?sector=Industrials&minScore=70&minConfidence=90&maxRisk=20&trend=up&sort=score&dir=desc");
  const filtered = app.stableFilterSort(rows, state);
  assert.deepEqual(filtered.map(row => row.instrument_id), ["1", "3"]);
  const tied = app.stableFilterSort(rows, app.parseRankingState("?sort=score&dir=asc"));
  assert.deepEqual(tied.slice(0, 2).map(row => row.instrument_id), ["2", "3"]);
});

test("normalization rejects corrupt snapshots and preserves canonical IDs", () => {
  assert.throws(() => app.normalizeRankingEnvelope({}, "static"), /corrupt_snapshot/);
  const normalized = app.normalizeRankingEnvelope({ data: [rows[0]], meta: { total: 1, build: { build_id: "build-a" } } }, "static");
  assert.equal(normalized.rows[0].instrument_id, "1");
  assert.equal(normalized.meta.build.build_id, "build-a");
  assert.equal(app.buildCompatible({ data: { latest_model_build: { build_id: "a" } } }, { meta: { build: { build_id: "b" } } }), false);
});

test("API query keeps server pagination and validated filters", () => {
  const query = new URLSearchParams(app.apiQuery(app.parseRankingState("?q=good&sector=Industrials&minScore=70&minConfidence=90&rankMin=1&rankMax=20&trend=up&sort=risk&dir=desc&page=2&pageSize=10")));
  assert.equal(query.get("page"), "2");
  assert.equal(query.get("page_size"), "10");
  assert.equal(query.get("min_confidence"), "0.9");
  assert.equal(query.get("technical_trend"), "up");
  assert.equal(query.get("sort"), "-risk");
});

test("CSV export escapes fields and report routing preserves useful destinations", () => {
  const csv = app.csvFor([{ ...rows[0], name: 'Good "Engineering"' }]);
  assert.match(csv, /"Good ""Engineering"""/);
  assert.equal(app.reportDestination(instruments[0]), "/reports/GOOD_NS.html");
  assert.equal(app.reportDestination(instruments[1]), "/company/id-food.html");
});

test("summary uses supported aggregate values only", () => {
  const summary = app.summaryFor(rows);
  assert.equal(summary.total, 3);
  assert.equal(summary.medianScore, 72);
  assert.equal(summary.topSector, "Industrials");
  assert.equal(summary.topSectorCount, 2);
});
