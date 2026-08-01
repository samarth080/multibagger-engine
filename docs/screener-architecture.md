# Advanced screener architecture

> Phase 8 verifies real-Chrome preset/edit/share/reload/export behavior,
> responsive layouts down to 320 CSS pixels, effective 200% browser zoom,
> light/dark axe scans and static performance budgets. The heavier static
> screener payload remains a measured preview condition; its query semantics and
> public values are unchanged.

Implemented: 2026-08-01; Phase 5 source-quality metadata appended

## Decision

The screener is a typed domain layered over the canonical model-build schema,
not a SQL console and not a second ranking-filter language. Python owns a
versioned field registry. The registry generates API metadata and the static
field manifest consumed by the browser, so validation, controls, formatting,
columns and CSV labels share one source of truth.

Queries are versioned, top-level `AND` expressions. A categorical `any_of`
condition uses OR within its selected values; `none_of` excludes selected
values. Ranges are inclusive. Nested groups and OR can be added in a future
schema version without changing Phase 3 semantics.

Dynamic mode compiles only allowlisted fields and operators into parameterized
SQLAlchemy expressions, filters/sorts/counts in SQL, and appends canonical
`instrument_id` as the final stable tie-breaker. Static mode evaluates the same
semantics over the bounded weekly 250-row snapshot. The browser refuses to
combine different field-registry or model-build IDs.

## Data-readiness inventory

| Location | Available now | Phase 3 decision |
|---|---|---|
| PostgreSQL/SQLite canonical schema | Company/listing identity, sector/industry, build metadata, rank, Multibagger/Investment/Confidence/Risk, signal/flag counts, coverage/missing state, technical trend, explanations and normalized component scores | Public where listed in the registry |
| DuckDB research ledger | Per-run ticker/build links, scores, trend, price, market cap, pillar JSON and a small metrics JSON containing 3-year ROCE/revenue/profit growth, margin of safety, implied growth and PEG | Compatibility/history only; not a public dynamic filter source |
| Analysis build objects | Full `FundamentalMetrics`, `TechnicalState`, valuation, business profile, risk and evidence objects | Internal build-time values unless normalized and persisted |
| Static JSON | Full 250-row Phase 3 screener dataset, 28-field manifest, build/cutoff/freshness/universe metadata; rankings remain the top 25 | Public, bounded weekly compatibility mode |
| Derived rather than stored | Previous rank/score and changes (adjacent builds), canonical company destination, matched-condition explanations | Public when a comparable prior build exists; null otherwise |
| Transient quote layer | Last price/change/status/timestamp for visible rows | Not a screener membership/filter/sort field in Phase 3 |
| Missing or insufficient | Complete BSE codes, SME/listing history, market-cap category, normalized statements/periods/units/restatements/consolidation lineage | Not exposed |

The latest local DuckDB run used for the assessment contained 250 companies.
It had market cap for 249 (99.6%), build price for 250 (100%), 3-year ROCE for
232 (92.8%), revenue CAGR for 246 (98.4%), profit CAGR for 206 (82.4%), margin
of safety and implied growth for 242 (96.8%), and PEG for 159 (63.6%). Coverage
alone is not readiness: those values remain JSON/ticker keyed, use Yahoo
statement semantics, and lack normalized period, units, consolidated versus
standalone, filing/restatement and source-lineage records.

## Public field registry

Phase 5 increments the registry to `2026-08-01.3`. Phase 4 added two
Ready-with-caveat financial fields. Existing IDs, schema `1.0`, URL state and
presets remain backward compatible.

Every comparison excludes null unless the user explicitly chooses
`is_missing` or `is_available`. Negative conditions (`ne`, `none_of`) also
exclude null rather than treating missing as an ordinary unequal value.

