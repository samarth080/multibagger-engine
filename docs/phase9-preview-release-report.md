# Phase 9 controlled-preview release report

Decision date: 2026-08-01

## Decision: preview failed — production blocked

Authenticated Safari validation reached the actual RC3 application and proved
the primary static routes, live quotes, the typed health/unavailable contracts,
the analysis error contract and Vercel runtime logging. Two release-blocking
Vercel packaging defects were found, fixed in separate tested commits, pushed
and revalidated through new immutable preview deployments.

Production promotion is still blocked because mandatory actual-response header,
compression and cache inspection, authenticated Chromium/Firefox/WebKit mobile
journeys, preview axe/Lighthouse/performance/security-hash checks and a real
VoiceOver journey remain unresolved. Build success and Safari accessibility-tree
inspection do not substitute for those gates. No production deployment or alias
change was attempted.

## Release identity

- Base branch: `main` at `dcaf069f25bc9ff023a8b65eeb4778de1e8ee88b`.
- Release branch/current branch: `release/v1.0.0-rc1`.
- Original RC1 commit: `6797a2eadf9d4fed6bbfbce6f02c9a5c7b22d89b`.
- Current RC3 commit: `9de46429119ae918b5b221fa4787fe400ed1446f`.
- Current commit message: `fix: package FastAPI for Vercel v1 routes`.
- Annotated tags: `v1.0.0-rc1`, `v1.0.0-rc2`, `v1.0.0-rc3`.
- Remote: `https://github.com/samarth080/multibagger-engine.git`.
- Remote release branch and peeled `v1.0.0-rc3` tag both resolve to the RC3
  commit. No force push or history rewrite occurred.
- Pull request: not created; GitHub CLI is unavailable and the in-app browser
  has no callable browser engine. The manual release-branch PR endpoint remains
  available through GitHub.
- Vercel team/project: `samarth080s-projects/multibagger-engine`.
- RC1 deployment: `7K7NSKs89gv9bGHNWzdMyfPeCmVt`, 1m 21s.
- RC2 deployment: `9ZYwbgXU7kt9SoaSMP2cZWYgWTdN`, 1m 26s.
- Validated RC3 deployment: `7iyyZhWCQDYg4XepdSx8W1ywedum`, Ready, 1m 28s.
- Protected preview URL: intentionally omitted from this public document.
- Model build: `1bd53d15-67c6-4b02-b830-0eb0bb1d582b`.
- Financial build: `34baaa1c-e2f6-508b-b2f0-389669739b2a`.
- Generated at: `2026-08-01T11:10:03.765519+00:00`.
- Rollback deployment: `rBeoLhBW8hNZv5fX3iT64nwrvCsc`, the unchanged
  last-known-good production deployment.

## Local verification

Original immutable RC1 verification:

- 457 Python tests, 24 frontend tests, 65 real-Chrome checks and 11 dedicated
  visual baselines passed.
- ESLint, JavaScript type checking, Python compileall, SQLite migration round
  trips, `alembic check`, 638-line PostgreSQL offline SQL, cached production
  build, JSON/HTML/CSP/route/canonical/private-leak/asset-parity checks, local
  HTTP/MIME smoke, `npm audit`, `pip-audit` and `git diff --check` passed.
- The build analyzed 250/250 companies with zero failures and no live NSE
  command. The release verifier validated 279 HTML, 507 JSON, 250 canonical
  company pages, 25 legacy report routes and 253 exact indexable URLs.

After the two preview fixes:

- `uv run pytest`: 461 passed, with one existing Starlette/httpx warning.
- `npm run check`: ESLint passed, JavaScript type checking passed and 24/24
  frontend tests passed.
- Python compileall and `git diff --check`: passed.
- The Phase 8 release verifier was rerun at RC3 HEAD and passed with 279 HTML,
  507 JSON, 250 canonical companies, 25 legacy routes, 253 indexable/sitemap
  routes and both pinned public-value hashes unchanged.
- Focused Vercel-entrypoint tests execute `api/quotes.py`, `api/analyze.py` and
  `api/v1.py` from an unrelated working directory without ambient
  `PYTHONPATH`, and assert FastAPI is packaged for Vercel.
