import numpy as np
import pandas as pd
import pytest

from mbe.data.provider import ProviderError
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.pipeline import analyze_ticker, screen

YEARS = [2019, 2020, 2021, 2022, 2023, 2024]

# The statement table below is written in compact units for legibility; SCALE
# converts it to rupees so it is coherent with StubProvider's 1e8 shares and
# Rs 3,000 cr market cap. Unscaled, the stub's P/E is market_cap / net_income =
# 1.15e9, which the forecast engine's peer-P/E sanity band (5x-80x) correctly
# rejects, so no peer anchor can form. Every ratio, margin and CAGR the engines
# compute is scale-invariant, so nothing else moves.
SCALE = 4e7
SHARES = 1e8  # matches CompanyInfo.shares_outstanding; a count, so never scaled


def _fin() -> FinancialHistory:
    data = {
        field: dict(zip(YEARS, [v * SCALE for v in values]))
        for field, values in {
            "revenue": [100, 115, 132, 152, 175, 200],
            "net_income": [10, 12, 15, 18, 22, 26],
            "operating_income": [15, 17, 20, 24, 28, 33],
            "ebitda": [20, 23, 27, 32, 37, 43],
            "interest_expense": [4, 4, 4, 4, 4, 4],
            "total_assets": [300, 340, 385, 435, 490, 550],
            "total_equity": [60, 70, 82, 96, 112, 130],
            "total_debt": [40, 40, 40, 40, 40, 40],
            "cash": [10, 12, 14, 16, 18, 20],
            "current_assets": [50, 55, 60, 65, 70, 75],
            "current_liabilities": [25, 27, 29, 31, 33, 35],
            "cfo": [12, 14, 18, 22, 26, 30],
            "capex": [5, 6, 7, 8, 9, 10],
            "fcf": [7, 8, 11, 14, 17, 20],
        }.items()
    }
    data["shares_diluted"] = dict(zip(YEARS, [SHARES] * len(YEARS)))
    return FinancialHistory(data=data)


def _prices(closes) -> PriceHistory:
    closes = pd.Series(closes, dtype=float)
    idx = pd.bdate_range("2023-01-02", periods=len(closes))
    return PriceHistory(
        df=pd.DataFrame(
            {
                "open": closes.values,
                "high": closes.values * 1.01,
                "low": closes.values * 0.99,
                "close": closes.values,
                "volume": 1_000_000.0,
            },
            index=idx,
        )
    )


class StubProvider:
    def __init__(self, bad: set[str] | None = None):
        self.bad = bad or set()

    def get_info(self, ticker: str) -> CompanyInfo:
        if ticker in self.bad:
            raise ProviderError(f"boom {ticker}")
        return CompanyInfo(
            ticker=ticker, name="Stub Co", market_cap=3e10,
            shares_outstanding=1e8, currency="INR", insider_pct=0.6,
            industry="Test Industry",
        )

    def get_financials(self, ticker: str) -> FinancialHistory:
        return _fin()

    def get_prices(self, ticker: str, years: int = 3) -> PriceHistory:
        if ticker.startswith("^"):
            return _prices(np.full(300, 100.0))  # flat benchmark
        return _prices(np.arange(100, 400))

    def benchmark_ticker(self, ticker: str) -> str:
        return "^NSEI"


def test_analyze_ticker_produces_full_bundle():
    bundle = analyze_ticker("GOOD.NS", StubProvider())
    assert bundle.card.ticker == "GOOD.NS"
    assert bundle.card.investment_score > 0
    assert bundle.fund.roce is not None
    assert bundle.tech.trend_state == "strong_up"
    assert bundle.val.fair_value_base is not None
    assert bundle.risk.permanent_loss_bucket in ("low", "medium", "high")


def test_screen_continues_past_failures_and_ranks():
    result = screen(["GOOD.NS", "BAD.NS", "ALSO.NS"], StubProvider(bad={"BAD.NS"}))
    assert [r.card.ticker for r in result.ranked][0] in ("GOOD.NS", "ALSO.NS")
    assert len(result.ranked) == 2
    assert "BAD.NS" in result.failures
    # ranked descending by multibagger score
    scores = [r.card.multibagger_score for r in result.ranked]
    assert scores == sorted(scores, reverse=True)


