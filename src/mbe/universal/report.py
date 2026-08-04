"""Deterministic Universal Research Score report payload. Template-driven,
no LLM. Deliberately excludes System A's (mbe.report.markdown) 3-Year
Price Forecast, Entry & Exit Framework and Position Sizing sections —
those generate scenario price targets and trading guidance, which
conflicts with this feature's explicit "no fabricated price targets or
recommendations" constraint. FORBIDDEN_REPORT_KEYS below is asserted
against directly by tests so that constraint cannot silently regress."""

from __future__ import annotations

from datetime import datetime

from mbe.universal.domain import UniversalScoreCard
from mbe.universal.explanations import build_strengths_and_risks

FORBIDDEN_REPORT_KEYS = ("price_forecast", "entry_exit_framework", "position_sizing", "price_target")


def _factor(card: UniversalScoreCard, name: str) -> dict:
    factor = next((f for f in card.factors if f.name == name), None)
    if factor is None:
        return {"available": False}
    return {
        "available": factor.score is not None,
        "score": factor.score,
        "confidence": round(factor.confidence, 3),
        "evidence": [e.model_dump(mode="json") for e in factor.evidence],
        "excluded_metrics": factor.excluded_metrics,
    }


def build_universal_report(card: UniversalScoreCard, *, generated_at: datetime) -> dict:
    strengths, risks = build_strengths_and_risks(card)
    return {
        "executive_summary": {
            "overall_score": card.overall_score,
            "confidence": card.confidence,
            "data_coverage_pct": card.data_coverage_pct,
            "report_state": card.report_state.value,
            "company_type": card.company_type.value,
        },
        "company_identity": {"ticker": card.ticker, "instrument_id": card.instrument_id, "company_type": card.company_type.value},
        "universal_score": {
            "overall_score": card.overall_score,
            "confidence": card.confidence,
            "confidence_score": card.confidence_score,
            "data_coverage_pct": card.data_coverage_pct,
        },
        "factor_breakdown": [
            {"name": f.name, "score": f.score, "confidence": round(f.confidence, 3)} for f in card.factors
        ],
        "business_and_financial_quality": _factor(card, "Profitability"),
        "growth": _factor(card, "Growth"),
        "profitability": _factor(card, "Profitability"),
        "capital_efficiency": _factor(card, "Capital efficiency"),
        "balance_sheet_strength": _factor(card, "Financial strength"),
        "cash_flow_quality": _factor(card, "Cash-flow quality"),
        "valuation": _factor(card, "Valuation"),
        "technical_trend": _factor(card, "Technical trend"),
        "momentum": _factor(card, "Momentum"),
        "volatility_and_risk": _factor(card, "Volatility and risk"),
        "strengths": strengths,
        "risks": risks,
        "data_quality_notes": {
            "coverage_pct": card.data_coverage_pct,
            "excluded_factor_notes": card.excluded_factor_notes,
        },
        "methodology": {
            "policy_version": card.policy_version,
            "company_type_policy": card.company_type.value,
            "factor_weights_note": "See docs/universal-research-score-architecture.md for the full weight table.",
        },
        "source_lineage": {"generated_at": generated_at.isoformat()},
    }
