"""Offline validation, inspection and deterministic research rebuild helpers."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median

from mbe.research.builder import build_company_research, canonical_company_url
from mbe.research.domain import CompanyResearch


def load_research_payloads(site_dir: Path, instrument_id: str | None = None) -> dict[str, CompanyResearch]:
    root = site_dir / "api" / "v1" / "research"
    paths = [root / f"{instrument_id}.json"] if instrument_id else sorted(root.glob("*.json"))
    if not paths or any(not path.exists() for path in paths):
        raise ValueError("No matching static company-research payload was found.")
    if len(paths) > 10_000:
        raise ValueError("Research payload count exceeds the offline validation bound.")
    result = {}
    for path in paths:
        envelope = json.loads(path.read_text())
        page = CompanyResearch.model_validate(envelope.get("data"))
        if page.identity.instrument_id != path.stem:
            raise ValueError(f"Instrument/path mismatch: {path}")
        result[path.stem] = page
    return result


def validate_research_site(site_dir: Path, instrument_id: str | None = None) -> dict:
    pages = load_research_payloads(site_dir, instrument_id)
    known = set(load_research_payloads(site_dir)) if instrument_id else set(pages)
    private_markers = ("/Users/", "data/official-pilot", "operator-review", "cache_path", "raw_metadata")
    warnings = 0
    for key, page in pages.items():
        html = site_dir / "company" / f"{key}.html"
        if not html.exists():
            raise ValueError(f"Canonical HTML is missing for {key}.")
        text = html.read_text()
        if any(marker in text for marker in private_markers):
            raise ValueError(f"Private marker found in {html}.")
        if page.identity.canonical_url != canonical_company_url(key):
            raise ValueError(f"Canonical URL mismatch for {key}.")
        for peer in page.peers:
            if peer.instrument_id not in known:
                raise ValueError(f"Unknown peer {peer.instrument_id} referenced by {key}.")
        warnings += len(page.warnings)
    return {"valid": True, "pages": len(pages), "warnings": warnings}


def measure_research_site(site_dir: Path) -> dict:
    payloads = sorted((site_dir / "api" / "v1" / "research").glob("*.json"))
    pages = sorted((site_dir / "company").glob("*.html"))
    payload_sizes = [path.stat().st_size for path in payloads]
    page_sizes = [path.stat().st_size for path in pages]
    return {
        "company_pages": len(pages), "research_payloads": len(payloads),
        "total_company_html_bytes": sum(page_sizes), "total_research_json_bytes": sum(payload_sizes),
        "largest_company_html_bytes": max(page_sizes, default=0),
        "largest_research_json_bytes": max(payload_sizes, default=0),
        "average_company_html_bytes": round(sum(page_sizes) / len(page_sizes), 2) if page_sizes else 0,
        "average_research_json_bytes": round(sum(payload_sizes) / len(payload_sizes), 2) if payload_sizes else 0,
    }


def rebuild_research_payloads(pages: dict[str, CompanyResearch]) -> dict[str, CompanyResearch]:
    """Re-run explanation and peer policies from an existing normalized corpus."""
    all_pages = list(pages.values())
    def values(field):
        return [float(value) for page in all_pages if (value := getattr(page.financials, field, None)) is not None]
    medians = {
        "multibagger_score": median([page.ranking.multibagger_score for page in all_pages]),
        "revenue_cagr_3y": median(values("revenue_cagr_3y")) if values("revenue_cagr_3y") else None,
        "roce_3y": median(values("roce_3y")) if values("roce_3y") else None,
    }
    candidates = [{
        "instrument_id": page.identity.instrument_id, "canonical_url": page.identity.canonical_url,
        "display_name": page.identity.display_name, "symbol": page.identity.symbol,
        "rank": page.ranking.rank, "multibagger_score": page.ranking.multibagger_score,
        "confidence": page.ranking.confidence, "risk_score": page.ranking.risk_score,
        "revenue_cagr_3y": page.financials.revenue_cagr_3y, "roce_3y": page.financials.roce_3y,
        "technical_trend": page.technical.trend, "market_cap_category": page.identity.market_cap_category,
        "source_quality_tier": page.financials.source_quality_tier,
        "sector": page.identity.sector, "industry": page.identity.industry,
    } for page in all_pages]
    rebuilt = {}
    for page in all_pages:
        ranking = page.ranking.model_dump(mode="json")
        ranking["previous_multibagger_score"] = ranking.pop("previous_score")
        model_build = {
            "build_id": page.ranking.model_build_id, "model_version": page.ranking.model_version,
            "built_at": page.ranking.build_timestamp, "data_cutoff": page.ranking.data_cutoff,
            "validation_status": page.ranking.validation_status,
        }
        financial = page.financials.model_dump(mode="json")
        financial["values"] = {"revenue_cagr_3y": page.financials.revenue_cagr_3y, "roce_3y": page.financials.roce_3y}
        financial["facts"] = [item.model_dump(mode="json") for item in page.financials.recent_facts]
        financial["selection_policy_version"] = page.financials.source_selection_policy_version
        rebuilt_page = build_company_research(
            identity=page.identity.model_dump(mode="json"), ranking=ranking, model_build=model_build,
            financial=financial, technical=page.technical.model_dump(mode="json"),
            history=[item.model_dump(mode="json") for item in page.history.points],
            peer_candidates=candidates, universe_medians=medians,
            news=[item.model_dump(mode="json") for item in page.news],
            filings=[item.model_dump(mode="json") for item in page.filings],
            generated_at=page.lineage.generated_at, data_mode=page.lineage.data_mode,
            quote=page.quote.model_dump(mode="json"),
        )
        rebuilt[page.identity.instrument_id] = rebuilt_page
    return rebuilt
