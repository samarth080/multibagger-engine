# Phase 8 release-readiness decision

Decision date: 2026-08-01

## Decision: ready with conditions for a preview; not approved for production

The generated artifact, real-Chrome journeys, responsive behavior, visual
baselines, automated accessibility, performance budgets, SEO/security contract,
dependency audits and public-value invariants are release-quality locally.

Production promotion is not approved because Firefox/WebKit journeys,
VoiceOver + Safari, and real Vercel header/function/compression behavior could
not be completed without an installed engine/runtime or a preview deployment.
Those are concrete promotion conditions, not inferred passes. Creating a
preview also requires explicit user authorization and was out of scope here.

No condition changes the Phase 6 official-NSE no-go, current Yahoo compatibility
source caveats, PostgreSQL absence or score/provider behavior.
