# Deployment and rollback runbook

## Pre-deployment

1. Confirm the branch and preserve the working tree; release from a reviewed,
   immutable commit only.
2. Run the commands in `pre-deployment-checklist.md` without live NSE flags.
3. Confirm the public-value hashes, migration head `20260801_0004`, 250/250
   build result and 253 sitemap URLs.
4. Review environment variables against `environment.md`; never place secrets
   in `site/` or client-side configuration.
5. Obtain explicit authorization before creating a preview or production
   deployment.

## Preview validation

Check `/`, `/screener.html`, representative complete/missing company pages,
`/reports/BLS_NS.html`, `/404.html`, static v1 JSON, quotes and dynamic status.
Confirm Chrome, Firefox and Safari journeys; VoiceOver + Safari; response CSP,
HSTS, cache headers, canonical/noindex behavior; compressed transfer sizes; and
Vercel function logs/request IDs. Do not promote if a public hash differs,
static routes fail, CSP blocks assets, or a critical/serious accessibility issue
is present.

If Deployment Protection redirects to Vercel SSO, stop application validation
and record the preview as blocked. Sign in through the existing project/team in
each required browser, or use an operator-approved temporary bypass supplied
through a secure channel. Never commit or print a bypass value, and do not
disable project protection as an automation shortcut. Protection-layer headers
do not prove that application headers or functions passed.

For this repository's Python functions, verify deployment packaging as a
separate gate: `api/quotes.py`, `api/analyze.py` and `api/v1.py` must import from
an unrelated working directory without ambient `PYTHONPATH`, and every runtime
import must be present in root `requirements.txt`. A successful static build
does not prove that an individual function can import.

## Current RC3 evidence — 2026-08-01

- Release HEAD/tag: `9de46429119ae918b5b221fa4787fe400ed1446f` /
  `v1.0.0-rc3`.
- Validated preview deployment: `7iyyZhWCQDYg4XepdSx8W1ywedum`, Ready in
  1m 28s. The protected URL remains outside public documentation.
- Authenticated build log: 39 lines; Python 3.12, uv 0.10.11, dependency
  installation, bytecode compilation and `/vercel/output` completion in 29s.
- Authenticated runtime logs: zero warning/error/fatal console events during the
  validation window; quotes 200, health 200, intended database-unavailable 503
  and missing/invalid ticker 400.
- Safari passed representative rankings, screener, methodology,
  complete/missing company, legacy, product-404 and static JSON journeys.
- Production remains blocked pending authenticated Chromium/Firefox/WebKit,
  VoiceOver, actual application headers/compression/cache, hosted accessibility/
  visual/performance and exhaustive hosted-integrity checks.
- Last-known-good production/rollback deployment remains
  `rBeoLhBW8hNZv5fX3iT64nwrvCsc`; no production alias changed.

## Production promotion

Promote the already-verified preview artifact; do not rebuild between preview
and production. Record commit, deployment URL/ID, generated model/financial
build IDs, operator, timestamp and verification result in the handover.

## Rollback

Rollback triggers include widespread 5xx, unavailable static rankings/company
routes, invalid/cross-build public data, missing security headers, broken
canonical/noindex policy, critical accessibility regression or unexpected
provider activity. Immediately promote the last known-good Vercel deployment,
then verify rankings, status, one company, one legacy route, headers and logs.
Do not delete the failed deployment or caches until evidence is retained. Data
rollback is not required for static snapshots; PostgreSQL is not provisioned.

Cache note: asset clients may retain files for up to one hour and static JSON
for five minutes. Because filenames are not content-hashed, rollback validation
must use a fresh profile/cache bypass and allow revalidation. If emergency
staleness persists, temporarily issue a no-cache header in a separately reviewed
deployment rather than mutating data in place.
