# Normalized financial architecture (Phases 4–6)

Implemented: 2026-08-01

Phase 6 adds a local validation boundary around official facts: immutable pilot
and corpus manifests, a private dated review gate, versioned concept mapping,
fact-selection evidence, append-only adjudication and explicit Tier-A/
publication eligibility. These artifacts do not alter canonical facts or the
public projection. No database migration was justified for the single-operator
offline pilot. See
[`phase6-official-corpus-pilot.md`](phase6-official-corpus-pilot.md).

## Decision and public boundary

Financial lineage is an additive canonical warehouse beside the unchanged legacy
score pipeline. Filed facts are relational and decimal-safe; build-time metric
snapshots provide indexed screener reads. DuckDB and historical model builds are
not rewritten. Static production projects the same definitions directly from the
weekly `FinancialHistory`, so it remains operational without PostgreSQL.

The first public filters are deliberately limited to `revenue_cagr_3y` and
`roce_3y`. Current production rows are labelled `valid_with_warning`, source
`yahoo_compatibility`, statement basis `unknown`, and filing date unavailable.
They are useful, high-coverage research filters but not filed-fact reproductions.
Every public surface carries that caveat. No value is filled, clamped or inferred
to improve coverage.

## Pre-implementation lineage inventory

The weekly pipeline calls `YahooProvider.get_financials`; optional CLI research
can substitute `NseFundamentals` or EDGAR. Legacy `FinancialHistory` stores only
annual `{field: {fiscal_year: value}}` plus optional annual filing dates. It does
not retain source row, exact period start/end, unit, currency, basis, revision or
filing URL. That loss is why Phase 4 uses new filing/fact contracts rather than
declaring legacy JSON canonical.

| Internal field | Yahoo source rows | NSE source tags/derivation | Kind/unit | Current use | Public before P4 | Normalization/readiness |
|---|---|---|---|---|---|---|
| `revenue` | Total Revenue; Operating Revenue | RevenueFromOperations; Income; legacy operating-income labels | annual flow, provider base currency | growth, margins, valuation, forecasts, sector context | report | Normalize; public input with caveat |
| `gross_profit` | Gross Profit | unavailable | annual flow | gross margin | report ratio | Normalize when sourced; deferred public ratio |
| `operating_income` | Operating Income; EBIT | PBT + FinanceCosts | annual flow | ROCE/ROIC, margin, scoring | report ratios | Normalize; proxy lineage required |
| `ebitda` | EBITDA; Normalized EBITDA | EBIT proxy + depreciation | annual flow | margins, leverage, valuation | report ratios | Normalize; deferred due taxonomy/proxy variation |
| `net_income` | Net Income; common-stockholder fallback | ProfitLossForPeriod; legacy PAT | annual flow | growth, returns, cash quality | report ratios | Normalize; profit CAGR deferred across sign changes |
| `interest_expense` | Interest Expense fallbacks | FinanceCosts | annual flow, positive expense magnitude | interest coverage | report ratio | Normalize; filter deferred due lender comparability/outliers |
| `total_assets` | Total Assets | Assets | annual instant stock | accruals | report ratio | Normalize; point-in-time semantics required |
| `total_equity` | three equity fallbacks | Equity; parent-attributable equity | annual instant stock | ROE, ROCE, leverage | report ratios | Normalize; negative equity preserved |
| `total_debt` | Total Debt | current + non-current borrowings | annual instant stock | leverage, valuation, risk | report ratios | Normalize; debt/equity filter deferred |
| `cash` | cash/equivalents fallbacks | CashAndCashEquivalents | annual instant stock | ROIC, net debt, valuation | report ratios | Normalize; taxonomy differences flagged |
| `current_assets` | Current Assets | CurrentAssets | annual instant stock | current ratio | report ratio | Normalize; deferred public ratio |
| `current_liabilities` | Current Liabilities | CurrentLiabilities | annual instant stock | current ratio | report ratio | Normalize; deferred public ratio |
| `cfo` | Operating Cash Flow | CashFlowsFromUsedInOperatingActivities | annual flow | cash conversion, accruals, FCF | report ratios | Normalize; cash-flow filter deferred |
| `capex` | Capital Expenditure fallbacks | purchase of PPE | annual flow, stored positive magnitude | FCF, reinvestment | report ratios | Normalize; source sign convention retained |
| `fcf` | Free Cash Flow or CFO − capex | CFO − capex | derived annual flow | growth, margin, valuation | report ratios | Normalize with input lineage; deferred public filter |
| `shares_diluted` | diluted/basic/ordinary shares | paid-up capital / face value | shares | dilution, per-share models | report ratio | Normalize; fallback semantics differ |
| `dividends_paid` | Cash Dividends Paid | financing dividends paid | annual flow, positive magnitude | stewardship | report | Normalize; deferred public filter |

