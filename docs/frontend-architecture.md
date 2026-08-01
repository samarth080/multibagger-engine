# Phase 2–3 frontend architecture (extended in Phase 7)

> Phase 8 release evidence: the application shell now has real system-Chrome
> journey, responsive, axe, performance and 11-state visual-regression coverage.
> Executable inline script was removed in favor of `assets/theme.js`; CSP now
> restricts scripts to self. See `phase8-browser-visual-qa.md` and
> `phase8-accessibility-audit.md`. Firefox/WebKit and VoiceOver remain preview
> promotion gates and are not claimed as passed.

Implemented: 2026-08-01

## Decision

Phase 2 progressively enhances the existing Python/Jinja static publisher with
a reusable HTML, CSS and vanilla-JavaScript application layer. It deliberately
does not introduce a client framework or a second routing/build system.

This is the least disruptive path because the public deployment is already a
fast, database-independent `site/` artifact, the ranking content benefits from
static rendering, and the next product phases can reuse the shell, data client,
filter state and table primitives without replacing the research engine.

The browser assets are source-controlled under `src/mbe/frontend/` and copied
to `site/assets/` by `render_site()`. Jinja templates provide shared landmarks,
navigation, search, status, disclaimer and metadata. JavaScript is progressive
enhancement: the initial ranking table and methodology remain useful when
scripts or dynamic APIs are unavailable.

## Routes and migration

| Route | Phase 2 behavior | Data source |
|---|---|---|
| `/` and `/index.html` | New application shell and interactive Multibagger rankings | Auto-selected v1 API or static snapshots |
| `/methodology.html` | New shell with statically rendered methodology and limitations | Build/model constants |
| `/screener.html` | Typed AND-first advanced screener, transparent presets, share state, columns, pagination and safe CSV | Auto-selected screener API or full 250-row weekly snapshot |
| `/company/<instrument_id>.html` | Canonical company page for every instrument the search universe can identify — a real static file for the 250 scored instruments, or (Phase 10A) an on-demand lightweight identity+quote page via `/api/company` for everything else | Shared research schema (static file) or `mbe.research.lightweight` (serverless fallback); see `search-architecture.md` |
| `/reports/<ticker>.html` | Full legacy compatibility rendering with canonical metadata | Same research payload as canonical route |
| `/api/analyze?ticker=…` | On-demand analysis for a raw typed ticker that matches nothing in the search index (rare since Phase 10A — most queries now resolve to a canonical `/company/` page) | Existing Vercel function |
| `/api/v1/*` | Existing typed dynamic read API | Canonical relational database when configured |
| `/api/v1/*.json` | Versioned static compatibility snapshots | Weekly static build |

Overview, Sectors and News link to working sections of the ranking page. The
Screener navigation now opens the real Phase 3 route. Calendar remains labelled
as a later-phase destination and is not presented as working.

Phase 7 completed the stock-detail migration. Search, rankings, screener and
peer links use immutable instrument-ID routes; existing report paths remain
useful compatibility renderings. See
[`company-research-architecture.md`](company-research-architecture.md).

## Data mode

The frontend has one normalized domain model and three selection modes:

- `auto` (default): probe the dynamic status/rankings routes once, use them
  when a database-backed build is available, otherwise fall back to snapshots.
- `api`: require the dynamic API and show an honest unavailable state on
  failure.
- `static`: only read `.json` snapshots.

Set `MBE_FRONTEND_DATA_MODE=auto|api|static` during the Python site build. The
value is public configuration, never a secret. Failed dynamic selection is
remembered for the browser session to avoid repeated slow failures. Data from
different build IDs is never merged. Search uses the same selection, while
quotes are fetched separately in bounded visible-row batches and cannot block
rankings.

The static instrument snapshot (`instruments.json`) contains the pinned
250-instrument research/ranking master and is unchanged. Since Phase 10A,
global search reads a separate, deliberately wider snapshot,
`search-index.json` — every NSE-listed security the platform can identify,
plus (Phase 10B) a curated BSE cross-listing starter set, each honestly
tagged with whether it is in the research/ranking universe, its BSE code
and every exchange listing. See `search-architecture.md` for why these are
different files and for the BSE sourcing disclosure. The ranking snapshot
remains the bounded published top 25.

