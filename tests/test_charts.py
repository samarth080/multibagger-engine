"""Charts are pure functions returning SVG strings, so they test on output."""

import re

from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.report import charts, svg


def _fin(**series) -> FinancialHistory:
    return FinancialHistory(data={k: dict(v) for k, v in series.items()})


def test_trend_bars_renders_every_field_and_year():
    fin = _fin(
        revenue={2023: 1.0e9, 2024: 1.4e9, 2025: 2.0e9},
        net_income={2023: 1.0e8, 2024: 1.5e8, 2025: 2.2e8},
        fcf={2023: 5.0e7, 2024: 9.0e7, 2025: 1.1e8},
    )
    out = charts.trend_bars(fin, "USD")
    assert out is not None
    for label in ("Revenue", "Net income", "Free cash flow"):
        assert label in out
    for year in ("FY23", "FY24", "FY25"):
        assert year in out
    assert "\n\n" not in out


def test_trend_bars_draws_a_loss_year_below_the_zero_line():
    """A loss must be visible as a loss, not clipped to nothing."""
    fin = _fin(net_income={2023: 100.0e7, 2024: -50.0e7, 2025: 20.0e7})
    out = charts.trend_bars(fin, "INR")
    assert out is not None
    assert svg.LOSS in out   # the negative bar is coloured as a loss
    assert svg.GAIN in out   # and the positive ones are not
    assert "-50" in out      # the negative value is labelled


def test_trend_bars_needs_two_years_to_be_a_trend():
    assert charts.trend_bars(_fin(revenue={2025: 1.0e9}), "USD") is None
    assert charts.trend_bars(_fin(), "USD") is None


def test_trend_bars_skips_a_field_without_dropping_the_others():
    fin = _fin(revenue={2024: 1.0e9, 2025: 2.0e9}, fcf={2025: 1.0e8})
    out = charts.trend_bars(fin, "USD")
    assert out is not None
    assert "Revenue" in out
    assert "Free cash flow" not in out   # single year: not a trend


def test_trend_bars_emits_no_literal_colour():
    fin = _fin(revenue={2024: 1.0e9, 2025: 2.0e9})
    assert not re.search(r"#[0-9a-fA-F]{3,6}", charts.trend_bars(fin, "USD"))


def _info(**kw) -> CompanyInfo:
    base = dict(ticker="X.NS", name="X Ltd", currency="INR",
                insider_pct=0.60, institution_pct=0.25,
                float_shares=40.0, shares_outstanding=100.0)
    return CompanyInfo(**{**base, **kw})


def test_shareholding_draws_three_slices_with_the_remainder_as_public():
    out = charts.shareholding(_info())
    assert out is not None
    assert "Insider / promoter" in out and "60.0%" in out
    assert "Institutions" in out and "25.0%" in out
    assert "Public / other" in out and "15.0%" in out
    assert "\n\n" not in out


def test_shareholding_drops_the_public_slice_rather_than_drawing_it_negative():
    out = charts.shareholding(_info(insider_pct=0.70, institution_pct=0.45))
    assert out is not None
    assert "Public / other" not in out   # 115% reported: no room left


def test_shareholding_needs_both_reported_figures():
    assert charts.shareholding(_info(insider_pct=None)) is None
    assert charts.shareholding(_info(institution_pct=None)) is None


def test_ownership_conflict_fires_on_hbls_real_numbers():
    """HBL: 8.1% insider reported, 104.4M of 277.2M shares free-floating,
    which implies ~62%. Both are Yahoo's own fields."""
    note = charts.ownership_conflict(
        _info(insider_pct=0.081, float_shares=104429095.0,
              shares_outstanding=277194946.0)
    )
    assert note is not None
    assert "8.1%" in note and "62" in note


def test_ownership_conflict_silent_when_the_two_fields_agree():
    # BLS: 72.7% insider, 116.7M of 411.5M floating -> implied 71.6%
    assert charts.ownership_conflict(
        _info(insider_pct=0.727, float_shares=116735981.0,
              shares_outstanding=411522253.0)
    ) is None


def test_ownership_conflict_says_when_it_could_not_run():
    note = charts.ownership_conflict(_info(float_shares=None))
    assert note is not None
    assert "could not be cross-checked" in note
