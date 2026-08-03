# Phase 11 Milestone 2A — Universal Company Report Architecture

Status: approved for planning (2026-08-03)

## Goal

Every one of the ~2,947 search-universe instruments resolves to the canonical
route `/company/{instrument_id}.html` with a report whose *depth* — not
existence — reflects how much validated data is available for it. Formalize
that depth as four versioned, deterministically-assigned coverage levels
(0 Identity, 1 Market, 2 Fundamentals, 3 Full Research), expose them through
search, the API and a static artifact, and generalize the existing two-tier
page system (full research vs. lightweight) into a coverage-aware one without
disturbing the 250 existing Level-3 pages, their score/financial/membership
hashes, or the deterministic offline build.

This milestone does **not** add large/mid-cap scoring, automatic quote
refresh, or new financial metrics. It is architecture and coverage plumbing
only.

## Current state (verified 2026-08-03)

- **Rendering**: `mbe.publish._render_company_page()` (`company.html`) renders
  the 250 Level-3 pages during `render_site()`; a Vercel serverless function
  `api/company.py` renders every other instrument on demand via
  `mbe.publish.render_lightweight_company_page()` (`company_lightweight.html`)
  — Vercel serves an existing static file before checking the
  `/company/:instrumentId.html → /api/company?id=…` rewrite, so the fallback
  only ever runs for non-modeled instruments. This exact static/serverless
  split is what Milestone 2A generalizes; it is not being replaced.
- **Payload builders**: `mbe.research.builder.build_company_research()`
  (Level 3, `CompanyResearch` schema `1.0`, `src/mbe/research/domain.py`)
  and `mbe.research.lightweight.build_lightweight_research()` (identity +
  quote only, explicitly refuses a `research_available` record).
- **Identity**: `mbe.models.instrument.stable_instrument_id()` /
  `stable_company_id()` — deterministic UUIDv5 IDs, already assigned to every
  search-universe record, not just the 250.
- **Search index**: `mbe.search.domain.SearchIndexRecord` /
  `mbe.search.catalog.build_search_index()` — already merges the NSE (2,927)
  + BSE (20) search universes with the 250-company research/ranking universe,
  tags `result_type` (`modeled`/`known`/`quote_only`/`unknown`) and
  `research_available`, and — critically — already carries `provider_symbol`
  per record, which is the exact "quote-provider mapping" capability Level 1
  needs. Bundled into `api/company.py` and `api/quotes.py` today via
  `vercel.json` `includeFiles`; **not** currently bundled into `api/v1.py`.
- **Financial data scope**: `scripts/build_financials.py` /
  `build_financials_from_model()` compute financials only for the instruments
  in `universes/nifty-smallcap250-instruments.json` — i.e. only the 250
  already-modeled companies. There is no financial data source for any other
  instrument today, and adding one is explicitly out of scope for this
  milestone.
- **API**: `src/mbe/api/app.py` is a FastAPI app, DB-backed
  (`Depends(get_session)`), mounted as one Vercel ASGI function. PostgreSQL is
  not provisioned in production, so every DB-backed route (including the
  existing `GET /api/v1/company/{instrument_id}/summary`) returns a bounded
  503 there today; static `/api/v1/*.json` and the `api/company.py` /
  `api/quotes.py` serverless functions carry all real production traffic.
- **Determinism/hash gates**: `scripts/verify_release.py:public_value_hashes()`
  hashes sorted `screener.json` rows (`scores_sha256`) and sorted per-instrument
  `financials`/`ranking` subsets (`financials_sha256`) against
  `tests/fixtures/phase8-public-value-hashes.json`. The Smallcap-membership
  hash is the SHA-256 of `universes/nifty-smallcap250.json`, recorded in
  `builds/manifests/phase11-m1-frozen-inputs.json`. None of these hash raw
  HTML — template changes are safe as long as these specific JSON subsets are
  untouched.

## Architecture

### 1. Coverage domain & policy — `src/mbe/coverage/`

New package, two modules:

