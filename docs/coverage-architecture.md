# Universal company report coverage architecture

Implemented: 2026-08-03 (Phase 11 Milestone 2A)

## Route and compatibility decision

The canonical route and the static/serverless split are unchanged by this
milestone: see `docs/company-research-architecture.md`'s "Route and
compatibility decision" for the full contract. `/company/{instrument_id}.html`
remains the one permanent canonical URL for every company, modeled or not;
Vercel still serves a real static file for the 250 research-universe
companies before evaluating rewrites, and every other instrument ID still
falls through to the `api/company.py` serverless fallback. This milestone
changes what that fallback (and the static search index behind it) knows
about *how much* data exists for a company — it does not change where a
company's page lives or how it is routed to.

## The four coverage levels

A coverage level is a deterministic, versioned statement of how much
validated data exists for an instrument — not a research verdict, and not a
quality or investability judgment. `mbe.coverage.domain.CoverageLevel` is an
`IntEnum` with four values; `COVERAGE_LEVEL_LABELS` gives the public label
for each, and `COVERAGE_LEVEL_SECTIONS` gives the exact page sections that
level unlocks. Each level's section table is a strict superset of the
previous level's (enforced by
`test_section_tables_are_nested_and_cover_all_sections`).

| Level | Label | Sections | Assignment rule |
|---|---|---|---|
| 0 | Level 0 — Identity Coverage | `identity` | The floor. Assigned whenever the instrument has no provider (Yahoo) quote-symbol mapping, regardless of any other data. |
| 1 | Level 1 — Market Coverage | `identity`, `quote` | Requires a provider symbol (a live quote can be fetched); no financial data. |
| 2 | Level 2 — Financial Coverage | `identity`, `quote`, `financial_summary` | Requires a provider symbol **and** financial data (Revenue CAGR 3y / ROCE 3y / source label). |
| 3 | Level 3 — Full Research | `identity`, `quote`, `financial_summary`, `score`, `rank`, `explanations`, `strengths`, `risks`, `score_history`, `peers`, `technical`, `news`, `filings`, `checklist` | Requires **all four** of: a model score, a full research payload, financial data, and a provider symbol. |

