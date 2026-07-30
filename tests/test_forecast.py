import pandas as pd
import pytest

from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.models.forecast import MultipleAnchor, PriceForecast, ScenarioPath


def test_models_construct_with_defaults():
    anchor = MultipleAnchor(peer_pe=22.0, peer_n=6, anchor=30.0)
    assert anchor.quality_multiplier == 1.0
    assert anchor.notes == []
    assert anchor.own_pe_median is None

    path = ScenarioPath(
        name="base", probability=0.5, growth_start=0.345, growth_end=0.10,
        terminal_net_margin=0.209, exit_multiple=30.0, revenue_fy3=6742.0,
        eps_fy3=50.8, target_price=1524.0, cagr_3y=0.275,
    )
    assert path.evidence == []

    fc = PriceForecast(
        ticker="TEST.NS", base_fiscal_year=2026, price=741.9,
        anchor=anchor, scenarios=[path],
    )
    assert fc.horizon_years == 3
    assert fc.expected_target is None
    assert fc.downside_probability == 0.0
    assert fc.completeness == 0.0


def test_probability_is_bounded():
    with pytest.raises(ValueError):
        ScenarioPath(
            name="base", probability=1.5, growth_start=0.1, growth_end=0.1,
            terminal_net_margin=0.2, exit_multiple=20.0, revenue_fy3=100.0,
            eps_fy3=2.0, target_price=40.0, cagr_3y=0.1,
        )


def _prices(dates: list[str], closes: list[float]) -> PriceHistory:
    idx = pd.to_datetime(dates)
    return PriceHistory(
        df=pd.DataFrame(
            {"open": closes, "high": closes, "low": closes,
             "close": closes, "volume": [1000.0] * len(closes)},
            index=idx,
        )
    )


def test_own_pe_series_uses_only_published_earnings():
    """Indian FY2025 ends 31-Mar-2025 and becomes visible 90 days later
    (29-Jun-2025). A price on 01-Jun-2025 must still use FY2024 earnings."""
    from mbe.analysis.forecast import own_pe_series

    fin = FinancialHistory(
        data={
            "net_income": {2024: 100.0, 2025: 200.0},
            "shares_diluted": {2024: 10.0, 2025: 10.0},
        }
    )
    info = CompanyInfo(ticker="PIT.NS")
    prices = _prices(["2025-06-01", "2025-08-01"], [100.0, 100.0])

    pes = own_pe_series(prices, fin, info)
    # 01-Jun: EPS 10.0 (FY2024) -> P/E 10.0;  01-Aug: EPS 20.0 (FY2025) -> 5.0
    assert pes == pytest.approx([10.0, 5.0])


def test_own_pe_series_honours_explicit_filed_dates():
    from mbe.analysis.forecast import own_pe_series
    from datetime import date

    fin = FinancialHistory(
        data={
            "net_income": {2024: 100.0, 2025: 200.0},
            "shares_diluted": {2024: 10.0, 2025: 10.0},
        },
        filed={2025: date(2025, 5, 1)},
    )
    info = CompanyInfo(ticker="PIT.NS")
    prices = _prices(["2025-06-01"], [100.0])
    # filed 01-May beats the 90-day default, so FY2025 is already visible
    assert own_pe_series(prices, fin, info) == pytest.approx([5.0])


def test_own_pe_series_skips_loss_years_and_empty_history():
    from mbe.analysis.forecast import own_pe_series

    loss = FinancialHistory(
        data={"net_income": {2024: -50.0}, "shares_diluted": {2024: 10.0}}
    )
    info = CompanyInfo(ticker="LOSS.NS")
    assert own_pe_series(_prices(["2025-06-01"], [100.0]), loss, info) == []

    empty = FinancialHistory(data={})
    assert own_pe_series(_prices(["2025-06-01"], [100.0]), empty, info) == []


def test_percentile_of_places_value_in_distribution():
    from mbe.analysis.forecast import percentile_of

    assert percentile_of([10.0, 20.0, 30.0, 40.0], 10.0) == pytest.approx(0.25)
    assert percentile_of([10.0, 20.0, 30.0, 40.0], 40.0) == pytest.approx(1.0)
    assert percentile_of([], 10.0) is None
