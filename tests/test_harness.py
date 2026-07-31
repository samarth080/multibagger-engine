from datetime import date

import numpy as np
import pandas as pd
import pytest

from mbe.backtest.harness import (
    analyze_as_of,
    evaluate_cutoff,
    forward_return,
    render_backtest_md,
    run_backtest,
)
from mbe.models.company import PriceHistory
from tests.test_pipeline import StubProvider, _fin


def test_evaluate_cutoff_perfect_monotone():
    scores = {f"T{i}": float(i) for i in range(10)}
    fwd = {f"T{i}": i * 0.01 for i in range(10)}
    res = evaluate_cutoff(scores, fwd, quantiles=5)
    assert res["ic"] == pytest.approx(1.0)
    assert res["spread"] > 0
    assert res["n"] == 10


def test_evaluate_cutoff_reversed():
    scores = {f"T{i}": float(i) for i in range(10)}
    fwd = {f"T{i}": -i * 0.01 for i in range(10)}
    res = evaluate_cutoff(scores, fwd, quantiles=5)
    assert res["ic"] == pytest.approx(-1.0)
    assert res["spread"] < 0


def test_evaluate_cutoff_too_small_returns_no_ic():
    res = evaluate_cutoff({"A": 1.0, "B": 2.0}, {"A": 0.1, "B": 0.2})
    assert res["ic"] is None
    assert res["n"] == 2


def _linear_prices(start="2022-01-03", periods=800):
    idx = pd.bdate_range(start, periods=periods)
    closes = np.arange(100.0, 100.0 + periods)
    return PriceHistory(
        df=pd.DataFrame(
            {"open": closes, "high": closes * 1.01, "low": closes * 0.99,
             "close": closes, "volume": 1e6},
            index=idx,
        )
    )


def test_forward_return_exact():
    prices = _linear_prices()
    cutoff = date(2023, 1, 2)
    df = prices.df
    start_price = float(df[df.index <= pd.Timestamp(cutoff)]["close"].iloc[-1])
    horizon = 365
    end_ts = pd.Timestamp(cutoff) + pd.Timedelta(days=horizon)
    end_price = float(df[df.index <= end_ts]["close"].iloc[-1])
    got = forward_return(prices, cutoff, horizon)
    assert got == pytest.approx(end_price / start_price - 1)


def test_forward_return_none_when_window_incomplete():
    prices = _linear_prices(periods=300)  # ends ~2023-02
    assert forward_return(prices, date(2023, 1, 2), 365) is None


class PITStubProvider(StubProvider):
    """Stub whose price history spans 2022-2025 so cutoffs have forward windows."""

    def get_prices(self, ticker: str, years: int = 3) -> PriceHistory:
        return _linear_prices()


def test_analyze_as_of_no_leakage():
    cutoff = date(2023, 6, 30)
    bundle, full_prices = analyze_as_of("GOOD.NS", PITStubProvider(), cutoff)
    # statements: FY2023 available 2023-06-29 <= cutoff; FY2024 must be absent
    assert max(bundle.fin.years()) == 2023
    # price seen by engines is the cutoff-date price, not the latest
    cut_df = full_prices.df[full_prices.df.index <= pd.Timestamp(cutoff)]
    assert bundle.tech.price == pytest.approx(float(cut_df["close"].iloc[-1]))
    # present-day holdings data must not leak
    assert bundle.info.insider_pct is None


def test_run_backtest_structure():
    report = run_backtest(
        tickers=["A.NS", "B.NS", "C.NS", "D.NS"],
        provider=PITStubProvider(),
        cutoffs=[date(2023, 6, 30)],
        horizon_days=365,
        score_name="multibagger",
        universe_name="stub",
    )
    assert report.cutoffs[0].n == 4
    assert report.skipped == {}
    ic = report.cutoffs[0].ic
    assert ic is None or -1.0 <= ic <= 1.0
    md = render_backtest_md(report)
    assert "Information coefficient" in md or "IC" in md
    assert "point-in-time" in md.lower()


class NoFinStubProvider(PITStubProvider):
    def get_financials(self, ticker: str):
        from mbe.data.provider import ProviderError
        raise ProviderError("no statements available")


