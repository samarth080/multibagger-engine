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

## Current production evidence — 2026-08-01

- Production source commit/tags: `6fb5a7ea26c2ce996e17e298aae4c41c0965605d` /
  `v1.0.0-rc4` and `v1.0.0`.
- Validated RC4 preview: `1nxtgBJQxq5Ty5VBbBH6MJMU7pxp`, Ready in 1m 27s.
- Production deployment: `EvCEEd2g9fkRVShmvAdwQeCdoZja`, Ready in 1m 26s.
- Live domain: `https://multibagger-engine.vercel.app/`.
- Safari loaded the real production rankings, model build `1bd53d15`, and live
  quote cells.
- Production HTTP checks passed the root, screener, methodology, canonical and
  legacy company routes, static JSON, quote and health contracts, intended
  status 503, and product 404.
- Actual application CSP/HSTS/referrer/permissions/frame/nosniff headers, gzip,
  MIME and HTML/CSS/static-JSON/dynamic cache policies passed.
- Representative local/production SHA-256 parity passed for root, CSS,
  instruments, KFINTECH research and canonical/legacy company HTML.
- Production runtime logs showed expected quote 200, health 200 and intended
  status 503 with zero warning/error/fatal events.
- Authenticated hosted Chromium/Firefox/WebKit, real VoiceOver, hosted axe/
  Lighthouse and exhaustive hosted hashing remain explicitly accepted
  post-release conditions.
- Last-known-good rollback deployment `rBeoLhBW8hNZv5fX3iT64nwrvCsc` was
  separately rechecked and remains Ready.

## Production promotion

Prefer promoting the already-verified preview artifact without rebuilding. If
the platform explicitly rebuilds with the Production environment, record that
behavior, verify the new immutable production deployment independently, and
compare representative production assets with the verified source artifact.
Record commit/tag, deployment URL/ID, generated model/financial build IDs,
operator authorization, timestamp and verification result in the handover.

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
