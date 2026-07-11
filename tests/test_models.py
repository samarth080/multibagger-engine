import pytest
from pydantic import ValidationError

from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.models.scoring import Evidence, PillarScore, ScoreCard


def test_financial_history_series_skips_none_and_sorts():
    fin = FinancialHistory(
        data={
            "revenue": {2023: 120.0, 2021: 100.0, 2022: None, 2024: 150.0},
            "net_income": {},
        }
    )
    assert fin.series("revenue") == [(2021, 100.0), (2023, 120.0), (2024, 150.0)]
    assert fin.series("net_income") == []
    assert fin.series("missing_field") == []


def test_financial_history_years_sorted_union():
    fin = FinancialHistory(
        data={"revenue": {2022: 1.0, 2020: 2.0}, "cfo": {2023: 3.0}}
    )
    assert fin.years() == [2020, 2022, 2023]


def test_financial_history_latest():
    fin = FinancialHistory(data={"revenue": {2022: 10.0, 2023: 12.0, 2024: None}})
    assert fin.latest("revenue") == 12.0
    assert fin.latest("cfo") is None


def test_company_info_minimal():
    info = CompanyInfo(ticker="RELIANCE.NS")
    assert info.ticker == "RELIANCE.NS"
    assert info.market_cap is None


def test_scorecard_rejects_out_of_range_scores():
    with pytest.raises(ValidationError):
        ScoreCard(
            ticker="X",
            investment_score=101,
            multibagger_score=50,
            confidence=0.5,
            pillars=[],
            hard_gate_failures=[],
            verdict="n/a",
        )


def test_pillar_score_holds_evidence():
    ev = Evidence(
        metric="roce_3y",
        value=0.24,
        benchmark=">=20% scores 75",
        points=75,
        weight=0.3,
        rationale="High ROCE indicates efficient capital deployment",
    )
    pillar = PillarScore(name="Quality", score=75.0, confidence=0.9, evidence=[ev])
    assert pillar.evidence[0].metric == "roce_3y"
