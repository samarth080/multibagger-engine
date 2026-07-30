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


def test_fade_is_linear_and_inclusive():
    from mbe.analysis.forecast import fade

    assert fade(0.30, 0.10, 3) == pytest.approx([0.30, 0.20, 0.10])
    assert fade(0.10, 0.10, 3) == pytest.approx([0.10, 0.10, 0.10])


def test_growth_paths_ordered_and_driven_by_revenue_cagr():
    from mbe.analysis.forecast import growth_paths

    paths = growth_paths(g0=0.345, g_term=0.10, spiked=False)
    assert paths["base"] == (pytest.approx(0.345), pytest.approx(0.10))
    # bull holds growth up: it fades only to 70% of the start
    assert paths["bull"][1] == pytest.approx(0.345 * 0.7)
    # bear starts at 40% of delivered growth and ends at half the terminal rate
    assert paths["bear"] == (pytest.approx(0.345 * 0.4), pytest.approx(0.05))
    assert paths["bear"][0] < paths["base"][0] <= paths["bull"][0]


def test_spiked_earnings_produce_a_harsher_bear_start():
    from mbe.analysis.forecast import growth_paths

    normal = growth_paths(g0=0.345, g_term=0.10, spiked=False)
    spiked = growth_paths(g0=0.345, g_term=0.10, spiked=True)
    assert spiked["bear"][0] < normal["bear"][0]
    assert spiked["base"] == normal["base"]   # only the bear path tightens


def test_growth_start_capped_and_floored():
    from mbe.analysis.forecast import GROWTH_CAP, growth_paths

    assert growth_paths(g0=0.90, g_term=0.10, spiked=False)["base"][0] == pytest.approx(
        GROWTH_CAP
    )
    assert growth_paths(g0=-0.20, g_term=0.10, spiked=False)["base"][0] == pytest.approx(
        0.0
    )


def test_terminal_growth_clamped_with_fallback():
    from mbe.analysis.forecast import (
        TERMINAL_GROWTH_FALLBACK, TERMINAL_GROWTH_MAX, TERMINAL_GROWTH_MIN,
        terminal_growth,
    )

    assert terminal_growth([]) == pytest.approx(TERMINAL_GROWTH_FALLBACK)
    assert terminal_growth([0.11, 0.12, 0.13]) == pytest.approx(0.12)
    assert terminal_growth([0.40, 0.45]) == pytest.approx(TERMINAL_GROWTH_MAX)
    assert terminal_growth([-0.05, 0.0]) == pytest.approx(TERMINAL_GROWTH_MIN)


def test_margin_paths_argue_peak_versus_new_normal():
    from mbe.analysis.forecast import margin_paths

    # HBL shape: latest 24.7%, 3y mean 17.1%, best ever 24.7%
    m = margin_paths(m0=0.247, m3=0.171, m_best=0.247)
    assert m["bull"] == pytest.approx(0.247)              # capped by own best
    assert m["base"] == pytest.approx((0.247 + 0.171) / 2)
    assert m["bear"] == pytest.approx(0.171)              # full reversion
    assert m["bear"] < m["base"] < m["bull"]


def test_bull_margin_expansion_capped_by_own_best_year():
    from mbe.analysis.forecast import margin_paths

    m = margin_paths(m0=0.20, m3=0.18, m_best=0.30)
    assert m["bull"] == pytest.approx(0.21)   # 0.20 * 1.05, below the 0.30 ceiling


def test_bear_margin_takes_the_worse_of_latest_and_mean():
    """A business improving off a low base must not have its bear case set
    above where it currently is."""
    from mbe.analysis.forecast import margin_paths

    m = margin_paths(m0=0.10, m3=0.16, m_best=0.16)
    assert m["bear"] == pytest.approx(0.10)


def test_project_compounds_revenue_and_dilution():
    from mbe.analysis.forecast import project

    p = project(
        revenue_0=1000.0, growth_path=[0.20, 0.15, 0.10], margin=0.20,
        shares_0=10.0, share_cagr=0.0, exit_multiple=20.0, price=40.0,
    )
    revenue = 1000.0 * 1.20 * 1.15 * 1.10
    assert p.revenue_fy3 == pytest.approx(revenue)
    assert p.eps_fy3 == pytest.approx(revenue * 0.20 / 10.0)
    assert p.target_price == pytest.approx(revenue * 0.20 / 10.0 * 20.0)
    assert p.cagr_3y == pytest.approx((p.target_price / 40.0) ** (1 / 3) - 1)


def test_project_dilution_reduces_eps():
    from mbe.analysis.forecast import project

    clean = project(1000.0, [0.10] * 3, 0.20, 10.0, 0.00, 20.0, 40.0)
    diluting = project(1000.0, [0.10] * 3, 0.20, 10.0, 0.05, 20.0, 40.0)
    assert diluting.eps_fy3 < clean.eps_fy3


