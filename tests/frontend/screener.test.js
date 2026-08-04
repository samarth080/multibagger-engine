"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const screener = require("../../src/mbe/frontend/assets/screener.js");
const parity = require("../fixtures/screener-parity.json");

const metadata = {
  limits: { max_conditions: 12, max_columns: 16, max_sorts: 3, max_categorical_values: 20, max_text_length: 80, max_export_rows: 250 },
  fields: [
    { field_id: "company", label: "Company", data_type: "text", operators: ["contains", "eq"], filterable: true, sortable: true, exportable: true },
    { field_id: "nse_symbol", label: "NSE symbol", data_type: "text", operators: ["eq"], filterable: true, sortable: true, exportable: true },
    { field_id: "sector", label: "Sector", data_type: "categorical", operators: ["any_of", "none_of", "is_missing"], filterable: true, sortable: true, exportable: true },
    { field_id: "rank", label: "Rank", data_type: "number", operators: ["gte", "between"], filterable: true, sortable: true, exportable: true },
    { field_id: "score", label: "Score", data_type: "number", operators: ["gte", "lte", "between", "is_missing"], filterable: true, sortable: true, exportable: true },
    { field_id: "missing", label: "Missing", data_type: "boolean", operators: ["is_true", "is_false"], filterable: true, sortable: true, exportable: true },
  ],
};
const rows = [
  { instrument_id: "b", values: { company: "Beta", nse_symbol: "BETA", sector: "Industrials", rank: 2, score: 80, missing: false } },
  { instrument_id: "a", values: { company: "Alpha", nse_symbol: "ALPHA", sector: "Consumer", rank: 1, score: 80, missing: true } },
  { instrument_id: "c", values: { company: "Gamma", nse_symbol: "GAMMA", sector: null, rank: 3, score: null, missing: true } },
];

test("share state round-trips a versioned bounded query", () => {
  const original = screener.defaultState();
  original.query.conditions = [{ condition_id: "score", field_id: "score", operator: "gte", value: 70, value_to: null, values: null }];
  original.density = "compact";
  const encoded = screener.encodeShareState(original);
  const decoded = screener.decodeShareState(`?screen=${encoded}`);
  assert.deepEqual(decoded.state, { query: original.query, density: "compact", preset: null });
  assert.deepEqual(decoded.warnings, []);
});

test("invalid URL fields are removed with a visible-warning payload", () => {
  const state = screener.defaultState();
  state.query.conditions = [{ condition_id: "bad", field_id: "sql", operator: "eq", value: "drop", value_to: null, values: null }];
  state.query.columns.push("secret");
  const sanitized = screener.sanitizeState(state, metadata);
  assert.equal(sanitized.state.query.conditions.length, 0);
  assert.equal(sanitized.state.query.columns.includes("secret"), false);
  assert.ok(sanitized.warnings.length >= 1);
});

test("static AND filters, null semantics and deterministic multi-sort match the contract", () => {
  const query = {
    ...screener.defaultState().query,
    conditions: [
      { condition_id: "sector", field_id: "sector", operator: "none_of", value: null, value_to: null, values: ["Consumer"] },
      { condition_id: "score", field_id: "score", operator: "gte", value: 70, value_to: null, values: null },
      { condition_id: "missing", field_id: "missing", operator: "is_false", value: null, value_to: null, values: null },
    ],
    sorts: [{ field_id: "score", direction: "desc" }, { field_id: "company", direction: "asc" }],
    columns: ["company", "nse_symbol", "score"],
  };
  const result = screener.staticQuery(rows, query);
  assert.deepEqual(result.rows.map(row => row.instrument_id), ["b"]);
  assert.equal(result.rows[0].matched_conditions.length, 3);
  assert.equal(screener.passes(null, { operator: "none_of", values: ["Consumer"] }), false);
});

test("inclusive ranges and null-only conditions remain explicit", () => {
  assert.equal(screener.passes(80, { operator: "between", value: 80, value_to: 90 }), true);
  assert.equal(screener.passes(null, { operator: "is_missing" }), true);
  assert.equal(screener.passes(null, { operator: "lte", value: 100 }), false);
});

test("CSV export carries lineage and neutralizes spreadsheet formulas", () => {
  const malicious = [{ instrument_id: "=cmd", values: { company: "+SUM(A1)", nse_symbol: "SAFE" } }];
  const csv = screener.csvFor(malicious, ["company", "nse_symbol"], metadata.fields, { build_id: "build-1", data_cutoff: "2026-08-01", generated_at: "2026-08-02" });
  assert.match(csv, /model_build_id/);
  assert.match(csv, /build-1/);
  assert.match(csv, /'=cmd/);
  assert.match(csv, /'\+SUM/);
});

test("field-registry and dataset versions must be compatible", () => {
  assert.equal(screener.compatible({ field_registry_version: "1", build: { build_id: "b" } }, { field_registry_version: "1", build_id: "b" }), true);
  assert.equal(screener.compatible({ field_registry_version: "1", build: { build_id: "b" } }, { field_registry_version: "2", build_id: "b" }), false);
  assert.equal(screener.compatible({ field_registry_version: "1", build: { build_id: "b" } }, { field_registry_version: "1", build_id: "c" }), false);
});

test("browser static evaluator matches the shared Python parity fixture", () => {
  const result = screener.staticQuery(parity.rows, parity.query);
  assert.deepEqual(result.rows.map(row => row.instrument_id), parity.expected_instrument_ids);
});

test("reportDestination resolves to the canonical company route for a row with instrument_id", () => {
  const row = { instrument_id: "abc-123", values: { nse_symbol: "RELIANCE" } };
  assert.equal(screener.reportDestination(row), "/company/abc-123.html");
});

test("reportDestination with no instrument_id and no report_url never returns an /api/analyze URL", () => {
  const row = { values: { nse_symbol: "RELIANCE" } };
  assert.doesNotMatch(screener.reportDestination(row), /\/api\/analyze/);
});
