# Phase 6 parser accuracy report — 2026-08-01

## Scope qualification

This report covers one previously captured KFINTECH FY2024 annual consolidated
reduced XBRL excerpt. No additional live discovery or download occurred because
the operator review gate was not acknowledged. Results must not be generalized
to the 12-company manifest, the Nifty Smallcap 250, or all NSE taxonomies.

## Measured sample

| Measure | Result |
|---|---:|
| Companies | 1 captured / 0 live attempted |
| Filings | 1 original annual consolidated |
| Committed corpus documents | 1 reduced excerpt |
| Corpus bytes | 2,696 |
| Parsed source/derived facts | 15 |
| Direct structured evidence records | 10 |
| Independently expected facts | 8 |
| Exact values | 8/8 (100%) |
| Within tolerance | 0/8 |
| Incorrect or missing | 0/8 |
| Period classification | 8/8 (100%) |
| Unit classification | 8/8 (100%) |
| Basis classification | 8/8 (100%) |
| Canonical mapping | 8/8 (100%) |

The eight facts are revenue, PAT, equity, total debt, finance cost, assets, CFO
and capex. Expected data is stored separately from parser output. The sample is
too small to estimate mapping precision/recall for unseen concepts; observed-
sample precision and recall are 8/8 only.

## Coverage and unsupported evidence

- Discovery metrics for the 12-company pilot are unmeasured: 0 live companies,
  filings, attachments, requests and bytes.
- Taxonomy namespace/release coverage is unmeasured. The reduced excerpt is
  labelled `supported_excerpt`, not a supported production taxonomy.
- Extension concepts encountered/accepted: 0/0; no extension is inferred.
- Revised filings, comparative contexts, alternate fiscal year ends, segment
  dimensions and typed members: unmeasured.
- EPS ground truth: unavailable in the reduced excerpt.
- Revenue CAGR and ROCE: not derivable from a one-year filing.
- Tier-A eligible facts/metrics: 0/0.

## Parser hardening verified by deterministic tests

Tests cover exact registry concepts, unknown namespaces, nil facts, duration vs
instant semantics, metadata/document basis conflicts, duplicate-equivalent and
conflicting duplicate facts, unit refs, decimals, one-time scale application,
negative/zero Decimal preservation, element-depth bounds and unsupported
formats. Unknown taxonomies and ambiguous facts fail closed.

## Accuracy conclusion

The parser is fixture-accurate for the observed reduced KFINTECH structure. It
is not yet taxonomy-qualified or representative-corpus accurate. The correct
production interpretation is **unmeasured**, not 100% universal accuracy.
