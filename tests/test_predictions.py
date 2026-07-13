from datetime import date

import pytest

from mbe.models.prediction import Outcome, Prediction
from mbe.models.thesis import Assumption, InvestmentThesis
from mbe.thesis.calibration import brier_score, reliability_table
from mbe.thesis.predictions import emit_predictions, resolve_prediction


def _thesis(currently: dict[str, bool] | None = None) -> InvestmentThesis:
    cur = currently or {}
    return InvestmentThesis(
        ticker="X.NS",
        business_summary="s",
        classification="Durable Compounder",
        assumptions=[
            Assumption(statement="Sustains a high return on capital (ROCE >= 15%)",
                       historical_support=0.875, currently_true=cur.get("roce", True)),
            Assumption(statement="Grows revenue over time",
                       historical_support=0.7, currently_true=cur.get("growth", True)),
        ],
        thesis_confidence=0.7,
    )


def test_emit_predictions_from_thesis():
    preds = emit_predictions(_thesis(), as_of=date(2024, 7, 15))
    # one per assumption + one classification-stability claim
    assert len(preds) == 3
    roce = next(p for p in preds if "ROCE" in p.statement)
    assert roce.kind == "assumption_holds"
    assert roce.confidence == pytest.approx(0.875)
    assert roce.made_on == date(2024, 7, 15)
    assert roce.due_on == date(2025, 7, 15)

    cls = next(p for p in preds if p.kind == "classification_stable")
    assert "Durable Compounder" in cls.statement


def test_resolution_checks_truth_at_due_date():
    preds = emit_predictions(_thesis(), as_of=date(2024, 7, 15))
    roce = next(p for p in preds if "ROCE" in p.statement)

    # a year later the assumption no longer holds
    later = _thesis(currently={"roce": False})
    outcome = resolve_prediction(roce, later, resolved_on=date(2025, 7, 16))
    assert outcome.correct is False

    # and one where it held
    outcome2 = resolve_prediction(roce, _thesis(), resolved_on=date(2025, 7, 16))
    assert outcome2.correct is True


def test_resolution_of_classification_claim():
    preds = emit_predictions(_thesis(), as_of=date(2024, 7, 15))
    cls = next(p for p in preds if p.kind == "classification_stable")
    changed = _thesis().model_copy(update={"classification": "Steady"})
    assert resolve_prediction(cls, changed, resolved_on=date(2025, 7, 16)).correct is False
    assert resolve_prediction(cls, _thesis(), resolved_on=date(2025, 7, 16)).correct is True


def test_brier_score_hand_anchor():
    # forecasts 0.9/1, 0.9/0, 0.5/1 -> ((0.1)^2 + (0.9)^2 + (0.5)^2)/3 = 0.3566...
    pairs = [(0.9, True), (0.9, False), (0.5, True)]
    assert brier_score(pairs) == pytest.approx((0.01 + 0.81 + 0.25) / 3)


def test_reliability_table_buckets():
    pairs = [(0.85, True)] * 8 + [(0.85, False)] * 2 + [(0.55, True)] * 3 + [(0.55, False)] * 3
    table = reliability_table(pairs, bucket_size=0.2)
    hi = next(r for r in table if r["bucket"] == "0.8-1.0")
    assert hi["n"] == 10
    assert hi["stated"] == pytest.approx(0.85)
    assert hi["observed"] == pytest.approx(0.8)
    mid = next(r for r in table if r["bucket"] == "0.4-0.6")
    assert mid["observed"] == pytest.approx(0.5)


def test_ledger_roundtrip_and_due_filtering(tmp_path):
    from mbe.storage import RunStore

    store = RunStore(tmp_path / "p.duckdb")
    preds = emit_predictions(_thesis(), as_of=date(2024, 7, 15))
    store.save_predictions(preds)

    # nothing due before the horizon
    assert store.due_predictions(as_of=date(2025, 1, 1)) == []
    due = store.due_predictions(as_of=date(2025, 7, 16))
    assert len(due) == 3

    outcome = Outcome(resolved_on=date(2025, 7, 16), actual="held", correct=True)
    store.record_outcome(due[0], outcome)
    # resolved ones drop out of the due list
    assert len(store.due_predictions(as_of=date(2025, 7, 16))) == 2
    resolved = store.resolved_predictions()
    assert len(resolved) == 1
    assert resolved[0]["correct"] is True
    assert resolved[0]["confidence"] == pytest.approx(due[0].confidence)


def test_learn_and_apply_calibration_map():
    from mbe.thesis.calibration import apply_calibration, learn_calibration_map

    # 0.6-0.8 bucket observed 0.9; 0.8-1.0 observed 0.85; sparse bucket ignored
    pairs = (
        [(0.7, True)] * 9 + [(0.7, False)] * 1
        + [(0.9, True)] * 17 + [(0.9, False)] * 3
        + [(0.1, True)] * 2  # n=2 < min_n -> no correction learned here
    )
    cmap = learn_calibration_map(pairs, bucket_size=0.2, min_n=5)
    assert apply_calibration(0.7, cmap) == pytest.approx(0.9)
    assert apply_calibration(0.9, cmap) == pytest.approx(0.85)
    # bucket without enough data -> identity
    assert apply_calibration(0.1, cmap) == pytest.approx(0.1)
    # empty map -> identity
    assert apply_calibration(0.42, []) == pytest.approx(0.42)


def test_emit_predictions_with_calibration_map():
    from mbe.thesis.calibration import learn_calibration_map

    pairs = [(0.7, True)] * 9 + [(0.7, False)] * 1
    cmap = learn_calibration_map(pairs, bucket_size=0.2, min_n=5)
    thesis = _thesis()
    preds = emit_predictions(thesis, as_of=date(2024, 7, 15), calibration_map=cmap)
    growth = next(p for p in preds if "revenue" in p.statement.lower())
    assert growth.confidence == pytest.approx(0.9)   # calibrated from 0.7
    assert growth.confidence_raw == pytest.approx(0.7)  # provenance kept