| Field ID | Meaning / unit | Source and period | Operators | Missing/freshness/caveat |
|---|---|---|---|---|
| `company` | Canonical display name | Current instrument master | contains, starts with, equal, not equal, available, missing | Master freshness; names can change |
| `nse_symbol` | Current primary NSE symbol | Current primary listing | text operators | Symbol is a label, never identity |
| `exchange` | Primary exchange | Current primary listing | categorical operators | NSE/BSE allowlist; current universe is NSE |
| `sector` | Broad provider-normalized sector | Current master | categorical operators | Taxonomy can change; null excluded |
| `industry` | Provider-normalized industry | Current master | categorical operators | Taxonomy can change; null excluded |
| `rank` | Current build position / rank | Selected weekly build | numeric operators | Always present for scored rows |
| `previous_rank` | Immediately prior available build rank | Adjacent score build | numeric operators | Null without a comparable prior row |
| `rank_change` | Previous minus current / positions | Adjacent score builds | numeric operators | Positive means improvement; null without history |
| `multibagger_score` | Explainable 0–100 score | Selected weekly build | numeric operators | Research score, not return forecast |
| `previous_multibagger_score` | Prior build 0–100 score | Adjacent score build | numeric operators | Null without history |
| `score_change` | Current minus previous / score points | Adjacent score builds | numeric operators | Null without history |
| `investment_score` | Weighted 0–100 investment score | Selected weekly build | numeric operators | Model output |
| `confidence` | Input coverage ratio, displayed as percent | Selected weekly build | numeric operators | Not a performance probability |
| `risk_score` | Rule-based 0–100 flag score | Selected weekly build | numeric operators | Higher means more/severer model flags |
| `positive_signal_count` | Evidence items scoring at least 70 / count | Selected weekly build | numeric operators | Count, not independent events |
| `red_flag_count` | Risk flags plus hard gates / count | Selected weekly build | numeric operators | Count does not encode identical severity |
| `coverage_quality` | Analysis coverage ratio | Selected weekly build | numeric operators | Currently aligned with confidence |
| `has_missing_data` | Missing inputs reduced confidence / boolean | Selected weekly build | true, false, available, missing | Explicit boolean |
| `technical_trend` | strong up/up/sideways/down/strong down/unknown | Daily history as of build cutoff | categorical operators | Build-time state, not live quote state |
| `quality_score` | Quality component / 0–100 | Normalized score component, selected build | numeric operators | Null only for legacy/incomplete builds |
| `growth_score` | Growth component / 0–100 | Normalized score component, selected build | numeric operators | Same |
| `financial_strength_score` | Financial Strength component / 0–100 | Normalized score component, selected build | numeric operators | Same |
| `valuation_score` | Valuation component / 0–100 | Normalized score component, selected build | numeric operators | Same |
| `momentum_score` | Company Momentum component / 0–100 | Normalized score component, selected build | numeric operators | Company model component, not sector context |
| `size_runway_score` | Size Runway component / 0–100 | Normalized score component, selected build | numeric operators | Same |
| `reinvestment_score` | Reinvestment component / 0–100 | Normalized score component, selected build | numeric operators | Same |
| `main_positive_signal` | Highest-weight positive rationale | Selected score snapshot | display/export only | Not filterable/sortable |
| `main_risk` | First rule/hard-gate risk context | Selected score snapshot | display/export only | Not filterable/sortable |
| `revenue_cagr_3y` | Annual revenue compound growth / ratio | Latest compatible normalized 3-year annual span | numeric operators | 246/250; Yahoo compatibility basis/filing date unknown |
| `roce_3y` | Average annual EBIT/(equity+debt) / ratio | Latest up to 3 compatible annual periods, minimum 2 | numeric operators | 232/250; basis unknown; lender comparability caveat |

The persisted `Sector Momentum` component is intentionally not public as a
screening field because its registered ablation failed; it remains descriptive
context on the ranking page.

Both financial field definitions now also publish their preferred official NSE
source, approved Yahoo fallback, Tier A/B/C policy and reconciliation
availability. These are metadata, not new filter fields. Current static rows
remain Tier B/compatibility-only because canonical official multi-year coverage
is 0/250; dynamic selection can promote an individual value only after the
official period/unit/basis/quality gates pass. Static and dynamic value/filter
semantics are unchanged.

## Financial-field readiness

| Candidate | Source / measured coverage | Period and units | Consolidation, date and restatement | Outlier/readiness decision |
|---|---|---|---|---|
| Market capitalisation | Yahoo company info; 249/250 latest local run | Point-in-time INR-like provider value | No canonical timestamp/lineage; not relationally persisted | Plausible range ₹59.5bn–₹1.08tn, but `Requires normalization` |
| Last/build price | Yahoo daily history; 250/250 | Listing currency at build cutoff | Build price only; quotes retrieved separately | Plausible ₹18.42–₹18,950; `Internal only` for screening |
| Revenue CAGR 3y | Yahoo statements; 246/250 | Ratio over available annual periods | Consolidated/standalone and restatements not normalized | Range -90.1%–232.4%; needs period/outlier policy; `Requires normalization` |
| Profit CAGR 3y | Yahoo statements; 206/250 | Ratio over available annual periods | Same lineage gap; sign changes complicate CAGR | Range -37.2%–422.6%; `Requires normalization` |
| ROCE 3y | Derived Yahoo statements; 232/250 | Ratio/three-year aggregate | Statement basis and restatements not normalized | Range -55.0%–54.7%; `Requires normalization` |
| Margin of safety | Internal valuation; 242/250 | Ratio at build cutoff | Depends on model assumptions and unnormalized inputs | Range -100%–453%; `Internal only` |
| Implied growth | Reverse DCF; 242/250 | Annual ratio | Model-derived, not reported financial fact | Range -19.0%–60%; `Internal only` |
| PEG | Yahoo/derived valuation; 159/250 | Multiple | Period/earnings basis inconsistent | Range 0.05–80.75 and 36.4% missing; `Requires normalization` |
| ROE, debt/equity, interest coverage, margins, P/E, P/B | Available in some analysis objects/providers | Mixed latest/annual ratios | Not normalized/persisted with lineage | `Unavailable` for the public registry |