- `domain.py`
  - `CoverageLevel(IntEnum)`: `IDENTITY = 0`, `MARKET = 1`, `FUNDAMENTALS = 2`,
    `FULL_RESEARCH = 3`.
  - `CoverageAssessment(BaseModel)`: `instrument_id`, `company_id`,
    `coverage_level: CoverageLevel`, `coverage_level_version: str`,
    `coverage_status: str` (e.g. `"active"`), `research_eligible: bool`,
    `research_eligibility_reasons: list[str]`,
    `research_sections_available: list[str]`,
    `research_sections_missing: list[str]`, `research_universe: str | None`
    (e.g. `"Nifty Smallcap 250"` or `None`), `ranking_available: bool`,
    `model_available: bool`, `financial_available: bool`,
    `quote_available: bool` (capability, not live success),
    `identity_completeness: Literal["complete", "partial"]`,
    `source_quality_summary: str`, `evaluated_at: str` (ISO8601),
    `coverage_policy_version: str`.
- `policy.py`
  - `RESEARCH_COVERAGE_POLICY_VERSION = "2026-08-03.11.2a.1"`.
  - `assess_coverage(*, identity: IdentityInput, has_provider_symbol: bool, has_financial_data: bool, has_model_score: bool, has_full_research_payload: bool) -> CoverageAssessment` — pure, deterministic, no I/O. `IdentityInput` is a small typed shape (not the full `SearchIndexRecord`, so the policy module doesn't import `mbe.search`) covering `instrument_id`, `company_id`, `isin`, `bse_code`, `legal_name`, `exchange`, `listing_status`, `is_sme`.
  - Level assignment (matches the spec's worked examples exactly):
    - Invalid/unresolvable identity → not applicable (caller 404s before calling this; the policy assumes a valid identity).
    - Level 0: valid identity; `has_provider_symbol=False` or `has_financial_data=False`/`has_model_score=False` doesn't matter — Level 0 is the floor whenever there's no quote mapping.
    - Level 1: valid identity, `has_provider_symbol=True`, `has_financial_data=False`, `has_model_score=False`.
    - Level 2: valid identity, `has_provider_symbol=True`, `has_financial_data=True`, `has_model_score=False`.
    - Level 3: valid identity, `has_model_score=True` **and** `has_full_research_payload=True` (both required — a model score alone without the full lineage/explanation payload does not promote to Level 3; this can't currently happen since the 250-company build always produces both together, but the policy encodes the real invariant rather than relying on that coincidence).
  - `research_sections_available`/`missing` are a fixed ordered list of section names (`"identity"`, `"quote"`, `"financial_summary"`, `"score"`, `"rank"`, `"explanations"`, `"strengths"`, `"risks"`, `"score_history"`, `"peers"`, `"technical"`, `"news"`, `"filings"`, `"checklist"`) partitioned by level via a static level→sections table in the same module — one source of truth for "don't render empty sections."

### 2. Page rendering — shared partials, not a template merge

Extract shared Jinja partials used by **both** the untouched Level-3 template
and a new/generalized coverage template for Levels 0–2:

- `_partials/coverage_banner.html` — level, label (`"Level 0 — Identity
  Coverage"` etc.), the two disclosure strings, canonical link.
- `_partials/identity_block.html`, `_partials/disclaimer.html`,
  `_partials/data_freshness.html`.

`company.html` (Level 3) is **not restructured** beyond including these
partials in place of its existing inline identity/disclaimer markup — this
keeps the 250 pages' content changes minimal and scoped, avoids rewriting
Playwright visual baselines wholesale, and satisfies "reusable sections"
without a risky full unification. `company_lightweight.html` is renamed/
generalized to `company_coverage.html` and grows conditional blocks for
Level 1 (market panel) and Level 2 (financial summary panel), reusing the
same partials. No empty section ever renders — the template checks
`coverage.research_sections_available` membership, not just "is the field
present," so a `None` quote at Level 1 renders an explicit "quote
unavailable" state rather than nothing or a zero.

`build_coverage_research()` (new, `src/mbe/research/coverage.py`) replaces
`build_lightweight_research()` as the payload builder for Levels 0–2: same
refusal guard for `research_available` records, but now also takes/returns
the `CoverageAssessment` and conditionally includes a financial-summary block
(Level 2) sourced the same way `FinancialResearch` is today, when
`financial_available` is true. `render_lightweight_company_page()` is
renamed `render_coverage_company_page()`; `api/company.py` and any Level-0–2
call sites are updated accordingly (grep-clean rename, not a compatibility
shim, per this repo's stated convention of not keeping backward-compat
shims for internal renames).

### 3. Static-vs-serverless decision (documented, not just decided)

**Decision: do not statically generate the ~2,697 non-Level-3 pages.** Extend
`api/company.py` to compute `CoverageAssessment` (via the search-index record
it already loads) and call `build_coverage_research()`/
`render_coverage_company_page()` instead of the flat lightweight builder.

Rationale, measured against the spec's criteria:
- **Canonical URLs preserved** — no routing change; `vercel.json`'s existing
  rewrite already covers every non-static instrument ID.
- **Deterministic builds preserved** — level assignment depends only on
  frozen build artifacts (search index, financial build membership, model
  build membership), never on the live quote fetch, so it's safe to compute
  once during the offline build (for the coverage artifact, see below) and
  again at request time in the serverless function (for rendering) without
  the two ever disagreeing.
- **No PostgreSQL required** — reads the same bundled `search-index.json`
  `api/company.py` already reads.
- **Avoids duplicated payloads** — statically generating ~2,697 pages at the
  measured ~25 KB/page average of the existing 250 (`docs/company-research-
  architecture.md`) would add on the order of tens of MB to the committed
  `site/` output for content that's mostly identical boilerplate per company;
  Level 0–1 pages in particular are small, near-identical payloads that
  differ only in identity/quote fields. The plan's Task list includes
  measuring the actual Level-0/1/2 payload sizes and reporting the real
  static-equivalent cost so this tradeoff is backed by numbers, not just
  the a-priori argument.
- **Deployable on Vercel unchanged** — same function, same `includeFiles`
  pattern, no new function needed.

### 4. Static coverage artifact — `site/data/research-coverage.json`

A small **aggregate** artifact, written by a new offline stage
(`scripts/build_coverage_artifact.py`, following the existing "explicit data
stage" convention alongside `build_search_assets.py` /
`build_frontend_assets.py`):

```json
{
  "schema_version": "1.0",
  "coverage_policy_version": "2026-08-03.11.2a.1",
  "search_build_id": "...",
  "financial_build_id": "34baaa1c-e2f6-508b-b2f0-389669739b2a",
  "model_build_ids": ["1bd53d15-67c6-4b02-b830-0eb0bb1d582b"],
  "instrument_count": 2947,
  "level_counts": {"0": 0, "1": 0, "2": 0, "3": 250},
  "coverage_reasons": {"no_quote_mapping": 0, "no_financial_data": 0, "not_modeled": 2697},
  "generated_at": "...",
  "source_hashes": {"search_index": "...", "financial_build": "...", "model_build": "..."}
}
```

Exact `level_counts` depend on how many search-universe instruments lack a
`provider_symbol` (verified during implementation; expected to be small or
zero, since NSE/BSE listing implies a Yahoo-mappable symbol in the existing
data). No raw provider payloads, no per-instrument detail (that lives in
`search-index.json`, see below) — this file is for reporting/monitoring, not
lookups.

### 5. Per-instrument coverage — additive `SearchIndexRecord` fields

Add to `mbe.search.domain.SearchIndexRecord` (additive, versioned, existing
consumers unaffected since they access by field name): `coverage_level: int`,
`coverage_level_version: str`, `coverage_status: str`,
`research_eligible: bool`, `research_eligibility_reasons: list[str]`,
`research_sections_available: list[str]`, `research_sections_missing: list[str]`,
`coverage_policy_version: str`. Computed in `build_search_index()` by calling
`assess_coverage()` once per record — the same function `api/company.py` and
the API call, so there is exactly one place the level logic lives.

This is the single source of truth `api/company.py`, the new API route, and
the frontend search results all read from — no separate per-instrument
coverage file, no drift risk.

### 6. API — additive, two surfaces

- `GET /api/v1/company/{instrument_id}/coverage` (new route in
  `src/mbe/api/app.py`, DB-backed like its siblings — same bounded 503 without
  Postgres as every other dynamic route today, consistent with the existing
  documented failure mode). Returns `CoverageAssessment` fields directly
  (no fake score fields — the model literally has none to fake).
- `GET /api/v1/company/{instrument_id}/summary` (existing route) gains the
  same additive coverage fields on `CompanySummaryData`, computed via the
  identical `assess_coverage()` call — extends rather than duplicates.
- `vercel.json`: add `site/api/v1/search-index.json` to `api/v1.py`'s
  `includeFiles` (currently only bundles `site/data.json`) so the DB-path
  fallback isn't the only way to reason about coverage in that function later;
  the DB-backed route itself computes `has_financial_data`/`has_model_score`
  from `PlatformRepository`/`ScoreSnapshotRow` queries, matching how
  `company_summary_route` already computes `research_available` today.

### 7. Search integration

Frontend search rendering (`site` JS, `tests/frontend/*.test.js`) reads the
new `coverage_level`/`research_sections_available` fields off each
`SearchIndexRecord` already in `search-index.json` and renders one of four
badge labels (`"Full Research"`, `"Financial Coverage"`, `"Market Coverage"`,
`"Identity Only"`). No change to `mbe.search.ranking` match tiers, scoring or
ordering — purely a rendering addition keyed off already-present-in-payload
data.

## Data flow summary

```
offline build (deterministic, no network):
  identity (stable_instrument_id) + search universes
    -> build_search_index() -> assess_coverage() per record
       -> search-index.json (with coverage fields)
       -> build_coverage_artifact.py -> research-coverage.json (aggregate)
  250 modeled instruments -> build_company_research() -> company.html (Level 3, unchanged)

request time (serverless, per instrument not in the 250):
  api/company.py -> load search-index.json record (has coverage fields already)
    -> build_coverage_research() -> render_coverage_company_page()
       (live quote fetch attempted; failure -> quote_state "unavailable", never a fabricated zero)

dynamic API (DB-backed, bounded 503 without Postgres):
  GET /api/v1/company/{id}/coverage, GET /api/v1/company/{id}/summary
    -> same assess_coverage() call, DB-sourced inputs
```

## Error handling

- Invalid/unrecognized `instrument_id` path segment: `api/company.py` already
  regex-validates (`^[A-Za-z0-9-]{1,80}\Z`) before any lookup — reused as-is,
  no new path-traversal surface.
- Instrument not in the search index at all: 404, unchanged behavior.
- `research_available=True` reaching the fallback (stale static build): 404
  with the existing honest "temporarily unavailable, please retry" message —
  unchanged; never silently downgrades a Level-3 company.
- Live quote fetch failure at Level 1/2: rendered as an explicit "quote
  unavailable" state (existing `_fetch_quote` try/except pattern), never a
  zero or blank.
- DB-backed coverage/summary routes without Postgres: existing bounded
  `{"code": "database_not_configured"}` 503 — no new failure mode introduced.

## Testing

Per the milestone spec's list, organized by file:

- `tests/test_coverage_policy.py` (new): Level 0/1/2/3 assignment from each
  documented input combination; invalid identity; missing quote mapping;
  missing financials; model unavailable but full payload claimed (rejected);
  no fake score/rank fields ever present below Level 3; no empty
  `research_sections_available` entries render (asserted structurally, via
  the level→sections table itself being exhaustive and disjoint).
- `tests/test_research_coverage.py` (new, alongside existing
  `test_research_lightweight.py` which stays for the parts of
  `build_lightweight_research`'s contract that carry over): coverage-aware
  payload building per level, refusal guard for `research_available` records
  preserved.
- `tests/test_publish_coverage.py` (new, alongside `test_publish_lightweight.py`):
  template rendering per level, no empty sections, coverage banner content.
- `tests/test_company_fn.py` (extend): `api/company.py` renders the correct
  level for fixture instruments at each coverage tier.
- `tests/test_coverage_artifact.py` (new): `research-coverage.json`
  determinism (byte-identical across repeated offline builds), schema fields
  present, counts reconcile with the search index.
- `tests/test_search_catalog.py` (extend): coverage fields present and
  correct per `SearchResultType`.
- `tests/test_api_v1.py` (extend): new `/coverage` route, extended
  `/summary` route, both with and without a configured DB.
- `tests/test_deterministic_build.py` / `tests/test_release_readiness.py`
  (extend): the coverage artifact/fields don't change `scores_sha256`,
  `financials_sha256`, or the Smallcap-membership hash — explicit
  before/after hash-equality assertions against the same fixture already
  in use, run as part of the existing offline-build determinism tests
  (`deny_network()` guard applies automatically).
- Canonical routing: parametrized test resolving every fixture security
  (spanning all four levels) through the same route-resolution logic Vercel
  uses (static-file-exists check + fallback), confirming no fixture 404s.
- Frontend (`tests/frontend/*.test.js`, extend): coverage badge rendering
  for each level, no fake cards below Level 3, keyboard/ARIA label presence
  for the badge (asserted via DOM attributes — full screen-reader/manual
  browser passes stay in the existing manual Phase 8 checklist, not
  automated here, consistent with how the rest of this repo's accessibility
  gate works).

Baseline (659 Python / 35 frontend) must only grow, never shrink.

## Security

- Reuses the existing `instrument_id` regex validator — no new path input
  surface.
- `CoverageAssessment` and the new artifact never carry raw provider
  payloads, local filesystem paths, or Phase 6 private evidence — same
  constraint already enforced on `CompanyResearch`/`SearchIndexRecord`, just
  extended to the new fields, which are all small enums/booleans/strings.
  spot-checked in tests via a corpus scan.
- API responses stay bounded (fixed enum-valued fields, bounded list
  lengths from the fixed section table) — no unbounded arrays introduced.
- CSP unchanged; no new script/style sources.

## Documentation

- `docs/HANDOVER.md`: new "Phase 11 Milestone 2A — universal company report
  coverage" section (phase ledger entry, following the existing style), plus
  an update to the "Search, research and ranking universes" section to
  reference the formal coverage levels.
- New `docs/coverage-architecture.md` (parallels
  `docs/company-research-architecture.md` and `docs/search-architecture.md`
  in structure/tone): policy version, level definitions, static/serverless
  decision with measured numbers, API contract, known limitation that Level
  2 currently has zero members (no financial data source exists yet outside
  the 250-company model universe — this is expected, not a bug, and is the
  natural Milestone 2B prerequisite: ingest a broader financial dataset, or
  wire the Nifty 100 / Midcap 150 membership import already gated in
  `docs/HANDOVER.md`'s Milestone 2 entry criteria).

## Known limitation to report explicitly at completion

Level 2 (Fundamentals) is fully specified and testable but will have **zero
real members** at the end of this milestone: financial data is only computed
for the 250 already-Level-3 companies (`scripts/build_financials.py` is
scoped to `nifty-smallcap250-instruments.json`), and ingesting a broader
financial source is explicitly out of scope here. This is the clearest
concrete recommendation for Milestone 2B.

## Milestone 2B recommendation (preview, to be finalized in the completion report)

Two independent follow-ups, either order: (a) import a financial data source
for the wider search universe so Level 2 gets real members, or (b) the
already-gated Nifty 100 / Midcap 150 membership import from
`docs/HANDOVER.md`'s Phase 11 Milestone 2 entry criteria, which would feed
Level 3 eligibility for a second research universe once Milestone 3's model
validation work is done. This milestone's coverage architecture supports
either without further schema changes — that's the point of building the
policy as data-driven rather than hard-coded to 250.
