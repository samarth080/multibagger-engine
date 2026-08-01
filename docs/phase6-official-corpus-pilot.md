# Phase 6 official-corpus pilot

Status: completed as an offline hardening exercise with a **no-go** production
decision on 2026-08-01. No additional live NSE request was authorized or made.

This document is an operational design and evidence record, not legal advice or
a conclusion that any use is permitted. NSE terms and endpoint behavior can
change. An operator must review the current terms again before any live pilot or
production deployment.

## Operator review gate

Live discovery and attachment download require all of the following:

1. `MBE_NSE_INGESTION_ENABLED=true`;
2. the exact versioned pilot manifest;
3. a private, timezone-aware review record no older than 90 days;
4. the review record's ID supplied again on the live command line;
5. an exact manifest scope hash and a requested symbol/date subset within it.

The record confirms review of current access/data-use terms, cadence, caching
and retention, redistribution, attribution, and operator responsibility. The
required acknowledgement is:

> I confirm that I reviewed current NSE access and data-use terms, request cadence, cache retention, public redistribution, and attribution for this bounded pilot.

The record lives under `data/` by default and is not committed or copied into
public assets. An environment variable cannot stand in for the record. Fixture
and offline commands do not require acknowledgement. Recording acknowledgement
does not constitute legal approval.

```bash
uv run mbe official-pilot-operator-status

# Run only by the responsible operator after an actual current review.
uv run mbe official-pilot-operator-record \
  --operator-id '<local identifier>' \
  --review-id '<unique review id>' \
  --acknowledgement '<exact text above>'
```

No review record was created during Phase 6.

## Reproducible pilot selection

Manifest: `universes/phase6-official-pilot-v1.json`

- Pilot ID: `nse-official-pilot-2026-08-v1`
- Manifest version: `2026-08-01.1`
- Scope hash: `a083848a6a51d6d18a34251d94f46730356b9207f881b7cb963823d0d250e2b5`
- Selection date: 2026-08-01
- Filing date range: 2022-04-01 through 2026-03-31
- Category: annual results only
- Size: 12 companies from the 25 published company reports
- Manual-review budget: 144 priority fact decisions

The deterministic judgment sample maximizes industry, operating-model and
statement-presentation diversity and deliberately includes difficult cases. It
is not randomized and is not optimized for parser success.

| Symbol | Industry | Selection role |
|---|---|---|
| BLS | Consumer Services | Asset-light international services and subsidiaries |
| HBLENGINE | Capital Goods | Manufacturing, inventory and finance-cost structure |
| NATCOPHARM | Healthcare | Pharmaceutical exports and revenue-concept diversity |
| SARDAEN | Metals & Mining | Capital intensity, debt and sign handling |
| FORCEMOT | Automobile and Auto Components | Working-capital and fixed-asset structure |
| WELCORP | Capital Goods | Export-oriented multi-business group |
| CAMS | Financial Services | Segregated fee-based financial-services case |
| KFINTECH | Financial Services | Captured Phase 5 evidence anchor; segregated |
| NETWEB | Information Technology | Recent issuer and shorter comparative history |
| LTFOODS | Fast Moving Consumer Goods | Export consumer business and foreign operations |
| CEMPRO | Construction | Project accounting plus identity/name-transition difficulty |
| NIVABUPA | Financial Services | Segregated insurance taxonomy difficulty case |

CAMS, KFINTECH and NIVABUPA must be reported separately from general-company
acceptance rates. Insurance accounting cannot be blended into a generalized
ROCE acceptance percentage.

## Acquisition bounds and stop conditions

| Boundary | Limit |
|---|---:|
| Companies | 12 |
| Discovery pages | 12 |
| Filings per company | 4 |
| Attachments per filing | 2 |
| Documents | 48 |
| Requests | 60 |
| Per-document bytes | 12,000,000 |
| Total downloaded bytes | 120,000,000 |
| Per-host concurrency | 1 |
| Minimum request interval | 0.75 seconds |
| Retries | 2 |
| Runtime | 1,800 seconds |
| Quarantine stop rate | 25% |
| Identity anomalies | 5 |

The cache is checked first. A live command refuses symbols or dates outside the
manifest and refuses requested byte/document caps above it. It stops on the
request, total-byte, per-document or runtime ceiling; repeated 403/429 denial;
cache checksum failure; unsupported endpoint shape; repeated signature or
identity anomalies; or excessive quarantine. Access denial is not answered by
header rotation, cookie acquisition, browser automation or more aggressive
retrying.

