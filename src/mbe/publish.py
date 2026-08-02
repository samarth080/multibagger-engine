"""Static publisher and progressive-application snapshot builder.

The weekly build remains database-independent. Jinja emits meaningful HTML;
the shared browser layer progressively normalizes dynamic `/api/v1` responses
or the versioned static snapshots written beside the pages.
"""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

from mbe.coverage.domain import CoverageAssessment
from mbe.data.news_rss import NewsItem
from mbe.models.instrument import BuildManifest, stable_company_id, stable_instrument_id
from mbe.pipeline import AnalysisBundle, ScreenResult
from mbe.report.charts import build_charts
from mbe.report.markdown import render_report
from mbe.scoring.engine import INVESTMENT_WEIGHTS, MULTIBAGGER_WEIGHTS
from mbe.scoring.sector_themes import CURATED_AS_OF, themes_for
from mbe.screener.registry import FIELD_REGISTRY_VERSION, SCREENER_FIELDS, field_manifest
from mbe.financials.projection import financial_build, project_history
from mbe.research.builder import canonical_company_url
from mbe.research.coverage import build_coverage_research
from mbe.research.static import build_static_research
from mbe.search.catalog import build_search_index
from mbe.search.ranking import SEARCH_RANKING_POLICY_VERSION
from mbe.versioning import MODEL_VERSION, VALIDATION_STATUS

TOP_N = 25
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
ASSET_DIR = FRONTEND_DIR / "assets"
TEMPLATE_DIR = FRONTEND_DIR / "templates"
# Search universe: every NSE-listed security, independent of the pinned
# research/ranking master above. See docs/HANDOVER.md "Search, research and
# ranking universes" — search must never be limited to what is scored.
SEARCH_UNIVERSE_PATH = Path("universes/nse-search-universe.json")
# BSE cross-listing source (Phase 10B): additive, never authoritative for
# ranking. See docs/search-architecture.md "BSE coverage and honesty about
# sourcing" for why this is a small curated fixture, not full BSE breadth.
BSE_SEARCH_UNIVERSE_PATH = Path("universes/bse-search-universe.json")
PUBLIC_SITE_URL = os.environ.get(
    "MBE_PUBLIC_SITE_URL", "https://multibagger-engine.vercel.app"
).rstrip("/")

VALIDATION_FOOTER = (
    "Model validation status: the multibagger score showed a cross-sample-"
    "consistent 2-year IC of +0.16/+0.10 on disjoint Indian smallcap samples "
    "(2016-2023 cutoffs) — a modest, survivorship-biased edge, not a "
    "guarantee. Sector momentum failed its pre-registered ablation and is "
    "shown as context only, never scored. Research tooling, not investment "
    "advice."
)

# Compatibility exports retained for existing API/tests while real styling and
# behavior now live in reusable source assets.
THEME_BOOT = '<script src="/assets/theme.js"></script>'
THEME_TOGGLE = '<button class="theme-toggle" type="button" data-theme-toggle>Toggle theme</button>'
THEME_CSS = f"<style>\n{(ASSET_DIR / 'app.css').read_text()}\n</style>"

_ENV = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _data_mode() -> str:
    value = os.environ.get("MBE_FRONTEND_DATA_MODE", "auto").strip().lower()
    if value not in {"auto", "api", "static"}:
        raise ValueError("MBE_FRONTEND_DATA_MODE must be auto, api or static")
    return value


def _dump_news(
    items: list[NewsItem],
    built_at: datetime,
    *,
    include_match_metadata: bool = True,
) -> list[dict]:
    """Serialize headlines with age relative to the immutable build time."""
    out = []
    for item in items:
        row = item.model_dump(mode="json")
        if not include_match_metadata:
            for key in (
                "relevance_score", "match_confidence", "match_reasons",
                "source_quality",
            ):
                row.pop(key, None)
        age = (
            (built_at.date() - item.published.date()).days
            if item.published else None
        )
        row["age_days"] = age if age is not None and age >= 0 else None
        out.append(row)
    return out