def test_report_contains_all_sections():
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    text = render_report(bundle)
    for section in [
        "Executive Summary",
        "Investment Thesis",
        "Financial Analysis",
        "Technical Analysis",
        "Valuation",
        "Risk Analysis",
        "3-Year Price Forecast",
        "Entry & Exit Framework",
        "Position Sizing",
        "Score Evidence Appendix",
        "Data Gaps",
        "Disclaimer",
    ]:
        assert section in text, f"missing section {section}"
    assert "GOOD.NS" in text


def test_screen_table_renders():
    from mbe.report.markdown import render_screen_table

    result = screen(["GOOD.NS", "ALSO.NS"], StubProvider())
    table = render_screen_table(result)
    assert "GOOD.NS" in table and "ALSO.NS" in table
    assert "Multibagger" in table


def test_sizing_never_recommends_position_on_avoid_verdict():
    from mbe.report.markdown import sizing_guidance

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    low_card = bundle.card.model_copy(update={"investment_score": 30.0})
    avoid_bundle = bundle.model_copy(update={"card": low_card})
    text = sizing_guidance(avoid_bundle)
    assert "No new position" in text


def test_report_discloses_validation_status():
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    text = render_report(bundle)
    assert "Model validation status" in text
    assert "no demonstrated" in text.lower()


def test_report_has_business_and_thesis_section():
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    text = render_report(bundle)
    assert "Business & Investment Thesis" in text
    assert "Franchise classification" in text
    assert "Key assumptions" in text  # falsifiable assumptions table
    assert "Self-critique" in text     # devil's advocate
    assert bundle.thesis is not None
    assert bundle.critique is not None


def test_report_has_stewardship_section():
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    text = render_report(bundle)
    assert "Management & capital allocation" in text
    assert bundle.stewardship is not None
    assert "share count CAGR" in text


def test_report_spike_disclosure_survives_an_absent_ratio():
    """The disclosure is guarded by a NaN test *and* a None test. An assumptions
    dict that never had the key — ValuationResult() defaults to {} — must render
    the report with the line omitted, not raise inside format()."""
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    assert "Base FCF is the latest year's" in render_report(bundle)

    for assumptions in ({}, {"fcf_spike_ratio": float("nan")}):
        val = bundle.val.model_copy(update={"assumptions": assumptions})
        text = render_report(bundle.model_copy(update={"val": val}))
        assert "Base FCF is the latest year's" not in text


def test_screen_populates_forecasts_with_peer_anchors():
    """Four names share StubProvider's industry, so the group clears MIN_GROUP
    and every member gets a leave-one-out peer anchor."""
    result = screen(["A.NS", "B.NS", "C.NS", "D.NS"], StubProvider())
    assert len(result.ranked) == 4
    for bundle in result.ranked:
        assert bundle.forecast is not None
        assert bundle.forecast.anchor.peer_n >= 1
        assert [s.name for s in bundle.forecast.scenarios] == ["bull", "base", "bear"]


def test_analyze_ticker_populates_a_lower_completeness_forecast():
    solo = analyze_ticker("GOOD.NS", StubProvider())
    assert solo.forecast is not None
    assert solo.forecast.anchor.peer_pe is None
    assert solo.forecast.completeness < 1.0


def test_screen_does_not_double_append_forecast_flags():
    """analyze_ticker attaches a solo forecast and its flags; the screen-level
    post-pass replaces both. A flag emitted by each pass must appear once."""
    from mbe.analysis.forecast import FORECAST_FLAG_CODES

    result = screen(["A.NS", "B.NS", "C.NS", "D.NS"], StubProvider())
    for bundle in result.ranked:
        codes = [f.code for f in bundle.risk.flags if f.code in FORECAST_FLAG_CODES]
        assert len(codes) == len(set(codes)), codes


def test_report_renders_news_and_policy_with_ages():
    from datetime import datetime, timezone
    from mbe.data.news_rss import NewsItem
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    pub = datetime(2026, 7, 15, tzinfo=timezone.utc)
    md = render_report(
        bundle,
        news=[NewsItem(title="Wins Rs 400cr order", link="https://x/1",
                       published=pub, source="Economic Times"),
              NewsItem(title="Undated one", link="https://x/3")],
        policy=[NewsItem(title="Cabinet clears grid scheme", link="https://x/2",
                         published=pub, source="PIB", sectors=["Test Industry"])],
    )
    assert "## Recent News & Policy Context" in md
    assert "Economic Times" in md
    assert "not catalysts the engine has identified" in md

    # Substring assertions alone pass on mangled markdown: jinja's trim_blocks
    # strips the newline after a line-ending {% endif %}, which silently ran
    # consecutive headlines together on one line. Assert the line structure.
    lines = md.splitlines()
    age = (bundle.as_of - pub.date()).days
    assert f"- [Wins Rs 400cr order](https://x/1) — Economic Times, {age}d ago" in lines
    assert "- [Undated one](https://x/3)" in lines  # no age, not dropped
    assert f"- [Cabinet clears grid scheme](https://x/2) — PIB, {age}d ago" in lines
    # a bold run-in heading needs its blank line or markdown swallows it
    assert "" == lines[lines.index("**Sector policy — Test Industry**") - 1]