Phase 4's warehouse and build projection qualify only Revenue CAGR and ROCE as
Ready-with-caveat. The remaining candidates stay deferred; see
[`financial-architecture.md`](financial-architecture.md).

## Public API

- `GET /api/v1/screener/fields` returns registry/schema versions, categories,
  operators, allowed current categorical values, presets, limits and build
  metadata. `/metadata` is a compatibility alias.
- `POST /api/v1/screener/query` accepts `ScreenerQuery`. `count_only: true`
  reuses the same planner. The response includes rows, stable pagination,
  applied filters, effective sorting, columns, warnings, dataset/build metadata,
  freshness, mode, request ID and a value-independent operational fingerprint.

Stable public error codes include `unknown_field`, `unsupported_operator`,
`invalid_value_type`, `invalid_range`, `too_many_conditions`,
`too_many_columns`, `too_many_sorts`, `page_size_exceeded`,
`query_too_complex`, `incompatible_schema_version`, `unknown_model_build`,
`dataset_unavailable` and `request_too_large`. SQL, provider exceptions,
database URLs and stack traces are never returned.

## Query and export limits

- 12 active conditions.
- 16 requested columns.
- 3 stable sort fields.
- 100 rows per page.
- 250 CSV rows.
- 20 values per categorical condition.
- 80 characters per text value.
- Complexity score 80.
- Raw POST body 64 KiB when Content-Length is present.

Representative SQLite query-plan inspection used
`ix_scores_build_multibagger` for build/score selection, the score snapshot
build/instrument uniqueness index for previous-build joins, and the existing
score component `(score_id, component_name)` uniqueness index for correlated
component lookup. A component screen executed four SELECTs total (current
build, previous build, count and result page), independent of result count; no
N+1 query was observed. At the current 250-row universe no additional index or
migration was justified.

Static mode ships about 250 normalized rows and is capped at the weekly Nifty
Smallcap 250. Move to mandatory dynamic/server pagination before publishing
several thousand scored securities or when the compressed screener artifact
exceeds the documented frontend payload budget.

## Public route and share state

All company and row actions resolve to `/company/{instrument_id}.html`. Ticker
report URLs remain compatibility pages but are no longer the primary identity
or destination.

`/screener.html` uses the Phase 2 shell. It provides a searchable grouped field
picker, type-specific operators/values, keyboard-native categorical
multi-select, editable/removable conditions, transparent presets, stable sort,
pagination, registry-driven columns/formatting, density, matched-condition
details, static/API states and CSV export.

The URL stores one bounded `screen` parameter: base64url-encoded UTF-8 JSON
with representation version `v: 1`, the screener schema/query, density and
active preset. Unknown fields/operators are removed with a visible warning;
malformed, oversized or incompatible state resets safely. Back/forward events
re-run the normalized screen. No server-side saved-screen ID or account is
created.

Presets are ordinary visible conditions:

- High Score, Moderate Risk: score ≥ 70 and risk ≤ 45.
- High Confidence Candidates: confidence ≥ 90%.
- Positive Technical Trend: up or strong up.
- Improving Rank: rank change ≥ 1.
- Lower-Risk Research Candidates: risk ≤ 25.

CSV exports visible columns plus canonical instrument ID, model build ID, data
cutoff and generated timestamp. Spreadsheet cells beginning with `=`, `+`, `-`
or `@` (after whitespace) are prefixed to prevent formula execution. Static
mode exports up to 250 matching rows locally; dynamic mode reuses paginated
query calls in 100-row batches and applies the same 250-row limit.

## Accessibility, security and remaining QA

Controls are native labelled form elements; condition errors use live alerts;
count/mode/copy/removal changes are announced; result headers expose
`aria-sort`; row focus moves with Up/Down; the mobile filter region is a native
collapsible `details`; focus, reduced-motion and colour-independent states
reuse Phase 2 tokens. Deterministic jsdom journeys cover presets, editing,
sorting, matched-condition details, share state, fallback and keyboard flow.

The filter/query path renders no raw HTML, performs no evaluation, accepts no
SQL/regex/arbitrary expressions, and never puts provider payloads or secrets in
snapshots. CSP remains unchanged and contains no `unsafe-eval`. Distributed
anonymous rate limiting remains a pre-deployment platform responsibility.

Real-engine desktop/tablet/mobile, light/dark, zoom, contrast and screen-reader
review remains required before deployment if the in-app browser is unavailable.