def _canonical_instruments(
    canonical_records: dict[str, dict], instrument_ids: dict[str, str],
) -> list[dict]:
    instruments = []
    for ticker, row in canonical_records.items():
        exchange = row.get("exchange") or (
            "NSE" if ticker.endswith(".NS") else "BSE"
        )
        symbol = row.get("symbol") or ticker.removesuffix(".NS").removesuffix(".BO")
        instrument_id = instrument_ids.get(ticker) or stable_instrument_id(
            exchange_code=exchange, symbol=symbol, isin=row.get("isin")
        )
        instruments.append({
            "instrument_id": instrument_id,
            "company_id": stable_company_id(
                country="IN", isin=row.get("isin"),
                name=row.get("company_name"), fallback=instrument_id,
            ),
            "display_name": row.get("company_name") or symbol,
            "legal_name": row.get("legal_name") or row.get("company_name"),
            "current_legal_name": row.get("company_name"),
            "exchange": exchange,
            "symbol": symbol,
            "nse_symbol": symbol if exchange == "NSE" else None,
            "bse_code": row.get("bse_code"),
            "isin": row.get("isin"),
            "country": "IN",
            "currency": row.get("currency") or "INR",
            "timezone": "Asia/Kolkata",
            "listing_status": row.get("listing_status") or "active",
            "primary_listing": True,
            "is_sme": row.get("is_sme"),
            "security_type": row.get("security_type") or "equity",
            "exchange_segment": row.get("exchange_segment"),
            "exchange_series": row.get("series"),
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "market_cap_category": row.get("market_cap_category"),
            "quality_status": "warning",
            "aliases": [
                ({"type": "alias", "value": alias}
                 if isinstance(alias, str) else alias)
                for alias in row.get("aliases", [])
            ],
            "provider_mappings": [
                {"provider": provider, "provider_symbol": provider_symbol}
                for provider, provider_symbol in row.get(
                    "provider_symbols", {"yahoo": ticker}
                ).items()
            ],
        })
    return sorted(instruments, key=lambda item: (item["display_name"], item["instrument_id"]))


def _main_positive(bundle: AnalysisBundle) -> str | None:
    evidence = [
        item
        for pillar in bundle.card.pillars
        for item in pillar.evidence
        if item.rationale
    ]
    if not evidence:
        return None
    best = max(evidence, key=lambda item: (item.points, item.weight))
    return best.rationale


def _main_risk(bundle: AnalysisBundle) -> str | None:
    risks = [*bundle.card.hard_gate_failures, *bundle.risk.flags]
    return str(risks[0]) if risks else None


