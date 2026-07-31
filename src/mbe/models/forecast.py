"""3-year scenario forecast models.

A forecast is three explicit paths that each move growth, margin AND the exit
multiple — not one growth knob nudged three ways, which is what made every
scenario in v0.1 tell the same story. Every assumption is carried as
report-ready evidence so a reader can disagree with a specific number instead
of the whole output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MultipleAnchor(BaseModel):
    """How the base-case exit multiple was built.

    Fully auditable by construction: a 3-year forecast is only as good as its
    exit multiple, so every input and every clamp that bound is recorded.
    """

    peer_pe: float | None = None           # leave-one-out peer median P/E
    peer_n: int = 0                        # peers that passed the sanity filter
    own_pe_median: float | None = None     # median trailing P/E over price history
    own_pe_percentile_now: float | None = None  # today's P/E within own history, 0..1
    own_pe_capped: float | None = None     # own median after the peer-relative cap
    quality_multiplier: float = 1.0
    anchor: float | None = None            # final base-case exit multiple
    notes: list[str] = []


class ScenarioPath(BaseModel):
    name: str                              # "bull" | "base" | "bear"
    probability: float = Field(ge=0, le=1)
    growth_start: float
    growth_end: float                      # revenue growth after the 3y fade
    terminal_net_margin: float
    exit_multiple: float
    revenue_fy3: float
    eps_fy3: float
    target_price: float
    cagr_3y: float
    evidence: list[str] = []


class PriceForecast(BaseModel):
    ticker: str
    horizon_years: int = 3
    base_fiscal_year: int
    price: float
    anchor: MultipleAnchor
    scenarios: list[ScenarioPath] = []     # ordered bull, base, bear
    expected_target: float | None = None
    expected_cagr_3y: float | None = None
    downside_probability: float = 0.0      # total probability of targets below price
    completeness: float = Field(ge=0, le=1, default=0.0)
