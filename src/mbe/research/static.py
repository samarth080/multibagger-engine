"""Database-independent adapter for weekly company-research snapshots."""

from __future__ import annotations

from statistics import median

from mbe.pipeline import ScreenResult
from mbe.research.builder import build_company_research, canonical_company_url
from mbe.research.lightweight import _universal_for


def _median(rows: list[dict], field: str) -> float | None:
    values = [float(row["values"][field]) for row in rows if row.get("values", {}).get(field) is not None]
    return median(values) if values else None


def build_static_research(data: dict, result: ScreenResult) -> dict[str, dict]:
    rows = data.get("_screener_rows", [])
    medians = {
        "multibagger_score": _median(rows, "multibagger_score"),
        "revenue_cagr_3y": _median(rows, "revenue_cagr_3y"),
        "roce_3y": _median(rows, "roce_3y"),
    }
    identity_by_id = {item["instrument_id"]: item for item in data.get("instruments", [])}
    financial_by_id = {item["instrument_id"]: item for item in data.get("_financial_summaries", [])}
    bundle_by_ticker = {bundle.card.ticker: bundle for bundle in result.ranked}
    top_by_id = {item["instrument_id"]: item for item in data.get("top", [])}
    row_by_id = {item["instrument_id"]: item for item in rows}
    build = data.get("build") or {}
    previous_build = data.get("_previous_model_build") or {}
    candidates = []
    for item in rows:
        values = item["values"]
        identity = identity_by_id.get(item["instrument_id"], {})
        financial = financial_by_id.get(item["instrument_id"], {})
        candidates.append({
            "instrument_id": item["instrument_id"],
            "canonical_url": canonical_company_url(item["instrument_id"]),
            "display_name": identity.get("display_name") or values.get("company") or values.get("nse_symbol"),
            "symbol": identity.get("symbol") or values.get("nse_symbol"),
            "rank": values["rank"], "multibagger_score": values["multibagger_score"],
            "confidence": values["confidence"], "risk_score": values["risk_score"],
            "revenue_cagr_3y": values.get("revenue_cagr_3y"), "roce_3y": values.get("roce_3y"),
            "technical_trend": values.get("technical_trend") or "unknown",
            "market_cap_category": identity.get("market_cap_category"),
            "source_quality_tier": financial.get("source_quality_tier"),
            "sector": identity.get("sector") or values.get("sector"),
            "industry": identity.get("industry") or values.get("industry"),
        })
    pages = {}
    for instrument_id, item in row_by_id.items():
        values = item["values"]
        identity = identity_by_id.get(instrument_id, {})
        symbol = identity.get("symbol") or values.get("nse_symbol") or ""
        ticker = next((key for key in bundle_by_ticker if key.removesuffix(".NS").removesuffix(".BO") == symbol), None)
        bundle = bundle_by_ticker.get(ticker) if ticker else None
        components = ([{
            "name": pillar.name, "score": pillar.score, "confidence": pillar.confidence,
            "evidence_count": len(pillar.evidence),
        } for pillar in bundle.card.pillars] if bundle else [])
        ranking = {
            **values, "components": components,
            "investment_score": values.get("investment_score"),
        }
        history = []
        if previous_build.get("build_id") and values.get("previous_rank") is not None and values.get("previous_multibagger_score") is not None:
            history.append({
                "build_id": previous_build["build_id"],
                "built_at": str(previous_build.get("built_at") or previous_build.get("data_cutoff")),
                "rank": int(values["previous_rank"]),
                "multibagger_score": float(values["previous_multibagger_score"]),
            })
        history.append({
            "build_id": str(build.get("build_id") or f"static-{data['built_at']}"),
            "built_at": str(build.get("built_at") or data["built_at"]),
            "rank": int(values["rank"]), "multibagger_score": float(values["multibagger_score"]),
            "confidence": values.get("confidence"), "risk_score": values.get("risk_score"),
            "investment_score": values.get("investment_score"), "components": components,
        })
        top = top_by_id.get(instrument_id, {})
        technical = {
            "trend": values.get("technical_trend") or "unknown",
            # Only trend is persisted in the canonical dynamic schema today.
            # Other validated technicals remain unavailable here so static and
            # dynamic research contracts do not silently diverge.
        }
        normalized_identity = {
            **identity,
            "instrument_id": instrument_id,
            "display_name": identity.get("display_name") or values.get("company"),
            "symbol": symbol,
            "exchange": identity.get("exchange") or values.get("exchange"),
            "sector": identity.get("sector") or values.get("sector"),
            "industry": identity.get("industry") or values.get("industry"),
        }
        page = build_company_research(
            identity=normalized_identity,
            ranking=ranking, model_build=build, financial=financial_by_id.get(instrument_id),
            technical=technical, history=history, peer_candidates=candidates,
            universe_medians=medians, news=top.get("news", []), filings=[],
            generated_at=data["built_at"], data_mode="static",
            quote={"price": bundle.tech.price if bundle else None, "currency": bundle.info.currency if bundle else "INR",
                   "timestamp": data["built_at"], "state": "build_close", "stale": True},
            universal=_universal_for(instrument_id),
        )
        pages[instrument_id] = page.model_dump(mode="json")
    return pages