def build_data(
    result: ScreenResult,
    news_by_ticker: dict[str, list[NewsItem]],
    policy: list[NewsItem],
    built_at: datetime | None = None,
    *,
    manifest: BuildManifest | None = None,
    instrument_ids: dict[str, str] | None = None,
    canonical_records: dict[str, dict] | None = None,
    previous_screener_rows: list[dict] | None = None,
) -> dict:
    built_at = built_at or datetime.now(timezone.utc)
    group_of: dict[str, tuple[str, int, float]] = {}
    for rank, score in enumerate(result.sector_scores, 1):
        for ticker in score.members:
            group_of[ticker] = (score.name, rank, score.score)

    instrument_ids = instrument_ids or {}
    canonical_records = canonical_records or {}
    previous_by_id = {
        row.get("instrument_id"): row.get("values", {})
        for row in (previous_screener_rows or [])
        if row.get("instrument_id")
    }
    financial_by_ticker = {}
    for bundle in result.ranked:
        ticker = bundle.card.ticker
        canonical = canonical_records.get(ticker, {})
        exchange = "NSE" if ticker.endswith(".NS") else "BSE" if ticker.endswith(".BO") else bundle.info.exchange
        instrument_id = instrument_ids.get(ticker) or stable_instrument_id(
            exchange_code=exchange or "UNKNOWN",
            symbol=ticker.removesuffix(".NS").removesuffix(".BO"),
        )
        financial_by_ticker[ticker] = project_history(
            bundle.fin, instrument_id=instrument_id, cutoff=built_at,
        )
    financial_dataset = financial_build(list(financial_by_ticker.values()), cutoff=built_at)
    for projection in financial_by_ticker.values():
        projection["financial_dataset_build_id"] = financial_dataset["financial_dataset_build_id"]
    top = []
    for rank, bundle in enumerate(result.ranked[:TOP_N], 1):
        ticker = bundle.card.ticker
        canonical = canonical_records.get(ticker, {})
        group, group_rank, group_score = group_of.get(ticker, ("", 0, 0.0))
        exchange = (
            "NSE" if ticker.endswith(".NS") else
            "BSE" if ticker.endswith(".BO") else bundle.info.exchange
        )
        top.append({
            "instrument_id": instrument_ids.get(ticker) or stable_instrument_id(
                exchange_code=exchange or "UNKNOWN",
                symbol=ticker.removesuffix(".NS").removesuffix(".BO"),
            ),
            "rank": rank,
            "ticker": ticker,
            "ticker_path": ticker.replace(".", "_") + ".html",
            "name": canonical.get("company_name") or bundle.info.name or ticker,
            "exchange": exchange,
            "currency": bundle.info.currency,
            "sector": canonical.get("sector") or bundle.info.sector,
            "industry": canonical.get("industry") or bundle.info.industry,
            "isin": canonical.get("isin"),
            "exchange_series": canonical.get("series"),
            "is_sme": canonical.get("is_sme"),
            "provider_symbols": {"yahoo": ticker},
            "mb": bundle.card.multibagger_score,
            "inv": bundle.card.investment_score,
            "conf": bundle.card.confidence,
            "risk": int(bundle.risk.risk_score),
            "trend": bundle.tech.trend_state,
            "price_at_build": bundle.tech.price,
            "group": group,
            "group_rank": group_rank,
            "group_score": group_score,
            "tags": [
                {"theme": theme.theme, "direction": theme.direction}
                for theme in themes_for(bundle.info.sector, bundle.info.industry)
            ],
            "news": _dump_news(news_by_ticker.get(ticker, []), built_at),
            "gated": bool(bundle.card.hard_gate_failures),
            "investability": bundle.card.verdict,
            "positive_signal_count": sum(
                1 for pillar in bundle.card.pillars for evidence in pillar.evidence
                if evidence.points >= 70
            ),
            "red_flag_count": len(bundle.risk.flags) + len(bundle.card.hard_gate_failures),
            "coverage_quality": bundle.card.confidence,
            "main_positive_signal": _main_positive(bundle),
            "main_risk": _main_risk(bundle),
            "components": [
                {
                    "name": pillar.name, "score": pillar.score,
                    "confidence": pillar.confidence,
                    "evidence_count": len(pillar.evidence),
                }
                for pillar in bundle.card.pillars
            ],
            "financial_summary": financial_by_ticker[ticker],
        })

    screener_rows = []
    for rank, bundle in enumerate(result.ranked, 1):
        ticker = bundle.card.ticker
        canonical = canonical_records.get(ticker, {})
        exchange = (
            "NSE" if ticker.endswith(".NS") else
            "BSE" if ticker.endswith(".BO") else bundle.info.exchange
        )
        instrument_id = instrument_ids.get(ticker) or stable_instrument_id(
            exchange_code=exchange or "UNKNOWN",
            symbol=ticker.removesuffix(".NS").removesuffix(".BO"),
        )
        previous = previous_by_id.get(instrument_id, {})
        previous_rank = previous.get("rank")
        previous_score = previous.get("multibagger_score")
        components = {pillar.name: pillar.score for pillar in bundle.card.pillars}
        values = {
            "company": canonical.get("company_name") or bundle.info.name or ticker,
            "nse_symbol": ticker.removesuffix(".NS").removesuffix(".BO"),
            "exchange": exchange,
            "sector": canonical.get("sector") or bundle.info.sector,
            "industry": canonical.get("industry") or bundle.info.industry,
            "rank": rank,
            "previous_rank": previous_rank,
            "rank_change": previous_rank - rank if previous_rank is not None else None,
            "multibagger_score": bundle.card.multibagger_score,
            "previous_multibagger_score": previous_score,
            "score_change": (
                bundle.card.multibagger_score - previous_score
                if previous_score is not None else None
            ),
            "investment_score": bundle.card.investment_score,
            "confidence": bundle.card.confidence,
            "risk_score": bundle.risk.risk_score,
            "positive_signal_count": sum(
                1 for pillar in bundle.card.pillars for evidence in pillar.evidence
                if evidence.points >= 70
            ),
            "red_flag_count": len(bundle.risk.flags) + len(bundle.card.hard_gate_failures),
            "coverage_quality": bundle.card.confidence,
            "has_missing_data": bundle.card.confidence < .999,
            "technical_trend": bundle.tech.trend_state,
            "revenue_cagr_3y": financial_by_ticker[ticker]["values"].get("revenue_cagr_3y"),
            "roce_3y": financial_by_ticker[ticker]["values"].get("roce_3y"),
            "quality_score": components.get("Quality"),
            "growth_score": components.get("Growth"),
            "financial_strength_score": components.get("Financial Strength"),
            "valuation_score": components.get("Valuation"),
            "momentum_score": components.get("Momentum"),
            "size_runway_score": components.get("Size Runway"),
            "reinvestment_score": components.get("Reinvestment"),
            "main_positive_signal": _main_positive(bundle),
            "main_risk": _main_risk(bundle),
        }
        screener_rows.append({
            "instrument_id": instrument_id,
            "values": values,
            "report_url": canonical_company_url(instrument_id),
        })

    instruments = _canonical_instruments(canonical_records, instrument_ids)
    if not instruments:
        instruments = [{
            "instrument_id": row["instrument_id"],
            "display_name": row["name"],
            "legal_name": row["name"],
            "current_legal_name": row["name"],
            "exchange": row["exchange"],
            "symbol": row["ticker"].removesuffix(".NS").removesuffix(".BO"),
            "nse_symbol": row["ticker"].removesuffix(".NS") if row["exchange"] == "NSE" else None,
            "bse_code": None, "isin": row.get("isin"), "country": "IN",
            "currency": row.get("currency") or "INR", "timezone": "Asia/Kolkata",
            "listing_status": "active", "primary_listing": True,
            "is_sme": row.get("is_sme"), "security_type": "equity",
            "exchange_segment": None, "exchange_series": row.get("exchange_series"),
            "sector": row.get("sector"), "industry": row.get("industry"),
            "market_cap_category": None, "quality_status": "warning", "aliases": [],
            "provider_mappings": [{"provider": "yahoo", "provider_symbol": row["ticker"]}],
        } for row in top]
    for item in instruments:
        item["report_url"] = canonical_company_url(item["instrument_id"])

    return {
        "schema_version": "1.1",
        "built_at": built_at.isoformat(),
        "universe": "nifty-smallcap250",
        "build": manifest.model_dump(mode="json") if manifest else None,
        "curated_as_of": CURATED_AS_OF.isoformat(),
        "top": top,
        "instruments": instruments,
        "sectors": [
            {"rank": i, "name": score.name, "level": score.level,
             "score": score.score, "n": score.n}
            for i, score in enumerate(result.sector_scores, 1)
        ],
        "policy": _dump_news(policy, built_at, include_match_metadata=False),
        "_screener_rows": screener_rows,
        "_financial_summaries": list(financial_by_ticker.values()),
        "financial_dataset_build": financial_dataset,
    }


