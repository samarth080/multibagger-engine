import pytest

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
