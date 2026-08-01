# Deployment architecture

## Release shape

The deployable artifact is the generated `site/` directory plus three bounded
Python functions under `api/`. Static mode is the production-compatible default:
rankings, screener fields/data, instruments, status and all company research
payloads are generated at build time. Runtime quote enhancement may fail without
destroying the server-rendered product.

Vercel serves `site/`, applies headers from `vercel.json`, and maps typed dynamic
`/api/v1/:path*` requests to `api/v1.py`. PostgreSQL is optional and is not
provisioned. `MBE_DATABASE_URL` absence must produce a bounded 503 for dynamic
database routes, while `.json` static routes remain available.

## Build and promotion boundaries

The weekly producer is `scripts/build_site.py`. It must analyze at least 100
names and currently expects all 250 for release. Official NSE acquisition is a
separate disabled gate and is never part of this build. A release does not
change scoring, provider selection, financial Tier-A status or the Phase 6
no-go.

Promotion order is local verification → immutable commit → Vercel preview →
preview checks → explicit production promotion. This phase performed only the
local verification step. No deployment, commit or push occurred.

## Observability

Functions emit structured request logs and request IDs. `/api/v1/status.json`
is the static health/freshness surface; the dynamic status route reports
database availability. Vercel function/error logs are the current runtime
monitoring source. There is no analytics SDK, durable job monitor or paid
observability integration.