Yahoo coverage over the cached current 250 is 250 histories. Official cached NSE
history exists for 86/250. Yahoo values are generally base currency amounts but
provide no filing identifier/date or consolidation basis in the current adapter.
NSE XBRL has broadcast timestamps and prefers consolidated original annual
filings, but the legacy cache discarded basis and filing identity. Future imports
must use `FilingInput` rather than round-tripping through `FinancialHistory`.

## Canonical schema and migration

Migration `20260801_0003` adds:

- `financial_dataset_builds`: schema/definition versions, source cutoff, counts,
  coverage, quality, configuration hash, source versions and status.
- `financial_filings`: canonical company/instrument, source filing identity,
  period, filing/publication dates, audit/basis/revision/restatement, currency,
  original unit, safe source URL, retrieval/normalization and payload hash.
- `financial_facts`: decimal original/normalized values, conversion factor,
  period/basis/audit/source field/location and quality.
- `financial_metric_snapshots`: one indexed accepted value per dataset build,
  instrument and derived metric for screening.
- `financial_quality_issues`: non-destructive warnings/rejections.

Facts use `NUMERIC(38,8)` and derived ratios `NUMERIC(38,12)`. Uniqueness prevents
duplicate filing revisions, duplicate source facts and duplicate build metrics.
Indexes cover company/period filings, company/metric/period facts, instrument
history and build/metric/value screener queries. Core facts are not stored in one
JSON blob.

## Period, basis, unit and restatement policy

- Period types: annual, quarter-only, year-to-date, TTM and instant.
- Quarter residuals require compatible same-year YTD facts. Source facts remain;
  the residual is marked derived.
- TTM requires four sequential quarter-only facts with identical metric, basis
  and currency. Annual values never fill a missing quarter.
- Consolidated is preferred, standalone is an explicit fallback, unknown remains
  labelled unknown. Numerator and denominator never cross basis.
- Monetary storage is decimal base currency (INR base rupees for current India
  facts). Original value/unit and conversion factor remain reproducible.
- Supported inputs: rupees, thousands, lakhs, millions and crores; negative and
  zero values are preserved. Missing is never converted to zero.
- A new revision is a new filing. `restates_filing_id` links its predecessor,
  which becomes superseded. Imports reject orphan restatements and payload changes
  that reuse a revision identity.
- Latest-known reads select the newest accepted revision. As-of/model-build reads
  must constrain source cutoff; later restatements cannot rewrite older builds.

## Metric dictionary and public formulas

The single dictionary is `src/mbe/financials/metrics.py`, version
`2026-08-01.1`. It defines 18 source/derived statement metrics plus two public
derived metrics with statement category, flow/stock, unit, sign, compatible
periods, additivity, TTM support, formula, missing behavior and quality rule.

| Public metric | Formula | Acceptance and null semantics | Coverage/range |
|---|---|---|---|
| Revenue CAGR (3y) | `(revenue[t] / revenue[t-3])^(1/3) - 1` | Positive annual endpoints exactly three fiscal years apart; same source/currency/basis. Otherwise null. | 246/250, 98.4%; -90.1% to 232.4% |
| ROCE (3y average) | mean of `EBIT / (equity + debt)` for latest up to 3 annual periods | Minimum two same-period ratios; capital must be positive; same source/currency/basis. Otherwise null. | 232/250, 92.8%; -55.0% to 54.7% |

Both are `Ready-with-caveat`, bounded for query input but values are not winsorized.
All ordinary and negative screener comparisons exclude null. `is_missing` and
`is_available` remain explicit.

Deferred: operating/net/FCF margins have extreme provider/taxonomy outliers;
debt/equity and interest coverage are not comparable for lenders and contain
negative or extreme denominators; profit CAGR crosses sign; cash metrics need
filing lineage; P/E/P/B/EV metrics need aligned price, shares and period cutoffs.