## Corpus manifest and offline integrity

The committed test corpus manifest is
`tests/fixtures/phase6-pilot/corpus-manifest.json`. It contains only the one
previously captured KFINTECH annual consolidated result from Phase 5:

- 1 company, 1 filing, 1 reduced XML excerpt;
- 2,696 committed bytes;
- excerpt SHA-256
  `fdc0e821ca20b375dca4b8bd868755c883618681dc1fb748536c4c204b3639d2`;
- full source-document SHA-256 retained separately as
  `22a8fecb8fc2539d48637e29294cae0513ca32e34c0cc69faf3df0b69fc56bb8`;
- acquisition mode `captured_reduced_fixture`;
- live acquisition authorized `false`;
- review state `unreviewed` and redistribution state explicitly unresolved.

The manifest stores immutable source identity, URLs, timestamps, filename,
validated MIME/signature, bytes, hashes, parser/taxonomy/basis/period/revision/
quality/review states, and a safe repository-relative fixture path. It never
relies on the mutable URL alone.

```bash
uv run mbe official-pilot-corpus-verify
uv run mbe official-pilot-parse --dry-run
```

Integrity verification is offline and checks the exact path boundary, file
size and SHA-256. Parser outputs are deterministic and require no session,
cookies, remote schemas or transient headers. The production static build does
not invoke these commands.

## Taxonomy and canonical concept registry

`src/mbe/financials/xbrl_concepts.py` is the centralized mapping registry,
version `2026-08-01.1`. Each mapping declares canonical metric, directly
observed standard concept names, namespace evidence, statement category,
duration/instant semantics, expected unit, allowed consolidation basis, sign
convention, confidence and public eligibility.

Direct concepts from the captured excerpt cover revenue, PAT, finance cost,
CFO, capex, dividends, assets, equity, cash, current assets and current
liabilities. Derived EBIT, EBITDA, debt, shares and FCF continue to retain their
source concept IDs.

The reduced excerpt intentionally has no namespace. Its taxonomy state is
`supported_excerpt`, not `supported`, and therefore cannot satisfy Tier A.
Unknown namespaced taxonomies parse only far enough to be reported unsupported;
they are not public eligible. No company extension concept is accepted from
label similarity. Future extension mappings require reviewed label,
presentation/calculation hierarchy, context, period, unit and comparable-filing
evidence in a new registry version.

## Context, candidate and numeric rules

- Flow concepts require the `FourD` duration; stock concepts require the
  `OneI` instant in the captured template.
- Metadata and filing basis must agree. Conflict quarantines the filing.
- Preferred standard concepts follow registry order.
- Duplicate-equivalent concept/context/unit values collapse with evidence.
- A conflicting duplicate in the preferred concept blocks that canonical
  metric; the parser does not silently fall through to a broader alias.
- Nil facts are not values. An accepted fallback concept can still be selected
  and its reason is retained.
- Original text, Decimal normalized value, unit ref, decimals, precision and
  scale are preserved in local evidence.
- Scale is constrained to -18 through 18 and applied exactly once. Binary
  floating point is never used.
- INR, shares and INR/share are explicit. Unsupported units remain unresolved.
- Negative and zero facts remain facts; impossible or ambiguous units do not.

XML is untrusted. `defusedxml` blocks entities/external resolution. Additional
bounds are 50,000 elements, depth 64, 1,000,000 characters per text node,
10,000 contexts and 100,000 numeric facts. No remote schemas, macros, formulas,
archives, embedded objects, HTML, PDF extraction or code are executed.

## Evidence and manual review

`official-pilot-parse` generates a private local evidence artifact. Every
directly selected fact includes company, filing, period, basis, canonical
metric, original/normalized value, unit, concept, context, decimals/precision/
scale, checksum, parser/mapping version, candidate count, selection reason,
warnings, reconciliation state and review state.

`official-pilot-review-list` generates a bounded private queue with stable
review IDs, severity, category, evidence summary, next action and affected rule
version. The captured fixture currently produces 13 items: 10 fact-level
taxonomy/manual-acceptance items plus blockers for EPS ground truth, revisions
and comparative contexts.

