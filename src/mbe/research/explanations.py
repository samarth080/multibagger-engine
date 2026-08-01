"""Versioned deterministic score explanations, strengths and risks."""

from __future__ import annotations

from mbe.research.domain import ResearchExplanation


def _item(code: str, label: str, text: str, classification: str, fields: list[str],
          *, value=None, comparison=None, period=None, source=None, freshness=None) -> ResearchExplanation:
    return ResearchExplanation(
        code=code, label=label, text=text, classification=classification,
        source_field_ids=fields, current_value=value, comparison_value=comparison,
        period=period, source=source, freshness=freshness,
    )


def explain(inputs: dict, medians: dict[str, float | None]) -> list[ResearchExplanation]:
    items: list[ResearchExplanation] = []
    score, median_score = inputs.get("multibagger_score"), medians.get("multibagger_score")
    if score is not None and median_score is not None:
        direction = "above" if score >= median_score else "below"
        items.append(_item(
            "score_vs_universe_median", "Multibagger Score",
            f"Multibagger Score is {score:.1f}, {direction} the compatible covered-universe median of {median_score:.1f}.",
            "positive" if score >= median_score else "warning", ["ranking.multibagger_score"],
            value=score, comparison=median_score, source="current model build",
        ))
    for field, label, code in (
        ("revenue_cagr_3y", "Revenue CAGR", "revenue_cagr_vs_median"),
        ("roce_3y", "ROCE", "roce_vs_median"),
    ):
        value, median_value = inputs.get(field), medians.get(field)
        if value is None:
            items.append(_item(
                f"{field}_unavailable", label,
                f"{label} three-year metric is unavailable for this compatible public dataset.",
                "warning", [f"financials.{field}"], period="3 years",
                source=inputs.get("financial_source"), freshness=inputs.get("financial_freshness"),
            ))
        elif median_value is not None:
            direction = "above" if value >= median_value else "below"
            items.append(_item(
                code, label,
                f"{label} over three years is {value:.1%}, {direction} the compatible covered-universe median of {median_value:.1%}.",
                "positive" if value >= median_value else "warning", [f"financials.{field}"],
                value=value, comparison=median_value, period="3 years",
                source=inputs.get("financial_source"), freshness=inputs.get("financial_freshness"),
            ))
    trend = str(inputs.get("technical_trend") or "unknown")
    if trend != "unknown":
        positive = trend in {"up", "strong_up"}
        negative = trend in {"down", "strong_down"}
        items.append(_item(
            "technical_trend", "Technical trend",
            f"The validated technical trend state is {trend.replace('_', ' ')}.",
            "positive" if positive else "risk" if negative else "neutral",
            ["technical.trend"], value=trend, source="current model build",
        ))
    confidence = inputs.get("confidence")
    if confidence is not None:
        classification = "positive" if confidence >= .9 else "risk" if confidence < .7 else "neutral"
        items.append(_item(
            "model_confidence", "Model confidence",
            f"Model confidence is {confidence:.0%}; this is a coverage indicator, not a probability of investment success.",
            classification, ["ranking.confidence"], value=confidence, source="current model build",
        ))
    risk = inputs.get("risk_score")
    if risk is not None:
        classification = "risk" if risk >= 60 else "warning" if risk >= 35 else "positive"
        items.append(_item(
            "model_risk", "Model risk",
            f"Model risk score is {risk:.0f} on a 0–100 scale where higher means more model flags.",
            classification, ["ranking.risk_score"], value=risk, source="current model build",
        ))
    rank_change = inputs.get("rank_change")
    if rank_change:
        items.append(_item(
            "rank_movement", "Rank movement",
            f"Rank {'improved' if rank_change > 0 else 'declined'} by {abs(int(rank_change))} places versus the previous compatible build.",
            "positive" if rank_change > 0 else "risk", ["ranking.rank", "ranking.previous_rank"],
            value=rank_change, source="compatible model builds",
        ))
    if inputs.get("financial_fallback"):
        items.append(_item(
            "financial_fallback", "Financial source",
            "Public financial metrics use the approved Yahoo compatibility fallback; they are not accepted Tier-A official NSE metrics.",
            "warning", ["financials.selected_source", "financials.official_tier_a_status"],
            value=inputs.get("financial_source"), source=inputs.get("financial_source"),
        ))
    if inputs.get("has_missing_data"):
        items.append(_item(
            "partial_model_inputs", "Coverage quality",
            "Some model inputs are missing; missing values were not replaced with zero.",
            "warning", ["ranking.has_missing_data", "ranking.coverage_quality"],
            value=inputs.get("coverage_quality"), source="current model build",
        ))
    return items


def split_strengths_and_risks(items: list[ResearchExplanation], *, limit: int = 5) -> tuple[list[ResearchExplanation], list[ResearchExplanation]]:
    strengths = [item for item in items if item.classification == "positive"][:limit]
    risks = [item for item in items if item.classification in {"warning", "risk"}][:limit]
    return strengths, risks