## Import, quality and provider policy

`mbe financials-import FILE [--dry-run]` accepts typed deterministic filing JSON,
resolves existing canonical IDs, normalizes units, maps only dictionary metrics,
preserves raw lineage, detects revisions, rejects unknown units/metrics visibly,
and reports counts. Dry-run rolls back every write. `mbe financials-coverage`
prints the latest persisted build.

Provider precedence is official exchange/company/regulator first, compatibility
provider second. Sources are never merged merely to fill a metric. Conflicts are
issues for review. The provider contract now exposes filing discovery/fetch in
addition to the legacy compatibility history call.

Quality checks distinguish rejection from warning. They cover periods, filing
dates, duplicate facts, unknown basis, negative equity and unit/balance-scale
anomalies. Freshness is based on financial period/filing cadence, not quote age:
annual periods up to 550 days are current, 551–730 aging, then stale. This initial
rule is intentionally conservative and should become fiscal-calendar aware.

## API, static contracts and company surface

Dynamic read routes:

- `GET /api/v1/financials/metrics`
- `GET /api/v1/financials/coverage`
- `GET /api/v1/instruments/{instrument_id}/financials`

Metric selection is allowlisted/capped at 20; periods at 12; period/basis values
are typed. Public errors never expose database URLs, paths or provider payloads.

Static output adds `site/api/v1/financials/coverage.json` and one bounded summary
for every scored canonical company research page. Screener JSON includes financial dataset
build ID, definition version and coverage, but no raw history. Generated report
pages show a semantic recent-period table, accepted metrics, basis/source/cutoff,
warning state, methodology link and disclaimer. The 25 legacy report routes
render the same canonical research payload and source disclosure.

Current final build IDs: model `8da41e8a-333d-45d8-818a-b8d4c124c404`, financial
`34baaa1c-e2f6-508b-b2f0-389669739b2a`. The financial build is deterministic for
the same instrument fingerprints; generated time remains operational metadata.

## Score compatibility and limitations

The static projection deliberately calls the unchanged legacy fundamental
calculator. Comparison against all available current score inputs found 0/246
Revenue-CAGR mismatches and 0/232 ROCE mismatches. This proves compatibility,
not historical filing reproducibility. Existing model weights, scores and ranks
did not change. A future model version should migrate only after official filing
coverage and mismatch attribution (unit/period/basis/restatement/provider/formula)
are measured.

Real-browser desktop/tablet/mobile, light/dark, 200% zoom, contrast, keyboard and
VoiceOver/NVDA review remains a deployment gate. The in-app browser was again
unavailable (`[]`) during Phase 4; automated DOM tests are not represented as
manual accessibility evidence.

## Phase 5 official-source extension

Additive migration `20260801_0004` preserves official NSE announcement source
records, attachments/checksums, parser/template states, filing relationships,
reconciliations and build-specific source selections. Discovery uses the NSE
corporate financial-results response. Ind-AS result XBRL is the only
fixture-qualified fact format; discovery JSON is metadata-only and CSV,
XLS/XLSX, HTML, PDF, ZIP and other documents remain explicitly unsupported or
quarantined.

Official access is disabled by default, allowlisted, rate/request/byte bounded,
cache-first and never part of static generation. A captured KFINTECH FY2024
fixture proves 15 Decimal facts with annual/instant context, INR units,
consolidated basis and source tags. One bounded live metadata request and one
XBRL request succeeded; no 250-company crawl was performed.

Reconciliation policy `2026-08-01.1` records exact, rounding, material, period,
unit, basis, official-only, compatibility-only, missing and unresolved states.
Selection policy `2026-08-01.1` prefers quality-valid official facts, permits
Yahoo fallback only for Revenue CAGR/ROCE, and otherwise leaves missing.
Cutoff-aware `latest_known` and `as_filed` reads prevent future restatements from
rewriting historical builds.

Current production-static official coverage remains 0/250; compatibility
fallback remains 246/250 for Revenue CAGR and 232/250 for ROCE. The static
financial build schema is `1.1`, with official/fallback coverage, parser/policy
versions and explicit not-comparable counts. No score input, weight, rank or
historical build changed. See [`official-nse-ingestion.md`](official-nse-ingestion.md)
and [`financial-reconciliation-2026-08-01.md`](financial-reconciliation-2026-08-01.md).
