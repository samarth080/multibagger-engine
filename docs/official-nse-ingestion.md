# Official NSE financial-result ingestion

Implemented: 2026-08-01 (Phase 5)

Phase 6 hardening is documented in
[`phase6-official-corpus-pilot.md`](phase6-official-corpus-pilot.md). Live
commands now require the exact versioned pilot manifest plus a non-expired
private operator-review record and explicitly supplied review ID; the Phase 5
environment switch alone is insufficient. No additional live request was made
in Phase 6.

## Boundary and source

The only live discovery source in this phase is NSE's public corporate
financial-results response:

`https://www.nseindia.com/api/corporates-financial-results`

Discovery is by an already resolved canonical NSE symbol, an explicit date
range, and `Annual` and/or `Quarterly` result category. The adapter stores the
announcement sequence number, issuer name/symbol/ISIN, broadcast and filing
timestamps, exact period, audited/cumulative indicators, consolidation hint,
revision hint, source URL, attachment URLs, raw row hash, and raw response hash.

The pipeline does not crawl unrelated pages, use browser automation, rotate
headers, acquire transient NSE cookies, bypass access controls, or treat an
unofficial mirror as authoritative. `MBE_NSE_INGESTION_ENABLED=false` is the
default. A production operator must review current NSE terms and data-use
conditions before enabling live or scheduled ingestion. This design is not a
claim of legal approval.

The implemented adapter completed one bounded read-only KFINTECH discovery
request and one linked XBRL request on 2026-08-01: two requests, 77,853 bytes,
16 parsed live facts and consolidated basis. No universe crawl was run. The deterministic fixture
retains public factual metadata and a minimal XBRL excerpt with the full source
document SHA-256 recorded in its comment.

## Supported format matrix

| Input | Phase 5 state | Behavior |
|---|---|---|
| NSE corporate-results JSON | Metadata only | Announcement lineage is retained; JSON rows are not treated as financial facts. |
| NSE Ind-AS result XBRL/XML | Supported | Template `nse-ind-as-results-xbrl` v1; safe XML parsing, explicit FourD/OneI contexts, unit refs, period and basis evidence. |
| CSV | Unsupported | Recorded; no NSE result CSV template is fixture-qualified. |
| XLS | Unsupported | Recorded; binary workbook parsing, macros and encryption are not executed. |
| XLSX | Unsupported | Recorded; formula-cache, hidden-sheet and external-link semantics are deferred. |
| Legacy HTML result table | Unsupported canonically | The old compatibility regex remains only in `NseFundamentals`; it is not promoted into canonical lineage. |
| Text PDF | Unsupported | Recorded; no bounded text/table template is qualified. |
| Image PDF | OCR required / unsupported | Recorded; OCR is out of scope. |
| ZIP/other | Unsupported/quarantined | No archive expansion or arbitrary member parsing occurs. |

The parser registry is centralized in `src/mbe/financials/parsers.py`. Unknown
formats and unrecognized structures produce explicit unsupported/quarantine
states; metadata-only never means facts were ingested.

## Request, cache and document safety

`SafeDocumentFetcher` enforces:

- HTTPS hosts limited to NSE and NSE archive hosts;
- a stable operator-configurable user agent;
- one synchronous request at a time, a default 0.75-second global interval,
  100-request run cap and at most two bounded exponential-backoff retries;
- no indiscriminate retry of permanent 4xx responses;
- connection/read timeout budget, three-redirect cap and final-host validation;
- 12 MB default document ceiling, declared-length and partial-read checks;
- MIME plus file-signature detection for XML/JSON/HTML/PDF/ZIP/XLS/XLSX;
- filename sanitization and checksum generation;
- immutable checksum-verified cache reuse and ETag/Last-Modified conditional
  revalidation on explicit force refresh;
- atomic cache writes; corrupt or checksum-mismatched entries are not reused;
- exact URL-plus-checksum cache invalidation only.

The cache defaults to `data/official-filings/`, is ignored by Git, and is never
copied into `site/`. Cache retention is operator-managed: immutable documents
are retained for reproducibility until the operator uses the exact invalidation
command or removes an expired data environment. Public APIs expose neither
cache paths nor raw payloads.

