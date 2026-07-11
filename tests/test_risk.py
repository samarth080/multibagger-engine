from mbe.analysis.risk import assess_risk
from mbe.models.analysis import FundamentalMetrics, TechnicalState, ValuationResult
from mbe.models.company import CompanyInfo, FinancialHistory


def _clean_inputs():
    fin = FinancialHistory(
        data={"fcf": {2022: 10.0, 2023: 12.0, 2024: 15.0}}
    )
    fund = FundamentalMetrics(
        debt_to_equity=0.2,
        interest_coverage=12.0,
        accruals_ratio=-0.02,
        cash_conversion=1.1,
        share_count_cagr_3y=0.0,
    )
    tech = TechnicalState(atr_pct=2.5, avg_traded_value_20d=5e8)  # INR 50 cr/day
    val = ValuationResult(implied_growth=0.10, peg=1.2)
    info = CompanyInfo(ticker="CLEAN.NS", insider_pct=0.55)
    return fin, fund, tech, val, info


def test_clean_company_low_risk():
    risk = assess_risk(*_clean_inputs())
    assert risk.risk_score < 25
    assert risk.permanent_loss_bucket == "low"
    assert not any(f.severity == 3 for f in risk.flags)


def test_junk_company_flags_and_high_bucket():
    fin = FinancialHistory(
        data={"fcf": {2022: -10.0, 2023: -12.0, 2024: -5.0}}
    )
    fund = FundamentalMetrics(
        debt_to_equity=2.5,
        interest_coverage=1.5,
        accruals_ratio=0.15,
        cash_conversion=0.3,
        share_count_cagr_3y=0.09,
    )
    tech = TechnicalState(atr_pct=7.0, avg_traded_value_20d=1e6)  # INR 10 lakh/day
    val = ValuationResult(implied_growth=0.40, peg=4.0)
    info = CompanyInfo(ticker="JUNK.NS", insider_pct=None)

    risk = assess_risk(fin, fund, tech, val, info)
    codes = {f.code for f in risk.flags}
    assert {
        "SOLVENCY_DEBT",
        "COVERAGE",
        "EARNINGS_QUALITY",
        "DILUTION",
        "NEGATIVE_FCF",
        "VALUATION_HOT",
        "MICRO_ILLIQUID",
        "GOVERNANCE_UNKNOWN",
    } <= codes
    assert risk.risk_score == 100  # capped
    assert risk.permanent_loss_bucket == "high"


def test_missing_metrics_produce_no_false_flags():
    fin = FinancialHistory(data={})
    fund = FundamentalMetrics()
    tech = TechnicalState()
    val = ValuationResult()
    info = CompanyInfo(ticker="X.NS", insider_pct=0.5)
    risk = assess_risk(fin, fund, tech, val, info)
    codes = {f.code for f in risk.flags}
    assert "SOLVENCY_DEBT" not in codes
    assert "COVERAGE" not in codes
    assert "GOVERNANCE_UNKNOWN" not in codes


def test_moderate_debt_is_warning_not_critical():
    fin, fund, tech, val, info = _clean_inputs()
    fund = fund.model_copy(update={"debt_to_equity": 1.4})
    risk = assess_risk(fin, fund, tech, val, info)
    flag = next(f for f in risk.flags if f.code == "SOLVENCY_DEBT")
    assert flag.severity == 2