def test_report_states_absence_explicitly_when_no_news():
    """Silence is what let the old policy section look like it worked."""
    from mbe.report.markdown import render_report

    md = render_report(analyze_ticker("GOOD.NS", StubProvider()))
    assert "## Recent News & Policy Context" in md
    assert "No recent company news found" in md
    assert "No sector policy items found" in md
    assert "arrives in v0.3" not in md


def test_report_filters_policy_to_its_own_industry():
    """build_site hands every report one flat multi-industry list."""
    from mbe.data.news_rss import NewsItem
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    md = render_report(bundle, policy=[
        NewsItem(title="Mine item", link="https://x/1", sectors=["Test Industry"]),
        NewsItem(title="Someone elses item", link="https://x/2", sectors=["Banks"]),
    ])
    assert "Mine item" in md
    assert "Someone elses item" not in md


def test_report_without_charts_keeps_every_table():
    """The CLI markdown path: no charts, nothing lost."""
    from mbe.report.markdown import render_report

    md = render_report(analyze_ticker("GOOD.NS", StubProvider()))
    assert "## Financial Analysis" in md
    assert "| Revenue CAGR 3y |" in md          # ratios table intact
    assert "| Scenario | Prob." in md           # full scenario table
    assert "3y CAGR |" in md                    # including the columns a chart would carry
    assert "<svg" not in md


def test_report_with_charts_embeds_svg_and_trims_the_scenario_columns():
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    md = render_report(bundle, charts={
        "trend": "<svg id='t'></svg>",
        "ownership": "<svg id='o'></svg>",
        "scenarios": "<svg id='s'></svg>",
    })
    assert "<svg id='t'></svg>" in md
    assert "<svg id='o'></svg>" in md
    assert "<svg id='s'></svg>" in md
    # the chart carries target and CAGR, so the table drops those two columns
    assert "| Scenario | Prob." in md           # assumptions remain
    assert "Exit multiple" in md
    assert "3y CAGR |" not in md


def test_report_states_why_peer_comparison_is_missing():
    from mbe.report.markdown import render_report

    md = render_report(analyze_ticker("GOOD.NS", StubProvider()))
    assert "## Peer Comparison" in md
    assert "requires a universe screen" in md


def test_report_ownership_section_carries_its_caveats_and_conflict():
    from mbe.report.markdown import render_report

    md = render_report(analyze_ticker("GOOD.NS", StubProvider()), charts={
        "ownership": "<svg id='o'></svg>",
        "ownership_note": "Yahoo reports 8.1% insider, but its own float implies 62%",
    })
    assert "## Ownership" in md
    assert "8.1% insider" in md
    assert "not SEBI's promoter category" in md
    assert "not the promoter/FII/DII" in md


def test_chart_svgs_survive_markdown_conversion_intact():
    """The load-bearing integration check. A blank line inside an SVG makes
    python-markdown split it into paragraphs, destroying the chart while the
    markdown source still looks correct.

    Note what is NOT asserted: '<p><svg' is fine — markdown wrapping a whole
    chart in a paragraph is valid, since SVG is phrasing content. The failure
    is a '</p>' appearing *inside* an SVG."""
    import re

    import markdown as md_lib

    from mbe.report import charts as chart_mod
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    built = chart_mod.build_charts(bundle)
    assert built, "the stub bundle should support at least one chart"

    html = md_lib.markdown(render_report(bundle, charts=built), extensions=["tables"])
    svgs = re.findall(r"<svg\b.*?</svg>", html, re.S)
    # every opening tag found a closing tag: none was truncated
    assert len(svgs) == html.count("<svg")
    for one in svgs:
        assert "</p>" not in one and "<p>" not in one
