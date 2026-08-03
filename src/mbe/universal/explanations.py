"""Deterministic, rule-based strengths/risks for the Universal Research
Score. Unlike mbe.research.explanations (which needs a cross-sectional
median over the Nifty Smallcap ranking universe — architecturally
incompatible with "any stock"), this module only ever looks at one
company's own factor scores and evidence — same self-contained approach
mbe.thesis.engine and mbe.analysis.risk already use for a single ticker.
No LLM; every sentence is template text keyed off a scored factor."""

from __future__ import annotations

from mbe.universal.domain import UniversalScoreCard

_STRENGTH_THRESHOLD = 70.0
_RISK_THRESHOLD = 35.0
_MIN_CONFIDENCE_FOR_EVIDENCE = 0.3


def build_strengths_and_risks(card: UniversalScoreCard) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    risks: list[str] = []
    for factor in card.factors:
        if factor.name == "Data quality" or factor.score is None:
            continue
        if factor.confidence < _MIN_CONFIDENCE_FOR_EVIDENCE:
            continue
        if factor.score >= _STRENGTH_THRESHOLD:
            strengths.append(f"{factor.name} scores {factor.score:.0f}/100, above the strength threshold.")
        elif factor.score <= _RISK_THRESHOLD:
            risks.append(f"{factor.name} scores {factor.score:.0f}/100, below the risk threshold.")
    for note in card.excluded_factor_notes:
        risks.append(note)
    return strengths, risks
