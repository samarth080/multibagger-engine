"""Database-backed adapter for the canonical company-research contract."""

from __future__ import annotations

from statistics import median

from sqlalchemy.orm import Session

from mbe.db.repository import PlatformRepository
from mbe.financials.official_repository import filing_list
from mbe.financials.repository import instrument_summary, metric_matrix
from mbe.research.builder import build_company_research, canonical_company_url
from mbe.research.lightweight import _universal_for

PUBLIC_METRICS = ["revenue_cagr_3y", "roce_3y"]


def build_dynamic_research(session: Session, instrument_id: str):
    repo = PlatformRepository(session)
    identity = repo.instrument(instrument_id)
    ranking = repo.ranking_detail(instrument_id)
    if not identity or not ranking:
        return None
    rows, _, build_row = repo.rankings(page=1, page_size=10_000, sort="rank")
    metric_values, financial_build = metric_matrix(session, metrics=PUBLIC_METRICS)
    values_by_metric = {
        metric: [item[metric] for item in metric_values.values() if item.get(metric) is not None]
        for metric in PUBLIC_METRICS
    }
    medians = {
        "multibagger_score": median([row["multibagger_score"] for row in rows]) if rows else None,
        **{metric: median(values) if values else None for metric, values in values_by_metric.items()},
    }
    candidates = [{
        "instrument_id": row["instrument_id"],
        "canonical_url": canonical_company_url(row["instrument_id"]),
        "display_name": row.get("name") or row.get("symbol"), "symbol": row.get("symbol"),
        "rank": row["rank"], "multibagger_score": row["multibagger_score"],
        "confidence": row["confidence"], "risk_score": row["risk_score"],
        "revenue_cagr_3y": metric_values.get(row["instrument_id"], {}).get("revenue_cagr_3y"),
        "roce_3y": metric_values.get(row["instrument_id"], {}).get("roce_3y"),
        "technical_trend": row.get("technical_trend") or "unknown",
        "market_cap_category": None, "source_quality_tier": "B",
        "sector": row.get("sector"), "industry": row.get("industry"),
    } for row in rows]
    financial = instrument_summary(
        session, instrument_id,
        metrics=["revenue", "operating_income", "net_income", "cfo", "fcf", "total_debt", "total_equity", *PUBLIC_METRICS],
        max_periods=5,
    )
    filings = filing_list(session, instrument_id, limit=20)
    build = repo.build_dict(build_row) if build_row else ranking.get("build")
    return build_company_research(
        identity=identity, ranking=ranking, model_build=build, financial=financial,
        technical={"trend": ranking.get("technical_trend") or "unknown"},
        history=repo.score_history(instrument_id, limit=26), peer_candidates=candidates,
        universe_medians=medians, news=[], filings=filings,
        generated_at=str((build or {}).get("built_at") or (financial_build.built_at if financial_build else "")),
        data_mode="dynamic",
        universal=_universal_for(instrument_id),
    )
