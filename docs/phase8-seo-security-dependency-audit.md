# Phase 8 SEO, security and dependency audit

Date: 2026-08-01

## Generated release contract

`uv run python scripts/verify_release.py --fixture tests/fixtures/phase8-public-value-hashes.json`
validates the complete static output without network access. Current result:

- 279 HTML, 507 JSON, 250 canonical company and 25 legacy files.
- 253 unique indexable titles/canonicals exactly matching 253 sitemap URLs.
- One main, h1, head title, canonical and description per page; unique IDs.
- Legacy report routes and `404.html` are `noindex`; robots excludes `/api/`
  and `/reports/` and points to the sitemap.
- No public source maps, unsafe URL protocols, inline executable scripts or
  target-blank opener leaks.
- Public score and financial hashes match the Phase 8 fixture.

A Phase 8 defect was fixed: legacy symbol reports previously received canonical
metadata but were not actually marked `noindex`, leaving duplicate indexing
possible. A generated 404 document, SVG favicon and explicit robots policy were
also added.

## Headers and deployment configuration

`vercel.json` is schema-linked and follows the current documented wildcard and
`:path*` patterns. Global headers include HSTS, nosniff, DENY framing, strict
referrer policy, Permissions Policy, COOP, cross-domain-policy denial and CSP.
Executable scripts are restricted to self; no `unsafe-eval` or inline script is
allowed. Inline styles remain permitted because deterministic history bars and
generated presentation attributes still use them; removing `style-src
'unsafe-inline'` is a future defense-in-depth item, not an unreported pass.

Static assets use a one-hour browser TTL with revalidation. Versioned static API
JSON uses a five-minute TTL with ten-minute stale-while-revalidate. Preview must
verify the actual Vercel headers because the local Python server cannot.

## Dependency and license posture

- `npm audit --audit-level=moderate`: 0 known vulnerabilities.
- `uvx pip-audit --progress-spinner off`: 0 known vulnerabilities.
- `npm ls --all`: dependency tree resolved successfully.
- Playwright, axe-core and Lighthouse are exact development-only versions and
  do not enter the Python runtime or public bundle.

The audit tools report known advisories, not a proof of supply-chain safety.
Lockfiles remain authoritative. A license review must be repeated before adding
any production dependency; Phase 8 adds only test tooling under established
permissive packages.
