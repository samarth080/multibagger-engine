# Universal Research Score architecture (Phase 11 Milestone 3)

This document describes the Universal Research Score — a company-type-aware,
missing-data-safe score computed for any searchable stock with sufficient
data, kept architecturally and byte-level separate from the existing
validated Nifty Smallcap 250 Multibagger/Investment score (see
[`coverage-architecture.md`](coverage-architecture.md) for the unrelated
concept of *coverage level*, and
[`quote-refresh-architecture.md`](quote-refresh-architecture.md) for the
unrelated concept of live market-price refresh — this milestone touches
neither of those mechanisms).

Full design record:
[`docs/superpowers/specs/2026-08-04-universal-research-score-design.md`](superpowers/specs/2026-08-04-universal-research-score-design.md).
Full implementation plan (19 tasks, subagent-driven, two-stage reviewed):
[`docs/superpowers/plans/2026-08-04-universal-research-score.md`](superpowers/plans/2026-08-04-universal-research-score.md).

## Audit finding this milestone is built on

A repository and git-history audit found that the "earlier any-stock
scoring implementation" the task asked to recover was not a lost feature —
it is live code today: `api/analyze.py` → `mbe.pipeline.analyze_ticker()` →
`mbe.scoring.engine.build_scorecard()` already computes a full score for any
ticker, live, with zero coupling to the 250-company universe, and
`mbe.analysis.fundamentals`/`technicals`/`valuation`/`risk` already handle
missing data correctly (a metric that can't be computed is `None`, never
imputed as zero; weights renormalize over what's present). It was simply
never integrated into the newer canonical `/company/{id}.html` +
coverage-level architecture, which explicitly refused to score anything
outside Level 3. This milestone reuses that proven metric layer and
scoring pattern under a new, versioned, company-type-aware policy rather
than rebuilding it.

## Package layout

New `mbe.universal` package, one file per responsibility:

- `domain.py` — `CompanyType`, `ReportState` enums; `UniversalFactorScore`,
  `UniversalScoreCard` Pydantic models.
- `classification.py` — `classify_company_type(sector, industry)`, a small
  explicit keyword table over raw Yahoo sector/industry strings (no cleaner
  taxonomy exists anywhere in this repository).
- `benchmarks.py` — additive benchmark table(s) for metrics
  `mbe.scoring.benchmarks` doesn't define (currently just `net_margin`).
  Never edits the existing file, so the validated Multibagger score stays
  byte-identical.
- `policy.py` — `UNIVERSAL_SCORE_POLICY_VERSION = "universal-score-v1"`,
  `FACTOR_WEIGHTS` (10 factors), per-company-type factor/metric
  definitions, `MIN_COVERAGE_FULL`/`MIN_COVERAGE_PARTIAL`,
  `FINANCIAL_COMPANY_TYPES`, `score_universal_metric()` (dispatches to
  `mbe.scoring.benchmarks.score_metric`/`score_rsi`/`score_trend` for every
  metric they already cover, and to this package's own table only for
  `net_margin`).
- `engine.py` — `build_universal_score()`: combines factor scores into an
  overall score, coverage percentage, confidence, report state.
- `explanations.py` — `build_strengths_and_risks()`: deterministic,
  rule-based, self-contained (no cross-sectional universe median needed,
  unlike `mbe.research.explanations`).
- `report.py` — `build_universal_report()`: the 19-section report payload,
  with `FORBIDDEN_REPORT_KEYS` asserted against directly by tests so a
  price-forecast/recommendation section can never be silently added.
- `pipeline.py` — `analyze_universal(ticker, provider)`: per-ticker
  orchestration, mirroring `mbe.pipeline.analyze_ticker`'s shape.
- `cache.py` — `cache_key_for()` (sha256 of source data + policy version),
  `read_cached_report()`/`write_cached_report()` (JSON artifact I/O),
  `load_universal_scores_summary()` (small per-instrument summary for the
  search index).

Plus `scripts/build_universal_scores.py` — the bounded, resumable refresh
CLI (see below).

## Factor taxonomy and company-type policy

Ten factors, reusing existing metric computations and benchmark thresholds
verbatim wherever a shared metric already has one:

| Factor | Weight | Metrics (general-corporate policy) |
|---|---|---|
| Growth | 0.15 | revenue_cagr_3y, profit_cagr_3y, margin_trend |
| Profitability | 0.12 | roe_3y, net_margin |
| Capital efficiency | 0.10 | roce_3y |
| Financial strength | 0.10 | debt_to_equity, interest_coverage, net_debt_to_ebitda, current_ratio |
| Cash-flow quality | 0.10 | fcf_margin, cash_conversion, accruals_ratio |
| Valuation | 0.15 | margin_of_safety, peg, implied_growth_gap, fcf_yield |
| Momentum | 0.08 | relative_strength_63d, cmf20 |
| Technical trend | 0.08 | trend_state, rsi14, dist_52w_high |
| Volatility and risk | 0.07 | derived from `mbe.analysis.risk.assess_risk`'s risk_score, not a metric table |
| Data quality | 0.05 | meta-factor: reports coverage%, excluded from the overall-score weighted mean (see below) |

For **bank / nbfc / insurance / asset_management / other_financial**
company types: `roce_3y`, `debt_to_equity`, `net_debt_to_ebitda`,
`interest_coverage` (all industrial-balance-sheet formulas) are removed
from the metric list entirely — not scored-then-zeroed — for Capital
efficiency and Financial strength. This lowers eligible weight and
therefore both coverage% and confidence for these types automatically,
with an explicit disclosure line in `excluded_factor_notes`. No
sector-specific metric (NIM, CASA, combined ratio, AUM growth) is
fabricated — Yahoo's canonical fields don't carry them, so they're
honestly omitted.

`unknown_limited_data` (no sector/industry signal at all) uses the
general-corporate policy.

## Missing-data and report-state rules

Within each factor: only metrics with real, non-`None` values are scored;
each factor's weighted mean renormalizes over what's present, exactly like
`mbe.scoring.pillars.build_pillar()` already does for the validated model.
`overall_score` is computed from the real factors only — the "Data
quality" meta-factor (whose score is literally the coverage percentage) is
deliberately excluded from that computation, so a company with zero
scoreable data gets `overall_score = None`, never a fabricated `0.0` (a
real bug found and fixed during this milestone's own review cycle — see
"Known issues found and fixed" below).

| Coverage (non-meta factor weight scored) | Financials present | Prices present | Report state |
|---|---|---|---|
| ≥ 60% | yes | — | `full_evaluated_report` |
| 30–60% | yes | — | `partial_evaluated_report` |
| any | no | yes | `technical_only_evaluated_report` |
| < 30%, or no financials and no prices | — | — | `insufficient_data_for_scoring` |

## Report generation

`mbe.universal.report.build_universal_report()` produces a 19-key
deterministic payload (executive summary, company identity, universal
score, factor breakdown, business/growth/profitability/capital-efficiency/
balance-sheet/cash-flow/valuation/technical/momentum/risk sections,
strengths, risks, data-quality notes, methodology, source lineage) — no
LLM, template text keyed off scored evidence. `FORBIDDEN_REPORT_KEYS =
("price_forecast", "entry_exit_framework", "position_sizing",
"price_target")` is a hard compliance boundary asserted directly by tests:
this report never generates a price target, trading recommendation, or
guaranteed outcome, unlike the legacy `mbe.report.markdown` engine (used by
`api/analyze.py`) it otherwise draws proven patterns from.

## Routing

`/company/{instrument_id}.html` remains the one canonical route.

- **Level 0-2** (`api/company.py`, the serverless coverage fallback): for
  any instrument with `coverage.quote_available`, attempts a pre-warmed
  artifact first (`site/api/v1/universal-scores/{id}.json`), falling back
  to a live, single-instrument `analyze_universal()` computation on a
  cache miss. `maxDuration: 60` (matching `api/analyze.py`) accounts for
  the live-fallback path's sequential Yahoo calls. Any failure (missing
  provider symbol, cache miss + provider error, malformed cached artifact)
  degrades to `universal=None`, never breaking the page.
