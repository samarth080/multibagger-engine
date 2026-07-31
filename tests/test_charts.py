"""Charts are pure functions returning SVG strings, so they test on output."""

import re

from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.models.forecast import MultipleAnchor, PriceForecast, ScenarioPath
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


def _peer(ticker, name, roce, growth, pe, score, mcap):
    return charts.PeerRow(ticker=ticker, name=name, roce=roce, growth=growth,
                          pe=pe, score=score, market_cap=mcap,
                          is_subject=(ticker == "HBLENGINE.NS"))


def _hbl_group():
    """HBL's real 8-name Electrical Equipment & Parts group, 2026-08-01."""
    return [
        _peer("HBLENGINE.NS", "HBL ENGINEERING", 0.329, 0.345, 24.5, 76.6, 199.2e9),
        _peer("SCHNEIDER.NS", "SCHNEIDER ELEC", 0.343, 0.179, 155.0, 65.3, 327.6e9),
        _peer("RRKABEL.NS", "R R KABEL", 0.199, 0.201, 48.9, 58.4, 297.4e9),
        _peer("ARE&M.NS", "AMARA RAJA", 0.141, 0.100, 18.1, 44.5, 166.7e9),
        _peer("FINCABLES.NS", "FINOLEX CABLES", 0.097, 0.127, 21.2, 43.3, 151.1e9),
        _peer("HEG.NS", "HEG LTD", 0.049, 0.016, 35.1, 35.8, 126.8e9),
        _peer("TARIL.NS", "TRANS & RECTI", 0.175, 0.223, 34.7, 35.0, 89.8e9),
        _peer("GRAPHITE.NS", "GRAPHITE INDIA", 0.002, -0.031, 73.1, 34.3, 128.4e9),
    ]


def test_peer_table_lists_every_peer_and_marks_the_subject():
    out = charts.peer_table(_hbl_group())
    assert out is not None
    for name in ("HBL ENGINEERING", "SCHNEIDER ELEC", "GRAPHITE INDIA"):
        assert name in out
    assert "32.9%" in out          # subject ROCE
    assert svg.SUBJECT in out      # subject highlighted
    assert "lower is cheaper" in out   # P/E column direction stated
    assert "\n\n" not in out


def test_peer_table_escapes_a_hostile_name():
    rows = [_peer("X.NS", '<script>alert(1)</script> & Co', 0.2, 0.1, 20.0, 50.0, 1e9)]
    out = charts.peer_table(rows)
    assert "<script>" not in out
    assert "&amp;" in out


def test_peer_table_leaves_a_missing_metric_blank_not_zero():
    rows = _hbl_group()
    rows[1] = _peer("SCHNEIDER.NS", "SCHNEIDER ELEC", None, 0.179, 155.0, 65.3, 327.6e9)
    out = charts.peer_table(rows)
    assert out is not None
    assert out.count(">n/a<") == 1        # the one absent metric, stated as absent
    # never imputed to zero. Matched on the whole text node, because a bare
    # "0.0%" substring also matches Amara Raja's real "10.0%".
    assert ">0.0%<" not in out
    assert ">10.0%<" in out               # the real 10.0% is untouched


def test_peer_scatter_plots_the_group_and_highlights_the_subject():
    out = charts.peer_scatter(_hbl_group())
    assert out is not None
    assert "ROCE" in out and "Revenue CAGR" in out
    assert out.count("<circle") >= 8
    assert svg.SUBJECT in out
    assert "\n\n" not in out


def test_peer_scatter_works_at_the_smallest_real_group_size():
    """MIN_GROUP is 4, so a 4-name group is the smallest that reaches a
    report page — it must still draw rather than falling back to text."""
    four = [
        _peer("HBLENGINE.NS", "HBL ENGINEERING", 0.329, 0.345, 24.5, 76.6, 199.2e9),
        _peer("SCHNEIDER.NS", "SCHNEIDER ELEC", 0.343, 0.179, 155.0, 65.3, 327.6e9),
        _peer("RRKABEL.NS", "R R KABEL", 0.199, 0.201, 48.9, 58.4, 297.4e9),
        _peer("HEG.NS", "HEG LTD", 0.049, 0.016, 35.1, 35.8, 126.8e9),
    ]
    out = charts.peer_scatter(four)
    assert out is not None
    assert out.count("<circle") >= 4
    assert charts.peer_table(four) is not None


def test_peer_scatter_needs_three_plottable_points():
    thin = [_peer("A.NS", "A", 0.2, 0.1, 10.0, 50.0, 1e9),
            _peer("B.NS", "B", None, None, 10.0, 40.0, 1e9),
            _peer("C.NS", "C", None, None, 10.0, 30.0, 1e9)]
    assert charts.peer_scatter(thin) is None


def test_peer_charts_are_none_for_an_empty_group():
    assert charts.peer_table([]) is None
    assert charts.peer_scatter([]) is None


def _forecast(price=717.0, targets=(1600.0, 1210.0, 640.0)):
    names = ("bull", "base", "bear")
    probs = (0.25, 0.5, 0.25)
    return PriceForecast(
        ticker="HBLENGINE.NS", base_fiscal_year=2026, price=price,
        anchor=MultipleAnchor(anchor=30.0, quality_multiplier=1.1),
        scenarios=[
            ScenarioPath(name=n, probability=p, growth_start=0.30,
                         growth_end=0.15, terminal_net_margin=0.18,
                         exit_multiple=30.0, revenue_fy3=1.0e10,
                         eps_fy3=40.0, target_price=t,
                         cagr_3y=(t / price) ** (1 / 3) - 1)
            for n, p, t in zip(names, probs, targets)
        ],
        completeness=1.0,
    )


def test_scenario_chart_labels_every_target_and_the_current_price():
    out = charts.scenario_chart(_forecast(), "INR")
    assert out is not None
    for name in ("Bull", "Base", "Bear"):
        assert name in out
    assert "717" in out            # today's price marked
    assert "1,600" in out or "1600" in out
    assert "\n\n" not in out


def test_scenario_chart_colours_downside_as_a_loss():
    out = charts.scenario_chart(_forecast(), "INR")
    assert svg.GAIN in out    # bull and base are above today
    assert svg.LOSS in out    # bear is below it


def test_scenario_chart_handles_an_all_downside_forecast():
    """The v0.13 bug this engine shipped was every scenario negative; the
    chart must render that honestly rather than break."""
    out = charts.scenario_chart(_forecast(targets=(600.0, 500.0, 400.0)), "INR")
    assert out is not None
    assert svg.LOSS in out
    assert svg.GAIN not in out


def test_scenario_chart_is_none_without_scenarios():
    f = _forecast()
    f.scenarios = []
    assert charts.scenario_chart(f, "INR") is None