Search also recognizes an allowlisted exchange hint (Phase 10B):
`NSE:TCS`/`BSE:500325` (prefix) or `TCS NSE`/`Reliance BSE` (trailing
suffix) — `app.js`'s `parseExchangeHint()`. An unrecognized `word:word`
shape, including anything colon-prefixed that isn't `NSE`/`BSE`, is treated
as a literal query, never as routing syntax.

Phase 3 adds `screener-fields.json` and `screener.json`. The latter contains all
250 successfully scored weekly companies, not merely the published top 25.
Static screener work remains explicitly bounded to that build. The generated
field-registry and model-build IDs must both match before filtering begins.

## Frontend boundaries

- Jinja templates: server/static rendering and semantic fallback content.
- `app.css`: design tokens and reusable shell, table, status, dialog, control,
  disclosure and responsive primitives.
- `app.js`: domain normalization, mode selection, search ranking, URL state,
  sorting/filtering/pagination, preferences, quotes and DOM presentation.
- `screener.js`: versioned screener share state, registry-driven controls,
  portable filter/sort/null semantics, presets, matched-condition explanations
  and bounded CSV export.
- `research.js`: quote enhancement, copy/comparison actions and the
  per-instrument local due-diligence checklist.
- `/api/v1` and `/api/v1/*.json`: provider-neutral contracts; presentation code
  never consumes Yahoo-shaped objects.

Canonical `instrument_id` values are the internal row/search keys. Symbols are
labels and compatibility route parameters only.

## Design system

The approved dark-professional direction remains the visual foundation:
charcoal surfaces, blue informational accent, compact research typography and
dense tables. The light palette is equally supported. System preference is
used when no override exists; an explicit theme is stored locally and applied
before paint. Green/red are reserved for directional market meaning and are
paired with signs or labels.

Tokens cover typography, type scale, spacing, radii, surfaces, borders, text,
semantic states, focus, shadows, density, breakpoints and stacking layers.
Motion is reduced when the operating system requests it.

## Accessibility and responsive model

The shell uses skip navigation and semantic header/nav/main/footer landmarks.
Search is a labelled modal with focus restoration, focus trapping, arrow-key
selection and explicit ambiguous-result handling. Mobile navigation reports
its expanded state, traps focus, closes on Escape/navigation and prevents
background scrolling.

The rankings table uses a caption, scoped headers, `aria-sort`, live result
counts and explicit row actions. Desktop keeps a dense sticky table. Tablet
uses controlled horizontal overflow. Mobile retains rank, company, score,
confidence and risk, with secondary fields in an expandable details row.

## Performance and security budgets

- No runtime framework, icon library, analytics or third-party font request.
- Initial JavaScript budget: 60 KiB uncompressed.
- Initial CSS budget: 40 KiB uncompressed.
- Route-specific screener JavaScript budget: 50 KiB uncompressed; it loads only
  on the screener route.
- Static ranking work is bounded to the published snapshot; dynamic mode uses
  server pagination capped by the API.
- Search requests are debounced and bounded; quote requests are deduplicated
  and limited to visible rows.
- All provider/API strings are inserted with `textContent`; user query values
  are parsed and validated; external links retain safe protocols and `rel`.
- Local storage contains only display preferences and recent public searches.

## Development and verification

Production needs only the existing Python build. Node tooling is development
only and checks the source asset without bundling it:

```bash
npm ci
npm run lint
npm run typecheck
npm test
uv run pytest
MBE_FRONTEND_DATA_MODE=static uv run python scripts/build_site.py
```

The normal weekly command remains valid and defaults to `auto` mode.

The complete screener registry, operator/null semantics, payload limits, field
readiness and API/static parity contract are in
[`screener-architecture.md`](screener-architecture.md).
