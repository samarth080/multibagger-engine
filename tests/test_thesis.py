import pytest

from mbe.analysis.business import assess_business
from mbe.analysis.fundamentals import compute_fundamentals
from mbe.models.analysis import RiskAssessment, ValuationResult
from mbe.models.company import CompanyInfo, FinancialHistory
from mbe.thesis.engine import build_thesis, critique_thesis
from tests.test_business import _compounder


def _bundle_compounder():
    fin = _compounder()
    info = CompanyInfo(
        ticker="COMP.NS", name="Compounder Co", sector="Industrials",
        industry="Tools", description="Makes precision tools sold to factories.",
    )
    fund = compute_fundamentals(fin, info)
    business = assess_business(fin, info, fund)
    val = ValuationResult(margin_of_safety=0.15, implied_growth=0.12, peg=1.1)
    risk = RiskAssessment(flags=[], risk_score=8.0, permanent_loss_bucket="low")
    return fin, info, fund, business, val, risk


def test_thesis_assumptions_track_record():
    fin, info, fund, business, val, risk = _bundle_compounder()
    thesis = build_thesis(info, fund, business, val, risk)

    roce_asm = next(a for a in thesis.assumptions if "return on capital" in a.statement.lower())
    # compounder: ROCE >= 15% in every year of history
    assert roce_asm.historical_support == pytest.approx(business.roce_consistency)
    assert roce_asm.currently_true is True

    growth_asm = next(a for a in thesis.assumptions if "grow" in a.statement.lower())
    assert growth_asm.historical_support == pytest.approx(1.0)  # every year grew

    assert thesis.business_summary
    assert thesis.bull_pillars
    assert thesis.falsifiers
    assert 0 <= thesis.thesis_confidence <= 1


def test_clean_compounder_survives_critique():
    fin, info, fund, business, val, risk = _bundle_compounder()
    thesis = build_thesis(info, fund, business, val, risk)
    critique = critique_thesis(thesis, fund, business, val, risk)

    assert critique.veto is False
    assert not critique.recommendation.lower().startswith("pass")


def test_deteriorating_levered_business_is_vetoed():
    years = list(range(2017, 2025))
    rev = [200, 205, 210, 208, 205, 200, 195, 190]
    op = [40, 38, 35, 30, 26, 22, 18, 14]
    fin = FinancialHistory(
        data={
            "revenue": dict(zip(years, rev)),
            "operating_income": dict(zip(years, op)),
            "net_income": dict(zip(years, [round(o * 0.6) for o in op])),
            "total_equity": dict(zip(years, [100] * 8)),
            "total_debt": dict(zip(years, [250] * 8)),  # heavily levered
            "cash": dict(zip(years, [5] * 8)),
            "interest_expense": dict(zip(years, [30] * 8)),
        }
    )
    info = CompanyInfo(ticker="DECL.NS", name="Declining Co")
    fund = compute_fundamentals(fin, info)
    business = assess_business(fin, info, fund)
    val = ValuationResult(margin_of_safety=-0.3, implied_growth=0.35)
    risk = RiskAssessment(flags=[], risk_score=72.0, permanent_loss_bucket="high")

    thesis = build_thesis(info, fund, business, val, risk)
    critique = critique_thesis(thesis, fund, business, val, risk)

    assert critique.veto is True
    assert critique.recommendation.lower().startswith("pass")
    assert critique.disconfirmers  # must name what's wrong


def test_thesis_confidence_lower_for_short_history():
    fin = FinancialHistory(
        data={
            "revenue": {2023: 100.0, 2024: 130.0},
            "operating_income": {2023: 20.0, 2024: 26.0},
            "total_equity": {2023: 60.0, 2024: 70.0},
            "total_debt": {2023: 40.0, 2024: 40.0},
        }
    )
    info = CompanyInfo(ticker="NEW.NS")
    fund = compute_fundamentals(fin, info)
    business = assess_business(fin, info, fund)
    val = ValuationResult()
    risk = RiskAssessment()
    thesis = build_thesis(info, fund, business, val, risk)
    assert thesis.thesis_confidence < 0.5  # 2 years -> low confidence


def test_thesis_diff_detects_changes():
    from mbe.thesis.engine import diff_theses
    from mbe.models.thesis import Assumption, InvestmentThesis

    prev = InvestmentThesis(
        ticker="X.NS", business_summary="s", classification="Durable Compounder",
        assumptions=[
            Assumption(statement="Sustains a high return on capital (ROCE >= 15%)",
                       historical_support=0.9, currently_true=True),
            Assumption(statement="Grows revenue over time",
                       historical_support=0.8, currently_true=True),
        ],
        thesis_confidence=0.7,
    )
    curr = InvestmentThesis(
        ticker="X.NS", business_summary="s", classification="Steady",
        assumptions=[
            Assumption(statement="Sustains a high return on capital (ROCE >= 15%)",
                       historical_support=0.85, currently_true=False),  # flipped!
            Assumption(statement="Grows revenue over time",
                       historical_support=0.85, currently_true=True),   # strengthened
        ],
        thesis_confidence=0.55,
    )
    diff = diff_theses(prev, curr)
    assert any("ROCE" in c and "no longer" in c.lower() for c in diff.changes)
    assert any("classification" in c.lower() for c in diff.changes)
    assert diff.confidence_delta == pytest.approx(-0.15)


def test_thesis_persistence_roundtrip(tmp_path):
    from mbe.storage import RunStore

    fin, info, fund, business, val, risk = _bundle_compounder()
    from mbe.thesis.engine import critique_thesis as _crit
    thesis = build_thesis(info, fund, business, val, risk)
    critique = _crit(thesis, fund, business, val, risk)

    store = RunStore(tmp_path / "t.duckdb")
    store.save_thesis(thesis, critique)
    store.save_thesis(thesis, critique)
    rows = store.thesis_history("COMP.NS")
    assert len(rows) == 2
    assert rows[0]["classification"] == thesis.classification
    assert rows[0]["thesis"]["assumptions"]  # full thesis JSON round-trips