def diff_weeks(prev: dict | None, new: dict) -> dict:
    """Return entrants/exits without changing the stable compatibility shape."""
    new_tickers = [row["ticker"] for row in new["top"]]
    previous = [row["ticker"] for row in (prev or {}).get("top", [])]
    return {
        "entered": [ticker for ticker in new_tickers if ticker not in previous],
        "exited": [ticker for ticker in previous if ticker not in new_tickers],
    }


def peer_bundles(result: ScreenResult, ticker: str) -> list[AnalysisBundle]:
    for group in result.sector_scores:
        if ticker in group.members:
            by_ticker = {bundle.card.ticker: bundle for bundle in result.ranked}
            return [by_ticker[item] for item in group.members if item in by_ticker]
    return []


def _base_context(
    *, title: str, description: str, path: str, active_route: str,
    asset_prefix: str = "/assets", root_href: str = "/",
) -> dict:
    return {
        "page_title": title,
        "page_description": description,
        "canonical_url": f"{PUBLIC_SITE_URL}{path}",
        "active_route": active_route,
        "asset_prefix": asset_prefix,
        "root_href": root_href,
        "methodology_href": f"{root_href.rstrip('/')}/methodology.html" if root_href != "/" else "/methodology.html",
        "data_mode": _data_mode(),
        "noindex": False,
    }


def render_report_page(
    bundle: AnalysisBundle,
    back_href: str = "../index.html",
    news: list[NewsItem] | None = None,
    policy: list[NewsItem] | None = None,
    peers: list[AnalysisBundle] | None = None,
    financial: dict | None = None,
) -> str:
    if financial and financial.get("official_source_url"):
        from urllib.parse import urlsplit
        from mbe.financials.document_fetch import OFFICIAL_ALLOWED_HOSTS
        parsed_source = urlsplit(str(financial["official_source_url"]))
        if parsed_source.scheme != "https" or (parsed_source.hostname or "").lower() not in OFFICIAL_ALLOWED_HOSTS:
            financial = {**financial, "official_source_url": None}
    body = md.markdown(
        render_report(
            bundle, news=news, policy=policy,
            charts=build_charts(bundle, peers),
        ),
        extensions=["tables"],
    )
    context = _base_context(
        title=f"{bundle.card.ticker} research report | Multibagger Engine",
        description=f"Explainable equity research report for {bundle.card.ticker}.",
        path=f"/reports/{bundle.card.ticker.replace('.', '_')}.html",
        active_route="rankings", asset_prefix="../assets", root_href=back_href,
    )
    context["methodology_href"] = (
        "/methodology.html" if back_href.startswith("/") else "../methodology.html"
    )
    return _ENV.get_template("report.html").render(
        **context, body=body, back_href=back_href, financial=financial,
    )


def render_error_page(ticker: str, reason: str) -> str:
    context = _base_context(
        title="Analysis unavailable | Multibagger Engine",
        description="The requested instrument analysis is unavailable.",
        path="/api/analyze", active_route="", asset_prefix="/assets", root_href="/",
    )
    context["noindex"] = True
    return _ENV.get_template("error.html").render(
        **context, ticker=ticker, reason=reason,
    )


