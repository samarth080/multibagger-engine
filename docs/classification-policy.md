# Classification-source policy (Phase 10C Milestone 1)

Every sector/industry/sub-industry value shown anywhere in search results or
company pages traces to one of four documented sources, in this priority
order for filling an otherwise-unclaimed instrument:

1. Official exchange-provided classification (`exchange_master` — currently
   the curated BSE starter fixture's `Industry` column; NSE's official
   `EQUITY_L.csv`/`SME_EQUITY_L.csv` archives carry no classification
   columns at all, verified not assumed).
2. Official index-provider classification already available in the
   repository (`index_provider` — not currently populated by any source).
3. Existing research-universe classification (`research_universe` — the
   250 research-universe companies' curated `industry` values).
4. Documented stable public classification source (`documented_public` —
   not currently populated by any source).
5. Missing.

**No classification is ever inferred from a company name, ticker symbol, or
free text.** `mbe.search.classification.ClassificationRecord` has no
name/symbol field for a future change to accidentally read.

## The no-overwrite-research rule

A research-universe classification, once it exists for an instrument, is
always kept as canonical over every other source — this does not contradict
the priority order above, which governs which source wins when *nothing*
has been classified yet. Once a company has a published research page with
a curated industry label, a generic exchange-provided category label must
never silently replace it. The losing claim is still recorded (not
discarded) and the instrument is flagged `review_status: conflict` when the
two sources materially disagree, so the disagreement is visible rather than
hidden.

## Versioning

`CLASSIFICATION_POLICY_VERSION` (`src/mbe/search/classification.py`) is
stamped on every classification record and selection. Current version:
`2026-08-02.10c.1`. Bump this string whenever the priority order or
reconciliation rule changes.

## Measured coverage (as of this milestone)

Run `uv run mbe classification-coverage-report` for current numbers. As of
this milestone: industry 270/2,947 (9.16%) — 250 from `research_universe`,
20 from `exchange_master` (BSE curated fixture) with zero overlap after
reconciliation (BSE-cross-listed research companies keep their research
industry value, so there are zero conflicts in the current real fixtures);
sector 0/2,947 (0%) — genuinely no source in this repository supplies a
sector value for any of the 2,947 search-universe companies, including the
250 research-universe companies. This is measured, not assumed; the
coverage report recomputes it from the live merged index every run rather
than hard-coding a number.

By exchange: all 2,947 records currently resolve to primary exchange NSE
(0 verified BSE-only companies exist in the curated fixture — see
`docs/search-architecture.md` "BSE coverage and honesty about sourcing").
By board: 2,389 main-board / 558 SME, with all 270 industry-covered records
on the main board (SME industry coverage is 0/558, since neither current
source's classified companies happen to be SME-listed).

## Known limitations

- Sub-industry is never populated by any current source.
- "Stale" detection compares a classification's `source_date` (when
  supplied) against a 730-day threshold, but no current source supplies a
  `source_date` distinct from the build's own retrieval timestamp — so
  `stale_count` is structurally implemented but will read 0 until source
  retrieval timestamps are persisted across builds (a dynamic-mode/DB
  concern, deferred to a future milestone).
- Reconciliation operates at the whole-record level (a source's
  sector+industry+sub_industry claim is accepted or rejected together), not
  per individual field, because no current source supplies a partial
  combination that would require field-level merging. This is documented
  here so a future source with partial-field coverage doesn't silently
  produce a wrong reconciliation.
- Adding a genuinely reliable sector source (an official exchange sectoral
  classification file, or a documented public GICS/ICB mapping) is out of
  scope for this milestone — no such source was verified reachable or
  license-clear from this repository's environment. Raising sector coverage
  requires acquiring and verifying such a source first, not inferring one.
- Multi-source provenance (every `ClassificationRecord` considered, not
  just the selected one) currently lives only in the in-memory search-index
  build; it is not persisted to the database. Persisting it to
  `InstrumentRow`/a new table is deferred to the static/dynamic-parity
  milestone, where the real need can be assessed against actual
  dynamic-mode requirements.

## Use in search ranking (Phase 10C Milestone 2)

`review_status`, `classification_conflict`, and `industry` presence are
consumed as a very late search-ranking tie-break — see
`docs/search-architecture.md` "Search ranking policy version 3",
`classification_quality_rank`. A conflict never suppresses an otherwise-
correct exact identity match, and missing `sector` is never used as a
ranking signal given 0% coverage. The dynamic (DB-backed) `/api/v1/search`
path does not have this provenance available at all (see the limitation
above) and always treats classification as conflict-free there.
