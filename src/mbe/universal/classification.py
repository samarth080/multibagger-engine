"""Deterministic company-type classification for the Universal Research
Score's company-type-aware scoring policy (mbe.universal.policy).

No cleaner company-type taxonomy exists anywhere in this repository (see
2026-08-04 audit): mbe.search.classification is source-provenance
reconciliation for raw sector/industry strings, not a type taxonomy, and
mbe.scoring.sector_themes explicitly keys off the same raw Yahoo strings
for descriptive-only theme matching. This module is a small, explicit
keyword table — not a fuzzy classifier — so every classification decision
is auditable. Real limitation, disclosed rather than hidden: Yahoo's
industry taxonomy is the only signal available; a company with an
unusual or missing industry string may be classified conservatively as
other_financial or unknown_limited_data rather than guessed precisely.
"""

from __future__ import annotations

from mbe.universal.domain import CompanyType

_BANK_KEYWORDS = ("bank",)
_INSURANCE_KEYWORDS = ("insurance",)
_NBFC_KEYWORDS = ("credit services",)
_ASSET_MANAGEMENT_KEYWORDS = ("asset management",)


def classify_company_type(sector: str | None, industry: str | None) -> CompanyType:
    sector_l = (sector or "").strip().lower()
    industry_l = (industry or "").strip().lower()

    if not sector_l and not industry_l:
        return CompanyType.UNKNOWN_LIMITED_DATA
    if sector_l != "financial services":
        return CompanyType.GENERAL_CORPORATE
    if any(keyword in industry_l for keyword in _BANK_KEYWORDS):
        return CompanyType.BANK
    if any(keyword in industry_l for keyword in _INSURANCE_KEYWORDS):
        return CompanyType.INSURANCE
    if any(keyword in industry_l for keyword in _NBFC_KEYWORDS):
        return CompanyType.NBFC
    if any(keyword in industry_l for keyword in _ASSET_MANAGEMENT_KEYWORDS):
        return CompanyType.ASSET_MANAGEMENT
    return CompanyType.OTHER_FINANCIAL
