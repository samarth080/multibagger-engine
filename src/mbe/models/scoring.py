"""Explainable scoring models: every point earned is backed by Evidence."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    metric: str
    value: float | str | None
    benchmark: str  # human-readable threshold that produced the points
    points: float = Field(ge=0, le=100)
    weight: float = Field(ge=0, le=1)
    rationale: str


class PillarScore(BaseModel):
    name: str
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = []


class ScoreCard(BaseModel):
    ticker: str
    investment_score: float = Field(ge=0, le=100)
    multibagger_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    pillars: list[PillarScore] = []
    hard_gate_failures: list[str] = []
    verdict: str

    def pillar(self, name: str) -> PillarScore | None:
        for p in self.pillars:
            if p.name == name:
                return p
        return None