- **Level 3** (the 250 statically-built, validated-universe pages): reads
  the same pre-warmed artifact directory only — never computes live during
  the offline build, preserving `render_site_from_manifest`'s
  `deny_network()` guarantee. A missing artifact renders "not yet
  refreshed," never a live fetch attempt.

`company_coverage.html` (Levels 0-2) and `company.html` (Level 3) each
render a Universal Research Score section when available; the coverage
template additionally distinguishes "not yet refreshed" (has a quote
mapping, just hasn't been scored yet) from "cannot be produced" (Level 0,
no quote mapping — structurally can never be scored) — a distinction Level
3 doesn't need, since ranking-universe membership guarantees a quote
mapping.

Search results (`app.js`) surface a `Universal {score} · {confidence}`
badge when available, and `reportDestination()` in both `app.js` and
`screener.js` now always resolves to the canonical `/company/{id}.html`
route — the previously-dead `/api/analyze?ticker=` fallback branch was
removed (every real search-universe record already carries a valid
`instrument_id`).

## Bounded refresh pipeline

`scripts/build_universal_scores.py`: for each instrument, fetches fresh
`(info, financials, prices)` with retry-with-backoff (linear, up to 3
attempts by default) against the real provider, computes a source-data
hash (`cache_key_for`), and only pays for the expensive scoring/report-
building step on a hash miss — a hash match means "resumable" in the sense
of skipping the expensive work, not skipping the network entirely, since
genuine staleness detection requires a fresh fetch every run to compute a
comparison hash (a policy-version bump must invalidate every cached entry
deterministically, which is impossible without this). One bad ticker never
aborts the batch (per-company failure isolation, same pattern as
`mbe.pipeline.screen()`). Deliberately sequential, not concurrent, to
avoid raising Yahoo rate-limit risk from one process — `--limit` plus
retry-with-backoff already satisfy "bounded" without that added
complexity. Writes one JSON artifact per company plus an aggregate
`manifest.json` (`succeeded_count`, `skipped_cached_count`, `failed_count`,
`failures`) for partial-completion reporting.