All documents are untrusted. No macro, formula, external workbook reference,
embedded object, HTML, archive member or downloaded code is executed. XLS/XLSX,
PDF and archive limits are documented now but their parsers remain disabled.

## Parser, period, unit and basis rules

The XBRL parser returns `ParsedOfficialFiling`, not database rows. Each fact
retains its source tag, context, Decimal source value, unit, currency, period,
basis, parser version and derived-input tags.

- `FourD` is the filing's duration context; `OneI` is the period-end instant.
- Annual filings require `ReportingQuarter=Yearly` or `Annual`.
- XML start/end dates override metadata only when they parse safely.
- Quarter/YTD semantics come from discovery metadata; quarter residuals still
  use Phase 4's compatibility checks and are not fabricated by this parser.
- The supported XBRL monetary unit is explicit INR. Per-share and share values
  use explicit unit refs. Unknown unit refs are retained as unresolved inputs,
  rejected from publication, and recorded as quality issues.
- Unit precedence is cell/context unit, then filing declaration, then no
  assumption. Magnitude never implies lakhs or crores.
- Consolidated/standalone evidence is compared between discovery metadata and
  XBRL. Agreement resolves the basis; absence remains `unknown`; disagreement
  becomes `conflicting` and rejects the canonical filing.
- EBIT, EBITDA, total debt, shares and FCF proxies preserve their exact source
  tags and are marked derived. Zero and negative values remain values.

Central aliases cover Revenue from Operations/Income, PAT, finance cost,
assets, equity, cash, current assets/liabilities, CFO, capex and dividends. A
new alias must map to a versioned Phase 4 metric definition before ingestion.

## Identity, duplicates and revisions

Announcement identity uses NSE sequence number when present. The canonical
economic identity hash includes instrument symbol, filing type, period end,
publication timestamp, basis and source filing ID; it does not use the
attachment filename alone.

- Exact metadata reruns are unchanged.
- Changed URLs with an existing attachment checksum reuse the canonical filing.
- Multiple attachments remain separate ordered records.
- Standalone and consolidated announcements remain separate.
- A later timestamp alone is not a revision.
- Only explicit revised/corrigendum/replacement evidence creates a new
  canonical revision and a `revises` relationship; the predecessor becomes
  superseded but remains queryable.
- `latest_known` chooses the newest official revision available at the supplied
  cutoff. `as_filed` returns every filing available at that cutoff. A later
  restatement cannot rewrite an older model-build view.

The attachment/source record is also the ingestion checkpoint. A successful
rerun skips parsed checksums; unsupported/quarantined records remain visible for
bounded reprocessing instead of disappearing.

## Reconciliation and source precedence

Reconciliation is per instrument, metric, exact period, unit and basis. States
are exact match, within rounding tolerance, material difference, period
mismatch, basis mismatch, unit mismatch, official only, compatibility only,
both missing and unresolved.

Tolerance policy version `2026-08-01.1`:

- ratios/per-share values: absolute 0.0001 or relative 0.5%;
- monetary values: absolute ₹1 or relative 0.1%;
- share counts: absolute one share or relative 0.1%;
- percentage difference is omitted when the official denominator is too close
  to zero for a useful interpretation.

Selection policy version `2026-08-01.1`:

1. Valid official NSE fact with resolved period, unit and consolidated or
   standalone basis.
2. Approved compatibility fallback only for Revenue CAGR (3y) and ROCE (3y).
3. Missing.

Phase 6 selection policy `2026-08-01.2` adds a review/publication gate. Parsed
but unreviewed official facts cannot replace an approved compatibility fallback.
The state sequence is parsed, validated, reviewed, eligible, selected and
published.

Conflicts remain stored even when precedence selects a value. Sources are never
blended inside a formula. Official Revenue CAGR requires positive official
annual endpoints exactly three years apart. Official ROCE requires at least two
compatible official annual EBIT/equity/debt periods with positive capital.
Consolidated is preferred; standalone is a labelled fallback.

Quality tiers:

- Tier A: official, resolved period/unit/basis, accepted quality and reproducible derivation;
- Tier B: metric-specific compatibility fallback with explicit caveat;
- Tier C: unknown/conflicting basis, weak lineage or material incompatibility; not public-filter eligible.

