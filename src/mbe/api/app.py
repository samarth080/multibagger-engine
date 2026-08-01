"""Versioned read-only platform API. Administrative writes remain CLI-only."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from mbe import __version__
from mbe.api.schemas import (
    ApiError, CompanySummaryData, Envelope, HealthData, InstrumentData, ListingData,
    LookupCandidate, MethodologyData, PageMeta, QuoteBatchData, RankingData, RankingDetailData,
    ScreenerResultData, SearchMetaData, SearchResultData, StatusData,
)
from mbe.data.market import QuoteRequest
from mbe.data.registry import ProviderRegistry, default_registry
from mbe.db.base import create_database_engine, database_url, session_factory
from mbe.db.models import ProviderSymbolRow
from mbe.db.models import InstrumentListingRow, InstrumentRow, ModelBuildRow, ScoreSnapshotRow
from mbe.financials.metrics import FINANCIAL_METRICS, METRIC_DEFINITION_VERSION
from mbe.financials.repository import coverage as financial_coverage_data, instrument_summary as financial_instrument_summary
from mbe.financials.official_repository import (
    filing_detail as official_filing_detail,
    filing_list as official_filing_list,
    reconciliation_summary as official_reconciliation_summary,
)
from mbe.db.repository import PlatformRepository
from mbe.instruments.resolution import InstrumentResolver
from mbe.models.instrument import Freshness, FreshnessState, QualityStatus
from mbe.research.builder import canonical_company_url
from mbe.research.lightweight import RANKING_UNIVERSE_BADGE, SCORING_DISCLOSURE
from mbe.scoring.engine import INVESTMENT_WEIGHTS, MULTIBAGGER_WEIGHTS
from mbe.search.ranking import SEARCH_RANKING_POLICY_VERSION
from mbe.screener.domain import ScreenerQuery, ScreenerValidationError
from mbe.screener.engine import ScreenerEngine
from mbe.screener.registry import FIELD_REGISTRY_VERSION, field_manifest
from mbe.versioning import MODEL_VERSION, VALIDATION_STATUS
from mbe.research.domain import CompanyResearch, ScoreHistoryResearch, PeerResearch
from mbe.research.dynamic import build_dynamic_research

log = logging.getLogger("mbe.api")
MAX_PAGE_SIZE = 100
MAX_QUOTE_INSTRUMENTS = 30
MAX_SCREENER_BODY_BYTES = 65_536


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _pages(total: int, size: int) -> int:
    return math.ceil(total / size) if total else 0


def _envelope(request: Request, data=None, **kwargs):
    return Envelope(data=data, request_id=_request_id(request), **kwargs)


def create_app(
    *, database_connection_url: str | None = None,
    engine: Engine | None = None,
    provider_registry: ProviderRegistry | None = None,
) -> FastAPI:
    configured_url = database_connection_url or database_url(required=False)
    db_engine = engine or (create_database_engine(configured_url) if configured_url else None)
    sessions = session_factory(db_engine) if db_engine else None
    registry = provider_registry or default_registry()

    app = FastAPI(
        title="Multibagger Engine Read API", version="1.0.0",
        description=(
            "Read-only canonical instrument and research-ranking API. "
            "Model output is research tooling, not investment advice."
        ),
    )
    app.state.engine = db_engine
    app.state.registry = registry

    origins = [x.strip() for x in os.environ.get("MBE_CORS_ORIGINS", "").split(",") if x.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
            allow_headers=["Accept", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,80}", supplied)
            else uuid.uuid4().hex
        )
        started = datetime.now(timezone.utc)
        content_length = request.headers.get("content-length")
        content_length_value = (
            int(content_length) if content_length and content_length.isdigit() else 0
        )
        if (
            request.method == "POST"
            and request.url.path == "/api/v1/screener/query"
            and content_length_value > MAX_SCREENER_BODY_BYTES
        ):
            return JSONResponse(
                status_code=413,
                content=Envelope(
                    request_id=request.state.request_id,
                    errors=[ApiError(
                        code="request_too_large",
                        message="The screener request exceeds the 64 KiB limit.",
                    )],
                ).model_dump(mode="json"),
                headers={
                    "X-Request-ID": request.state.request_id,
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer",
                    "X-Frame-Options": "DENY",
                    "Cache-Control": "no-store",
                },
            )
        try:
            response = await call_next(request)
        except Exception:
            log.exception(json.dumps({
                "event": "api_unhandled_error", "request_id": request.state.request_id,
                "path": request.url.path,
            }))
            response = JSONResponse(
                status_code=500,
                content=Envelope(
                    request_id=request.state.request_id,
                    errors=[ApiError(code="internal_error", message="The request could not be completed.")],
                ).model_dump(mode="json"),
            )
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store" if response.status_code >= 400 else "public, max-age=60"
        log.info(json.dumps({
            "event": "api_request", "request_id": request.state.request_id,
            "method": request.method, "path": request.url.path,
            "status": response.status_code,
            "duration_ms": int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
        }))
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [ApiError(
            code="validation_error", message=item.get("msg", "Invalid input"),
            field=".".join(str(x) for x in item.get("loc", [])[1:]) or None,
        ) for item in exc.errors()]
        return JSONResponse(
            status_code=422,
            content=Envelope(request_id=_request_id(request), errors=errors).model_dump(mode="json"),
        )

    def get_session(request: Request):
        if sessions is None:
            raise HTTPException(status_code=503, detail={
                "code": "database_not_configured",
                "message": "Canonical database access is not configured for this deployment.",
            })
        with sessions() as session:
            yield session

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {
            "code": "http_error", "message": str(exc.detail)
        }
        return JSONResponse(
            status_code=exc.status_code,
            content=Envelope(
                request_id=_request_id(request),
                errors=[ApiError(
                    code=detail.get("code", "http_error"),
                    message=detail.get("message", "Request failed"),
                    field=detail.get("field"),
                )],
            ).model_dump(mode="json"),
        )

    @app.get("/api/v1/health", response_model=Envelope[HealthData])
    def health(request: Request):
        db_status = "not_configured"
        service_status = "degraded"
        code = 200
        if db_engine:
            try:
                with db_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                db_status, service_status = "connected", "ok"
            except Exception:
                db_status, service_status, code = "unavailable", "degraded", 503
        payload = _envelope(request, HealthData(
            service_status=service_status, database=db_status,
            application_version=__version__, current_timestamp=datetime.now(timezone.utc),
        ))
        return JSONResponse(status_code=code, content=payload.model_dump(mode="json"))

    @app.get("/api/v1/status", response_model=Envelope[StatusData])
    def status(request: Request, session: Session = Depends(get_session)):
        repo = PlatformRepository(session)
        latest_import = repo.latest_import()
        latest_build = repo.latest_build()
        data = StatusData(
            latest_instrument_import=({
                "import_run_id": latest_import.import_run_id,
                "source_version": latest_import.source_version,
                "status": latest_import.status,
                "started_at": latest_import.started_at,
                "finished_at": latest_import.finished_at,
                "summary": latest_import.summary,
            } if latest_import else None),
            instrument_counts={
                "total": repo.instrument_count(), "active": repo.instrument_count(status="active"),
            },
            latest_model_build=repo.build_dict(latest_build) if latest_build else None,
            quote_providers=registry.health(), datasets=repo.freshness(),
            supported_markets=["IN"], supported_exchanges=["NSE", "BSE"],
        )
        warnings = []
        if not latest_import:
            warnings.append("No instrument import has completed.")
        if not latest_build:
            warnings.append("No model build has been persisted.")
        return _envelope(request, data, warnings=warnings)

    @app.get("/api/v1/instruments", response_model=Envelope[list[InstrumentData]])
    def instruments(
        request: Request, session: Session = Depends(get_session), page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=MAX_PAGE_SIZE), exchange: str | None = None,
        sector: str | None = None, industry: str | None = None,
        listing_status: str | None = None, is_sme: bool | None = None,
        search: str | None = Query(None, max_length=160), sort: str = "name",
    ):
        try:
            rows, total = PlatformRepository(session).list_instruments(
                page=page, page_size=page_size, exchange=exchange, sector=sector,
                industry=industry, listing_status=listing_status, is_sme=is_sme,
                search=search, sort=sort,
            )
        except ValueError as exc:
            raise HTTPException(422, {"code": "invalid_sort", "message": str(exc)}) from None
        return _envelope(request, [InstrumentData(**row) for row in rows], meta=PageMeta(
            page=page, page_size=page_size, total=total, total_pages=_pages(total, page_size), sort=sort,
        ))

    @app.get("/api/v1/instruments/lookup", response_model=Envelope[list[LookupCandidate]])
    def lookup(
        request: Request, session: Session = Depends(get_session),
        q: str = Query(min_length=1, max_length=160),
        limit: int = Query(10, ge=1, le=20), require_unique: bool = False,
    ):
        candidates = InstrumentResolver(session).resolve(q, limit=limit)
        if require_unique and (
            not candidates or len(candidates) > 1 and candidates[0].score == candidates[1].score
        ):
            raise HTTPException(409, {
                "code": "ambiguous_instrument", "message": "Lookup did not produce one unambiguous candidate."
            })
        return _envelope(request, [LookupCandidate(**c.model_dump()) for c in candidates])

    @app.get("/api/v1/instruments/{instrument_id}", response_model=Envelope[InstrumentData])
    def instrument_detail(request: Request, instrument_id: str, session: Session = Depends(get_session)):
        row = PlatformRepository(session).instrument(instrument_id)
        if not row:
            raise HTTPException(404, {"code": "instrument_not_found", "message": "Instrument was not found."})
        return _envelope(request, InstrumentData(**row))

    def _current_scores(session: Session, instrument_ids: list[str]) -> dict[str, ScoreSnapshotRow]:
        if not instrument_ids:
            return {}
        build = PlatformRepository(session).latest_build()
        if not build:
            return {}
        rows = session.scalars(select(ScoreSnapshotRow).where(
            ScoreSnapshotRow.build_id == build.build_id,
            ScoreSnapshotRow.instrument_id.in_(instrument_ids),
        )).all()
        return {row.instrument_id: row for row in rows}

    def _listing_data(candidate) -> list[ListingData]:
        return [ListingData(
            exchange=listing.exchange, symbol=listing.symbol, bse_code=listing.bse_code,
            isin=listing.isin, listing_status=listing.listing_status or "active",
            is_primary=listing.is_primary, is_sme=listing.is_sme,
        ) for listing in candidate.listings]

    def _fallback_bse_code(candidate) -> str | None:
        if candidate.bse_code:
            return candidate.bse_code
        return next((l.bse_code for l in candidate.listings if l.bse_code), None)

    @app.get("/api/v1/search", response_model=Envelope[list[SearchResultData]])
    def search(
        request: Request, session: Session = Depends(get_session),
        q: str = Query(min_length=1, max_length=160),
        limit: int = Query(10, ge=1, le=20),
        exchange: str | None = Query(None, max_length=8),
        active_only: bool = False,
        include_sme: bool = True,
        include_inactive: bool = True,
    ):
        """Search-universe results: identity for every instrument the
        platform can identify, honestly tagged with research/ranking status.
        Unlike /api/v1/instruments/lookup (kept unchanged for backward
        compatibility), this never omits a company for lacking a score.
        ``exchange`` (NSE/BSE only) scopes to instruments with a listing on
        that exchange. See docs/HANDOVER.md "Search, research and ranking
        universes" and docs/search-architecture.md "Search ranking policy
        version 2"."""
        exchange_filter = exchange.upper() if exchange and exchange.upper() in {"NSE", "BSE"} else None
        candidates = InstrumentResolver(session).resolve(q, limit=limit * 3 if exchange_filter else limit)
        show_only_active = active_only or not include_inactive
        filtered = []
        for candidate in candidates:
            if exchange_filter and not any(l.exchange == exchange_filter for l in candidate.listings):
                continue
            if show_only_active and candidate.listing_status != "active":
                continue
            if not include_sme and candidate.is_sme:
                continue
            filtered.append(candidate)
        filtered = filtered[:limit]
        scores = _current_scores(session, [c.instrument_id for c in filtered])
        results = []
        for candidate in filtered:
            score = scores.get(candidate.instrument_id)
            results.append(SearchResultData(
                instrument_id=candidate.instrument_id, display_name=candidate.display_name,
                symbol=candidate.symbol, exchange=candidate.exchange,
                primary_exchange=candidate.exchange, isin=candidate.isin,
                bse_code=_fallback_bse_code(candidate), sector=candidate.sector,
                sector_source="canonical_platform" if candidate.sector else None,
                industry=candidate.industry,
                industry_source="canonical_platform" if candidate.industry else None,
                listing_status=candidate.listing_status, is_sme=candidate.is_sme,
                listings=_listing_data(candidate),
                result_type="modeled" if score else "known",
                research_available=score is not None,
                rank=score.rank if score else None,
                multibagger_score=float(score.multibagger_score) if score else None,
                confidence=float(score.confidence) if score else None,
                risk_score=float(score.risk_score) if score else None,
                report_url=canonical_company_url(candidate.instrument_id),
                score=candidate.score, matched_by=candidate.matched_by,
                matched_value=candidate.matched_value,
            ))
        return _envelope(request, results)

    @app.get("/api/v1/search/meta", response_model=Envelope[SearchMetaData])
    def search_meta(request: Request, session: Session = Depends(get_session)):
        """Search-universe statistics (Phase 10B)."""
        listings = session.scalars(select(InstrumentListingRow).where(
            InstrumentListingRow.valid_to.is_(None),
        )).all()
        instrument_ids = {listing.instrument_id for listing in listings}
        by_instrument: dict[str, list] = {}
        for listing in listings:
            by_instrument.setdefault(listing.instrument_id, []).append(listing)
        nse_count = sum(1 for ls in by_instrument.values() if any(l.exchange_code == "NSE" for l in ls))
        bse_count = sum(1 for ls in by_instrument.values() if any(l.exchange_code == "BSE" for l in ls))
        cross_listed_count = sum(
            1 for ls in by_instrument.values() if len({l.exchange_code for l in ls}) > 1
        )
        active_count = sum(1 for ls in by_instrument.values() if any(l.status == "active" for l in ls))
        sme_count = sum(1 for ls in by_instrument.values() if any(l.is_sme for l in ls))
        build = PlatformRepository(session).latest_build()
        ranked_count = session.scalar(select(func.count()).select_from(ScoreSnapshotRow).where(
            ScoreSnapshotRow.build_id == build.build_id
        )) if build else 0
        research_count = session.scalar(select(func.count(func.distinct(InstrumentRow.instrument_id))))
        return _envelope(request, SearchMetaData(
            search_schema_version="1.0",
            search_ranking_policy_version=SEARCH_RANKING_POLICY_VERSION,
            nse_count=nse_count, bse_count=bse_count, cross_listed_count=cross_listed_count,
            research_count=int(research_count or 0), ranked_count=int(ranked_count or 0),
            active_count=active_count, sme_count=sme_count,
            generated_at=datetime.now(timezone.utc).isoformat(),
        ))

    @app.get("/api/v1/company/{instrument_id}/summary", response_model=Envelope[CompanySummaryData])
    def company_summary_route(
        request: Request, instrument_id: str, session: Session = Depends(get_session),
    ):
        """Always-available company summary — modeled or not. Never
        fabricates rank/score/badges for a company outside the research
        universe; see mbe.research.lightweight."""
        row = PlatformRepository(session).instrument(instrument_id)
        if not row:
            raise HTTPException(404, {"code": "company_not_found", "message": "No matching listed company."})
        score = _current_scores(session, [instrument_id]).get(instrument_id)
        research_available = score is not None
        all_listings = session.scalars(select(InstrumentListingRow).where(
            InstrumentListingRow.instrument_id == instrument_id,
            InstrumentListingRow.valid_to.is_(None),
        )).all()
        listings = [ListingData(
            exchange=listing.exchange_code, symbol=listing.symbol, bse_code=listing.bse_code,
            isin=listing.isin, listing_status=listing.status or "active",
            is_primary=listing.is_primary, is_sme=listing.is_sme,
        ) for listing in all_listings]
        bse_code = row.get("bse_code") or next((l.bse_code for l in listings if l.bse_code), None)
        quote = None
        try:
            provider_symbol = next(
                (m["provider_symbol"] for m in row.get("provider_mappings", []) if m["provider"] == "yahoo"),
                None,
            )
            if provider_symbol:
                quote = app.state.registry.get("quotes").get_quotes([
                    QuoteRequest(instrument_id=instrument_id, provider_symbol=provider_symbol, exchange=row.get("exchange")),
                ])[0]
        except Exception:
            quote = None
        return _envelope(request, CompanySummaryData(
            instrument_id=instrument_id, display_name=row.get("display_name"),
            legal_name=row.get("legal_name"), symbol=row.get("symbol"), exchange=row.get("exchange"),
            primary_exchange=row.get("exchange"), isin=row.get("isin"), bse_code=bse_code,
            sector=row.get("sector"),
            sector_source="canonical_platform" if row.get("sector") else None,
            industry=row.get("industry"),
            industry_source="canonical_platform" if row.get("industry") else None,
            listing_status=row.get("listing_status"), is_sme=row.get("is_sme"),
            listings=listings,
            result_type="modeled" if research_available else "known",
            research_available=research_available,
            rank=score.rank if score else None,
            multibagger_score=float(score.multibagger_score) if score else None,
            confidence=float(score.confidence) if score else None,
            risk_score=float(score.risk_score) if score else None,
            report_url=canonical_company_url(instrument_id),
            quote=quote,
            ranking_universe_badge=None if research_available else RANKING_UNIVERSE_BADGE,
            scoring_disclosure=None if research_available else SCORING_DISCLOSURE,
        ))

    @app.get("/api/v1/rankings", response_model=Envelope[list[RankingData]])
    def rankings(
        request: Request, session: Session = Depends(get_session), build_id: str | None = None,
        page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=MAX_PAGE_SIZE),
        sector: str | None = None, industry: str | None = None,
        min_score: float | None = Query(None, ge=0, le=100),
        max_risk: float | None = Query(None, ge=0, le=100),
        min_confidence: float | None = Query(None, ge=0, le=1),
        technical_trend: str | None = Query(None, max_length=40),
        search: str | None = Query(None, max_length=80),
        min_rank: int | None = Query(None, ge=1),
        max_rank: int | None = Query(None, ge=1), sort: str = "rank",
    ):
        try:
            rows, total, build = PlatformRepository(session).rankings(
                build_id=build_id, page=page, page_size=page_size, sector=sector,
                industry=industry, min_score=min_score, max_risk=max_risk,
                min_confidence=min_confidence, technical_trend=technical_trend,
                search=search, min_rank=min_rank, max_rank=max_rank, sort=sort,
            )
        except ValueError as exc:
            raise HTTPException(422, {"code": "invalid_sort", "message": str(exc)}) from None
        if build_id and not build:
            raise HTTPException(404, {"code": "build_not_found", "message": "Model build was not found."})
        meta = PageMeta(page=page, page_size=page_size, total=total, total_pages=_pages(total, page_size), sort=sort)
        result = _envelope(request, [RankingData(**row) for row in rows], meta={
            **meta.model_dump(), "build": PlatformRepository.build_dict(build) if build else None,
        })
        return result

    @app.get(
        "/api/v1/rankings/{instrument_id}",
        response_model=Envelope[RankingDetailData],
    )
    def ranking_detail(request: Request, instrument_id: str, session: Session = Depends(get_session), build_id: str | None = None):
        row = PlatformRepository(session).ranking_detail(instrument_id, build_id)
        if not row:
            raise HTTPException(404, {"code": "ranking_not_found", "message": "Ranking was not found."})
        return _envelope(request, RankingDetailData(**row), freshness=Freshness(
            state=FreshnessState.UNKNOWN, reason="Score input freshness varies by provider.",
            quality_status=QualityStatus.WARNING,
        ))

    @app.get("/api/v1/quotes", response_model=Envelope[QuoteBatchData])
    def quotes(
        request: Request, session: Session = Depends(get_session),
        instrument_ids: str = Query(min_length=1, max_length=1200),
    ):
        ids = list(dict.fromkeys(x.strip() for x in instrument_ids.split(",") if x.strip()))
        if not ids:
            raise HTTPException(400, {
                "code": "empty_quote_request", "message": "At least one instrument ID is required."
            })
        if len(ids) > MAX_QUOTE_INSTRUMENTS:
            raise HTTPException(429, {
                "code": "quote_batch_limit", "message": f"At most {MAX_QUOTE_INSTRUMENTS} instruments are allowed."
            })
        mappings = session.scalars(select(ProviderSymbolRow).where(
            ProviderSymbolRow.instrument_id.in_(ids),
            ProviderSymbolRow.provider == "yahoo", ProviderSymbolRow.valid_to.is_(None),
        )).all()
        mapped = {m.instrument_id: m for m in mappings}
        requests = [QuoteRequest(
            instrument_id=instrument_id,
            provider_symbol=mapped[instrument_id].provider_symbol,
        ) for instrument_id in ids if instrument_id in mapped]
        provider = registry.get("quotes")
        results = provider.get_quotes(requests)
        errors = [ApiError(
            code="provider_mapping_missing", message="No public quote mapping is available.",
            field=instrument_id,
        ) for instrument_id in ids if instrument_id not in mapped]
        errors.extend(ApiError(
            code=quote.error_code or "provider_unavailable",
            message=quote.error_message or "Quote unavailable.", field=quote.instrument_id,
        ) for quote in results if quote.error_code)
        successful = [q for q in results if not q.error_code]
        return _envelope(
            request, QuoteBatchData(quotes=successful), errors=errors,
            warnings=["Yahoo Finance is an unofficial delayed provider."]
        )

    @app.get("/api/v1/methodology", response_model=Envelope[MethodologyData])
    def methodology(request: Request):
        return _envelope(request, MethodologyData(**{
            "model_version": MODEL_VERSION,
            "components": {
                "investment": INVESTMENT_WEIGHTS,
                "multibagger": MULTIBAGGER_WEIGHTS,
            },
            "build_cadence": "weekly, Monday before NSE market open",
            "validation_status": VALIDATION_STATUS,
            "data_categories": [
                "fundamentals", "valuation", "technical trend", "risk",
                "descriptive sector context", "descriptive news and policy context",
            ],
            "major_limitations": [
                "Current production fundamentals and quotes depend on unofficial Yahoo data.",
                "News matching uses RSS titles rather than article-body entity extraction.",
                "Backtests retain survivorship and historical-data limitations.",
            ],
            "disclaimer": "Research tooling, not investment advice. Verify source data independently.",
        }))

    @app.get("/api/v1/financials/metrics", response_model=Envelope[dict])
    def financial_metrics(request: Request):
        return _envelope(request, {
            "metric_definition_version": METRIC_DEFINITION_VERSION,
            "metrics": [vars(item) for item in FINANCIAL_METRICS.values()],
        })

    @app.get("/api/v1/financials/coverage", response_model=Envelope[dict])
    def financial_coverage(request: Request, session: Session = Depends(get_session)):
        data = financial_coverage_data(session)
        if not data:
            raise HTTPException(503, {"code": "financial_dataset_unavailable", "message": "No completed financial dataset build is available."})
        return _envelope(request, data, warnings=data.get("warnings", []))

    @app.get("/api/v1/instruments/{instrument_id}/financials", response_model=Envelope[dict])
    def instrument_financials(request: Request, instrument_id: str,
        period_type: str | None = Query(None, pattern="^(annual|quarter|year_to_date|ttm|instant)$"),
        basis: str | None = Query(None, pattern="^(consolidated|standalone|unknown|conflicting)$"),
        max_periods: int = Query(5, ge=1, le=12), latest_only: bool = False,
        as_of: datetime | None = Query(None),
        metrics: str = Query("revenue,operating_income,net_income,cfo,fcf,total_debt,total_equity,revenue_cagr_3y,roce_3y", max_length=600),
        session: Session = Depends(get_session)):
        if session.get(InstrumentRow, instrument_id) is None:
            raise HTTPException(404, {"code": "instrument_not_found", "message": "Instrument was not found."})
        selected = list(dict.fromkeys(item.strip() for item in metrics.split(",") if item.strip()))
        if not selected or len(selected) > 20:
            raise HTTPException(422, {"code": "financial_metric_limit", "message": "Select between 1 and 20 financial metrics."})
        unknown = [item for item in selected if item not in FINANCIAL_METRICS]
        if unknown:
            raise HTTPException(422, {"code": "unknown_financial_metric", "message": f"Unknown financial metric: {unknown[0]}", "field": "metrics"})
        data = financial_instrument_summary(session, instrument_id, metrics=selected,
            max_periods=1 if latest_only else max_periods, period_type=period_type,
            basis=basis, as_of=as_of)
        if not data:
            raise HTTPException(404, {"code": "financials_not_found", "message": "No accepted financial data is available for this instrument."})
        return _envelope(request, data, warnings=[item["message"] for item in data["quality_warnings"]])

    @app.get("/api/v1/instruments/{instrument_id}/filings", response_model=Envelope[list[dict]])
    def instrument_filings(
        request: Request,
        instrument_id: str,
        filing_type: str | None = Query(None, pattern="^(annual_results|quarterly_results)$"),
        date_from: date | None = None,
        date_to: date | None = None,
        basis: str | None = Query(None, pattern="^(consolidated|standalone|unknown|conflicting)$"),
        revised: bool | None = None,
        source: str | None = Query(None, pattern="^nse_financial_results$"),
        limit: int = Query(20, ge=1, le=100),
        as_of: datetime | None = None,
        session: Session = Depends(get_session),
    ):
        if session.get(InstrumentRow, instrument_id) is None:
            raise HTTPException(404, {"code": "instrument_not_found", "message": "Instrument was not found."})
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, {"code": "invalid_date_range", "message": "date_from must not follow date_to.", "field": "date_from"})
        rows = official_filing_list(
            session,
            instrument_id,
            filing_type=filing_type,
            date_from=date_from,
            date_to=date_to,
            basis=basis,
            revised=revised,
            source=source,
            limit=limit,
            as_of=as_of,
        )
        return _envelope(request, rows, meta={"limit": limit, "returned": len(rows)})

    @app.get("/api/v1/filings/{filing_id}", response_model=Envelope[dict])
    def filing_detail(request: Request, filing_id: str, session: Session = Depends(get_session)):
        data = official_filing_detail(session, filing_id)
        if not data:
            raise HTTPException(404, {"code": "filing_not_found", "message": "Official filing metadata was not found."})
        return _envelope(request, data)

    @app.get("/api/v1/instruments/{instrument_id}/financials/reconciliation", response_model=Envelope[list[dict]])
    def financial_reconciliation(
        request: Request,
        instrument_id: str,
        limit: int = Query(20, ge=1, le=100),
        session: Session = Depends(get_session),
    ):
        if session.get(InstrumentRow, instrument_id) is None:
            raise HTTPException(404, {"code": "instrument_not_found", "message": "Instrument was not found."})
        rows = official_reconciliation_summary(session, instrument_id, limit=limit)
        return _envelope(request, rows, meta={"limit": limit, "returned": len(rows)})

    @app.get(
        "/api/v1/instruments/{instrument_id}/research",
        response_model=Envelope[CompanyResearch],
    )
    def company_research(
        request: Request, instrument_id: str, session: Session = Depends(get_session),
    ):
        data = build_dynamic_research(session, instrument_id)
        if not data:
            raise HTTPException(404, {
                "code": "research_not_found",
                "message": "No compatible company research payload is available for this instrument.",
            })
        return _envelope(request, data, warnings=data.warnings, freshness=Freshness(
            state=FreshnessState.UNKNOWN, source_timestamp=data.ranking.data_cutoff,
            normalized_at=data.lineage.generated_at,
            reason="Quote and news can change independently of persisted model and financial builds.",
            quality_status=QualityStatus.WARNING,
        ))

    @app.get(
        "/api/v1/instruments/{instrument_id}/score-history",
        response_model=Envelope[ScoreHistoryResearch],
    )
    def score_history(
        request: Request, instrument_id: str,
        limit: int = Query(26, ge=1, le=52),
        session: Session = Depends(get_session),
    ):
        data = build_dynamic_research(session, instrument_id)
        if not data:
            raise HTTPException(404, {"code": "score_history_not_found", "message": "Score history was not found."})
        history = data.history.model_copy(update={"points": data.history.points[-limit:], "max_points": limit})
        return _envelope(request, history, meta={"limit": limit, "returned": len(history.points)})

    @app.get(
        "/api/v1/instruments/{instrument_id}/peers",
        response_model=Envelope[list[PeerResearch]],
    )
    def company_peers(
        request: Request, instrument_id: str,
        limit: int = Query(6, ge=1, le=8),
        session: Session = Depends(get_session),
    ):
        data = build_dynamic_research(session, instrument_id)
        if not data:
            raise HTTPException(404, {"code": "peers_not_found", "message": "Peer research was not found."})
        return _envelope(request, data.peers[:limit], meta={
            "limit": limit, "returned": min(limit, len(data.peers)),
            "policy_version": data.peer_policy_version,
        })

    @app.get("/api/v1/screener/fields", response_model=Envelope[dict])
    @app.get(
        "/api/v1/screener/metadata", response_model=Envelope[dict],
        include_in_schema=False,
    )
    def screener_fields(
        request: Request, session: Session = Depends(get_session),
    ):
        engine = ScreenerEngine(session)
        build = engine._build(None)
        if not build:
            raise HTTPException(503, {
                "code": "dataset_unavailable",
                "message": "No complete screener model build is available.",
            })
        return _envelope(
            request,
            field_manifest(
                build=PlatformRepository.build_dict(build),
                categorical_values=engine.categorical_values(build.build_id),
            ),
            freshness=Freshness(
                state=FreshnessState.UNKNOWN,
                source_timestamp=build.data_cutoff,
                normalized_at=build.built_at,
                reason="Underlying statement dates vary by provider.",
                quality_status=QualityStatus.WARNING,
            ),
        )

    @app.post(
        "/api/v1/screener/query", response_model=Envelope[ScreenerResultData],
    )
    def screener_query(
        request: Request, query: ScreenerQuery,
        session: Session = Depends(get_session),
    ):
        started = time.perf_counter()
        try:
            result, build = ScreenerEngine(session).query(query)
        except ScreenerValidationError as exc:
            raise HTTPException(422, {
                "code": exc.code, "message": exc.message, "field": exc.field,
            }) from None
        if not build:
            if query.build_id:
                raise HTTPException(404, {
                    "code": "unknown_model_build",
                    "message": "The requested model build is unavailable.",
                })
            raise HTTPException(503, {
                "code": "dataset_unavailable",
                "message": "No complete screener model build is available.",
            })
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        result["dataset"] = {
            "schema_version": query.schema_version,
            "field_registry_version": FIELD_REGISTRY_VERSION,
            "universe": build.universe_name,
            "data_cutoff": build.data_cutoff,
            "generated_at": build.built_at,
            "query_duration_ms": duration_ms,
        }
        result["build"] = PlatformRepository.build_dict(build)
        result["mode"] = "dynamic"
        warnings = result.pop("warnings", [])
        log.info(json.dumps({
            "event": "screener_query", "request_id": _request_id(request),
            "fingerprint": result["query_fingerprint"],
            "conditions": len(query.conditions), "columns": len(query.columns),
            "total": result["pagination"]["total"], "duration_ms": duration_ms,
        }))
        return _envelope(
            request, ScreenerResultData(**result), warnings=warnings,
            freshness=Freshness(
                state=FreshnessState.UNKNOWN,
                source_timestamp=build.data_cutoff,
                normalized_at=build.built_at,
                reason="Underlying statement dates vary by provider.",
                quality_status=QualityStatus.WARNING,
            ),
        )

    return app


def run() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.environ.get("MBE_API_PORT", "8000")))


app = create_app()