def test_bull_guard_trims_exit_multiple_and_records_it():
    from mbe.analysis.forecast import BULL_CAGR_CAP, apply_bull_guard

    trimmed, evidence = apply_bull_guard(
        eps_fy3=60.0, exit_multiple=49.0, base_exit_multiple=35.0, price=741.9
    )
    cagr = (60.0 * trimmed / 741.9) ** (1 / 3) - 1
    assert cagr == pytest.approx(BULL_CAGR_CAP, abs=1e-6)
    assert trimmed < 49.0
    assert any("trimmed" in e for e in evidence)


def test_bull_guard_floors_at_base_multiple_on_hbl_bull_earnings():
    """HBL's measured 5x bull case: eps_fy3 75 at a 741.9 price and a 49x bull
    multiple. Here the *base* multiple alone already implies 52%/yr, so the cap
    cannot be honoured without inverting the scenarios. The guard still removes
    most of the excess (5.0x -> 3.5x) and says it could not reach the bound."""
    from mbe.analysis.forecast import apply_bull_guard

    trimmed, evidence = apply_bull_guard(
        eps_fy3=75.0, exit_multiple=49.0, base_exit_multiple=35.0, price=741.9
    )
    assert trimmed == pytest.approx(35.0)
    assert any("could not" in e for e in evidence)
    assert 75.0 * trimmed / 741.9 == pytest.approx(3.538, abs=0.001)  # was 4.95x


def test_bull_guard_never_inverts_scenario_ordering():
    """If the cap cannot be met even at the base multiple, the earnings path
    alone implies a tripling — surface it, do not clamp below base."""
    from mbe.analysis.forecast import apply_bull_guard

    trimmed, evidence = apply_bull_guard(
        eps_fy3=500.0, exit_multiple=49.0, base_exit_multiple=35.0, price=100.0
    )
    assert trimmed == pytest.approx(35.0)
    assert any("could not" in e for e in evidence)


def test_bull_guard_is_a_no_op_below_the_cap():
    from mbe.analysis.forecast import apply_bull_guard

    trimmed, evidence = apply_bull_guard(
        eps_fy3=10.0, exit_multiple=20.0, base_exit_multiple=15.0, price=150.0
    )
    assert trimmed == pytest.approx(20.0)
    assert evidence == []


def test_probabilities_sum_to_one_and_track_quality():
    from mbe.analysis.forecast import scenario_probabilities

    strong = scenario_probabilities(0.87, 91.7, veto=False)   # HBL's real inputs
    weak = scenario_probabilities(0.35, 20.0, veto=False)
    for p in (strong, weak):
        assert sum(p.values()) == pytest.approx(1.0)
        assert all(v >= 0 for v in p.values())
    assert strong["bull"] > weak["bull"]
    assert strong["bear"] < weak["bear"]
    assert strong["bull"] == pytest.approx(0.368, abs=0.002)
    assert strong["bear"] == pytest.approx(0.177, abs=0.002)


def test_veto_shifts_weight_from_bull_to_bear():
    from mbe.analysis.forecast import scenario_probabilities

    clean = scenario_probabilities(0.80, 80.0, veto=False)
    vetoed = scenario_probabilities(0.80, 80.0, veto=True)
    assert vetoed["bull"] == pytest.approx(clean["bull"] - 0.15)
    assert vetoed["bear"] == pytest.approx(clean["bear"] + 0.15)
    assert sum(vetoed.values()) == pytest.approx(1.0)


def test_veto_cannot_drive_bull_probability_negative():
    from mbe.analysis.forecast import scenario_probabilities

    p = scenario_probabilities(0.0, 0.0, veto=True)
    assert p["bull"] >= 0.0
    assert sum(p.values()) == pytest.approx(1.0)


def test_expected_value_is_computed_on_prices_not_by_averaging_cagrs():
    """CAGR is non-linear in price, so averaging CAGRs is not the same thing.
    A wide spread makes the two answers differ measurably."""
    from mbe.analysis.forecast import expected_outcome

    targets = {"bull": 4000.0, "base": 1000.0, "bear": 250.0}
    probs = {"bull": 0.3, "base": 0.5, "bear": 0.2}
    exp_target, exp_cagr, downside = expected_outcome(targets, probs, price=1000.0)

    assert exp_target == pytest.approx(0.3 * 4000 + 0.5 * 1000 + 0.2 * 250)
    assert exp_cagr == pytest.approx((exp_target / 1000.0) ** (1 / 3) - 1)
    naive = sum(
        probs[k] * ((targets[k] / 1000.0) ** (1 / 3) - 1) for k in targets
    )
    assert exp_cagr != pytest.approx(naive, abs=1e-4)
    assert downside == pytest.approx(0.2)


def test_downside_probability_counts_every_scenario_below_price():
    from mbe.analysis.forecast import expected_outcome

    targets = {"bull": 1200.0, "base": 900.0, "bear": 500.0}
    probs = {"bull": 0.3, "base": 0.5, "bear": 0.2}
    _, _, downside = expected_outcome(targets, probs, price=1000.0)
    assert downside == pytest.approx(0.7)
