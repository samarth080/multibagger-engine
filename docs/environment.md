# Environment and runtime configuration

## Phase 7 company research operations

Phase 7 adds no environment variables. Canonical company pages inherit
`MBE_FRONTEND_DATA_MODE=auto|api|static`; model, financial, news and quote
timestamps remain independent in the public lineage panel. Offline validation
and rerendering require neither PostgreSQL nor network access:

```bash
uv run mbe company-research-validate
uv run mbe company-research-legacy-validate
uv run mbe company-research-measure
uv run mbe company-research-inspect <instrument-id>
uv run mbe company-research-build --instrument-id <instrument-id>
```

`company-research-parity` requires a configured migrated `MBE_DATABASE_URL`;
it is read-only and never provisions or migrates a database. The normal site
build reconstructs all pages from analysis objects. It does not invoke official
NSE ingestion or the private pilot.

Phase 5 keeps official ingestion disabled by default. Financial migrations and
imports use the existing `MBE_DATABASE_URL` / `MBE_MIGRATION_DATABASE_URL`.

```bash
uv run mbe db-migrate
uv run mbe financials-import path/to/filings.json --dry-run
uv run mbe financials-import path/to/filings.json
uv run mbe financials-coverage
uv run mbe nse-filings-discover --fixture-dir tests/fixtures/nse-official
uv run mbe nse-financials-ingest --fixture-dir tests/fixtures/nse-official --dry-run
```

The existing static build requires no API keys. The canonical dynamic API adds
a database credential when deployed. Data still comes from public endpoints
and Yahoo Finance through `yfinance`; these sources are not licensed exchange
feeds.

## Canonical platform variables

| Variable | Required | Default | Purpose |
|---|---:|---:|---|
| `MBE_DATABASE_URL` | For canonical DB/API data routes | None | SQLAlchemy URL. PostgreSQL in production; SQLite is local/test only. |
| `MBE_MIGRATION_DATABASE_URL` | No | `MBE_DATABASE_URL` | Optional privileged URL for explicit Alembic operations; never used automatically by requests. |
| `MBE_DATABASE_POOL_MODE` | No | `serverless` | `serverless` disables process-local pooling; `pooled` is for a long-lived service. |
| `MBE_CORS_ORIGINS` | No | Empty/same-origin | Comma-separated explicit browser origin allowlist. |
| `MBE_API_PORT` | No | `8001` | Local versioned API port. |

## Frontend variables

| Variable | Required | Default | Purpose |
|---|---:|---:|---|
| `MBE_FRONTEND_DATA_MODE` | No | `auto` | Public build setting: `auto` probes the database-backed v1 API and falls back to static snapshots, `api` requires the API, and `static` disables dynamic reads. |
| `MBE_PUBLIC_SITE_URL` | No | `https://multibagger-engine.vercel.app` | Public origin used for canonical and Open Graph metadata. No path or secret belongs here. |

The safe production default is `auto`: the current database-free deployment
selects its static snapshots after one bounded API failure and remembers that
decision for the browser session. Set `static` for deterministic local/static
previews. `api` is intended only after PostgreSQL has been migrated and a model
build has been persisted.

## Weekly build variables

| Variable | Required | Default | Purpose |
|---|---:|---:|---|
| `MBE_CACHE_TTL_HOURS` | No | `24` | TTL for company, price, statement and news cache files. CI currently sets `144`. |
| `MBE_THROTTLE_SECS` | No | `0` | Base per-ticker Yahoo delay. CI currently sets `0.8` and adds jitter. |

Values must be non-negative numbers. A larger cache TTL reduces provider load
but increases the risk of stale metadata. The generated site and each quote row
show their own timestamps; cache age is not a substitute for source freshness.

## Official NSE filing variables

| Variable | Required | Default | Purpose |
|---|---:|---:|---|
| `MBE_NSE_INGESTION_ENABLED` | For live official ingestion | `false` | Explicit kill switch. Set true only after the production operator reviews current NSE terms and data-use conditions. Fixture ingestion does not require it. |
| `MBE_NSE_REQUEST_INTERVAL_SECONDS` | No | `0.75` | Global minimum interval between official requests. Do not use it to evade access controls. |
| `MBE_NSE_FILING_CACHE_DIR` | No | `data/official-filings` | Private cache for validated attachments and metadata; never copied into `site/`. |
| `MBE_NSE_MAX_DOCUMENT_BYTES` | No | `12000000` | Per-document byte ceiling before parsing. |
| `MBE_NSE_MAX_TOTAL_BYTES` | No | `120000000` | Whole-run downloaded-byte ceiling. The Phase 6 manifest can only lower it. |
| `MBE_NSE_MAX_REQUESTS_PER_RUN` | No | `100` | Run-level request cap; CLI scope is also capped at 25 symbols and 100 documents. |
| `MBE_NSE_MAX_RUNTIME_SECONDS` | No | `1800` | Whole-run wall-clock ceiling for official retrieval. |
| `MBE_NSE_USER_AGENT` | No | Identifying research agent | Stable operator-configurable identification. Rotating/evasive headers are not supported. |

Phase 6 live commands additionally require the versioned pilot manifest, a
private dated operator-review record and its explicitly supplied review ID.
Acknowledgement is deliberately not encoded in `.env.example`. Fixture and
offline verification require no secret, environment acknowledgement or NSE
session state.

Static builds never read these variables to refresh NSE data and never perform
official network requests. Live ingestion is an explicit CLI operation only.

## Local paths

The following are paths rather than environment variables:

- `data/cache/`: JSON and Parquet provider cache.
- `data/mbe.duckdb`: local research ledger.
- `data/mbe-platform.db`: optional local canonical SQLite database.
- `data/official-filings/`: private checksum-addressed official attachment cache.
- `reports/`: generated local Markdown reports.
- `site/`: generated deployment output.

These paths are intentionally workspace-local. Do not place provider secrets in
them or in generated `site/` assets.

## Data cadence and limitations

| Data | Current cadence | Source/limitation |
|---|---|---|
| Rankings and reports | Weekly, Monday pre-open | End-of-day/statement data available to the build; not a live recommendation |
| Quotes | On page load, cached at CDN for five minutes | Yahoo metadata declares delay where available; not an official exchange feed |
| Financial statements | Provider/cache refresh during analysis | Yahoo is weekly default; typically four to five annual periods |
| Company news | Weekly build, seven-day window | Google News RSS; title-level entity matching because article bodies are unavailable |
| Policy context | Weekly build, seven-day window | Google News RSS query mapped to Indian regulators/terms; descriptive only |
| Sector themes | Manually curated | Curated date is displayed; descriptive only |
| Score history | Per local snapshot/weekly build | Local DuckDB is not a production multi-user database |

Unavailable values are not imputed. They lower model confidence or render an
explicit unavailable/stale state.

Canonical identity, migrations, imports, PostgreSQL/Vercel operations,
freshness semantics and API examples are documented in
[`platform-foundation.md`](platform-foundation.md).
The Phase 2 route migration, design system, data adapter and frontend commands
are documented in [`frontend-architecture.md`](frontend-architecture.md).
The Phase 3 screener reuses the same frontend mode and database variables; it
adds no environment variable or secret. Its contracts and limits are documented
in [`screener-architecture.md`](screener-architecture.md).
