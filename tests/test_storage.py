from datetime import date

from mbe.storage import RunStore
from tests.test_pipeline import StubProvider
from mbe.pipeline import screen


def _result():
    return screen(["GOOD.NS", "ALSO.NS"], StubProvider())


def test_save_run_and_history(tmp_path):
    store = RunStore(tmp_path / "test.duckdb")
    run_id = store.save_run(_result(), universe="unit-test")
    assert run_id

    rows = store.history("GOOD.NS")
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "GOOD.NS"
    assert row["universe"] == "unit-test"
    assert row["as_of"] == date.today()
    assert 0 <= row["multibagger"] <= 100
    assert 0 <= row["investment"] <= 100


def test_two_runs_two_history_rows(tmp_path):
    store = RunStore(tmp_path / "test.duckdb")
    store.save_run(_result(), universe="unit-test")
    store.save_run(_result(), universe="unit-test")
    assert len(store.history("GOOD.NS")) == 2


def test_history_empty_for_unknown_ticker(tmp_path):
    store = RunStore(tmp_path / "test.duckdb")
    store.save_run(_result(), universe="unit-test")
    assert store.history("NOPE.NS") == []


def test_save_and_list_backtests(tmp_path):
    store = RunStore(tmp_path / "test.duckdb")
    store.save_backtest(
        universe="unit-test",
        score_name="multibagger",
        horizon_days=365,
        mean_ic=0.42,
        details={"cutoffs": ["2024-07-01"], "n": 50},
    )
    rows = store.backtests()
    assert len(rows) == 1
    assert rows[0]["mean_ic"] == 0.42
    assert rows[0]["details"]["n"] == 50


def test_runs_listing_and_run_results(tmp_path):
    store = RunStore(tmp_path / "test.duckdb")
    run_id = store.save_run(_result(), universe="unit-test")
    runs = store.runs()
    assert len(runs) == 1
    assert runs[0]["run_id"] == run_id
    assert runs[0]["universe"] == "unit-test"
    assert runs[0]["n_results"] == 2

    rows = store.run_results(run_id)
    assert len(rows) == 2
    assert rows[0]["multibagger"] >= rows[1]["multibagger"]  # ranked desc
    assert {"ticker", "investment", "multibagger", "verdict"} <= set(rows[0])
