"""Rule-based risk assessment. Each rule fires only when its inputs exist —
missing data never produces a false flag (it shows up as GOVERNANCE_UNKNOWN
or reduced confidence elsewhere, not as invented risk).

risk_score = min(100, sum(severity) * 12); severity: 1 info, 2 warning, 3 critical.
"""

from __future__ import annotations

from mbe.models.analysis import (
    FundamentalMetrics,
    RiskAssessment,
    RiskFlag,
    TechnicalState,
    ValuationResult,
)
from mbe.models.company import CompanyInfo, FinancialHistory

# minimum healthy average daily traded value, by listing region
MIN_TRADED_VALUE_INR = 1e7  # ~ INR 1 crore / day
MIN_TRADED_VALUE_USD = 1e6


def assess_risk(
    fin: FinancialHistory,
    fund: FundamentalMetrics,
    tech: TechnicalState,
    val: ValuationResult,
    info: CompanyInfo,
) -> RiskAssessment:
    flags: list[RiskFlag] = []

    def flag(code: str, severity: int, detail: str) -> None:
        flags.append(RiskFlag(code=code, severity=severity, detail=detail))

    de = fund.debt_to_equity
    if de is not None:
        if de > 2:
            flag("SOLVENCY_DEBT", 3, f"Debt/equity {de:.2f} — heavily levered balance sheet")
        elif de > 1:
            flag("SOLVENCY_DEBT", 2, f"Debt/equity {de:.2f} — elevated leverage")

    ic = fund.interest_coverage
    if ic is not None:
        if ic < 2:
            flag("COVERAGE", 3, f"Interest coverage {ic:.1f}x — solvency at risk in a downturn")
        elif ic < 4:
            flag("COVERAGE", 1, f"Interest coverage {ic:.1f}x — limited headroom")

    if fund.accruals_ratio is not None and fund.accruals_ratio > 0.10:
        flag(
            "EARNINGS_QUALITY", 3,
            f"Accruals ratio {fund.accruals_ratio:.2f} — reported profits far ahead of cash",
        )
    elif fund.cash_conversion is not None and fund.cash_conversion < 0.6:
        flag(
            "EARNINGS_QUALITY", 2,
            f"Cash conversion {fund.cash_conversion:.2f} — weak profit-to-cash translation",
        )

    if fund.share_count_cagr_3y is not None and fund.share_count_cagr_3y > 0.05:
        flag(
            "DILUTION", 2,
            f"Share count growing {fund.share_count_cagr_3y:.1%}/yr — persistent dilution",
        )

    fcf_values = [v for _, v in fin.series("fcf")[-3:]]
    if fcf_values and sum(fcf_values) < 0:
        flag("NEGATIVE_FCF", 2, "Cumulative free cash flow negative over the last 3 years")

    if val.implied_growth is not None and val.implied_growth > 0.30:
        flag(
            "VALUATION_HOT", 2,
            f"Market pricing {val.implied_growth:.0%} growth — little room for error",
        )
    elif val.peg is not None and val.peg > 3:
        flag("VALUATION_HOT", 1, f"PEG {val.peg:.1f} — expensive relative to delivered growth")

    if tech.avg_traded_value_20d is not None:
        threshold = (
            MIN_TRADED_VALUE_INR
            if info.ticker.endswith((".NS", ".BO"))
            else MIN_TRADED_VALUE_USD
        )
        if tech.avg_traded_value_20d < threshold:
            flag(
                "MICRO_ILLIQUID", 2,
                "Thinly traded — exit slippage risk and manipulation exposure",
            )

    if tech.atr_pct is not None and tech.atr_pct > 6:
        flag("DRAWDOWN_VOL", 1, f"ATR {tech.atr_pct:.1f}% of price — violent drawdowns likely")

    if info.insider_pct is None:
        flag(
            "GOVERNANCE_UNKNOWN", 1,
            "Promoter/insider holding unavailable from current data source",
        )

    score = float(min(100, sum(f.severity for f in flags) * 12))
    if score < 25:
        bucket = "low"
    elif score < 50:
        bucket = "medium"
    else:
        bucket = "high"

    return RiskAssessment(flags=flags, risk_score=score, permanent_loss_bucket=bucket)
