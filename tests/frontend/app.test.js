"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const app = require("../../src/mbe/frontend/assets/app.js");
const searchRankingParity = require("../fixtures/search-ranking-parity.json");

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

const searchIndex = [
  {
    instrument_id: "id-modeled", display_name: "Modeled Motors Limited", symbol: "MODELED",
    exchange: "NSE", isin: "INE000C01019", listing_status: "active", aliases: [],
    result_type: "modeled", research_available: true, rank: 4, multibagger_score: 71.2,
    confidence: 0.8, risk_score: 20, report_url: "/company/id-modeled.html",
  },
  {
    instrument_id: "id-unmodeled", display_name: "Unmodeled Industries Limited", symbol: "UNMODELED",
    exchange: "NSE", isin: "INE000D01010", listing_status: "active", aliases: [],
    result_type: "known", research_available: false, rank: null, multibagger_score: null,
    confidence: null, risk_score: null, report_url: "/company/id-unmodeled.html",
  },
];

const crossListedIndex = [
  {
    instrument_id: "id-reliance", display_name: "Reliance Industries Limited", symbol: "RELIANCE",
    exchange: "NSE", primary_exchange: "NSE", isin: "INE002A01018", bse_code: "500325",
    listing_status: "active", aliases: [],
    listings: [
      { exchange: "NSE", symbol: "RELIANCE", bse_code: null, isin: "INE002A01018", listing_status: "active", is_primary: true },
      { exchange: "BSE", symbol: "RELIANCE", bse_code: "500325", isin: "INE002A01018", listing_status: "active", is_primary: false },
    ],
  },
  {
    instrument_id: "id-bseonly", display_name: "BSE Only Company Ltd.", symbol: "BSEONLY",
    exchange: "BSE", primary_exchange: "BSE", isin: "INE999X01011", bse_code: "500999",
    listing_status: "active", aliases: [],
    listings: [{ exchange: "BSE", symbol: "BSEONLY", bse_code: "500999", isin: "INE999X01011", listing_status: "active", is_primary: true }],
  },
];

test("static search matches an exact BSE code across a company's listings", () => {
  const results = app.staticSearch(crossListedIndex, "500325");
  assert.equal(results[0].instrument_id, "id-reliance");
  assert.equal(results[0].matched_by, "exact BSE code");
});

test("parseExchangeHint supports NSE:/BSE: prefix and trailing suffix syntax", () => {
  assert.deepEqual(app.parseExchangeHint("NSE:TCS"), { query: "TCS", exchange: "NSE" });
  assert.deepEqual(app.parseExchangeHint("BSE:500325"), { query: "500325", exchange: "BSE" });
  assert.deepEqual(app.parseExchangeHint("Reliance BSE"), { query: "Reliance", exchange: "BSE" });
  assert.deepEqual(app.parseExchangeHint("TCS"), { query: "TCS", exchange: null });
  assert.deepEqual(app.parseExchangeHint("javascript:alert(1)"), { query: "javascript:alert(1)", exchange: null });
});

test("static search exchange filter excludes companies without a listing on that exchange", () => {
  const bseResults = app.staticSearch(crossListedIndex, "RELIANCE", 10, "BSE");
  assert.equal(bseResults.length, 1);
  assert.equal(bseResults[0].instrument_id, "id-reliance");

  const nseResults = app.staticSearch(crossListedIndex, "BSE Only Company", 10, "NSE");
  assert.deepEqual(nseResults, []);
});

test("static search carries research/ranking status through so the UI can badge results honestly", () => {
  const modeled = app.staticSearch(searchIndex, "Modeled Motors")[0];
  assert.equal(modeled.result_type, "modeled");
  assert.equal(modeled.research_available, true);
  assert.equal(modeled.rank, 4);
  assert.equal(modeled.multibagger_score, 71.2);
  assert.equal(modeled.report_url, "/company/id-modeled.html");

  const unmodeled = app.staticSearch(searchIndex, "Unmodeled Industries")[0];
  assert.equal(unmodeled.result_type, "known");
  assert.equal(unmodeled.research_available, false);
  assert.equal(unmodeled.rank, null);
  assert.equal(unmodeled.multibagger_score, null);
  assert.equal(unmodeled.report_url, "/company/id-unmodeled.html");
});

test("staticSearch finds a full-phrase match not covered by prefix or word match", () => {
  const universe = [
    { instrument_id: "id-tcs", display_name: "Tata Consultancy Services Limited", symbol: "TCS", listing_status: "active" },
    { instrument_id: "id-reliance", display_name: "Reliance Industries Limited", symbol: "RELIANCE", listing_status: "active" },
  ];
  const results = app.staticSearch(universe, "Consultancy Services");
  assert.equal(results[0].instrument_id, "id-tcs");
  assert.equal(results[0].matched_by, "full phrase match");
});

test("staticSearch finds an all-token match regardless of order", () => {
  const universe = [
    { instrument_id: "id-hal", display_name: "Hindustan Aeronautics Limited", symbol: "HAL", listing_status: "active" },
  ];
  const results = app.staticSearch(universe, "Aeronautics Hindustan");
  assert.equal(results[0].instrument_id, "id-hal");
  assert.equal(results[0].matched_by, "word match");
});

test("staticSearch prefers active listing over inactive at equal score", () => {
  const universe = [
    { instrument_id: "id-inactive", display_name: "Similar Prefix Company Two Ltd.", symbol: "INAC", listing_status: "delisted" },
    { instrument_id: "id-active", display_name: "Similar Prefix Company One Ltd.", symbol: "ACTV", listing_status: "active" },
  ];
  const results = app.staticSearch(universe, "Similar Prefix Company");
  assert.equal(results[0].instrument_id, "id-active");
});

test("staticSearch prefers verified broad-index membership at equal score", () => {
  const universe = [
    { instrument_id: "id-plain", display_name: "Tie Break Nu Ltd.", symbol: "TBN", listing_status: "active" },
    { instrument_id: "id-member", display_name: "Tie Break Xi Ltd.", symbol: "TBX", listing_status: "active", index_memberships: ["Nifty 50"] },
  ];
  const results = app.staticSearch(universe, "Tie Break");
  assert.equal(results[0].instrument_id, "id-member");
});

test("staticSearch exposes v3 evidence fields on every result", () => {
  const universe = [{ instrument_id: "id-evid", display_name: "Evidence Fields Ltd.", symbol: "EVID", listing_status: "active", research_available: true, rank: 1 }];
  const results = app.staticSearch(universe, "EVID");
  assert.equal(results[0].ranking_policy_version, "2026-08-02.10c.2");
  assert.equal(results[0].match_reason, "Exact company symbol");
  assert.equal(results[0].active_listing, true);
  assert.equal(results[0].ranking_available, true);
});

test("browser static search matches the shared Python ranking parity fixture", () => {
  for (const testCase of searchRankingParity.cases) {
    const results = app.staticSearch(searchRankingParity.universe, testCase.query, 10, testCase.exchange);
    const actualOrder = results
      .map(r => r.instrument_id)
      .filter(id => testCase.expected_order.includes(id));
    assert.deepEqual(actualOrder, testCase.expected_order, testCase.query);
  }
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
