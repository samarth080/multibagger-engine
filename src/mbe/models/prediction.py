"""Prediction ledger models: every checkable claim, recorded and accountable."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Prediction(BaseModel):
    ticker: str
    made_on: date
    due_on: date
    kind: str  # assumption_holds | classification_stable
    statement: str
    confidence: float = Field(ge=0, le=1)
    source: str = "thesis"  # which module staked the claim


class Outcome(BaseModel):
    resolved_on: date
    actual: str
    correct: bool