The exact logic lives in `mbe.coverage.policy.assess_coverage()` — the single
function every caller (`mbe.search.catalog.build_search_index()`,
`api/company.py`, and `mbe.api.app`'s dynamic routes) calls, so none of them
can independently disagree about a company's level:

```python
if has_model_score and has_full_research_payload and has_financial_data and has_provider_symbol:
    level = CoverageLevel.FULL_RESEARCH       # 3
elif has_financial_data and has_provider_symbol:
    level = CoverageLevel.FUNDAMENTALS        # 2
elif has_provider_symbol:
    level = CoverageLevel.MARKET              # 1
else:
    level = CoverageLevel.IDENTITY            # 0
```

`assess_coverage()` also derives `research_eligibility_reasons` (e.g.
`no_quote_provider_mapping`, `no_financial_data`, `not_in_model_universe`),
`research_sections_available`/`research_sections_missing`,
`identity_completeness` (`"complete"` only when both ISIN and legal name are
present), and `research_coverage_status` (`"active"` vs.
`"inactive_listing"`, from the record's listing status). It never fabricates
a positive field: `ranking_available`, `model_available` and
`financial_available` are always exactly the booleans passed in.

## Policy version

`RESEARCH_COVERAGE_POLICY_VERSION = "2026-08-03.11.2a.1"`, defined in
`mbe.coverage.policy` and stamped onto every `CoverageAssessment` as
`coverage_policy_version`. `CoverageLevel`/`COVERAGE_LEVEL_SECTIONS` also
carry an independent `COVERAGE_LEVEL_VERSION = "1.0"` (`coverage_level_version`
on the assessment) for the level/section taxonomy itself, tracked separately
from the assignment-rule policy version so the two can evolve independently.

## Static-vs-serverless decision

**Decision:** the 250 Level-3 pages remain static, exactly as before. The
other ~2,697 instruments in the search universe (2,947 total minus 250) are
served by the coverage-aware `api/company.py` serverless fallback, which
computes `assess_coverage()` on demand from the bundled `search-index.json`
snapshot (the `financial_available`/`research_coverage_level` fields are
precomputed into that snapshot at build time by
`mbe.search.catalog.build_search_index()`, so the serverless function never
recomputes coverage from scratch — it reads the same policy output the
static build already wrote).

**Measured, from a full offline+search+coverage-artifact build:**

| Artifact | Size |
|---|---|
| `site/` total | ~21.02 MiB (22,043,312 bytes) |
| `site/company/` (250 static Level-3 pages) | ~6.06 MiB (6,352,941 bytes) |
| `search-index.json` average record | 1,725.9 bytes (max 1,953 bytes, 2,947 records) |
| `research-coverage.json` | 764 bytes |

Level counts in the current frozen build: **Level 0: 0, Level 1: 2,697,
Level 2: 0, Level 3: 250** (total 2,947). Level 2 being empty is expected and
is real, tested architecture — see "Known limitations" below, not a bug in
this count.

**Static-equivalent cost estimate:** rendering all 2,697 non-Level-3
instruments as real static pages, at a sampled real page size of ~10,753
bytes/page, would cost approximately **~27.66 MiB** — roughly 4x the size of
the entire current `site/` output and ~4.6x the current `company/` directory
alone — for content that is mostly near-identical identity/quote boilerplate
differing only in a few fields per company (symbol, exchange, ISIN,
sector/industry if known, listing status, live quote). This is the concrete
justification for serving those companies on demand rather than statically:
the marginal content per company does not justify a committed static file at
this scale, and it grows every time the search universe grows while the
research/ranking universe does not.

**Build durations** for the three independent offline stages (small,
deterministic, offline, no network — see `mbe.builds.offline`):

| Stage | Duration |
|---|---|
| Site render (`build_site.py` / `render_site_from_manifest`) | ~2.16s |
| Search-asset build (`build_search_assets.py` / `build_search_only`) | ~1.19s |
| Coverage-artifact build (`build_coverage_artifact.py` / `build_coverage_only`) | ~0.89s |

## API contract

Two DB-backed routes in `mbe.api.app` expose coverage dynamically:

- `GET /api/v1/company/{instrument_id}/coverage` — returns a `CoverageData`
  envelope: `instrument_id`, `company_id`, `research_coverage_level`,
  `coverage_label`, `coverage_level_version`, `research_coverage_status`,
  `research_eligible`, `research_eligibility_reasons`,
  `research_sections_available`, `research_sections_missing`,
  `research_universe`, `ranking_available`, `model_available`,
  `financial_available`, `quote_available`, `identity_completeness`,
  `source_quality_summary`, `evaluated_at`, `coverage_policy_version`. 404s
  with `company_not_found` for an unknown instrument, otherwise always 200 —
  the same `_assess()` helper the summary route below uses, so both routes
  always agree for the same instrument.
- `GET /api/v1/company/{instrument_id}/summary` — `CompanySummaryData` gains
  the additive fields `research_coverage_level`, `coverage_label`,
  `research_eligible`, `research_sections_available`,
  `research_sections_missing`, `coverage_policy_version`, alongside its
  existing identity/quote/ranking fields.

Both routes are DB-backed and, like every other dynamic route in this
codebase, return the standard bounded 503 `database_not_configured` error
(`mbe.api.app`'s `get_session` dependency) when PostgreSQL isn't
provisioned — there is no special-cased error contract for coverage.

## `research-coverage.json` schema

Written by `mbe.builds.offline.build_coverage_only()`, which aggregates the
per-record coverage fields already present in `api/v1/search-index.json`
(written earlier by `build_search_only`) into one small reporting artifact.
It does not recompute `assess_coverage()` itself — only tallies what the
search build already wrote — so it can never disagree with the per-instrument
data. Fields: `schema_version`, `coverage_policy_version` (read off the first
row), `search_build_id` (sha256 of `search-index.json`), `financial_build_id`,
`model_build_ids` (list, from the frozen manifest), `instrument_count`,
`level_counts` (a `{"0": n, "1": n, "2": n, "3": n}` map), `coverage_reasons`
(a tally of every `research_eligibility_reasons` value across all records),
`generated_at` (controlled build time), and `source_hashes`
(`search_index`/`financial_build`/`model_build`).

## Search integration

`app.js`'s `researchBadgeText(level)` maps each coverage level to the badge
shown in search results: `3` → "Full Research", `2` → "Financial Coverage",
`1` → "Market Coverage", `0` → "Identity Only" (including any unmapped or
non-integer level, with a console warning). The comment above the function
in `src/mbe/frontend/assets/app.js` calls out that it must stay in sync with
`CoverageLevel`/`COVERAGE_LEVEL_LABELS` in `src/mbe/coverage/domain.py` by
hand — there is no shared codegen between the two. Ranking and match-tier
logic (`mbe.search.ranking`, `SEARCH_RANKING_POLICY_VERSION`) are unchanged
by this milestone; coverage level is exposed as data on each search result,
not folded into the ranking score or tie-break order.

## Known limitations

- **Level 2 has zero real members today.** Financial data is only computed
  for the 250 companies already in the Smallcap model universe
  (`scripts/build_financials.py` is scoped to
  `universes/nifty-smallcap250-instruments.json`) — there is no financial
  data source for any other instrument yet, and ingesting one is explicitly
  out of scope for this milestone. Concretely, `build_search_index()` derives
  `has_financial_data` from `record.research_available`
  (`mbe.search.catalog`, `assess_coverage()` call site), so today every
  instrument with financial data also has a model score and full research
  payload and therefore qualifies for Level 3 outright — nothing currently
  lands in the Level 2 band. Level 2 is fully specified, policy-tested
  (`tests/test_coverage_policy.py`) and template-tested
  (`tests/test_publish_coverage.py::test_level_2_page_shows_the_financial_summary_section`),
  but will show 0 members until a broader financial data source exists.
- **The checked-in `site/api/v1/search-index.json` in this repository
  predates this milestone's coverage-field work and does not yet carry
  `research_coverage_level`/`coverage_label`/etc.** Regenerating it requires
  running `scripts/build_search_assets.py` (and then
  `scripts/build_coverage_artifact.py`) against the frozen manifest and
  committing the output — this was deliberately **not** done as part of this
  milestone's implementation, because it touches a checked-in build artifact
  whose interaction with `builds/manifests/phase11-m1-frozen-inputs.json`'s
  pinned artifact hashes needs explicit human review before being
  regenerated in place. This has been verified safe for the score/financial
  hash gate specifically —
  `tests/test_deterministic_build.py::test_coverage_artifact_does_not_change_the_preserved_public_hashes`
  — but the broader interaction with frozen-manifest artifact validation was
  not fully characterized. **This is the single concrete pre-deploy step
  required before this milestone's coverage data is live:** run the
  search-asset and coverage-artifact build stages and commit the refreshed
  `site/api/v1/search-index.json` and `site/data/research-coverage.json`.
- **`scripts/verify_release.py` needs two small updates for a from-scratch
  3-stage rebuild** (discovered during measurement, not yet fixed):
  - Its hardcoded expected JSON file count (`EXPECTED["json"]`, currently
    509) doesn't account for the new `research-coverage.json` artifact —
    it would need to become 510.
  - Its "complete offline build" check
    (`site_manifest.build_mode != "offline"`) expects `build-manifest.json`'s
    `build_mode` field to read `"offline"`, but running
    `build_search_assets.py`/`build_coverage_artifact.py` as separate stages
    after `build_site.py` leaves it stamped `"search-only"` — the last
    stage's own label (`_site_manifest(..., "search-only")` in
    `mbe.builds.offline.build_search_only`), because each stage overwrites
    the manifest with its own mode rather than merging.

  The actual score/financial hash-preservation invariant is unaffected by
  any of this — verified independently against the real checked-in `site/`
  (which still passes `verify_release.py` cleanly as-is, since it has no
  `research-coverage.json` yet and its manifest still reads `"offline"`).
  This is a tooling/orchestration gap for the next full from-scratch
  rebuild, not a data-correctness issue.

## Milestone 2B recommendation

Two independent follow-ups, neither blocking the other:

1. Ingest a broader financial data source so Level 2 gets real members —
   the architecture (policy, schema, template, artifact) already supports
   this without further schema changes; only a new financial-data source
   feeding `has_financial_data` for non-Smallcap instruments is needed.
2. The already-gated Nifty 100 / Midcap 150 membership import described in
   `docs/HANDOVER.md`'s Phase 11 Milestone 1 entry ("Exact Milestone 2
   recommendation") — importing broader index memberships would grow the
   ranking/research universe independently of coverage-level plumbing.

This milestone's architecture supports either without further schema
changes: a wider financial source raises the Level 2 population, and a wider
research/ranking universe raises the Level 3 population, but neither changes
`assess_coverage()`'s four-level logic or the `CoverageAssessment`/
`CoverageData` shape.