Operating margin, debt/equity and interest coverage remain deferred. Phase 5
does not promote them based on a single supported fixture or compatibility-only
coverage.

## Persistence and migration

Migration `20260801_0004` adds:

- `official_filing_sources` for versioned discovery metadata and hashes;
- `official_filing_attachments` for checksums, safe formats, parser/template
  versions, cache state, unsupported/quarantine state and canonical links;
- `financial_filing_relationships` for revises/replaces/supplements/restates/
  duplicate relationships;
- `financial_reconciliations` for normalized comparisons, conflicts, selected
  values and versioned reasons;
- `financial_source_selections` for build-specific selected facts/values.

Indexes cover source filing IDs, instrument/publication history, economic
identity, attachment checksum and parse state, relationship targets,
reconciliation conflicts, instrument/metric/period history and build selection.
Attachment bytes are not stored in database rows or normal API queries.

Financial build schema `1.1` adds manifest sections for official/compatibility
cutoffs, parser and policy versions, official/fallback coverage, conflicts,
unknown basis, unsupported formats and metric eligibility. Those sections live
inside existing versioned JSON manifest columns; no build column was added just
to label the phase.

## Commands

```bash
# Offline deterministic contract
uv run mbe nse-filings-discover --fixture-dir tests/fixtures/nse-official
uv run mbe nse-financials-ingest --fixture-dir tests/fixtures/nse-official --dry-run

# Live, only after terms review and explicit enablement
MBE_NSE_INGESTION_ENABLED=true uv run mbe nse-filings-discover \
  --symbols KFINTECH --date-from 2024-01-01 --date-to 2026-08-01
MBE_NSE_INGESTION_ENABLED=true uv run mbe nse-financials-ingest \
  --symbols KFINTECH --date-from 2024-01-01 --date-to 2026-08-01 \
  --max-documents 20

uv run mbe financials-reconcile reconciliation-input.json --dry-run
uv run mbe financials-coverage
uv run mbe financials-unsupported
uv run mbe financials-conflicts
uv run mbe financials-cache-invalidate URL SHA256

# Offline Phase 6 control/evidence workflow
uv run mbe official-pilot-validate
uv run mbe official-pilot-corpus-verify
uv run mbe official-pilot-evaluate --dry-run
```

Commands are bounded, emit JSON summaries and exit nonzero for material
failures. Live ingestion never runs from a page request or static build.

## Public APIs and static behavior

- `GET /api/v1/instruments/{instrument_id}/filings`
- `GET /api/v1/filings/{filing_id}`
- `GET /api/v1/instruments/{instrument_id}/financials/reconciliation`
- extended `GET /api/v1/financials/coverage`

Filters and limits are typed. Responses contain safe lineage only—no cache path,
raw metadata/body, database URL, cookies or transient request headers.

The current 250-company static dataset contains no imported canonical official
multi-year series. It therefore reports official public-metric coverage 0/250,
Revenue CAGR compatibility fallback 246/250, and ROCE compatibility fallback
232/250. This is not an ingestion failure disguised as official coverage: the
86 legacy `nse_fin_*.json` caches remain explicitly non-canonical because they
lost attachment, basis and revision lineage. Static builds perform no NSE
requests and continue to succeed offline.

The KFINTECH fixture covers one official annual consolidated audited filing,
one supported XBRL attachment and 15 parsed/accepted source or derived facts.
It proves the contract and parser, not 250-company production coverage.

## Operations and rollback

Disable ingestion by leaving `MBE_NSE_INGESTION_ENABLED=false`. Quarantined
records require operator review; do not change parser rules merely to raise
coverage. Reprocess only after a template/parser version change and retain the
old source record/checksum.

To roll back the schema, first stop writers and run `alembic downgrade
20260801_0003`; this removes only Phase 5 source/reconciliation tables and does
not rewrite Phase 4 filings/facts. Cache removal is separate and should use the
exact checksum invalidation command where practical.

Before deployment: review NSE terms, configure a truthful user agent, verify
request caps, inspect unsupported/conflict reports, test backup/restore, and
complete real desktop/tablet/mobile, light/dark, keyboard, zoom, contrast and
screen-reader QA.
