import numpy as np
import pandas as pd
import pytest

from mbe.data.provider import ProviderError
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.pipeline import analyze_ticker, screen

YEARS = [2019, 2020, 2021, 2022, 2023, 2024]


def _fin() -> FinancialHistory:
    return FinancialHistory(
        data={
            field: dict(zip(YEARS, values))
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
                "shares_diluted": [100, 100, 100, 100, 100, 100],
            }.items()
        }
    )


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
        "Bull / Base / Bear",
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
