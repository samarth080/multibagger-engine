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


def test_anchor_blends_peer_and_own_with_quality_premium():
    from mbe.analysis.forecast import build_anchor

    a = build_anchor(
        peer_pes=[20.0, 22.0, 24.0], own_pes=[25.0, 30.0, 35.0],
        current_pe=25.0, franchise_score=50.0,
    )
    assert a.peer_pe == pytest.approx(22.0)
    assert a.peer_n == 3
    assert a.own_pe_median == pytest.approx(30.0)
    # 1.5 * 22 = 33 > 30, so the cap does not bind
    assert a.own_pe_capped == pytest.approx(30.0)
    assert a.quality_multiplier == pytest.approx(0.85 + 0.35 * 0.5)
    # (0.6 * 22 + 0.4 * 30) * 1.025 = 25.2 * 1.025
    assert a.anchor == pytest.approx(25.2 * 1.025)
    assert a.own_pe_percentile_now == pytest.approx(1 / 3)


def test_anchor_caps_regime_inflated_own_history_against_peers():
    """HBL's real shape: own 3y median 74x against a ~22x peer median."""
    from mbe.analysis.forecast import build_anchor

    a = build_anchor(
        peer_pes=[20.0, 22.0, 24.0], own_pes=[74.3], current_pe=25.2,
        franchise_score=91.7,
    )
    assert a.own_pe_capped == pytest.approx(1.5 * 22.0)
    assert any("capped" in n for n in a.notes)
    raw = 0.6 * 22.0 + 0.4 * 33.0
    assert a.anchor == pytest.approx(raw * (0.85 + 0.35 * 0.917))


def test_anchor_clamped_to_bounds_and_noted():
    from mbe.analysis.forecast import ANCHOR_MAX, build_anchor

    a = build_anchor(
        peer_pes=[70.0, 75.0, 78.0], own_pes=[80.0], current_pe=75.0,
        franchise_score=100.0,
    )
    assert a.anchor == pytest.approx(ANCHOR_MAX)
    assert any("clamped" in n for n in a.notes)


def test_anchor_filters_insane_peer_multiples():
    from mbe.analysis.forecast import build_anchor

    a = build_anchor(
        peer_pes=[2.0, 20.0, 22.0, 500.0], own_pes=[25.0],
        current_pe=20.0, franchise_score=50.0,
    )
    assert a.peer_n == 2          # 2.0 and 500.0 rejected
    assert a.peer_pe == pytest.approx(21.0)


def test_anchor_falls_back_to_single_source():
    from mbe.analysis.forecast import build_anchor

    peers_only = build_anchor([20.0, 22.0], [], None, 50.0)
    assert peers_only.anchor == pytest.approx(21.0 * 1.025)
    assert any("own-history" in n for n in peers_only.notes)

    own_only = build_anchor([], [28.0, 32.0], 30.0, 50.0)
    assert own_only.anchor == pytest.approx(30.0 * 1.025)
    assert any("peer" in n for n in own_only.notes)


def test_anchor_absent_when_no_multiple_source():
    from mbe.analysis.forecast import build_anchor

    a = build_anchor([], [], None, 50.0)
    assert a.anchor is None
    assert any("neither" in n for n in a.notes)