def render_coverage_company_page(
    record: dict, quote: dict | None, coverage: CoverageAssessment,
    financial_summary: dict | None = None,
) -> str:
    """Canonical page for a search-universe company at coverage Level 0, 1
    or 2 — rendered on demand by the api/company.py serverless fallback
    (never part of the weekly static build: see docs/HANDOVER.md "Search,
    research and ranking universes" and docs/coverage-architecture.md)."""
    payload = build_coverage_research(record, quote, coverage, financial_summary)
    identity = payload["identity"]
    canonical_path = payload["canonical_url"]
    context = _base_context(
        title=f"{identity['display_name']} ({identity['symbol']}) | Multibagger Engine",
        description=(
            f"Company identity and live quote for {identity['display_name']}. "
            f"{coverage.source_quality_summary}"
        ),
        path=canonical_path, active_route="rankings", asset_prefix="/assets", root_href="/",
    )
    context["canonical_url"] = f"{PUBLIC_SITE_URL}{canonical_path}"
    return _ENV.get_template("company_coverage.html").render(**context, company=payload)


def _render_company_page(research: dict, *, canonical: bool = True) -> str:
    identity = research["identity"]
    canonical_path = identity["canonical_url"]
    context = _base_context(
        title=f"{identity['display_name']} ({identity['symbol']}) research | Multibagger Engine",
        description=(
            f"Explainable Multibagger ranking, financial source lineage, technical context, "
            f"peers, filings and entity-matched news for {identity['display_name']}."
        ),
        path=canonical_path, active_route="rankings", asset_prefix="/assets", root_href="/",
    )
    context["canonical_url"] = f"{PUBLIC_SITE_URL}{canonical_path}"
    context["noindex"] = not canonical
    return _ENV.get_template("company.html").render(**context, research=research)


def _summary(top: list[dict]) -> dict:
    def median(values):
        ordered = sorted(values)
        if not ordered:
            return None
        middle = len(ordered) // 2
        return (
            ordered[middle] if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2
        )

    sectors = Counter(row.get("sector") for row in top if row.get("sector"))
    top_sector, top_sector_count = sectors.most_common(1)[0] if sectors else ("Unavailable", 0)
    median_score = median([float(row["mb"]) for row in top])
    median_confidence = median([float(row["conf"]) * 100 for row in top])
    median_risk = median([float(row["risk"]) for row in top])
    return {
        "total": len(top),
        "median_score": f"{median_score:.1f}" if median_score is not None else "—",
        "median_confidence": f"{median_confidence:.0f}%" if median_confidence is not None else "—",
        "median_risk": f"{median_risk:.0f}" if median_risk is not None else "—",
        "high_confidence": sum(float(row["conf"]) >= .9 for row in top),
        "top_sector": top_sector,
        "top_sector_count": top_sector_count,
    }


def _render_index(data: dict, *, rendered_at: datetime | None = None) -> str:
    built_at = datetime.fromisoformat(data["built_at"].replace("Z", "+00:00"))
    filters = {
        "sectors": sorted({row["sector"] for row in data["top"] if row.get("sector")}),
        "industries": sorted({row["industry"] for row in data["top"] if row.get("industry")}),
        "trends": sorted({row["trend"] for row in data["top"] if row.get("trend")}),
    }
    context = _base_context(
        title="Multibagger Rankings | India Small-cap Research",
        description="Explainable weekly Nifty Smallcap 250 research rankings with score, confidence, risk, freshness and methodology.",
        path="/", active_route="rankings", asset_prefix="/assets", root_href="/",
    )
    return _ENV.get_template("index.html").render(
        **context,
        d=data,
        summary=_summary(data["top"]),
        filters=filters,
        display_built_at=built_at.astimezone().strftime("%d %b %Y, %H:%M %Z"),
        snapshot_stale=((rendered_at or datetime.now(timezone.utc)) - built_at).days > 10,
    )