`official-pilot-review-decide` appends an attributed decision event. A reversal
is a new event referencing the old decision; history is not edited. Decisions,
operator identifiers and notes stay under `data/` and are excluded from public
assets. Supported states are unreviewed, accepted, accepted with caveat,
rejected, needs source/taxonomy/period/unit/consolidation review, duplicate and
unsupported.

```bash
uv run mbe official-pilot-review-list --dry-run
uv run mbe official-pilot-review-decide <review-id> \
  --state needs_taxonomy_mapping --operator-id '<local identifier>' \
  --note '<private evidence note>'
```

## Ground truth, Tier A and publication

`tests/fixtures/phase6-pilot/ground-truth.json` contains eight independently
transcribed KFINTECH expectations: revenue, PAT, equity, debt, finance cost,
assets, CFO and capex. Expected values are not produced by the parser.

Results are 8/8 exact values, 8/8 period, 8/8 unit, 8/8 basis and 8/8 mapping
on this one filing. The sample size is always shown. It excludes EPS, revision,
comparative and full-taxonomy validation, so it cannot support a broad accuracy
claim.

Tier A is explicit per fact. It requires verified official identity and
checksum, supported parser and taxonomy, accepted mapping, resolved period/unit/
basis, valid normalization, no duplicate conflict, non-superseded filing,
accepted quality and accepted manual review. A derived metric additionally
requires every input fact to pass, compatible basis/periods, complete sequence
and a recorded formula version.

Source-selection policy `2026-08-01.2` adds the publication gate. An unreviewed
official value cannot replace an approved Yahoo fallback, even if it parses and
matches. States are parsed, validated, reviewed, eligible, selected and
published. Eligibility does not itself publish anything.

## Operational command map

| Operation | Command |
|---|---|
| Validate selection/bounds | `official-pilot-validate` |
| Record/check operator review | `official-pilot-operator-record`, `official-pilot-operator-status` |
| Metadata discovery | gated `nse-filings-discover` |
| Bounded acquisition/import | gated `nse-financials-ingest` |
| Verify corpus | `official-pilot-corpus-verify` |
| Parse/export evidence | `official-pilot-parse` |
| Reprocess one captured fixture | `official-pilot-parse` with exact local corpus scope |
| Rebuild mappings | update versioned registry, then rerun `official-pilot-parse` |
| Queue/filter review | `official-pilot-review-list --category ...` |
| Record/reverse decision | `official-pilot-review-decide` |
| Evaluate ground truth/Tier A | `official-pilot-evaluate` |
| Reconcile | `financials-reconcile` with explicit publication state |
| Inspect conflicts/coverage | `financials-conflicts`, `financials-coverage` |
| Build public output | `scripts/build_site.py` (always network-independent) |

Live commands remain bounded and fail nonzero. Offline/fixture commands support
dry run. A future authorized acquisition must export a new immutable corpus
manifest before its cache can be treated as reproducible pilot evidence.

## Persistence, performance and rollback

No migration was justified. Phase 6 is a single-operator local validation
workflow and versioned manifests plus append-only private decision files meet
the present traceability requirement without placing operator identity or
unreviewed evidence in production persistence. A future multi-user reviewer or
accepted publication workflow would justify normalized review/evidence tables.

Measured offline work: one 2,696-byte document, 15 parsed source/derived facts,
10 direct evidence records, 13 review items, and negligible command runtime.
These figures are not useful scaling estimates. Query-plan additions are not
applicable because no schema/query was added. Existing Phase 5 official,
reconciliation and selection indexes remain the relevant plans.

Rollback is additive: disable live ingestion, remove no public data, revert the
Phase 6 modules/manifest/docs if necessary, and retain private review/audit
files until the operator applies local retention policy. No Phase 5 table or
fact is rewritten.

## Security and pre-deployment checklist

- Re-review current terms and record acknowledgement privately.
- Confirm manifest scope/hash and identifying user agent.
- Confirm cache retention and redistribution decisions.
- Run corpus checksum verification before parsing.
- Inspect unsupported taxonomy, quarantine, identity and conflict counts.
- Ensure public scans contain no cache path, operator identity or review note.
- Verify static builds make no NSE request and retain fallback values.
- Complete real desktop/tablet/mobile, light/dark, keyboard, 200% zoom,
  contrast and screen-reader checks when a browser is available.

No deployment, PostgreSQL provisioning, commit or push is part of Phase 6.
