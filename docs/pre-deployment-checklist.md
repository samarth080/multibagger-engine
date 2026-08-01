# Pre-deployment checklist

- [ ] `git status --short --branch` reviewed; release commit is immutable.
- [ ] No live NSE/pilot acquisition flags or private review artifacts present.
- [ ] Cached static build reports 250 analyzed and zero failures.
- [ ] `uv run pytest` passes.
- [ ] `npm run check` passes.
- [ ] `npm run test:browser:chromium` and `npm run test:visual` pass.
- [ ] Firefox and WebKit journeys pass in the preview-capable environment.
- [ ] VoiceOver + Safari manual journey is recorded.
- [ ] `uv run python scripts/verify_release.py --fixture tests/fixtures/phase8-public-value-hashes.json` passes.
- [ ] Python compileall, Alembic upgrade/check/downgrade/re-upgrade and PostgreSQL
  offline SQL generation pass at head `20260801_0004`.
- [ ] `npm audit` and `pip-audit` have no unresolved release-blocking advisory.
- [ ] Preview headers, compression, quotes, dynamic unavailable state and logs
  are verified.
- [ ] Rollback deployment ID and operator are recorded.
- [ ] Explicit user authorization exists for deployment/promotion.

## Phase 9 RC3 status — 2026-08-01

- [x] RC1, RC2 and RC3 commits/tags were pushed without rewriting history.
- [x] RC3 preview deployment `7iyyZhWCQDYg4XepdSx8W1ywedum` is Ready; build
  and runtime logs were inspected through the authenticated Vercel session.
- [x] Local post-fix verification passed: 461 Python, 24 frontend, ESLint,
  JavaScript type checking, compileall, diff check and a fresh RC3 release
  verifier run. Original RC1 Chrome, visual, migration and audit gates remain
  recorded.
- [x] Authenticated Safari reached the actual protected preview.
- [x] Representative rankings, screener, methodology, complete/missing company,
  legacy, product-404, static JSON, quotes, health/status and analysis contracts
  were exercised; runtime statuses were 200, intended 503 and intended 400.
- [x] Rollback deployment `rBeoLhBW8hNZv5fX3iT64nwrvCsc` is recorded and
  production remains unchanged.
- [ ] Actual authenticated application headers, MIME, compression and static/
  dynamic cache behavior are captured and pass.
- [ ] Authenticated Chromium, Firefox and WebKit desktop/mobile/fallback
  journeys pass against RC3.
- [ ] Real VoiceOver + Safari, hosted axe/visual and focus journeys pass.
- [ ] Preview Lighthouse/transfer/request metrics and exhaustive hosted
  security/private-leak/public-hash checks pass.
- [ ] Separate explicit production-promotion authorization is received.