def test_momentum_backtest_survives_missing_statements():
    """Technical-only backtests must not require fundamentals: prices go back
    10 years, statements only ~5 — momentum cutoffs can predate statements."""
    report = run_backtest(
        tickers=["A.NS", "B.NS", "C.NS", "D.NS"],
        provider=NoFinStubProvider(),
        cutoffs=[date(2023, 6, 30)],
        horizon_days=365,
        score_name="momentum",
        universe_name="stub",
    )
    assert report.cutoffs[0].n == 4
    assert report.skipped == {}


def test_fundamental_backtest_still_requires_statements():
    report = run_backtest(
        tickers=["A.NS"],
        provider=NoFinStubProvider(),
        cutoffs=[date(2023, 6, 30)],
        horizon_days=365,
        score_name="multibagger",
        universe_name="stub",
    )
    assert report.cutoffs[0].n == 0
    assert len(report.skipped) == 1


def test_run_backtest_multi_scores_single_pass():
    """One analysis pass must yield reports for every requested score,
    including individual pillars."""
    from mbe.backtest.harness import run_backtest_multi

    reports = run_backtest_multi(
        tickers=["A.NS", "B.NS", "C.NS", "D.NS"],
        provider=PITStubProvider(),
        cutoffs=[date(2023, 6, 30)],
        horizon_days=365,
        score_names=["multibagger", "investment", "Quality", "Momentum"],
        universe_name="stub",
    )
    assert set(reports) == {"multibagger", "investment", "Quality", "Momentum"}
    for name, report in reports.items():
        assert report.score_name == name
        assert report.cutoffs[0].n == 4, name


def test_run_backtest_multi_returns_raw_panel_when_asked():
    from mbe.backtest.harness import run_backtest_multi

    reports = run_backtest_multi(
        tickers=["A.NS", "B.NS"],
        provider=PITStubProvider(),
        cutoffs=[date(2023, 6, 30)],
        horizon_days=365,
        score_names=["multibagger"],
        universe_name="stub",
        collect_raw=True,
    )
    panel = reports["multibagger"].raw_panel
    assert panel is not None
    day = panel["2023-06-30"]
    assert set(day) == {"A.NS", "B.NS"}
    score, fwd = day["A.NS"]
    assert 0 <= score <= 100
    assert isinstance(fwd, float)


def test_forecast_error_signs_under_and_over_estimates():
    """Signed on purpose: the failure this measures was systematic
    understatement, which a mean absolute error would have concealed."""
    from mbe.backtest.harness import forecast_error

    assert forecast_error(predicted=1500.0, realized=1500.0) == pytest.approx(0.0)
    assert forecast_error(predicted=1500.0, realized=750.0) == pytest.approx(-0.5)
    assert forecast_error(predicted=1000.0, realized=2000.0) == pytest.approx(1.0)


def test_forecast_error_none_on_missing_or_unusable_inputs():
    from mbe.backtest.harness import forecast_error

    assert forecast_error(predicted=None, realized=1500.0) is None
    assert forecast_error(predicted=1500.0, realized=None) is None
    assert forecast_error(predicted=0.0, realized=1500.0) is None
    assert forecast_error(predicted=-10.0, realized=1500.0) is None


def test_cutoff_result_carries_a_signed_mean_forecast_error():
    from mbe.backtest.harness import CutoffResult

    assert CutoffResult(
        cutoff=date(2024, 1, 1), ic=None, top_q_mean=None, bottom_q_mean=None,
        spread=None, hit_rate=None, n=0,
    ).forecast_mean_error is None


def test_analyze_as_of_carries_truncated_prices_for_the_forecast():
    """The forecast's own-P/E history reads bundle.prices. If analyze_as_of
    leaves it None the whole forecast silently vanishes from the backtest, and
    if it passes the *untruncated* series the P/E history looks ahead. It must
    be the cutoff-truncated one."""
    from mbe.backtest.harness import analyze_as_of

    cutoff = date(2024, 1, 2)
    bundle, full_prices = analyze_as_of("GOOD.NS", StubProvider(), cutoff)
    assert bundle.prices is not None, "forecast has no price history to anchor on"
    assert bundle.prices.df.index.max().date() <= cutoff
    assert len(bundle.prices.df) < len(full_prices.df), "prices were not truncated"
