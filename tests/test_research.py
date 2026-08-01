"""Deterministic canonical company-research domain tests."""

from datetime import datetime, timezone

from mbe.research.builder import build_company_research
from mbe.research.domain import EXPLANATION_POLICY_VERSION, PEER_POLICY_VERSION, RESEARCH_SCHEMA_VERSION
from mbe.research.peers import select_peers

NOW = "2026-08-01T08:00:00+00:00"


def _identity(instrument_id="instrument-a", name="Alpha Engineering"):
    return {
        "instrument_id": instrument_id, "display_name": name,
        "legal_name": f"{name} Limited", "symbol": "ALPHA", "exchange": "NSE",
        "isin": "INE000A01018", "sector": "Industrials", "industry": "Engineering",
        "listing_status": "active",
    }


def _ranking(**overrides):
    return {
        "rank": 7, "previous_rank": 18, "rank_change": 11,
        "multibagger_score": 78.2, "previous_multibagger_score": 74.0, "score_change": 4.2,
        "investment_score": 75.0, "confidence": .92, "risk_score": 61.0,
        "investability": "Deep-dive diligence warranted", "technical_trend": "strong_up",
        "coverage_quality": .92, "has_missing_data": True,
        "positive_signal_count": 8, "red_flag_count": 2,
        "components": [{"name": "Quality", "score": 84, "confidence": .9, "evidence_count": 4}],
        **overrides,
    }


def _financial(**overrides):
    return {
        "selected_source": "yahoo_compatibility", "source_quality_tier": "B",
        "selection_policy_version": "2026-08-01.2", "basis": "unknown",
        "basis_reason": "The provider does not identify statement basis.",
        "latest_annual_fiscal_year": 2025, "data_cutoff": NOW,
        "quality_status": "valid_with_warning", "quality_warnings": ["Verify independently."],
        "financial_dataset_build_id": "financial-build", "metric_definition_version": "2026-08-01.1",
        "values": {"revenue_cagr_3y": .184, "roce_3y": .211},
        "facts": [{"metric_id": "revenue", "value": 1_500_000_000, "fiscal_year": 2025, "unit": "INR"}],
        **overrides,
    }


def _build():
    return {
        "build_id": "model-build", "model_version": "model-v1", "built_at": NOW,
        "data_cutoff": NOW, "validation_status": "research validation only",
    }


def _page(**overrides):
    args = dict(
        identity=_identity(), ranking=_ranking(), model_build=_build(), financial=_financial(),
        technical={"trend": "strong_up", "return_3m": .12},
        history=[{"build_id": "old", "built_at": "2026-07-25T08:00:00+00:00", "rank": 18, "multibagger_score": 74.0},
                 {"build_id": "model-build", "built_at": NOW, "rank": 7, "multibagger_score": 78.2,
                  "confidence": .92, "risk_score": 61, "investment_score": 75}],
        peer_candidates=[], universe_medians={"multibagger_score": 63, "revenue_cagr_3y": .121, "roce_3y": .15},
        news=[], filings=[], generated_at=NOW,
    )
    args.update(overrides)
    return build_company_research(**args)


def test_complete_payload_is_versioned_deterministic_and_never_overclaims_official_data():
    page = _page()
    assert page.schema_version == RESEARCH_SCHEMA_VERSION
    assert page.identity.canonical_url == "/company/instrument-a.html"
    assert page.ranking.rank_change == 11 and page.ranking.score_change == 4.2
    assert any(item.code == "revenue_cagr_vs_median" for item in page.explanations)
    assert any(item.code == "financial_fallback" for item in page.risks)
    assert all(item.version == EXPLANATION_POLICY_VERSION for item in page.explanations)
    assert page.financials.source_label == "Yahoo compatibility fallback"
    assert page.financials.official_tier_a_status == "unavailable"
    assert "buy" not in " ".join(page.research_summary).lower()
    public = page.model_dump(mode="json")
    assert "cache_path" not in str(public) and "operator" not in str(public).lower()


def test_missing_inputs_are_honest_and_do_not_generate_unsupported_claims():
    page = _page(
        ranking=_ranking(confidence=.5, risk_score=10, technical_trend="unknown", has_missing_data=True),
        financial=None, history=[], news=[{
            "title": "Low confidence", "link": "https://example.com/news", "relevance_score": 20,
            "match_confidence": "low", "match_reasons": ["symbol only"],
        }],
    )
    assert page.quote.price is None and page.quote.state == "unavailable"
    assert page.financials.revenue_cagr_3y is None
    assert page.news == [] and "threshold" in page.news_state
    assert page.history.points == [] and "no continuous trend" in page.history.summary.lower()
    assert any(item.code == "revenue_cagr_3y_unavailable" for item in page.explanations)


def test_peer_policy_prefers_industry_then_score_and_is_stable():
    target = {"instrument_id": "a", "industry": "Engineering", "sector": "Industrials",
              "market_cap_category": None, "multibagger_score": 70, "revenue_cagr_3y": .2, "roce_3y": .15}
    base = {"canonical_url": "/company/x.html", "confidence": .9, "risk_score": 20,
            "technical_trend": "up", "market_cap_category": None, "source_quality_tier": "B",
            "sector": "Industrials", "revenue_cagr_3y": .2, "roce_3y": .15}
    candidates = [
        {**base, "instrument_id": "sector", "display_name": "Sector", "symbol": "SEC", "rank": 1,
         "multibagger_score": 70, "industry": "Services"},
        {**base, "instrument_id": "industry-far", "display_name": "Far", "symbol": "FAR", "rank": 3,
         "multibagger_score": 50, "industry": "Engineering"},
        {**base, "instrument_id": "industry-near", "display_name": "Near", "symbol": "NEAR", "rank": 2,
         "multibagger_score": 69, "industry": "Engineering"},
        {**base, "instrument_id": "unrelated", "display_name": "Other", "symbol": "OTH", "rank": 4,
         "multibagger_score": 70, "industry": "Banking", "sector": "Financials"},
    ]
    selected = select_peers(target, candidates, limit=3)
    assert [item["instrument_id"] for item in selected] == ["industry-near", "industry-far", "sector"]
    assert selected[0]["selection_reasons"][0] == "Same industry"
    assert all(item["peer_policy_version"] == PEER_POLICY_VERSION for item in selected)
    assert all(item["instrument_id"] not in {"a", "unrelated"} for item in selected)


def test_news_and_filing_links_fail_closed():
    page = _page(
        news=[{"title": "Unsafe", "link": "javascript:alert(1)", "relevance_score": 90,
               "match_confidence": "high", "match_reasons": ["full company name"]}],
        filings=[{"filing_id": "f1", "source_url": "https://evil.example/filing.xml",
                  "filing_type": "annual_results", "period_type": "annual"}],
    )
    assert page.news == []
    assert page.filings[0].source_url is None


def test_history_is_ordered_deduplicated_and_bounded():
    points = [{"build_id": f"b{i}", "built_at": f"2026-07-{(i % 28) + 1:02d}T00:00:00+00:00",
               "rank": i + 1, "multibagger_score": 50 + i / 10} for i in range(30)]
    points.append({**points[-1], "rank": 1})
    page = _page(history=points)
    assert len(page.history.points) == 26
    assert page.history.points == sorted(page.history.points, key=lambda item: (item.built_at, item.build_id))
