# Phase 9 controlled-release report

Decision date: 2026-08-01

## Decision: production live by explicit risk acceptance

RC1 through RC3 found and fixed two Vercel packaging defects. RC3 then passed
the authenticated Safari and function checks that were available, while hosted
cross-browser automation, real VoiceOver, and hosted axe/Lighthouse remained
unresolved. That state was reported as production-blocking.

The user subsequently gave explicit production-promotion authorization with
those bounded unresolved conditions disclosed. A documentation-only RC4 was
pushed and verified, then Vercel promoted the RC4 source commit by creating a
new Production-environment build. Production is live at
`https://multibagger-engine.vercel.app/`.

This is not a claim that the unresolved browser, assistive-technology, or
performance gates passed. It records an authorized release with accepted
conditions and a retained, verified rollback target.

## Release identity

- Base branch: `main` at `dcaf069f25bc9ff023a8b65eeb4778de1e8ee88b`.
- Release branch: `release/v1.0.0-rc1`.
- RC1: `6797a2eadf9d4fed6bbfbce6f02c9a5c7b22d89b`, tag `v1.0.0-rc1`.
- RC2: `786e61d803f5c0e0cb15121a4eb7120626934823`, tag `v1.0.0-rc2`.
- RC3: `9de46429119ae918b5b221fa4787fe400ed1446f`, tag `v1.0.0-rc3`.
- Production source commit: `6fb5a7ea26c2ce996e17e298aae4c41c0965605d`,
  message `docs: record RC3 preview validation`, tags `v1.0.0-rc4` and final
  `v1.0.0`.
- Remote: `https://github.com/samarth080/multibagger-engine.git`.
- Remote release branch and peeled RC4/final tags resolve to the production
  source commit. No force push or history rewrite occurred.
- Vercel project: `samarth080s-projects/multibagger-engine`.
- RC4 preview: `1nxtgBJQxq5Ty5VBbBH6MJMU7pxp`, Ready in 1m 27s.
- Production deployment: `EvCEEd2g9fkRVShmvAdwQeCdoZja`, Ready in 1m 26s,
  created 2026-08-01 at 18:22:08 IST.
- Immutable production URL:
  `https://multibagger-engine-72n576ihq-samarth080s-projects.vercel.app/`.
- Production domain: `https://multibagger-engine.vercel.app/`.
- Model build: `1bd53d15-67c6-4b02-b830-0eb0bb1d582b`.
- Financial build: `34baaa1c-e2f6-508b-b2f0-389669739b2a`.
- Generated at: `2026-08-01T11:10:03.765519+00:00`.
- Retained rollback deployment: `rBeoLhBW8hNZv5fX3iT64nwrvCsc`, Ready.

## Verification inherited from the immutable product artifact

- 461 Python tests and 24 frontend tests passed after the preview fixes.
- ESLint, JavaScript type checking, Python compileall and `git diff --check`
  passed.
- Original RC1 evidence remains 65 real-Chrome checks and 11 visual baselines.
- The release verifier passed 279 HTML files, 507 JSON files, 250 canonical
  companies, 25 legacy routes and 253 exact indexable/sitemap routes.
- Public score hash:
  `12a5ef89c55847e010a33a0b9cada7280033219cc285d1d16164a43103a2cb19`.
- Public financial hash:
  `3e99218116374dcf3968a08dda0bb187926178f357b07ce7cedb1a3ac7955638`.
- The cached build analyzed 250/250 companies with zero failures.
- Official Tier-A coverage remains 0/250; Revenue CAGR fallback coverage is
  246/250 and ROCE fallback coverage is 232/250.
- Phase 6 remains `live_enabled: false`; the release made zero live NSE
  requests and did not change scoring, provider, migration, or generated data.

## Preview defects and fixes

RC1 quote requests failed with `ModuleNotFoundError: No module named 'mbe'`.
RC2 added explicit `src` bootstraps and regression tests. RC2 then exposed a
missing FastAPI Vercel dependency on `/api/v1/health`; RC3 aligned root
`requirements.txt` with the serverless imports and added packaging coverage.
RC3 restored quotes and typed v1 routes.