- No generated site, scoring, provider, migration, public value or NSE-control
  file changed in either fix.

## Preview bugs and fix deployments

### RC1: source-package import failure

Authenticated access exposed repeated `/api/quotes` 500 responses. RC1 runtime
logs showed `ModuleNotFoundError: No module named 'mbe'` in `api/quotes.py`.
`api/analyze.py` already bootstrapped `src/`; `api/quotes.py` and `api/v1.py`
did not.

- Fix commit: `786e61d803f5c0e0cb15121a4eb7120626934823`.
- Commit message: `fix: bootstrap source package in Vercel functions`.
- Tag/deployment: `v1.0.0-rc2` / `9ZYwbgXU7kt9SoaSMP2cZWYgWTdN`.
- Revalidation: quotes returned 200 with a bounded Yahoo quote contract.

### RC2: missing FastAPI runtime dependency

RC2 `/api/v1/health` returned a function-invocation 500. Runtime logs showed
`ModuleNotFoundError: No module named 'fastapi'`; the Vercel root
`requirements.txt` omitted a runtime dependency present in `pyproject.toml`.

- Fix commit: `9de46429119ae918b5b221fa4787fe400ed1446f`.
- Commit message: `fix: package FastAPI for Vercel v1 routes`.
- Tag/deployment: `v1.0.0-rc3` / `7iyyZhWCQDYg4XepdSx8W1ywedum`.
- Revalidation: health returned 200 and status returned the intended 503
  database-not-configured envelope with request IDs.

## RC3 build and runtime evidence

The authenticated Vercel deployment page records Ready status, commit
`9de4642`, Preview environment and duration 1m 28s. The 39-line deploy log
records Python 3.12, uv 0.10.11, dependency installation from `uv.lock`, Python
bytecode compilation, build completion in `/vercel/output` in 29 seconds,
output deployment and a 58.63 MB build cache upload. No secret, migration, live
NSE command or build-time application error was visible.

The deployment-filtered runtime view reported zero Warning, Error or Fatal
console-level events in the selected 30-minute validation window. It recorded:

- 200 for bounded single- and 25-symbol `/api/quotes` requests.
- 200 for `/api/v1/health`, request
  `258a03938d9647e7a292394200a67351`, 3 ms function duration.
- Intended 503 for `/api/v1/status`, request
  `2c8b1e090ead46d989788a96601b9a84`, 1 ms function duration.
- Intended 400 for `/api/analyze` with a missing ticker and with a rejected
  `<bad>` ticker; the rendered error content remained escaped and product-safe.

## Hosted-preview gate results

