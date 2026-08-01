"""Query and persistence boundary for canonical platform records."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from mbe.db.models import (
    CompanyRow, FreshnessRow, ImportRunRow, IndustryRow, InstrumentAliasRow,
    InstrumentListingRow, InstrumentRow, ModelBuildRow, ProviderSymbolRow,
    ScoreComponentRow, ScoreSnapshotRow, SectorRow,
)
from mbe.models.instrument import BuildManifest
from mbe.pipeline import ScreenResult


def _decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


class PlatformRepository:
    def __init__(self, session: Session):
        self.session = session

    def persist_build(
        self, manifest: BuildManifest, result: ScreenResult,
        instrument_ids: dict[str, str],
    ) -> str:
        missing = sorted({b.card.ticker for b in result.ranked} - instrument_ids.keys())
        if missing:
            raise ValueError(f"canonical mapping missing for: {', '.join(missing[:10])}")
        row = ModelBuildRow(
            build_id=manifest.build_id, model_version=manifest.model_version,
            factor_config_version=manifest.factor_config_version,
            factor_config_hash=manifest.factor_config_hash,
            universe_name=manifest.universe_name,
            universe_version=manifest.universe_version,
            data_cutoff=manifest.data_cutoff, built_at=manifest.built_at,
            status=manifest.status, duration_seconds=_decimal(manifest.duration_seconds),
            attempted_count=manifest.attempted_count, scored_count=manifest.scored_count,
            failed_count=manifest.failed_count, provider_versions=manifest.provider_versions,
            source_data_version=manifest.source_data_version,
            validation_status=manifest.validation_status, notes=manifest.notes,
            error_summary=manifest.error_summary,
        )
        self.session.add(row)
        self.session.flush()
        for rank, bundle in enumerate(result.ranked, 1):
            evidence = [
                item
                for pillar in bundle.card.pillars
                for item in pillar.evidence
                if item.rationale
            ]
            best_evidence = (
                max(evidence, key=lambda item: (item.points, item.weight))
                if evidence else None
            )
            risks = [*bundle.card.hard_gate_failures, *bundle.risk.flags]
            score = ScoreSnapshotRow(
                build_id=manifest.build_id,
                instrument_id=instrument_ids[bundle.card.ticker], rank=rank,
                multibagger_score=_decimal(bundle.card.multibagger_score),
                investment_score=_decimal(bundle.card.investment_score),
                confidence=_decimal(bundle.card.confidence),
                risk_score=_decimal(bundle.risk.risk_score),
                investability=bundle.card.verdict,
                positive_signal_count=sum(
                    1 for pillar in bundle.card.pillars for evidence in pillar.evidence
                    if evidence.points >= 70
                ),
                red_flag_count=len(bundle.risk.flags) + len(bundle.card.hard_gate_failures),
                coverage_quality=_decimal(bundle.card.confidence),
                has_missing_data=bundle.card.confidence < 0.999,
                technical_trend=bundle.tech.trend_state,
                main_positive_signal=(best_evidence.rationale if best_evidence else None),
                main_risk=(str(risks[0]) if risks else None),
            )
            self.session.add(score)
            self.session.flush()
            for pillar in bundle.card.pillars:
                self.session.add(ScoreComponentRow(
                    score_id=score.score_id, component_name=pillar.name,
                    score=_decimal(pillar.score), confidence=_decimal(pillar.confidence),
                    contribution=None, evidence_count=len(pillar.evidence),
                ))
        freshness = self.session.scalar(select(FreshnessRow).where(
            FreshnessRow.dataset == "model_scores",
            FreshnessRow.partition_key == manifest.universe_name,
        ))
        values = {
            "state": "fresh" if manifest.status == "complete" else "failed",
            "source_timestamp": manifest.data_cutoff,
            "retrieved_at": manifest.built_at,
            "normalized_at": manifest.built_at,
            "data_version": manifest.build_id,
            "quality_status": "valid" if manifest.failed_count == 0 else "warning",
            "warning": (
                f"{manifest.failed_count} instruments failed scoring"
                if manifest.failed_count else None
            ),
        }
        if freshness:
            for field, value in values.items():
                setattr(freshness, field, value)
        else:
            self.session.add(FreshnessRow(
                dataset="model_scores", partition_key=manifest.universe_name,
                **values,
            ))
        self.session.commit()
        return manifest.build_id

    def instrument_count(self, *, status: str | None = None) -> int:
        stmt = select(func.count(func.distinct(InstrumentRow.instrument_id))).select_from(InstrumentRow)
        if status:
            stmt = stmt.join(InstrumentListingRow).where(
                InstrumentListingRow.status == status,
                InstrumentListingRow.valid_to.is_(None),
            )
        return int(self.session.scalar(stmt) or 0)

    def latest_import(self) -> ImportRunRow | None:
        return self.session.scalar(select(ImportRunRow).order_by(ImportRunRow.started_at.desc()).limit(1))

    def latest_build(self) -> ModelBuildRow | None:
        return self.session.scalar(select(ModelBuildRow).order_by(ModelBuildRow.built_at.desc()).limit(1))

    def freshness(self) -> list[dict[str, Any]]:
        rows = self.session.scalars(select(FreshnessRow).order_by(
            FreshnessRow.dataset, FreshnessRow.partition_key
        )).all()
        return [{
            "dataset": row.dataset, "partition_key": row.partition_key,
            "state": row.state, "source_timestamp": row.source_timestamp,
            "retrieved_at": row.retrieved_at, "normalized_at": row.normalized_at,
            "data_version": row.data_version, "quality_status": row.quality_status,
            "warning": row.warning,
        } for row in rows]

    def list_instruments(
        self, *, page: int = 1, page_size: int = 25, exchange: str | None = None,
        sector: str | None = None, industry: str | None = None,
        listing_status: str | None = None, is_sme: bool | None = None,
        search: str | None = None, sort: str = "name",
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = (
            select(InstrumentRow, CompanyRow, InstrumentListingRow, SectorRow, IndustryRow)
            .join(InstrumentListingRow, and_(
                InstrumentListingRow.instrument_id == InstrumentRow.instrument_id,
                InstrumentListingRow.is_primary.is_(True),
                InstrumentListingRow.valid_to.is_(None),
            ))
            .outerjoin(CompanyRow, CompanyRow.company_id == InstrumentRow.company_id)
            .outerjoin(SectorRow, SectorRow.sector_id == InstrumentRow.sector_id)
            .outerjoin(IndustryRow, IndustryRow.industry_id == InstrumentRow.industry_id)
        )
        filters = []
        if exchange:
            filters.append(InstrumentListingRow.exchange_code == exchange.upper())
        if sector:
            filters.append(SectorRow.name == sector)
        if industry:
            filters.append(IndustryRow.name == industry)
        if listing_status:
            filters.append(InstrumentListingRow.status == listing_status)
        if is_sme is not None:
            filters.append(InstrumentListingRow.is_sme.is_(is_sme))
        if search:
            term = f"%{search.strip()}%"
            filters.append(or_(
                InstrumentListingRow.symbol.ilike(term),
                InstrumentListingRow.bse_code.ilike(term),
                InstrumentListingRow.isin.ilike(term),
                CompanyRow.display_name.ilike(term),
                CompanyRow.legal_name.ilike(term),
                InstrumentRow.instrument_id.in_(select(InstrumentAliasRow.instrument_id).where(
                    InstrumentAliasRow.normalized_value.ilike(term)
                )),
                InstrumentRow.instrument_id.in_(select(ProviderSymbolRow.instrument_id).where(
                    ProviderSymbolRow.provider_symbol.ilike(term),
                    ProviderSymbolRow.valid_to.is_(None),
                )),
            ))
        stmt = stmt.where(*filters)
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int(self.session.scalar(count_stmt) or 0)
        order = {
            "name": (CompanyRow.display_name.asc(), InstrumentRow.instrument_id.asc()),
            "symbol": (InstrumentListingRow.symbol.asc(), InstrumentRow.instrument_id.asc()),
            "-name": (CompanyRow.display_name.desc(), InstrumentRow.instrument_id.asc()),
        }.get(sort)
        if order is None:
            raise ValueError("unsupported instrument sort")
        rows = self.session.execute(
            stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)
        ).all()
        return [self._instrument_dict(*row) for row in rows], total

    @staticmethod
    def _instrument_dict(instrument, company, listing, sector, industry) -> dict[str, Any]:
        return {
            "instrument_id": instrument.instrument_id,
            "company_id": instrument.company_id,
            "legal_name": company.legal_name if company else None,
            "display_name": company.display_name if company else None,
            "current_legal_name": company.current_legal_name if company else None,
            "exchange": listing.exchange_code,
            "symbol": listing.symbol,
            "nse_symbol": listing.symbol if listing.exchange_code == "NSE" else None,
            "bse_code": listing.bse_code,
            "isin": listing.isin,
            "exchange_segment": listing.exchange_segment,
            "exchange_series": listing.exchange_series,
            "country": instrument.country,
            "currency": instrument.currency,
            "timezone": instrument.timezone,
            "listing_status": listing.status,
            "listing_date": listing.listing_date,
            "delisting_date": listing.delisting_date,
            "primary_listing": listing.is_primary,
            "is_sme": listing.is_sme,
            "security_type": instrument.security_type,
            "sector": sector.name if sector else None,
            "industry": industry.name if industry else None,
            "sub_industry": industry.sub_industry if industry else None,
            "market_cap_category": instrument.market_cap_category,
            "quality_status": instrument.quality_status,
        }

    def instrument(self, instrument_id: str) -> dict[str, Any] | None:
        stmt = (
            select(InstrumentRow, CompanyRow, InstrumentListingRow, SectorRow, IndustryRow)
            .join(InstrumentListingRow, and_(
                InstrumentListingRow.instrument_id == InstrumentRow.instrument_id,
                InstrumentListingRow.is_primary.is_(True),
                InstrumentListingRow.valid_to.is_(None),
            ))
            .outerjoin(CompanyRow, CompanyRow.company_id == InstrumentRow.company_id)
            .outerjoin(SectorRow, SectorRow.sector_id == InstrumentRow.sector_id)
            .outerjoin(IndustryRow, IndustryRow.industry_id == InstrumentRow.industry_id)
            .where(InstrumentRow.instrument_id == instrument_id)
        )
        row = self.session.execute(stmt).first()
        if not row:
            return None
        result = self._instrument_dict(*row)
        result["aliases"] = [
            {"type": item.alias_type, "value": item.value}
            for item in self.session.scalars(select(InstrumentAliasRow).where(
                InstrumentAliasRow.instrument_id == instrument_id
            )).all()
        ]
        result["provider_mappings"] = [
            {"provider": item.provider, "provider_symbol": item.provider_symbol}
            for item in self.session.scalars(select(ProviderSymbolRow).where(
                ProviderSymbolRow.instrument_id == instrument_id,
                ProviderSymbolRow.valid_to.is_(None),
            )).all()
        ]
        return result

    def rankings(
        self, *, build_id: str | None = None, page: int = 1, page_size: int = 25,
        sector: str | None = None, industry: str | None = None,
        min_score: float | None = None, max_risk: float | None = None,
        min_confidence: float | None = None, technical_trend: str | None = None,
        search: str | None = None, min_rank: int | None = None,
        max_rank: int | None = None, sort: str = "rank",
    ) -> tuple[list[dict[str, Any]], int, ModelBuildRow | None]:
        build = self.session.get(ModelBuildRow, build_id) if build_id else self.latest_build()
        if not build:
            return [], 0, None
        stmt = (
            select(ScoreSnapshotRow, CompanyRow, InstrumentListingRow, SectorRow, IndustryRow)
            .join(InstrumentRow, InstrumentRow.instrument_id == ScoreSnapshotRow.instrument_id)
            .join(InstrumentListingRow, and_(
                InstrumentListingRow.instrument_id == InstrumentRow.instrument_id,
                InstrumentListingRow.is_primary.is_(True),
                InstrumentListingRow.valid_to.is_(None),
            ))
            .outerjoin(CompanyRow, CompanyRow.company_id == InstrumentRow.company_id)
            .outerjoin(SectorRow, SectorRow.sector_id == InstrumentRow.sector_id)
            .outerjoin(IndustryRow, IndustryRow.industry_id == InstrumentRow.industry_id)
            .where(ScoreSnapshotRow.build_id == build.build_id)
        )
        filters = []
        if sector:
            filters.append(SectorRow.name == sector)
        if industry:
            filters.append(IndustryRow.name == industry)
        if min_score is not None:
            filters.append(ScoreSnapshotRow.multibagger_score >= min_score)
        if max_risk is not None:
            filters.append(ScoreSnapshotRow.risk_score <= max_risk)
        if min_confidence is not None:
            filters.append(ScoreSnapshotRow.confidence >= min_confidence)
        if technical_trend:
            filters.append(ScoreSnapshotRow.technical_trend == technical_trend)
        if search:
            term = f"%{search.strip()}%"
            filters.append(or_(
                InstrumentListingRow.symbol.ilike(term),
                CompanyRow.display_name.ilike(term),
                CompanyRow.legal_name.ilike(term),
            ))
        if min_rank is not None:
            filters.append(ScoreSnapshotRow.rank >= min_rank)
        if max_rank is not None:
            filters.append(ScoreSnapshotRow.rank <= max_rank)
        stmt = stmt.where(*filters)
        total = int(self.session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
        orders = {
            "rank": (ScoreSnapshotRow.rank.asc(), ScoreSnapshotRow.instrument_id.asc()),
            "-rank": (ScoreSnapshotRow.rank.desc(), ScoreSnapshotRow.instrument_id.asc()),
            "-score": (ScoreSnapshotRow.multibagger_score.desc(), ScoreSnapshotRow.instrument_id.asc()),
            "score": (ScoreSnapshotRow.multibagger_score.asc(), ScoreSnapshotRow.instrument_id.asc()),
            "risk": (ScoreSnapshotRow.risk_score.asc(), ScoreSnapshotRow.instrument_id.asc()),
            "-risk": (ScoreSnapshotRow.risk_score.desc(), ScoreSnapshotRow.instrument_id.asc()),
            "confidence": (ScoreSnapshotRow.confidence.asc(), ScoreSnapshotRow.instrument_id.asc()),
            "-confidence": (ScoreSnapshotRow.confidence.desc(), ScoreSnapshotRow.instrument_id.asc()),
            "investment": (ScoreSnapshotRow.investment_score.asc(), ScoreSnapshotRow.instrument_id.asc()),
            "-investment": (ScoreSnapshotRow.investment_score.desc(), ScoreSnapshotRow.instrument_id.asc()),
            "name": (CompanyRow.display_name.asc(), ScoreSnapshotRow.instrument_id.asc()),
            "-name": (CompanyRow.display_name.desc(), ScoreSnapshotRow.instrument_id.asc()),
        }
        if sort not in orders:
            raise ValueError("unsupported ranking sort")
        rows = self.session.execute(
            stmt.order_by(*orders[sort]).offset((page - 1) * page_size).limit(page_size)
        ).all()
        score_ids = [score.score_id for score, *_ in rows]
        components_by_score: dict[int, list[dict[str, Any]]] = {
            score_id: [] for score_id in score_ids
        }
        if score_ids:
            for component in self.session.scalars(
                select(ScoreComponentRow).where(
                    ScoreComponentRow.score_id.in_(score_ids)
                ).order_by(ScoreComponentRow.score_id, ScoreComponentRow.component_name)
            ).all():
                components_by_score[component.score_id].append({
                    "name": component.component_name,
                    "score": float(component.score),
                    "confidence": float(component.confidence),
                    "evidence_count": component.evidence_count,
                })
        previous_build = self.session.scalar(
            select(ModelBuildRow)
            .where(ModelBuildRow.built_at < build.built_at)
            .order_by(ModelBuildRow.built_at.desc()).limit(1)
        )
        previous_by_instrument = {}
        if previous_build and rows:
            instrument_ids = [score.instrument_id for score, *_ in rows]
            previous_by_instrument = {
                previous.instrument_id: previous.rank
                for previous in self.session.scalars(
                    select(ScoreSnapshotRow).where(
                        ScoreSnapshotRow.build_id == previous_build.build_id,
                        ScoreSnapshotRow.instrument_id.in_(instrument_ids),
                    )
                ).all()
            }
        data = [{
            "instrument_id": score.instrument_id,
            "rank": score.rank,
            "symbol": listing.symbol,
            "exchange": listing.exchange_code,
            "name": company.display_name if company else None,
            "sector": sector_row.name if sector_row else None,
            "industry": industry_row.name if industry_row else None,
            "multibagger_score": float(score.multibagger_score),
            "investment_score": float(score.investment_score),
            "confidence": float(score.confidence),
            "risk_score": float(score.risk_score),
            "investability": score.investability,
            "positive_signal_count": score.positive_signal_count,
            "red_flag_count": score.red_flag_count,
            "coverage_quality": float(score.coverage_quality) if score.coverage_quality is not None else None,
            "has_missing_data": score.has_missing_data,
            "technical_trend": score.technical_trend,
            "main_positive_signal": score.main_positive_signal,
            "main_risk": score.main_risk,
            "components": components_by_score.get(score.score_id, []),
            "previous_rank": previous_by_instrument.get(score.instrument_id),
            "rank_change": (
                previous_by_instrument[score.instrument_id] - score.rank
                if score.instrument_id in previous_by_instrument else None
            ),
        } for score, company, listing, sector_row, industry_row in rows]
        return data, total, build

    def ranking_detail(self, instrument_id: str, build_id: str | None = None) -> dict[str, Any] | None:
        build = self.session.get(ModelBuildRow, build_id) if build_id else self.latest_build()
        if not build:
            return None
        score = self.session.scalar(select(ScoreSnapshotRow).where(
            ScoreSnapshotRow.build_id == build.build_id,
            ScoreSnapshotRow.instrument_id == instrument_id,
        ))
        if not score:
            return None
        components = self.session.scalars(select(ScoreComponentRow).where(
            ScoreComponentRow.score_id == score.score_id
        ).order_by(ScoreComponentRow.component_name)).all()
        previous = self.session.scalar(
            select(ScoreSnapshotRow)
            .join(ModelBuildRow, ModelBuildRow.build_id == ScoreSnapshotRow.build_id)
            .where(
                ScoreSnapshotRow.instrument_id == instrument_id,
                ModelBuildRow.built_at < build.built_at,
            )
            .order_by(ModelBuildRow.built_at.desc()).limit(1)
        )
        return {
            "instrument_id": instrument_id, "build_id": build.build_id,
            "rank": score.rank, "multibagger_score": float(score.multibagger_score),
            "investment_score": float(score.investment_score),
            "confidence": float(score.confidence), "risk_score": float(score.risk_score),
            "investability": score.investability,
            "positive_signal_count": score.positive_signal_count,
            "red_flag_count": score.red_flag_count,
            "coverage_quality": float(score.coverage_quality) if score.coverage_quality is not None else None,
            "has_missing_data": score.has_missing_data,
            "technical_trend": score.technical_trend,
            "main_positive_signal": score.main_positive_signal,
            "main_risk": score.main_risk,
            "components": [{
                "name": c.component_name, "score": float(c.score),
                "confidence": float(c.confidence), "evidence_count": c.evidence_count,
            } for c in components],
            "build": self.build_dict(build),
            "previous": ({
                "build_id": previous.build_id, "rank": previous.rank,
                "multibagger_score": float(previous.multibagger_score),
            } if previous else None),
        }

    def score_history(self, instrument_id: str, *, limit: int = 26) -> list[dict[str, Any]]:
        if limit < 1 or limit > 52:
            raise ValueError("score history limit must be between 1 and 52")
        rows = self.session.execute(
            select(ScoreSnapshotRow, ModelBuildRow)
            .join(ModelBuildRow, ModelBuildRow.build_id == ScoreSnapshotRow.build_id)
            .where(ScoreSnapshotRow.instrument_id == instrument_id)
            .order_by(ModelBuildRow.built_at.desc(), ModelBuildRow.build_id.desc())
            .limit(limit)
        ).all()
        score_ids = [score.score_id for score, _ in rows]
        components: dict[int, list[dict[str, Any]]] = {score_id: [] for score_id in score_ids}
        if score_ids:
            for row in self.session.scalars(select(ScoreComponentRow).where(
                ScoreComponentRow.score_id.in_(score_ids)
            ).order_by(ScoreComponentRow.score_id, ScoreComponentRow.component_name)).all():
                components[row.score_id].append({
                    "name": row.component_name, "score": float(row.score),
                    "confidence": float(row.confidence), "evidence_count": row.evidence_count,
                })
        return list(reversed([{
            "build_id": build.build_id, "built_at": build.built_at.isoformat(),
            "rank": score.rank, "multibagger_score": float(score.multibagger_score),
            "confidence": float(score.confidence), "risk_score": float(score.risk_score),
            "investment_score": float(score.investment_score),
            "components": components.get(score.score_id, []),
        } for score, build in rows]))

    @staticmethod
    def build_dict(build: ModelBuildRow) -> dict[str, Any]:
        return {
            "build_id": build.build_id, "model_version": build.model_version,
            "factor_config_version": build.factor_config_version,
            "factor_config_hash": build.factor_config_hash,
            "universe_name": build.universe_name, "universe_version": build.universe_version,
            "data_cutoff": build.data_cutoff, "built_at": build.built_at,
            "status": build.status, "attempted_count": build.attempted_count,
            "scored_count": build.scored_count, "failed_count": build.failed_count,
            "provider_versions": build.provider_versions,
            "validation_status": build.validation_status,
        }