def _render_methodology(data: dict) -> str:
    components = {}
    for name, weight in MULTIBAGGER_WEIGHTS.items():
        components[f"Multibagger · {name.replace('_', ' ').title()}"] = weight
    for name, weight in INVESTMENT_WEIGHTS.items():
        components[f"Investment · {name.replace('_', ' ').title()}"] = weight
    context = _base_context(
        title="Methodology | Multibagger Engine",
        description="Model components, validation caveats, data limitations and freshness semantics for Multibagger Engine.",
        path="/methodology.html", active_route="methodology",
        asset_prefix="/assets", root_href="/",
    )
    return _ENV.get_template("methodology.html").render(
        **context,
        methodology={
            "model_version": MODEL_VERSION,
            "components": components.items(),
            "validation_status": VALIDATION_STATUS,
            "limitations": [
                "Current production fundamentals and quotes depend on unofficial Yahoo Finance data and can be delayed, stale or unavailable.",
                "News matching uses RSS titles rather than article-body entity extraction; low-confidence matches are hidden.",
                "Backtests retain survivorship and historical point-in-time limitations and do not establish guaranteed outcomes.",
                "The canonical master is Nifty-index focused and does not yet contain complete BSE codes, listing history, SME history or corporate actions.",
                "Confidence describes input coverage; it is not a forecast probability.",
            ],
        },
        build=data.get("build"), built_at=data["built_at"], universe=data["universe"],
    )


def _render_screener(data: dict) -> str:
    built_at = datetime.fromisoformat(data["built_at"].replace("Z", "+00:00"))
    context = _base_context(
        title="Advanced Stock Screener | Multibagger Engine",
        description=(
            "Build explainable screens across the weekly Nifty Smallcap 250 "
            "using typed model, risk, classification and trend fields."
        ),
        path="/screener.html", active_route="screener",
        asset_prefix="/assets", root_href="/",
    )
    return _ENV.get_template("screener.html").render(
        **context,
        build=data.get("build"),
        rows=data.get("_screener_rows", [])[:25],
        total=len(data.get("_screener_rows", [])),
        display_built_at=built_at.astimezone().strftime("%d %b %Y, %H:%M %Z"),
    )


def _render_not_found() -> str:
    context = _base_context(
        title="Page not found | Multibagger Engine",
        description="The requested Multibagger Engine research page is unavailable.",
        path="/404.html", active_route="", asset_prefix="/assets", root_href="/",
    )
    context["noindex"] = True
    return _ENV.get_template("not_found.html").render(**context)


def _copy_assets(out: Path) -> None:
    target = out / "assets"
    target.mkdir(parents=True, exist_ok=True)
    for source in ASSET_DIR.iterdir():
        if source.is_file():
            shutil.copyfile(source, target / source.name)


def render_site(
    data: dict, changes: dict, result: ScreenResult, out_dir,
    *, search_universe_rows: list[dict] | None = None, bse_rows: list[dict] | None = None,
) -> None:
    out = Path(out_dir)
    reports = out / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    _copy_assets(out)
    complete = {**data, "changes": changes}
    research_pages = build_static_research(complete, result)
    public_complete = {
        key: value for key, value in complete.items()
        if key not in {"_screener_rows", "_financial_summaries", "_previous_model_build"}
    }
    (out / "data.json").write_text(json.dumps(public_complete, indent=1))
    if search_universe_rows is None:
        search_universe_rows = json.loads(SEARCH_UNIVERSE_PATH.read_text())["records"]
    if bse_rows is None:
        bse_rows = json.loads(BSE_SEARCH_UNIVERSE_PATH.read_text())["records"]
    _render_static_v1(
        complete, out, research_pages=research_pages,
        search_universe_rows=search_universe_rows, bse_rows=bse_rows,
    )
    company_dir = out / "company"
    company_dir.mkdir(parents=True, exist_ok=True)
    expected_company = {f"{instrument_id}.html" for instrument_id in research_pages}
    for old in company_dir.glob("*.html"):
        if old.name not in expected_company:
            old.unlink()
    for instrument_id, research in research_pages.items():
        (company_dir / f"{instrument_id}.html").write_text(_render_company_page(research))
    published = {row["ticker"] for row in data["top"]}
    expected = {ticker.replace(".", "_") + ".html" for ticker in published}
    for old in reports.glob("*.html"):
        if old.name not in expected:
            old.unlink()
    for row in data["top"]:
        page = _render_company_page(research_pages[row["instrument_id"]], canonical=False)
        (reports / row["ticker_path"]).write_text(page)
    (out / "index.html").write_text(_render_index(public_complete))
    (out / "methodology.html").write_text(_render_methodology(data))
    (out / "screener.html").write_text(_render_screener(data))
    (out / "404.html").write_text(_render_not_found())


def _static_envelope(data, *, meta=None, warnings=None, freshness=None) -> dict:
    return {
        "data": data,
        "meta": meta or {},
        "errors": [],
        "warnings": warnings or [],
        "freshness": freshness,
        "request_id": "static-build",
    }