The RC3 authenticated Safari journey passed rankings, screener, methodology,
complete/missing company pages, a legacy report, the product 404, static JSON,
quotes, degraded health, intended database-unavailable status and safe analysis
error contracts. Its runtime logs showed expected 200/400/503 results and zero
warning/error/fatal console events.

RC4 changed only release documentation. Its preview loaded the real application
with model build `1bd53d15`; `/api/v1/health` returned the expected degraded 200
envelope with a request ID, and its runtime window remained clean.

## Production verification

Vercel's promotion dialog explicitly stated that promotion would create a new
deployment using the Production environment. Therefore production deployment
`EvCEEd2g9fkRVShmvAdwQeCdoZja` is a rebuild from the verified RC4 source commit,
not a byte-for-byte alias promotion of preview deployment
`1nxtgBJQxq5Ty5VBbBH6MJMU7pxp`. This platform behavior is recorded rather than
described as immutable preview promotion.

Safari loaded the public production domain and rendered the actual rankings
application, model build `1bd53d15`, and live quote cells. Public HTTP probes
passed:

| Route | Result |
|---|---|
| `/` | 200 HTML |
| `/screener.html` | 200 HTML |
| `/methodology.html` | 200 HTML |
| Representative canonical company | 200 HTML |
| `/reports/KFINTECH_NS.html` | 200 HTML |
| `/api/v1/instruments.json` | 200 JSON |
| Representative `/api/v1/research/...json` | 200 JSON |
| `/api/v1/health` GET | 200 degraded JSON with request ID |
| `/api/v1/status` GET | Intended 503 database-not-configured JSON |
| `/phase9-production-missing-route` | 404 product HTML |
| `/api/quotes?symbols=KFINTECH.NS` | 200 JSON |

The accidental diagnostic `HEAD /api/v1/health` returned the designed 405 with
`Allow: GET`; the required GET passed.

Production responses proved gzip compression and the configured policies:

- HTML: `public, max-age=0, must-revalidate`.
- CSS: `public, max-age=3600, must-revalidate`.
- Static JSON: `public, max-age=300, stale-while-revalidate=600`.
- Health: `public, max-age=60`; status: `no-store`.
- CSP, HSTS, `nosniff`, frame denial, COOP, referrer and permissions policies
  were present on application responses.
- Root, CSS and static JSON produced Vercel cache hits; dynamic status and quote
  probes were misses as expected for the exercised requests.

Representative local-to-production SHA-256 comparisons were exact for
`index.html`, `assets/app.css`, `api/v1/instruments.json`, KFINTECH research
JSON, the canonical KFINTECH page and its legacy report page. This closes the
representative hosted artifact-integrity condition; it is not an exhaustive
hash of all 786 generated files.

The production-deployment runtime view showed zero Warning, Error or Fatal
events in the selected validation window. It recorded quote 200s, health 200
and intended status 503 responses. The retained rollback deployment
`rBeoLhBW8hNZv5fX3iT64nwrvCsc` was separately reopened and remained Ready.

## Accepted unresolved conditions

- No authenticated hosted Chromium, Firefox or WebKit desktop/mobile/fallback
  automation was completed against RC4/production. Local Chrome evidence is
  valid only for the local immutable product artifact.
- No real VoiceOver speech/navigation journey was completed.
- Hosted axe/visual automation and hosted Lighthouse/transfer performance
  budgets were not completed; Vercel Speed Insights remains disabled.
- Hosted integrity validation is representative rather than exhaustive.

These are post-release closure items, not hidden passes. Any material defect
found while closing them triggers the rollback procedure.

## Rollback

The last-known-good deployment `rBeoLhBW8hNZv5fX3iT64nwrvCsc` is Ready. If
production develops widespread 5xx, broken rankings/company routes, invalid
public data, missing security headers, a critical accessibility defect, or
unexpected provider activity, promote that retained deployment and verify the
root, status, canonical company, legacy route, headers and runtime logs. No
database rollback is required because PostgreSQL is not provisioned.

Final decision: **Production live by explicit user authorization with bounded
cross-browser, VoiceOver, hosted accessibility/performance and exhaustive
integrity conditions accepted for post-release closure.**
