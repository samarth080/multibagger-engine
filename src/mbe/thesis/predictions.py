"""Emission and resolution of thesis predictions.

Each falsifiable assumption becomes a 1-year prediction whose confidence is
the assumption's historical support — the thesis now has skin in the game.
Return/price forecasts are deliberately not emitted: no return edge has been
validated, and the ledger must not launder unvalidated claims into forecasts.
"""

from __future__ import annotations

from datetime import date, timedelta

from mbe.models.prediction import Outcome, Prediction
from mbe.models.thesis import InvestmentThesis

HORIZON_DAYS = 365
CLASSIFICATION_CONFIDENCE = 0.7  # prior; will be replaced by measured base rate


def emit_predictions(thesis: InvestmentThesis, as_of: date) -> list[Prediction]:
    due = as_of + timedelta(days=HORIZON_DAYS)
    preds = [
        Prediction(
            ticker=thesis.ticker,
            made_on=as_of,
            due_on=due,
            kind="assumption_holds",
            statement=a.statement,
            confidence=a.historical_support,
        )
        for a in thesis.assumptions
    ]
    preds.append(
        Prediction(
            ticker=thesis.ticker,
            made_on=as_of,
            due_on=due,
            kind="classification_stable",
            statement=f"Still classified '{thesis.classification}'",
            confidence=CLASSIFICATION_CONFIDENCE,
        )
    )
    return preds


def resolve_prediction(
    prediction: Prediction, thesis_now: InvestmentThesis, resolved_on: date
) -> Outcome:
    """Check the claim against a thesis built from data as of the due date."""
    if prediction.kind == "assumption_holds":
        match = next(
            (a for a in thesis_now.assumptions if a.statement == prediction.statement),
            None,
        )
        if match is None:
            return Outcome(
                resolved_on=resolved_on, actual="no longer measurable", correct=False
            )
        return Outcome(
            resolved_on=resolved_on,
            actual="held" if match.currently_true else "broke",
            correct=match.currently_true,
        )
    if prediction.kind == "classification_stable":
        expected = prediction.statement.split("'")[1]
        actual = thesis_now.classification
        return Outcome(
            resolved_on=resolved_on, actual=actual, correct=(actual == expected)
        )
    raise ValueError(f"unknown prediction kind {prediction.kind!r}")