def build_search_asset_payload(
    *, data: dict, search_universe_rows: list[dict], bse_rows: list[dict],
) -> dict:
    """Build only the public search artifact from frozen, non-model inputs."""
    instruments = data.get("instruments", [])
    screener_rows = data.get("_screener_rows", [])
    search_index = build_search_index(
        search_universe_rows, instruments, screener_rows, bse_rows=bse_rows,
    )
    rows = sorted(
        (record.model_dump(mode="json") for record in search_index),
        key=lambda row: (row["display_name"] or "", row["instrument_id"]),
    )
    bse_count = sum(
        1 for row in rows
        if any(listing["exchange"] == "BSE" for listing in row["listings"])
    )
    cross_listed_count = sum(
        1 for row in rows
        if len({listing["exchange"] for listing in row["listings"]}) > 1
    )
    built_at = data.get("built_at")
    freshness = {
        "state": "unknown", "source": "weekly-static-build",
        "source_timestamp": built_at, "retrieved_at": built_at,
        "normalized_at": built_at, "delay_minutes": None,
        "reason": "Underlying statement dates vary by provider.",
        "quality_status": "warning",
    }
    return _static_envelope(
        rows,
        meta={
            "total": len(rows),
            "research_universe_count": len(instruments),
            "ranking_universe_count": len(screener_rows),
            "nse_count": sum(
                1 for row in rows
                if any(listing["exchange"] == "NSE" for listing in row["listings"])
            ),
            "bse_count": bse_count,
            "cross_listed_count": cross_listed_count,
            "search_universe_source": "nse_listed_securities,bse_listed_securities",
            "search_ranking_policy_version": SEARCH_RANKING_POLICY_VERSION,
        },
        warnings=[
            "Search covers every identified NSE/BSE-listed security. Only "
            "research_available companies have a full research page, "
            "score and rank; others show identity and a live quote only. "
            "BSE coverage is a curated starter set, not full BSE breadth "
            "— see docs/search-architecture.md.",
        ],
        freshness=freshness,
    )


