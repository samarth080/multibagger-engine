# Phase 11 Milestone 1 — deterministic offline build architecture

Status: implemented against the verified Phase 10C Milestone 2 Smallcap 250
baseline. Large-cap and mid-cap imports/modeling remain out of scope.

## Root-cause audit

Before this milestone, one invocation of `scripts/build_site.py` owned the
entire weekly lifecycle. The coupling was structural, not a cache defect.

| Previous step | Network | Computes or mutates | Generated output |
|---|---|---|---|
| `get_universe("nifty-smallcap250")` | NSE index CSV on cache miss/expiry | Could change the ranking membership before the canonical-master equality check | None directly |
| `YahooProvider.get_info/get_financials/get_prices` | Yahoo through `yfinance` on every cache miss/expiry | Supplies all model, financial and price inputs; also fetches `^NSEI` benchmark history | Cache JSON/Parquet |
| `screen()` | No direct network; calls the provider above | Recomputes features, factors, risk, confidence, scores, ranks, forecasts and sector context | In-memory `ScreenResult` |
| `build_manifest()` | No | Used a wall-clock cutoff/build time and a newly generated build ID | In-memory model manifest |
| `RunStore.save_run()` | No | Appended a new DuckDB run and score rows | `data/mbe.duckdb` |
| `company_news()` / `sector_policy()` | Google News RSS on cache miss/expiry | Changed company/policy context independently of model inputs | Cache JSON |
| `build_data()` | No | Reprojected all financial summaries; `financial_build()` used another wall clock | In-memory public/research payload |
| `render_site()` | No | Regenerated all HTML, v1 JSON, company research, search index, sitemap, robots and assets; pruned old pages | About 795 files in `site/` |
| GitHub weekly workflow | All of the above | Committed every `site/` difference and pushed it | Production deployment trigger |
| Vercel | No build command | Served the already committed `site/` directory | Static deployment plus API functions |

The important hidden dependencies were:

- rendering implicitly selected live membership and ran Yahoo analysis;
- the search index could not be regenerated without the model path;
- frontend asset copying happened only after analysis;
- DuckDB persistence was an unavoidable side effect of site generation;
- model, financial, news, freshness and HTML timestamps shared one mutable
  `built_at` flow, while `financial_build()` also called `datetime.now()`;
- ranking change fields depended on the previously generated screener file;
- `render_site()` deleted pages not present in the newly computed result.

That explains the observed roughly 790-file test-build diff: expired/live
inputs altered membership and derived values before the requested frontend or
search change reached the publisher.

## New stage boundaries

The normal site build is now `scripts/build_site.py`. It requires the checked,
hashed frozen-input manifest and runs inside a fail-closed socket/URL network
guard. It does not import a provider through its execution path, run `screen`,
write DuckDB, project financials, or rebuild search.

The explicit operations are:

```text
uv run python scripts/refresh_market_data.py --universe nifty-smallcap250 --out data/frozen/<source-id>
uv run python scripts/build_model.py --source data/frozen/<source-id> --out data/model-builds/<model-id>
uv run python scripts/build_financials.py --model data/model-builds/<model-id> --out data/financial-builds/<financial-id>
uv run python scripts/build_research_payloads.py --model data/model-builds/<model-id> --financials data/financial-builds/<financial-id> --out data/research-builds/<research-id>
uv run python scripts/build_site.py --manifest builds/manifests/phase11-m1-frozen-inputs.json
uv run python scripts/build_search_assets.py --manifest builds/manifests/phase11-m1-frozen-inputs.json
uv run python scripts/build_frontend_assets.py --manifest builds/manifests/phase11-m1-frozen-inputs.json
uv run python scripts/verify_deterministic_build.py --manifest builds/manifests/phase11-m1-frozen-inputs.json
```

`refresh_market_data.py` is the only new command that is expected to use the
network. It uses pinned membership and writes normalized provider values plus a
source manifest. `build_model.py` consumes only that artifact and persists a
hash-linked model result. `build_financials.py` consumes the model result and
writes a separate deterministic financial artifact. Those artifacts are under
ignored `data/` by default; promotion into a release is an explicit reviewed
operation.

Search-only generation consumes the pinned NSE/BSE search snapshots plus the
frozen instrument and screener payloads. It is allowed to write only
`search-index.json`, `app.js`, `app.css`, and its site-build manifest. Frontend
generation consumes frozen `data.json` and company-research payloads and writes
only HTML, sitemap/robots, frontend assets, and its site-build manifest.

## Frozen baseline and manifest contract

`builds/manifests/phase11-m1-frozen-inputs.json` pins the verified Smallcap 250
baseline with SHA-256 values for:

- membership and canonical-instrument snapshots;
- NSE and BSE search-universe snapshots;
- ranking, screener, instrument, status and search payloads;
- the complete 250-company research tree;
- the complete 250-company financial tree and coverage payload;
- the legacy `data.json` public snapshot.

The baseline is honestly marked `legacy_baseline`: its pre-Phase-11 raw Yahoo
cache was never a committed immutable acquisition artifact. The verified
derived values are frozen and reproducible for rendering, while all future
refreshes must begin with the explicit source-data command.

Every completed render writes `site/build-manifest.json` with:

- schema and deterministic site-build ID;
- controlled generated timestamp (`SOURCE_DATE_EPOCH`, otherwise the frozen
  manifest timestamp);
- search build/policy and classification policy versions;
- nullable large-cap/mid-cap build slots and the frozen Smallcap build ID;
- financial build ID, news cutoff, quote mode and universe versions;
- input and output hashes, build-configuration hash, build mode;
- `network_used: false`, status and warnings.

The manifest does not hash itself. Its ID is UUIDv5 over the canonical build
identity, so identical inputs and outputs produce the same ID.

## Network behavior

Offline commands patch socket connection entry points and `urllib` URL opening.
An attempted Yahoo, NSE, BSE, RSS or external API request fails immediately
with `OfflineNetworkError`. Tests exercise both direct denial and an attempted
network call inside rendering. The offline site build reports
`network_used=false` only after the guarded operation completes.

## Determinism and preservation gates

`verify_deterministic_build.py` creates two independent output directories,
runs the same frozen build twice, and compares a deterministic tree digest and
the public score/financial hashes. The release fixture remains the independent
preservation anchor:

- scores: `12a5ef89c55847e010a33a0b9cada7280033219cc285d1d16164a43103a2cb19`;
- financials: `3e99218116374dcf3968a08dda0bb187926178f357b07ce7cedb1a3ac7955638`.

The verifier also retains the 250 canonical company pages, 25 legacy routes,
253 indexable/sitemap URLs and all HTML/security/performance checks. The only
new static JSON is the site-build manifest.

## Operational policy and rollback

- Never run provider acquisition from a render or asset job.
- Never promote an unhashed or hash-mismatched input.
- Review membership, score, financial and canonical-ID hashes before changing
  the frozen-input manifest.
- Keep historic model/financial artifacts append-only; do not recalculate an
  old build under a new model configuration.
- Roll back by selecting the previous frozen-input manifest and running the
  offline site command. The legacy coupled function remains temporarily in
  `scripts/build_site.py` for forensic comparison only and is not a supported
  release command.

## Milestone 2 entry gate

Milestone 2 may begin only from this architecture. Import official, pinned
Nifty 100 and Nifty Midcap 150 membership into additive versioned universe
manifests; reconcile every member to the existing canonical instrument IDs;
record primary-versus-secondary memberships and history; then generate
coverage/eligibility reports. Do not calculate or publish large/mid-cap scores
until those reports pass and universe-specific model configurations are
reviewed in Milestone 3.
