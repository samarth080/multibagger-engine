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