| Gate | Result | RC3 evidence |
|---|---|---|
| Vercel build | Pass | Ready; 39-line authenticated deploy log; 1m 28s; `/vercel/output` completed |
| Root/rankings | Pass in Safari | Actual model build rendered; live closed-market quote cells populated |
| Screener | Pass in Safari | 250-company static mode; High Score/Moderate Risk created two visible conditions and 10 results |
| Methodology | Pass in Safari | Full build ID, static/live explanation, validation limits and disclaimers rendered |
| Canonical complete company | Pass in Safari | KFINTECH route, live quote, 22.5% Revenue CAGR, 27.4% ROCE, Tier-B lineage, peers/news/trust states |
| Canonical missing-data company | Pass in Safari | CANHLIFE showed unavailable Revenue CAGR/ROCE without zero imputation and explicit Tier-B limitations |
| Legacy company route | Pass in Safari | `/reports/KFINTECH_NS.html` preserved equivalent research content |
| Custom missing route | Pass at product-content level | Product 404 page rendered; authenticated HTTP status was not independently captured |
| Static search/research JSON | Pass in Safari | Instrument collection and KFINTECH typed research payload rendered as JSON |
| Quotes function | Pass | 200 and live quote payloads; 25-symbol batch visible in runtime logs |
| Typed v1 health/status | Pass | 200 degraded health and intended 503 database-not-configured envelope with request IDs |
| Analysis function | Pass | Intended 400 missing/invalid-ticker contracts recorded in runtime logs |
| Runtime logs | Pass for exercised functions | Zero warning/error/fatal events; expected 200/400/503 statuses |
| Actual application headers/CSP | Unresolved | Protection redirects are observable without auth; authenticated response headers were not exposed by the available UI |
| Compression/cache behavior | Unresolved | Authenticated transfer encoding, static cache status and revalidation could not be captured |
| Chromium preview journeys | Unresolved | In-app browser reported no available browser engine; local Phase 8 Chrome cannot be generalized to hosted RC3 |
| Firefox preview journeys | Unresolved | No authenticated callable Firefox engine |
| WebKit preview journeys | Unresolved | No authenticated callable WebKit automation engine |
| Safari desktop journey | Partial pass | Real application and semantic accessibility tree exercised; mobile layout and JavaScript-disabled states were not captured |
| VoiceOver journey | Not run | Accessibility-tree inspection is not VoiceOver speech/navigation evidence |
| Preview axe/visual QA | Unresolved | No authenticated automation engine; local RC1 evidence remains 17 axe scans and 11 visual baselines |
| Preview Lighthouse/performance | Unresolved | Speed Insights is disabled and protected auth prevented valid Lighthouse/transfer measurement |
| Hosted security/private-leak/hash scan | Unresolved | No log secret was visible, but protected output could not be retrieved for exhaustive hosted hashing/leak scans |

Unauthenticated `curl` continues to receive a Vercel Deployment Protection 302
with HSTS, frame denial, `no-store` and `noindex`. Those are protection-layer
headers and are not counted as the application-header gate.

## Data-integrity and provider state

- Public score hash:
  `12a5ef89c55847e010a33a0b9cada7280033219cc285d1d16164a43103a2cb19`.
- Public financial hash:
  `3e99218116374dcf3968a08dda0bb187926178f357b07ce7cedb1a3ac7955638`.
- Official Tier-A coverage: 0/250.
- Revenue CAGR compatibility coverage: 246/250.
- ROCE compatibility coverage: 232/250.
- Phase 6 operator state: `live_enabled: false`, `not_reviewed`.
- Live NSE requests during Phase 9/9B: zero.

These invariants passed locally on the artifact lineage and the authenticated
Safari content showed the same model/financial builds and representative public
values. Exhaustive hosted hash retrieval remains unresolved because the preview
is protected.

## Remaining blockers and exact closure path

1. Use an authenticated preview-capable Chromium, Firefox and WebKit environment
   to run the representative desktop/mobile, fallback, JavaScript-disabled,
   accessibility and visual journeys against RC3.
2. Perform a real operator VoiceOver + Safari journey over landmarks, search,
   rankings/scrollers, screener conditions, company disclosures, charts,
   checklist feedback and focus order.
3. Capture the actual authenticated application CSP/HSTS/referrer/permissions/
   frame/nosniff headers, MIME types, compression and static/dynamic cache
   behavior; do not substitute Deployment Protection headers.
4. Run authenticated preview Lighthouse/transfer/request measurements and an
   exhaustive hosted security/private-leak/public-hash scan.
5. Revalidate RC3 runtime logs after those journeys. If any release defect is
   found, use a separately tested fix commit/tag/deployment and repeat affected
   gates.
6. Request explicit production-promotion authorization only after all required
   gates pass or the user explicitly accepts a bounded unresolved condition.

## Rollback and production recommendation

Production remains unchanged. Deployment `rBeoLhBW8hNZv5fX3iT64nwrvCsc` is
still Ready and remains the last-known-good rollback target. No database
rollback is needed because PostgreSQL is not provisioned. If a future promotion
fails, promote that retained deployment and verify rankings, status, one
canonical company, one legacy route, application headers and runtime logs.

Final decision: **Preview failed — production blocked.** RC3 is materially
healthier and its exercised Safari/function paths pass, but the mandatory
cross-browser, VoiceOver, actual-header/compression/cache, preview performance,
accessibility and hosted-integrity gates are not complete. New explicit
production authorization would still be required after closure.
