"""Universal Research Score engine: combines factor scores into an overall
score, coverage percentage, confidence and report state. Reuses the exact
renormalized-weighted-mean pattern mbe.scoring.pillars.build_pillar and
mbe.scoring.engine.combine already use — missing data is excluded and
weight renormalized within each factor, never scored as zero."""

from __future__ import annotations

from mbe.models.analysis import FundamentalMetrics, RiskAssessment, TechnicalState, ValuationResult
from mbe.models.company import CompanyInfo
from mbe.models.scoring import Evidence
from mbe.universal.classification import classify_company_type
from mbe.universal.domain import CompanyType, ReportState, UniversalFactorScore, UniversalScoreCard
from mbe.universal.policy import (
    FACTOR_WEIGHTS, FINANCIAL_COMPANY_TYPES, MIN_COVERAGE_FULL, MIN_COVERAGE_PARTIAL,
    UNIVERSAL_SCORE_POLICY_VERSION, factors_for_company_type, score_universal_metric,
)


def _combined_values(fund: FundamentalMetrics, tech: TechnicalState, val: ValuationResult) -> dict:
    delivered = fund.profit_cagr_3y if fund.profit_cagr_3y is not None else fund.revenue_cagr_3y
    implied_growth_gap = None
    if val.implied_growth is not None and delivered is not None:
        implied_growth_gap = val.implied_growth - delivered
    return {
        "revenue_cagr_3y": fund.revenue_cagr_3y,
        "profit_cagr_3y": fund.profit_cagr_3y,
        "margin_trend": fund.margin_trend,
        "roe_3y": fund.roe_3y if fund.roe_3y is not None else fund.roe,
        "net_margin": fund.net_margin,
        "roce_3y": fund.roce_3y if fund.roce_3y is not None else fund.roce,
        "debt_to_equity": fund.debt_to_equity,
        "interest_coverage": fund.interest_coverage,
        "net_debt_to_ebitda": fund.net_debt_to_ebitda,
        "current_ratio": fund.current_ratio,
        "fcf_margin": fund.fcf_margin,
        "cash_conversion": fund.cash_conversion,
        "accruals_ratio": fund.accruals_ratio,
        "margin_of_safety": val.margin_of_safety,
        "peg": val.peg,
        "implied_growth_gap": implied_growth_gap,
        "fcf_yield": val.fcf_yield,
        "relative_strength_63d": tech.relative_strength_63d,
        "cmf20": tech.cmf20,
        "trend_state": tech.trend_state if tech.trend_state != "unknown" else None,
        "rsi14": tech.rsi14,
        "dist_52w_high": tech.dist_52w_high,
    }


def _build_factor(name: str, items: list[tuple[str, float, str]], values: dict) -> UniversalFactorScore:
    evidence: list[Evidence] = []
    weighted_points = 0.0
    weight_present = 0.0
    excluded: list[str] = []
    for metric, weight, rationale in items:
        value = values.get(metric)
        if value is None:
            excluded.append(metric)
            continue
        scored = score_universal_metric(metric, value)
        if scored is None:
            excluded.append(metric)
            continue
        points, benchmark = scored
        evidence.append(Evidence(
            metric=metric, value=round(value, 6) if isinstance(value, float) else value,
            benchmark=benchmark, points=points, weight=weight, rationale=rationale,
        ))
        weighted_points += weight * points
        weight_present += weight
    score = weighted_points / weight_present if weight_present > 0 else None
    return UniversalFactorScore(
        name=name, score=score, confidence=weight_present,
        eligible_weight=weight_present, evidence=evidence, excluded_metrics=excluded,
    )


def _risk_factor(risk: RiskAssessment, data_confidence: float) -> UniversalFactorScore:
    score = max(0.0, 100.0 - risk.risk_score)
    evidence = [
        Evidence(
            metric=f"risk_flag:{flag.code}", value=flag.severity, benchmark=flag.detail,
            points=max(0, 100 - flag.severity * 30), weight=0.0, rationale=flag.detail,
        )
        for flag in risk.flags
    ]
    return UniversalFactorScore(
        name="Volatility and risk", score=score, confidence=data_confidence,
        eligible_weight=data_confidence, evidence=evidence,
    )


def _report_state(coverage_fraction: float, has_financials: bool, has_prices: bool) -> ReportState:
    if not has_financials and has_prices:
        return ReportState.TECHNICAL_ONLY
    if not has_financials and not has_prices:
        return ReportState.INSUFFICIENT
    if coverage_fraction >= MIN_COVERAGE_FULL:
        return ReportState.FULL
    if coverage_fraction >= MIN_COVERAGE_PARTIAL:
        return ReportState.PARTIAL
    return ReportState.INSUFFICIENT


def build_universal_score(
    ticker: str,
    info: CompanyInfo,
    fund: FundamentalMetrics,
    tech: TechnicalState,
    val: ValuationResult,
    risk: RiskAssessment,
    *,
    instrument_id: str | None = None,
) -> UniversalScoreCard:
    company_type = classify_company_type(info.sector, info.industry)
    factor_defs = factors_for_company_type(company_type)
    values = _combined_values(fund, tech, val)

    factors = [_build_factor(name, items, values) for name, items in factor_defs.items()]
    data_confidence = (fund.completeness + tech.completeness + val.completeness) / 3
    factors.append(_risk_factor(risk, data_confidence))

    total_possible_weight = sum(FACTOR_WEIGHTS.values())
    scored_weight = sum(FACTOR_WEIGHTS[f.name] for f in factors if f.confidence > 0)
    non_meta_total = total_possible_weight - FACTOR_WEIGHTS["Data quality"]
    non_meta_scored = sum(
        FACTOR_WEIGHTS[f.name] for f in factors if f.confidence > 0 and f.name != "Data quality"
    )
    coverage_pct = round(100 * non_meta_scored / non_meta_total, 1) if non_meta_total else 0.0
    factors.append(UniversalFactorScore(
        name="Data quality", score=coverage_pct, confidence=1.0, eligible_weight=1.0, evidence=[],
    ))
    scored_weight += FACTOR_WEIGHTS["Data quality"]

    overall_score = None
    if scored_weight > 0:
        overall_score = round(
            sum(FACTOR_WEIGHTS[f.name] * f.score for f in factors if f.confidence > 0) / scored_weight, 1
        )

    has_financials = fund.completeness > 0
    has_prices = tech.completeness > 0
    report_state = _report_state(non_meta_scored / non_meta_total if non_meta_total else 0.0, has_financials, has_prices)

    confidence_score = round(
        0.6 * (coverage_pct / 100) + 0.2 * data_confidence + 0.2 * (1.0 if has_prices else 0.0), 3
    )
    confidence_label = "High" if confidence_score >= 0.7 else "Medium" if confidence_score >= 0.4 else "Low"

    excluded_notes: list[str] = []
    if company_type in FINANCIAL_COMPANY_TYPES:
        excluded_notes.append(
            "Capital-efficiency and leverage metrics (ROCE, debt-to-equity, "
            "net-debt-to-EBITDA, interest coverage) are not meaningful for "
            f"{company_type.value.replace('_', ' ')} companies and were excluded "
            "from scoring, not zeroed."
        )

    return UniversalScoreCard(
        instrument_id=instrument_id, ticker=ticker, company_type=company_type,
        overall_score=overall_score, confidence=confidence_label, confidence_score=confidence_score,
        data_coverage_pct=coverage_pct, report_state=report_state, factors=factors,
        policy_version=UNIVERSAL_SCORE_POLICY_VERSION, excluded_factor_notes=excluded_notes,
    )
