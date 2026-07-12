"""Living investment thesis: falsifiable assumptions, self-critique, verdict."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Assumption(BaseModel):
    statement: str
    historical_support: float = Field(ge=0, le=1)  # probability from track record
    currently_true: bool


class InvestmentThesis(BaseModel):
    ticker: str
    business_summary: str
    classification: str
    bull_pillars: list[str] = []
    assumptions: list[Assumption] = []
    falsifiers: list[str] = []
    trajectory_bull: str = ""
    trajectory_base: str = ""
    trajectory_bear: str = ""
    thesis_confidence: float = Field(ge=0, le=1, default=0.0)


class Critique(BaseModel):
    disconfirmers: list[str] = []
    veto: bool = False
    recommendation: str = ""


class ThesisDiff(BaseModel):
    """Change detection between two snapshots of a living thesis."""

    ticker: str
    changes: list[str] = []
    confidence_delta: float = 0.0
