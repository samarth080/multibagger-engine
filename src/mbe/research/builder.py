"""Build one canonical company-research payload from normalized public inputs."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from mbe.financials.document_fetch import OFFICIAL_ALLOWED_HOSTS
from mbe.research.domain import (
    ChecklistItem, CompanyResearch, FilingResearch, FinancialFactResearch,
    FinancialResearch, NewsResearch, PeerResearch, RankingResearch,
    ResearchIdentity, ResearchLineage, ResearchQuote, ScoreComponentResearch,
    ScoreHistoryPoint, ScoreHistoryResearch, TechnicalResearch,
)
from mbe.research.explanations import explain, split_strengths_and_risks
from mbe.research.peers import select_peers

PUBLIC_FACTS = {
    "revenue": "Revenue", "operating_income": "Operating profit",
    "net_income": "PAT", "cfo": "Cash flow from operations", "fcf": "Free cash flow",
    "total_debt": "Debt", "total_equity": "Net worth",
}


def canonical_company_url(instrument_id: str) -> str:
    return f"/company/{instrument_id}.html"


def _safe_https(url: str | None, *, official: bool = False) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    if official and parsed.hostname.lower() not in OFFICIAL_ALLOWED_HOSTS:
        return None
    return url


def _days_between(newer: str | None, older: str | None) -> int | None:
    if not newer or not older:
        return None
    try:
        left = datetime.fromisoformat(str(newer).replace("Z", "+00:00"))
        right = datetime.fromisoformat(str(older).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (left - right).days


def _iso_utc(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _history(points: list[dict]) -> ScoreHistoryResearch:
    unique = {}
    for point in points:
        normalized = dict(point)
        normalized["built_at"] = _iso_utc(str(normalized["built_at"]))
        normalized["components"] = sorted(
            normalized.get("components", []), key=lambda item: (item.get("name") or "")
        )
        unique[str(point["build_id"])] = normalized
    ordered = sorted(
        unique.values(), key=lambda item: (str(item["built_at"]), str(item["build_id"]))
    )[-26:]
    typed = [ScoreHistoryPoint(**point) for point in ordered]
    if len(typed) < 2:
        summary = "Only one compatible persisted model build is available; no continuous trend is inferred."
    else:
        first, last = typed[0], typed[-1]
        summary = (
            f"Across {len(typed)} compatible builds, score changed by "
            f"{last.multibagger_score - first.multibagger_score:+.1f} and rank changed from {first.rank} to {last.rank}."
        )
    return ScoreHistoryResearch(points=typed, summary=summary, is_continuous=False)


def _financial(raw: dict | None) -> FinancialResearch:
    if not raw:
        return FinancialResearch(
            quality_warnings=["No accepted public financial summary is available."],
            basis_warning="Statement basis is unavailable.",
        )
    selected = str(raw.get("selected_source") or raw.get("source_code") or "unavailable")
    fallback = selected == "yahoo_compatibility"
    values = raw.get("values") or {
        item.get("metric_id"): item.get("value") for item in raw.get("derived_metrics", [])
    }
    facts = []
    for fact in raw.get("facts", []):
        metric_id = fact.get("metric_id")
        if metric_id not in PUBLIC_FACTS or fact.get("value") is None:
            continue
        facts.append(FinancialFactResearch(
            metric_id=metric_id, label=PUBLIC_FACTS[metric_id], value=float(fact["value"]),
            fiscal_year=fact.get("fiscal_year"), unit=fact.get("unit") or "INR",
        ))
    basis = str(raw.get("basis") or "unknown")
    source_label = "Yahoo compatibility fallback" if fallback else (
        "Official NSE filing" if selected == "nse_financial_results" else "Unavailable"
    )
    return FinancialResearch(
        revenue_cagr_3y=values.get("revenue_cagr_3y"), roce_3y=values.get("roce_3y"),
        recent_facts=facts[:8], selected_source=selected, source_label=source_label,
        source_quality_tier=raw.get("source_quality_tier"), fallback=fallback,
        basis=basis, basis_warning=raw.get("basis_reason") if basis == "unknown" else None,
        latest_period=(f"FY{raw['latest_annual_fiscal_year']}" if raw.get("latest_annual_fiscal_year") else None),
        data_cutoff=str(raw.get("data_cutoff") or raw.get("financial_dataset_build", {}).get("source_cutoff") or "") or None,
        source_date=raw.get("official_filing_date"), freshness="unknown",
        quality_status=raw.get("quality_status") or "unavailable",
        quality_warnings=[str(item) for item in raw.get("quality_warnings", [])],
        official_tier_a_status=("accepted" if selected == "nse_financial_results" and raw.get("source_quality_tier") == "A" else "unavailable"),
        reconciliation_status=raw.get("reconciliation_status") or "not_reconciled",
        financial_build_id=raw.get("financial_dataset_build_id") or raw.get("financial_dataset_build", {}).get("financial_dataset_build_id"),
        metric_definition_version=raw.get("metric_definition_version") or raw.get("financial_dataset_build", {}).get("metric_definition_version"),
        source_selection_policy_version=raw.get("selection_policy_version"),
        source_selection_reason=raw.get("source_selection_reason"),
    )


def _news(items: list[dict]) -> list[NewsResearch]:
    accepted = []
    for item in items[:12]:
        confidence = item.get("match_confidence")
        score = float(item.get("relevance_score") or 0)
        link = _safe_https(item.get("link"))
        if confidence not in {"high", "medium"} or score < 55 or not link:
            continue
        accepted.append(NewsResearch(
            title=str(item.get("title") or "Untitled news item"), link=link,
            source=item.get("source"), published=item.get("published"),
            relevance_score=score, match_confidence=confidence,
            match_reasons=[str(reason) for reason in item.get("match_reasons", [])[:4]],
            deduplication_cluster=item.get("deduplication_cluster"),
        ))
    return accepted


def _filings(items: list[dict]) -> list[FilingResearch]:
    rows = []
    for item in items[:20]:
        url = _safe_https(item.get("source_url"), official=True)
        rows.append(FilingResearch(
            filing_id=str(item.get("filing_id")), filing_date=str(item.get("filing_date") or "") or None,
            category=str(item.get("filing_type") or "financial results"),
            subject=str(item.get("subject") or item.get("filing_type") or "Financial result filing"),
            period_type=str(item.get("period_type") or "unknown"), basis=str(item.get("basis") or "unknown"),
            revision_state="revised" if item.get("revision_number", 0) else "original",
            parsing_status=str(item.get("parsing_status") or "metadata_only"),
            acceptance_status=str(item.get("acceptance_status") or "not accepted for public metric use"),
            source_url=url,
        ))
    return sorted(rows, key=lambda item: (item.filing_date or "", item.filing_id), reverse=True)


CHECKLIST = [
    ChecklistItem(code="financials", label="Review the latest company financial summary"),
    ChecklistItem(code="quarterly_filing", label="Read the latest quarterly result filing when available"),
    ChecklistItem(code="annual_filing", label="Read the latest annual result filing when available"),
    ChecklistItem(code="score_history", label="Check score and rank changes"),
    ChecklistItem(code="model_risks", label="Review the main model risks"),
    ChecklistItem(code="peers", label="Compare with industry peers"),
    ChecklistItem(code="news", label="Review recent high-confidence news"),
    ChecklistItem(code="lineage", label="Check data sources and freshness"),
    ChecklistItem(code="methodology", label="Read the methodology and verify primary sources"),
]


def build_company_research(
    *, identity: dict, ranking: dict, model_build: dict | None, financial: dict | None,
    technical: dict | None, history: list[dict], peer_candidates: list[dict],
    universe_medians: dict[str, float | None], news: list[dict] | None = None,
    filings: list[dict] | None = None, generated_at: str, data_mode: str = "static",
    quote: dict | None = None,
) -> CompanyResearch:
    instrument_id = str(identity["instrument_id"])
    symbol = str(identity.get("symbol") or identity.get("nse_symbol") or "")
    canonical_url = canonical_company_url(instrument_id)
    legacy_url = f"/reports/{symbol}_NS.html" if symbol and str(identity.get("exchange") or "NSE") == "NSE" else None
    research_identity = ResearchIdentity(
        instrument_id=instrument_id, company_id=identity.get("company_id"),
        display_name=str(identity.get("display_name") or identity.get("legal_name") or symbol),
        legal_name=identity.get("legal_name"), symbol=symbol,
        exchange=str(identity.get("exchange") or "NSE"), bse_code=identity.get("bse_code"),
        isin=identity.get("isin"), sector=identity.get("sector"), industry=identity.get("industry"),
        market_cap_category=identity.get("market_cap_category"), is_sme=identity.get("is_sme"),
        listing_status=str(identity.get("listing_status") or "active"),
        canonical_url=canonical_url, legacy_url=legacy_url,
    )
    build = model_build or {}
    components = [
        ScoreComponentResearch(**item)
        for item in sorted(ranking.get("components", []), key=lambda value: value.get("name") or "")
    ]
    previous = ranking.get("previous") or {}
    previous_rank = ranking.get("previous_rank", previous.get("rank"))
    previous_score = ranking.get("previous_multibagger_score", previous.get("multibagger_score"))
    current_rank, current_score = int(ranking["rank"]), float(ranking["multibagger_score"])
    rank_change = ranking.get("rank_change")
    if rank_change is None and previous_rank is not None:
        rank_change = int(previous_rank) - current_rank
    score_change = ranking.get("score_change")
    if score_change is None and previous_score is not None:
        score_change = current_score - float(previous_score)
    rank_domain = RankingResearch(
        rank=current_rank, previous_rank=previous_rank, rank_change=rank_change,
        multibagger_score=current_score, previous_score=previous_score, score_change=score_change,
        investment_score=float(ranking.get("investment_score") or 0),
        confidence=float(ranking.get("confidence") or 0), risk_score=float(ranking.get("risk_score") or 0),
        investability=str(ranking.get("investability") or "Unavailable"),
        technical_trend=str(ranking.get("technical_trend") or "unknown"),
        momentum_rank=ranking.get("group_rank") or (technical or {}).get("momentum_rank"),
        coverage_quality=ranking.get("coverage_quality"), has_missing_data=bool(ranking.get("has_missing_data")),
        positive_signal_count=int(ranking.get("positive_signal_count") or 0),
        red_flag_count=int(ranking.get("red_flag_count") or 0),
        model_version=build.get("model_version"), model_build_id=build.get("build_id"),
        build_timestamp=str(build.get("built_at") or generated_at),
        data_cutoff=str(build.get("data_cutoff") or generated_at), validation_status=build.get("validation_status"),
        components=components,
    )
    financial_domain = _financial(financial)
    explanation_inputs = {
        "multibagger_score": current_score, "confidence": rank_domain.confidence,
        "risk_score": rank_domain.risk_score, "rank_change": rank_domain.rank_change,
        "technical_trend": rank_domain.technical_trend,
        "revenue_cagr_3y": financial_domain.revenue_cagr_3y, "roce_3y": financial_domain.roce_3y,
        "financial_source": financial_domain.source_label, "financial_fallback": financial_domain.fallback,
        "financial_freshness": financial_domain.freshness,
        "has_missing_data": rank_domain.has_missing_data, "coverage_quality": rank_domain.coverage_quality,
    }
    explanations = explain(explanation_inputs, universe_medians)
    strengths, risks = split_strengths_and_risks(explanations)
    peer_rows = select_peers({
        "instrument_id": instrument_id, "industry": research_identity.industry,
        "sector": research_identity.sector, "market_cap_category": research_identity.market_cap_category,
        "multibagger_score": current_score, "revenue_cagr_3y": financial_domain.revenue_cagr_3y,
        "roce_3y": financial_domain.roce_3y,
    }, peer_candidates)
    peers = [PeerResearch(**{key: value for key, value in row.items() if key != "peer_policy_version"}) for row in peer_rows]
    quote_raw = quote or {}
    price = quote_raw.get("price")
    quote_domain = ResearchQuote(
        price=price, absolute_change=quote_raw.get("absolute_change"), percentage_change=quote_raw.get("percentage_change"),
        currency=str(quote_raw.get("currency") or "INR"), market_status=str(quote_raw.get("market_status") or "unavailable"),
        timestamp=quote_raw.get("timestamp"), delay_minutes=quote_raw.get("delay_minutes"),
        stale=bool(quote_raw.get("stale", True)), state=quote_raw.get("state") or ("build_close" if price is not None else "unavailable"),
        message=str(quote_raw.get("message") or ("Build-close price context; request a current quote before relying on it." if price is not None else "Quote unavailable; the rest of the research page remains usable.")),
    )
    accepted_news = _news(news or [])
    accepted_filings = _filings(filings or [])
    history_domain = _history(history)
    trend = technical or {}
    technical_domain = TechnicalResearch(
        trend=str(trend.get("trend") or rank_domain.technical_trend), momentum_rank=trend.get("momentum_rank"),
        momentum_group=trend.get("momentum_group"), momentum_score=trend.get("momentum_score"),
        return_3m=trend.get("return_3m"), return_6m=trend.get("return_6m"),
        return_12m=trend.get("return_12m"), relative_strength_3m=trend.get("relative_strength_3m"),
        message="Technical fields are descriptive current-build context and are not a trading signal.",
    )
    summary = [
        f"{research_identity.display_name} ranks {current_rank} in the latest Nifty Smallcap 250 model build.",
        f"Its Multibagger Score is {current_score:.1f}, with {rank_domain.confidence:.0%} model confidence and a risk score of {rank_domain.risk_score:.0f}.",
        f"Three-year revenue CAGR is {financial_domain.revenue_cagr_3y:.1%}." if financial_domain.revenue_cagr_3y is not None else "Three-year revenue CAGR is unavailable.",
        f"Three-year average ROCE is {financial_domain.roce_3y:.1%}." if financial_domain.roce_3y is not None else "Three-year average ROCE is unavailable.",
        f"Financial metrics use {financial_domain.source_label.lower()}; accepted Tier-A official NSE coverage is unavailable for this instrument.",
    ]
    news_cutoff = max((item.published or "" for item in accepted_news), default="") or None
    financial_age_days = _days_between(rank_domain.data_cutoff, financial_domain.data_cutoff)
    news_age_days = _days_between(rank_domain.data_cutoff, news_cutoff) if accepted_news else None
    warnings = list(dict.fromkeys([
        *financial_domain.quality_warnings,
        "The financial build is more than 45 days older than the model cutoff." if financial_age_days is not None and financial_age_days > 45 else "",
        "The entity-matched news cutoff is more than 14 days older than the model cutoff." if news_age_days is not None and news_age_days > 14 else "",
        "The financial source-selection policy differs from the expected public policy version." if financial_domain.source_selection_policy_version not in {None, "2026-08-01.2"} else "",
        "Only one score-history point is available; no historical continuity is inferred." if len(history_domain.points) < 2 else "",
        "No public-safe official filing metadata is present in this static build." if not accepted_filings else "",
        "No accepted entity-matched company news is present at this build cutoff." if not accepted_news else "",
        "The quote is unavailable or stale." if quote_domain.stale else "",
    ]))
    warnings = [item for item in warnings if item]
    lineage = ResearchLineage(
        model_build_id=rank_domain.model_build_id, financial_build_id=financial_domain.financial_build_id,
        model_version=rank_domain.model_version,
        financial_metric_definition_version=financial_domain.metric_definition_version,
        source_selection_policy_version=financial_domain.source_selection_policy_version,
        data_cutoff=rank_domain.data_cutoff, quote_timestamp=quote_domain.timestamp,
        news_cutoff=news_cutoff, generated_at=generated_at, data_mode=data_mode,
        financial_source=financial_domain.source_label,
        financial_source_quality_tier=financial_domain.source_quality_tier,
        official_tier_a_status=financial_domain.official_tier_a_status,
        known_limitations=warnings,
    )
    return CompanyResearch(
        identity=research_identity, quote=quote_domain, ranking=rank_domain,
        research_summary=summary, explanations=explanations, strengths=strengths, risks=risks,
        history=history_domain, financials=financial_domain, technical=technical_domain,
        peers=peers, filings=accepted_filings,
        filings_state=("available" if accepted_filings else "unavailable — no public-safe filing metadata in this build"),
        news=accepted_news, news_state=("available" if accepted_news else "unavailable at the current entity-match threshold"),
        checklist=CHECKLIST, lineage=lineage, warnings=warnings,
        feature_flags={"quote_enhancement": True, "history_chart": bool(history_domain.points),
                       "filings": bool(accepted_filings), "news": bool(accepted_news), "checklist": True},
        methodology_links={"model": "/methodology.html", "financials": "/methodology.html#financial-methodology",
                           "validation": "/methodology.html#validation"},
        compatibility={"model_financial_builds_aligned": bool(rank_domain.model_build_id and financial_domain.financial_build_id),
                       "financial_age_days_at_model_cutoff": financial_age_days,
                       "news_age_days_at_model_cutoff": news_age_days,
                       "peer_model_build_id": rank_domain.model_build_id,
                       "allowed_runtime_differences": ["live quote values", "runtime market status", "news after static cutoff"]},
    )
