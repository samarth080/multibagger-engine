# Universal Research Score — Design

**Date:** 2026-08-04 · **Status:** Approved design (Phase 11 Milestone 3)
**Builds on:** Phase 11 Milestone 2A (`coverage-architecture.md`, four coverage
levels) and Milestone 2B (`quote-refresh-architecture.md`, dynamic quotes),
both complete on this branch (`phase11-m2b-dynamic-quotes`).

## Goal

Restore the original product promise — "search any supported listed Indian
stock, get a detailed evaluated institutional-style report" — without
limiting scoring to the 250-company Nifty Smallcap ranking universe, and
without touching that universe's existing validated scores, ranks, model
build IDs, or history.

## Audit findings this design is built on

A full repository and git-history audit (see conversation record; not
duplicated here) found:

1. **The "earlier any-stock scoring implementation" is not a relic — it is
   live code today.** `api/analyze.py` → `mbe.pipeline.analyze_ticker()` →
   `mbe.scoring.engine.build_scorecard()` → `mbe.report.markdown.render_report()`
   already computes a full Multibagger/Investment score and a long
   deterministic markdown report for **any ticker**, live, via
   `YahooProvider(cache=None)`, with zero coupling to the 250-company
   universe. It was designed this way from the start — see
   `docs/superpowers/specs/2026-07-19-live-search-analyze-design.md`. It
   just never got integrated into the newer canonical `/company/{id}.html` +
   coverage-level architecture built in Phase 10A/11-M2A, which explicitly
   *refuses* to score anything outside Level 3
   (`api/company.py`'s docstring: "never a fabricated score, rank or
   research content"; `company_coverage.html`: "No score, rank, strengths,
   risks... exist for this company").
2. **Missing-data handling is already correct** in
   `mbe.analysis.fundamentals`/`technicals`/`valuation`/`risk` and
   `mbe.scoring.pillars.build_pillar()`/`engine.combine()`: a metric that
   can't be computed is `None`, never imputed as zero; pillar/score weights
   renormalize over only the metrics/pillars actually present; confidence is
   the fraction of designed weight backed by real data. This pattern is
   reused, not rebuilt.
3. **No company-type taxonomy exists anywhere** in the data model — only raw
   Yahoo `sector`/`industry` strings on `CompanyInfo`. The existing formulas
   (`_roce_like`/capital-employed ROCE, debt-to-equity, net-debt-to-EBITDA,
   interest-coverage in `mbe.analysis.fundamentals`, and the DCF debt/cash
   netting in `mbe.analysis.valuation`) assume an industrial balance sheet
   and are not meaningful for banks/NBFCs/insurers/AMCs. `sector_themes.py`
   already documents that sector/industry is "descriptive only, never
   scored" today.
4. **Two independent, non-integrated report engines exist.** System A
   (`mbe.report.markdown`, used by `api/analyze.py`) is entirely
   self-contained per company — no peer universe required — and includes
   sections this new feature must **not** reuse (3-Year Price Forecast,
   Entry & Exit Framework, Position Sizing — these generate scenario price
   targets and trading guidance, which conflicts with this task's explicit
   "no fabricated price targets/recommendations" constraint). System B
   (`mbe.research.explanations`, used by `company.html`) generates
   strengths/risks by comparing a company to **cross-sectional medians over
   the ranking universe** — architecturally incompatible with "any stock,"
   and is not touched by this design; it stays exactly as-is for the 250.

## Architecture: two packages, cleanly separated

- **`mbe.scoring.*` (Multibagger/Investment score) — untouched.** Still the
  only thing that produces ranks, universe-relative percentiles, model
  builds, and score history for the 250-company ranking universe.
- **New `mbe.universal.*`** — a new, centralized, versioned policy
  (`UNIVERSAL_SCORE_POLICY_VERSION`) that:
  - Reuses the existing metric layer unchanged
    (`mbe.analysis.fundamentals/technicals/valuation/risk` — already
    missing-data-safe, already universe-agnostic).
  - Reuses the existing generic scoring primitives from
    `mbe.scoring.benchmarks` (the `HIGHER_BETTER`/`LOWER_BETTER` threshold
    tables and `score_metric()`) and the renormalized-weighted-mean pattern
    from `mbe.scoring.pillars.build_pillar()` — these are already generic
    over any company, not Smallcap-specific.
  - Regroups metrics into the required 10-factor taxonomy: Growth,
    Profitability, Capital efficiency, Financial strength, Cash-flow
    quality, Valuation, Momentum, Technical trend, Volatility/risk, Data
    quality. (The current Multibagger pillars are Quality, Growth,
    Financial Strength, Valuation, Momentum, Size Runway, Reinvestment —
    close but not identical; Profitability/Capital efficiency/Cash-flow
    quality split out of what is today folded into "Quality," and Momentum
    splits into separate Momentum + Technical trend factors. Metric
    computations and benchmark thresholds are reused directly; only the
    grouping/weights/company-type variants are new.)
  - Owns its own weights, thresholds, missing-data/coverage rules, minimum
    coverage thresholds, confidence rules, and company-type rules, all in
    one versioned module outside frontend code (per the "scoring policy"
    requirement).

## Factor taxonomy and metric mapping (general-corporate policy)

**Note (added after implementation, reconciling this preliminary sketch
with what shipped):** the exact metric-to-factor assignment below was
refined during Task 4 of the implementation plan
(`docs/superpowers/plans/2026-08-04-universal-research-score.md`) into
`src/mbe/universal/policy.py`'s `_GENERAL_FACTORS`, the actual source of
truth. Two changes from this original sketch, both deliberate: `fcf_cagr_3y`
and `share_count_cagr_3y` were dropped (Growth and Financial strength ended
up with three and four metrics respectively, at clean round per-metric
weights, rather than including every superficially-plausible metric);
`dist_52w_high` moved from Momentum to Technical trend (it's a trend/
positioning signal, closer to `trend_state`/`rsi14` than to the
relative-strength/money-flow pair). See the architecture doc
(`docs/universal-research-score-architecture.md`) for the exact final
factor/weight table.

| Factor | Metrics reused from existing engine | Source module |
|---|---|---|
| Growth | `revenue_cagr_3y`, `profit_cagr_3y`, `margin_trend`, `fcf_cagr_3y` | `mbe.analysis.fundamentals` |
| Profitability | `roe_3y` (or `roe`), net margin (new: derived from `net_income`/`revenue`, not currently a scored metric — added) | `fundamentals` |
| Capital efficiency | `roce_3y` (or `roce`) | `fundamentals` |
| Financial strength | `debt_to_equity`, `interest_coverage`, `net_debt_to_ebitda`, `current_ratio`, `share_count_cagr_3y` | `fundamentals` |
| Cash-flow quality | `fcf_margin`, `cash_conversion`, `accruals_ratio` | `fundamentals` |
| Valuation | `margin_of_safety`, `peg`, `implied_growth_gap`, `fcf_yield` | `fundamentals`/`valuation` |
| Momentum | `relative_strength_63d`, `dist_52w_high`, `cmf20` | `technicals` |
| Technical trend | `trend_state`, `rsi14` | `technicals` |
| Volatility/risk | risk flags/severity from `mbe.analysis.risk.assess_risk` recast as a 0-100 subscore (inverse of triggered-flag severity), not just a haircut | `risk` |
| Data quality | derived directly from the coverage/completeness fraction across all other factors — not a metric lookup, a meta-factor | `mbe.universal.policy` |

All thresholds reuse `mbe.scoring.benchmarks`'s existing tables verbatim
where the metric is shared; no new threshold is invented for a metric that
already has one. New metrics (net margin) get a new, clearly-labeled,
narrower benchmark entry.

## Missing-data and confidence rules

Per factor: only valid, company-type-compatible inputs are scored; each
factor tracks its eligible weight (designed weight minus inputs excluded for
missing data *or* company-type incompatibility) and renormalizes within
itself, exactly like `build_pillar()` does today. Overall score combines
factors the same way `combine()` does today (weighted mean over factors with
confidence > 0, renormalized over what's present).

Coverage percentage = (eligible weight actually scored) / (total possible
weight across all factors for this company type). Confidence is a
qualitative bucket (Low/Medium/High) derived from coverage plus data recency
and price-history depth, matching the existing confidence formula's shape
(`0.5×metric-completeness + 0.3×history-years + 0.2×price-days`, reused
directly).

**Minimum coverage thresholds** determine the report state:

| Coverage | State |
|---|---|
| ≥ 60% eligible weight scored, financials + prices both present | Full evaluated report |
| ≥ 30% and < 60%, or one of financials/prices missing | Partial evaluated report |
| Financials absent, only price history present | Technical-only evaluated report (technical trend + momentum only; no fundamental score) |
| < 30% eligible weight or no usable data at all | Insufficient data for scoring |

A company with only price history gets a technical/momentum analysis and an
explicit "insufficient fundamental data" note — never a fabricated
fundamental subscore of 0.

## Company-type classification and policy variants

No company-type taxonomy exists in the data model today. New deterministic
classifier in `mbe.universal.classification`, keyed off `CompanyInfo.sector`/
`.industry` (raw Yahoo strings — the only signal available, matching how
`sector_themes.py` already keys off the same strings for descriptive theme
matching):

- `sector == "Financial Services"` and `industry` contains "Bank" →
  **bank**
- `industry` contains "Insurance" → **insurance**
- `industry` contains "Credit Services" or "Asset Management" or "Capital
  Markets" → **nbfc** / **asset_management** / **other_financial**
  respectively (exact keyword table documented in the module, small and
  explicit, not a fuzzy classifier)
- `sector == "Financial Services"` with no matched keyword → **other_financial**
  (conservative default; never silently treated as general corporate)
- Otherwise → **general_corporate**
- Insufficient sector/industry data → **unknown_limited_data**

For **bank / nbfc / insurance / asset_management / other_financial**:
Capital efficiency (ROCE) and the leverage-shaped parts of Financial
strength (debt-to-equity, net-debt-to-EBITDA, interest-coverage — all
industrial-balance-sheet assumptions per the audit) are **excluded from
scoring**, not zeroed. Financial strength for these types falls back to
whatever remains compatible (current ratio where meaningful) plus an
explicit "leverage/capital-efficiency metrics not meaningful for this
company type — excluded from scoring" note in the report's data-quality
section. This automatically lowers eligible weight and therefore both
coverage% and confidence for these types, per the missing-data rules above —
no separate "financial company confidence penalty" constant is needed
beyond that natural effect, keeping the policy simpler and self-consistent.
Growth, Profitability (ROE), Valuation, Momentum, Technical trend, and
Volatility/risk apply unchanged — these are meaningful across company
types and reuse the same benchmark thresholds. No sector-specific metric
(NIM, CASA, combined ratio, AUM growth) is fabricated — the repository's
Yahoo-sourced canonical fields (`CANONICAL_FIELDS` in
`mbe.models.company`) don't carry them, so they are honestly omitted, not
approximated.

`unknown_limited_data` uses the general-corporate policy but starts from a
reduced confidence ceiling and a mandatory data-quality disclosure, since
the company type itself is uncertain.

## Report generation

New deterministic template module, `mbe.universal.report` (no LLM, pure
Python/Jinja over already-scored evidence, mirroring how
`mbe.report.markdown` and `mbe.research.explanations` are built today).
Reuses, unmodified, wherever the underlying data is present:

- `mbe.analysis.business.assess_business` — franchise classification
  (Durable Compounder / Deteriorating / Turnaround / Steady / Cyclical /
  Unproven) for the "Business and financial quality" section. Purely
  qualitative, no price implication.
- `mbe.analysis.stewardship.assess_stewardship` — capital-allocation
  classification, for a "Management and capital allocation" note where
  data supports it.
- The ratio-based Financial Analysis, Technical Analysis, and
  ratio/DCF-based Valuation *analysis* (fair value / margin-of-safety band,
  disclosed as a valuation estimate, not a price target promise) from the
  existing per-metric evidence tables.
- Risk flag list and severities from `mbe.analysis.risk.assess_risk`.

**Explicitly excluded** (new report never generates these, even though
System A's code can): 3-Year Price Forecast scenario table, Entry & Exit
Framework, Position Sizing, and the "verdict" ladder's
buy/sell-flavored language ("Strong candidate" / "Avoid") — replaced with
neutral factor-evidence language. No probability-weighted price target, no
guaranteed outcome, no explicit buy/sell recommendation anywhere in the new
template.

Sections (mapped 1:1 to the task's required list): Executive summary ·
Company identity and classification (incl. detected company-type policy) ·
Dynamic market snapshot (quote block, reusing the existing Milestone 2B
quote controller/hooks — never recalculated by a quote tick) · Universal
Research Score (overall + factor subscores + confidence + coverage%) ·
Factor breakdown · Business and financial quality · Growth · Profitability
· Capital efficiency · Balance-sheet strength · Cash-flow quality ·
Valuation · Technical trend · Momentum · Volatility and risk · Strengths ·
Risks and red flags (deterministic, evidence-keyed, same rule-based
approach `mbe.thesis.engine`/`mbe.analysis.risk` already use — not the
universe-median-based `mbe.research.explanations`, since there's no
universe to compare against) · Data-quality and coverage notes · Model
methodology (policy version, weights, company-type policy applied) ·
Research timestamp and source lineage.

## Routing and integration

`/company/{instrument_id}.html` remains the one canonical route (unchanged
per the coverage architecture's existing "route and compatibility
decision"). Changes:

- **Level 3 pages (the 250, static):** gain an *additional* Universal
  Research Score section, computed from the same offline build's already-
  fresh financial/price data (no extra live call — the data is already
  being fetched for the Multibagger score). Rendered alongside the existing
  Validated Universe sections, clearly labeled as a separate score. Existing
  Multibagger sections, hashes, and build IDs are untouched.
- **Levels 0-2 (the ~2,697 others, serverless fallback,
  `api/company.py`):** for any instrument with a provider-symbol mapping
  (`quote_available`), attempt a Universal Research Score. Order of
  resolution: (1) a committed pre-warmed static artifact if one exists for
  this instrument (see refresh pipeline below) — fast, no live call; (2) if
  absent, compute on demand, live, bounded to this one instrument (same
  cost profile as `api/analyze.py` today), and serve with a long edge
  `Cache-Control` header (real caching for a stateless serverless function
  means HTTP edge-cache + committed static artifacts, not a paid KV store —
  no paid provider is added). Level 0 (no provider mapping) and inactive/
  delisted listings never attempt any live call, matching the existing
  Milestone 2B quote-capability gating exactly.
- `/api/analyze?ticker=` stays exactly as it is today (legacy, tested,
  untouched) — but `app.js`/`screener.js` stop falling through to it, since
  every search-universe item now resolves to the canonical
  `/company/{id}.html` route instead. This finally makes every safely
  identified search-universe stock resolve to the canonical route, per the
  task's required search-to-report flow.

## Bounded universal analysis refresh pipeline

New `scripts/build_universal_scores.py`, following the existing
`mbe.builds.offline` pattern (frozen manifests, explicit stages, resumable):

- Input: an explicit instrument-ID list or a cursor into the search
  universe.
- Bounded concurrency (small worker pool, same shape as the existing quote
  batch fetcher), per-request timeout, retry with backoff on transient
  provider failures.
- Per-company failure isolation: one bad ticker recorded as a failure,
  batch continues (same pattern as `mbe.pipeline.screen()`).
- Cache key: `sha256(source financial+price snapshot) + UNIVERSAL_SCORE_POLICY_VERSION`
  — a cache hit skips recomputation entirely; a policy version bump
  invalidates every cached entry deterministically.
- Output: one JSON artifact per company under
  `site/api/v1/universal-scores/{instrument_id}.json` (mirroring how
  `research-coverage.json`/`search-index.json` are already built and
  committed) plus one aggregate manifest (source hashes, request/retry
  counts, per-company outcome, generated timestamp) for partial-completion
  reporting — same shape as `research-coverage.json`'s aggregation role.
- Resumable: reruns skip already-cached, still-valid entries; a `--limit`/
  `--resume-from` flag bounds any single invocation.

**This session's run** (per your answer): the required verification set
(Reliance, TCS, Infosys, HDFC Bank, ICICI Bank, HAL, BEL, Dixon, Polycab,
one SME, one incomplete-fundamentals company, one inactive/unmapped
listing) plus a ~50-100 company sample to demonstrate the pipeline at
scale — not the full ~2,697, which would mean thousands of live Yahoo
calls in this sandboxed environment. The pipeline itself is written
generically; a future operator run with more time/request budget extends
coverage without any code change.

## Search and company pages

Search results gain: Universal report availability, Universal score (when
available), confidence, data coverage, validated Multibagger availability —
alongside the existing coverage-level badge, company/symbol/exchange, and
canonical route. Company pages render every available section from both
score types; for a company without a validated universe score, the page
shows the required honest line: "Universal Research Report available. This
company is not currently included in a validated universe ranking." No
fake universe rank is ever displayed.

## Compatibility guarantees (explicit, testable)

Unchanged: `mbe.scoring.*` weights/formulas/output values for the 250;
Smallcap ranks; model build IDs; Smallcap membership; approved financial
values; canonical instrument IDs; Milestone 2B dynamic quote behavior
(90s/15min/pause/backoff/manual-retry/60s cache — untouched, reused as-is
by the new quote block); search-ranking policy (`SEARCH_RANKING_POLICY_VERSION`
untouched — Universal Research Score is exposed as data on a result, not
folded into ranking, exactly like coverage level already is). Verified by
reusing the existing `public_value_hashes()` fixture and Milestone 2B's
coverage-membership hash fixture, both re-asserted unchanged after every
change, plus a new fixture pinning the verification-set Universal scores
themselves (so an unintended scoring-policy drift is caught the same way).

## Known limitations (disclosed up front, not discovered late)

- Universal coverage grows incrementally via bounded refresh runs, not a
  single big-bang batch — most of the ~2,697 non-Level-3 instruments won't
  have a pre-warmed artifact after this session; they get computed on
  first on-demand request instead (still functional, just first-hit-slow,
  same tradeoff `api/analyze.py` already accepts today).
- Company-type classification is keyword-matched off raw Yahoo
  sector/industry strings, since no cleaner taxonomy exists in this
  repository — documented as a real, disclosed limitation of the
  classifier itself, not hidden behind false precision.
- Sector-specific financial metrics (NIM, CASA ratio, combined ratio, AUM
  growth) are never fabricated for financial-company types — they're
  honestly omitted since the current Yahoo-backed canonical fields don't
  carry them; a future milestone could add a financial-sector-specific
  data source, same shape as the coverage architecture's own recommended
  Level-2 financial-data-source follow-up.
- Real per-request HTTP caching for the on-demand serverless path relies on
  Vercel edge `Cache-Control` semantics, not a persistent store — a cold
  edge cache still means a live Yahoo call for a genuinely first-ever
  request to an instrument with no pre-warmed artifact.