`scripts/verify_release.py` tracks the resulting `site/api/v1/universal-scores/`
directory as a variable-size, incrementally-grown artifact set — excluded
from the fixed `EXPECTED["json"]` literal (which would otherwise break on
every refresh run), with its own separate consistency check (artifact
count vs. `manifest.json`'s `succeeded_count`, reported as an error rather
than crashing on a corrupt manifest).

## Compatibility guarantees

Unchanged: `mbe.scoring.*` weights/formulas/output for the 250; Smallcap
ranks; model build IDs; Smallcap membership; approved financial values;
canonical instrument IDs; Milestone 2B dynamic quote behavior; search-
ranking policy (Universal Research Score is exposed as data on a search
result, exactly like coverage level already is, never folded into
ranking). Verified via `public_value_hashes()` (scores/financials,
byte-identical to the existing fixture before and after this milestone's
real build), the Milestone 2B coverage-membership fixture, and a new
`tests/fixtures/phase11-m3-universal-score-hash.json` drift guard pinning
the Universal engine's own output for a fixed, network-free verification
set.

## Known issues found and fixed during implementation

Two-stage subagent review (spec compliance, then code quality) on every
task caught several real defects before they shipped:

- **`overall_score` fabricated as `0.0` instead of `None`** when a company
  had zero scoreable data — the "Data quality" meta-factor was originally
  included in the overall-score weighted mean, so when it was the only
  factor left with confidence > 0, the score collapsed to the coverage
  percentage itself. Fixed by excluding it from that computation entirely
  (§"Missing-data and report-state rules" above).
- **Resumable-vs-staleness design tension** in the refresh CLI: an
  intermediate fix made cache hits skip the fetch entirely, which broke
  genuine staleness detection (a policy-version bump would never be
  noticed). Resolved by fetching fresh data every run for hash comparison,
  only skipping the expensive scoring/report-building step on a genuine
  hash match.
- **`KeyError` risk on a malformed cached artifact** (`cached["report"]`
  instead of `cached.get("report")`) in both `api/company.py` and
  `src/mbe/research/lightweight.py` — the latter would have crashed the
  entire 250-company offline build on one bad artifact, not just one page.
- **Missing `maxDuration` bump** for `api/company.py`'s live-fallback path
  — without it, a platform timeout would have killed the whole function
  (including the previously-reliable identity/quote content) rather than
  degrading gracefully.
- **Eager provider construction** on every request (importing `yfinance`
  even on a cache hit where it's never used) — fixed by passing a lazy
  factory instead of an already-constructed provider.
- **Null-score badge rendering** (`"Universal 0 · null"`) when
  `universal_score_available` is true but the underlying score is `None` —
  fixed with a `Number.isFinite()` guard matching the existing pattern.

## Known limitations

- Universal coverage grows incrementally via bounded refresh runs. This
  milestone's real run covered the required verification set (Reliance,
  TCS, Infosys, HDFC Bank, ICICI Bank, HAL, BEL, Dixon, Polycab, one SME,
  one thin-data company) plus a 60-company scale sample — 62 of 2,947
  search-universe companies, not the full universe. The refresh pipeline
  itself is written generically for the full universe; a future operator
  run with more time/request budget extends coverage without any code
  change.
- No real company in the current search universe has `listing_status`
  outside `active`/`unknown` or lacks a `provider_symbol` (Level 0
  currently has zero members, per `coverage-architecture.md`'s own known
  limitation) — the "inactive/unmapped listing" verification case was
  therefore exercised with a synthetic invalid ticker instead of a real
  inactive company, and failed cleanly as expected.
- In this run, every company that returned usable data landed in
  `full_evaluated_report` state (coverage 73.7%–100%) — none landed in
  `partial_evaluated_report` or `technical_only_evaluated_report`. Yahoo
  generally provides fairly complete data for actively-traded listed
  Indian companies; the "partial"/"technical-only" states are real,
  policy-tested code paths (exercised directly by
  `tests/test_universal_engine.py`), just not naturally hit by this
  particular live sample. The 10 failures did exercise the "insufficient
  data" path via total fetch failure (no info/no financials at all).
- Company-type classification is keyword-matched off raw Yahoo
  sector/industry strings, since no cleaner taxonomy exists in this
  repository — a disclosed limitation of the classifier itself.
- Real per-request HTTP caching for the on-demand serverless path relies
  on Vercel's platform behavior, not a persistent store — a genuinely
  first-ever request to an instrument with no pre-warmed artifact still
  means a live Yahoo call.
