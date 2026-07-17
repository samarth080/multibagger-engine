"""Curated sector/industry theme tags — DESCRIPTIVE ONLY, never scored.

Data, not code (same pattern as benchmarks.py). Curator judgment, refreshed
manually; every rendering must print CURATED_AS_OF so staleness is visible.
Industry keys take precedence over sector keys. Two-sided industries carry
both directions, honestly. These tags become a scored input only if a future
increment validates them on their own — until then they are narrative context.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

CURATED_AS_OF = date(2026, 7, 17)

KNOWN_YAHOO_SECTORS = frozenset({
    "Technology", "Financial Services", "Healthcare", "Consumer Cyclical",
    "Consumer Defensive", "Industrials", "Basic Materials", "Energy",
    "Utilities", "Communication Services", "Real Estate",
})


class SectorTheme(BaseModel):
    theme: str
    direction: Literal["tailwind", "headwind"]
    reason: str


def _t(theme: str, reason: str) -> SectorTheme:
    return SectorTheme(theme=theme, direction="tailwind", reason=reason)


def _h(theme: str, reason: str) -> SectorTheme:
    return SectorTheme(theme=theme, direction="headwind", reason=reason)


# key: exact Yahoo industry string (specific) or sector string (broad)
THEMES: dict[str, list[SectorTheme]] = {
    "Semiconductors": [
        _t("AI infrastructure capex supercycle",
           "Datacenter accelerator, memory and networking demand pulls the whole supply chain"),
        _t("India Semiconductor Mission fab/OSAT incentives",
           "Capital subsidies for fabs and packaging plants seed a domestic ecosystem"),
    ],
    "Semiconductor Equipment & Materials": [
        _t("AI capex supercycle spillover",
           "Fab equipment and materials ride the same buildout one step upstream"),
    ],
    "Information Technology Services": [
        _h("GenAI automation pressure on headcount-linked revenue",
           "Code and BPO automation compresses billable-hours economics"),
        _t("GenAI integration-services demand",
           "Enterprises pay integrators to deploy AI into legacy estates"),
    ],
    "Software - Infrastructure": [
        _t("AI/data-platform spend",
           "Model serving, data pipelines and security are budget-protected line items"),
    ],
    "Aerospace & Defense": [
        _t("Defence indigenization and export push",
           "Procurement preference for domestic platforms plus rising export approvals"),
    ],
    "Electrical Equipment & Parts": [
        _t("Grid capex and energy-transition buildout",
           "Transmission, transformers and switchgear are the bottleneck of electrification"),
    ],
    "Solar": [
        _t("PLI and rooftop-solar programs",
           "Module/cell PLI allocations and subsidized rooftop demand"),
        _h("Module price cyclicality",
           "Global oversupply episodes crush realizations regardless of volume"),
    ],
    "Auto Parts": [
        _t("EV transition re-tooling opportunity",
           "New EV platforms re-open component slots incumbents had locked up"),
        _h("ICE-content obsolescence risk",
           "Engine/exhaust-linked content shrinks as the fleet electrifies"),
    ],
    "Drug Manufacturers - Specialty & Generic": [
        _t("CDMO/China+1 supply-chain shift",
           "Global pharma re-sources manufacturing away from single-country risk"),
    ],
    "Electronic Components": [
        _t("Electronics-manufacturing PLI / China+1",
           "Assembly incentives pull component ecosystems onshore"),
    ],
    "Capital Markets": [
        _t("Financialization of household savings",
           "Structural shift of savings into demat, funds and exchanges"),
    ],
    "Utilities": [
        _t("Renewables transition capex",
           "Generation mix shift funds a multi-year buildout pipeline"),
    ],
}


def themes_for(sector: str | None, industry: str | None) -> list[SectorTheme]:
    if industry and industry in THEMES:
        return THEMES[industry]
    if sector and sector in THEMES:
        return THEMES[sector]
    return []
