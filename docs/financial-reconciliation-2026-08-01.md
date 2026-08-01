# Financial provider reconciliation report — 2026-08-01

## Result

Phase 5 implements and fixture-verifies normalized official-versus-compatibility
comparison, conflict attribution and versioned source selection. It does not
claim a universe-wide official match rate because no canonical official
multi-year filing dataset was bulk-imported.

| Metric | Official Tier A coverage in current static build | Yahoo Tier B fallback | Both missing | Exact/rounding/material official comparisons |
|---|---:|---:|---:|---:|
| Revenue CAGR (3y) | 0/250 | 246/250 (98.4%) | 4/250 | 0 / 0 / 0; official series not imported |
| ROCE (3y average) | 0/250 | 232/250 (92.8%) | 18/250 | 0 / 0 / 0; official series not imported |

Legacy NSE history cache exists for 86/250 instruments, but those JSON files
discarded filing identity, exact attachment, basis and revision lineage. They
were not relabelled or counted as canonical official coverage.

## Fixture verification

The captured KFINTECH FY2024 consolidated audited XBRL fixture produced 15
facts with exact period/unit/basis lineage. Reconciliation tests cover exact,
absolute/relative rounding, material, period, unit and basis mismatches,
official-only, compatibility-only, both-missing, negative/near-zero-safe
differences and selected-source reasons. Revision fixtures prove cutoff-aware
latest-known and as-filed behavior.

One year cannot produce a three-year CAGR or multi-year ROCE. Synthetic domain
fixtures verify those formulas over four compatible official annual filings;
they are test inputs only and never enter `site/` or production metrics.

## Score-input migration assessment

The current static projector still calls the unchanged score-input calculator:

- Revenue CAGR: 0 differences across 246 available compatibility rows.
- ROCE: 0 differences across 232 available compatibility rows.
- Official replacement candidates in the current static build: zero.
- Hypothetical ranking changes from verified official replacements: not
  computable yet; no model build or score was altered.

Mismatch attribution codes are ready for unit, period, basis, restatement,
provider staleness, missing source, parser limitation and formula difference.
A future model migration requires sufficient Tier A history, a new model
version, preserved historical builds and a measured ranking-impact report.

## Deferred metrics

Operating margin, debt/equity and interest coverage remain non-public. The
supported fixture is insufficient to establish sector-aware denominator rules,
multi-company coverage, conflict rates or outlier behavior. No new screener
filter or score input was introduced for them.

## Phase 6 publication-gate hardening

Source-selection policy `2026-08-01.2` requires an official fact to be
publication-eligible or already published before it can displace the two
approved compatibility fallbacks. Parser success alone is insufficient. The
offline Phase 6 sample contains no eligible official derived metric, so coverage
and conflict counts above remain unchanged. See
[`phase6-coverage-conflict-report.md`](phase6-coverage-conflict-report.md).