def _render_static_v1(
    data: dict, out: Path, *, research_pages: dict[str, dict] | None = None,
    search_universe_rows: list[dict] | None = None, bse_rows: list[dict] | None = None,
) -> None:
    """Emit normalized v1 contracts for database-free browser clients."""
    api_dir = out / "api" / "v1"
    api_dir.mkdir(parents=True, exist_ok=True)
    top = data.get("top", [])
    instruments = data.get("instruments", [])
    build = data.get("build")
    screener_rows = data.get("_screener_rows", [])
    financial_summaries = data.get("_financial_summaries", [])
    financial_dataset = data.get("financial_dataset_build")
    freshness = {
        "state": "unknown",
        "source": "weekly-static-build",
        "source_timestamp": data.get("built_at"),
        "retrieved_at": data.get("built_at"),
        "normalized_at": data.get("built_at"),
        "delay_minutes": None,
        "reason": "Underlying statement dates vary by provider.",
        "quality_status": "warning",
    }
    rankings = [{
        "instrument_id": row["instrument_id"],
        "rank": row["rank"],
        "previous_rank": row.get("previous_rank"),
        "rank_change": row.get("rank_change"),
        "symbol": row["ticker"].removesuffix(".NS").removesuffix(".BO"),
        "legacy_ticker": row["ticker"],
        "exchange": row.get("exchange"),
        "name": row["name"],
        "sector": row.get("sector"),
        "industry": row.get("industry"),
        "multibagger_score": row["mb"],
        "investment_score": row["inv"],
        "confidence": row["conf"],
        "risk_score": row["risk"],
        "investability": row["investability"],
        "positive_signal_count": row["positive_signal_count"],
        "red_flag_count": row["red_flag_count"],
        "coverage_quality": row["coverage_quality"],
        "has_missing_data": row["conf"] < .999,
        "technical_trend": row.get("trend"),
        "group_rank": row.get("group_rank"),
        "main_positive_signal": row.get("main_positive_signal"),
        "main_risk": row.get("main_risk"),
        "components": row.get("components", []),
        "recent_news": row.get("news", []),
        "report_url": canonical_company_url(row["instrument_id"]),
        "price_at_build": row.get("price_at_build"),
        "freshness": freshness,
    } for row in top]
    search_payload = build_search_asset_payload(
        data=data, search_universe_rows=search_universe_rows or [],
        bse_rows=bse_rows or [],
    )
    files = {
        "search-index.json": search_payload,
        "instruments.json": _static_envelope(
            instruments,
            meta={"page": 1, "page_size": len(instruments), "total": len(instruments),
                  "total_pages": 1 if instruments else 0, "sort": "name"},
            warnings=[
                "Static instrument master is limited to the pinned Nifty Smallcap 250 universe."
            ],
            freshness=freshness,
        ),
        "rankings.json": _static_envelope(
            rankings,
            meta={"page": 1, "page_size": len(rankings), "total": len(rankings),
                  "total_pages": 1 if rankings else 0, "sort": "rank", "build": build},
            freshness=freshness,
        ),
        "status.json": _static_envelope({
            "latest_instrument_import": None,
            "instrument_counts": {
                "master": len(instruments), "published": len(rankings),
            },
            "latest_model_build": build,
            "quote_providers": [
                {"provider": "yahoo", "status": "configured", "capability": "quotes"}
            ],
            "datasets": [{"dataset": "weekly-rankings", **freshness}],
            "supported_markets": ["IN"],
            "supported_exchanges": ["NSE", "BSE"],
        }, warnings=[
            "Persistent database status is available only from the dynamic API."
        ]),
        "screener-fields.json": _static_envelope(
            field_manifest(
                build=build,
                categorical_values={
                    field_id: sorted({
                        row["values"].get(field_id) for row in screener_rows
                        if row["values"].get(field_id) is not None
                    })
                    for field_id in ("exchange", "sector", "industry", "technical_trend")
                },
            ),
            meta={"field_registry_version": FIELD_REGISTRY_VERSION, "build": build},
            freshness=freshness,
        ),
        "screener.json": _static_envelope({
            "schema_version": "1.0",
            "field_registry_version": FIELD_REGISTRY_VERSION,
            "build_id": build.get("build_id") if build else None,
            "data_cutoff": build.get("data_cutoff") if build else data.get("built_at"),
            "generated_at": data.get("built_at"),
            "universe": {
                "id": data.get("universe"),
                "label": "Nifty Smallcap 250",
                "total": len(screener_rows),
                "scope": "full scored weekly universe",
            },
            "supported_fields": list(SCREENER_FIELDS),
            "financial_dataset_build_id": financial_dataset.get("financial_dataset_build_id") if financial_dataset else None,
            "metric_definition_version": financial_dataset.get("metric_definition_version") if financial_dataset else None,
            "financial_coverage": financial_dataset.get("coverage") if financial_dataset else {},
            "rows": screener_rows,
        }, meta={
            "page": 1, "page_size": len(screener_rows), "total": len(screener_rows),
            "total_pages": 1 if screener_rows else 0, "build": build,
            "field_registry_version": FIELD_REGISTRY_VERSION,
        }, warnings=[
            "Static screening is bounded to this weekly Nifty Smallcap 250 build; use API mode for larger or historical datasets."
        ], freshness=freshness),
    }
    for name, payload in files.items():
        (api_dir / name).write_text(json.dumps(payload, indent=1))
    financial_dir = api_dir / "financials"
    financial_dir.mkdir(parents=True, exist_ok=True)
    (financial_dir / "coverage.json").write_text(json.dumps(_static_envelope(
        financial_dataset,
        warnings=(financial_dataset or {}).get("warnings", []),
        freshness={"state": "unknown", "source": "financial-dataset-build",
                   "source_timestamp": (financial_dataset or {}).get("source_cutoff"),
                   "normalized_at": (financial_dataset or {}).get("built_at"),
                   "quality_status": "warning",
                   "reason": "Compatibility provider rows lack filing-date and statement-basis metadata."},
    ), indent=1))
    for summary in financial_summaries:
        payload = {**summary, "financial_dataset_build": financial_dataset}
        (financial_dir / f"{summary['instrument_id']}.json").write_text(
            json.dumps(_static_envelope(payload, warnings=summary.get("quality_warnings", [])), indent=1)
        )
    research_dir = api_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    expected_research = {f"{instrument_id}.json" for instrument_id in (research_pages or {})}
    for old in research_dir.glob("*.json"):
        if old.name not in expected_research:
            old.unlink()
    for instrument_id, research in (research_pages or {}).items():
        (research_dir / f"{instrument_id}.json").write_text(json.dumps(
            _static_envelope(research, warnings=research.get("warnings", []), freshness={
                "state": "unknown", "source": "company-research-static-build",
                "source_timestamp": research.get("lineage", {}).get("data_cutoff"),
                "normalized_at": research.get("lineage", {}).get("generated_at"),
                "quality_status": "warning",
                "reason": "Quote and news may change after the static build cutoff.",
            }), indent=1,
        ))
    sitemap_urls = ["/", "/screener.html", "/methodology.html", *(
        canonical_company_url(instrument_id) for instrument_id in sorted(research_pages or {})
    )]
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
        f"  <url><loc>{PUBLIC_SITE_URL}{path}</loc></url>\n" for path in sitemap_urls
    ) + "</urlset>\n"
    (out / "sitemap.xml").write_text(sitemap)
    (out / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /reports/\n"
        f"Sitemap: {PUBLIC_SITE_URL}/sitemap.xml\n"
    )
