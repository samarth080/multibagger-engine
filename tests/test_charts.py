"""Charts are pure functions returning SVG strings, so they test on output."""

import re

from mbe.models.company import FinancialHistory
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
