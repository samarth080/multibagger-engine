"""Stewardship (management & capital allocation) profile model."""

from __future__ import annotations

from pydantic import BaseModel, Field

from mbe.models.scoring import Evidence


class StewardshipProfile(BaseModel):
    history_years: int = 0
    share_cagr_full: float | None = None
    dilution_years_frac: float | None = None
    buyback_years_frac: float | None = None
    debt_ebit_gap: float | None = None  # CAGR(debt) - CAGR(EBIT); positive = warning
    coverage_stress_frac: float | None = None  # fraction of years coverage < 2
    dividend_consistency: float | None = None
    allocation_fit_label: str = ""
    stewardship_score: float = Field(ge=0, le=100, default=0.0)
    classification: str = "Unproven"
    evidence: list[Evidence] = []
    completeness: float = Field(ge=0, le=1, default=0.0)
