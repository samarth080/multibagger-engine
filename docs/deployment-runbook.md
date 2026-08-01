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
