"""Sector rotation models (P2.4): group-level scores and the cross-sectional
context computed as a post-pass over a screened universe (never per-ticker)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from mbe.models.scoring import Evidence


class MemberComponents(BaseModel):
    """One member's inputs to its group's aggregates. None = not computable."""

    ret_6m: float | None = None
    ret_12m: float | None = None
    rev_accel: float | None = None    # latest YoY revenue growth minus prior YoY
    margin_delta: float | None = None  # operating-margin change (fund.margin_trend)


class SectorScore(BaseModel):
    name: str    # industry name, or "<Sector> (other)" fallback pool
    level: str   # "industry" | "sector"
    n: int
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = []
    members: list[str] = []  # tickers, best multibagger score first


class SectorContext(BaseModel):
    groups: dict[str, SectorScore] = {}
    membership: dict[str, str] = {}                # ticker -> group name
    member_data: dict[str, MemberComponents] = {}  # ticker -> components
    universe_median_ret_6m: float | None = None
    universe_median_ret_12m: float | None = None
