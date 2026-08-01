"""Portable screener semantics and SQLAlchemy query planning."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from mbe.db.models import (
    CompanyRow,
    IndustryRow,
    InstrumentListingRow,
    InstrumentRow,
    ModelBuildRow,
    ScoreComponentRow,
    ScoreSnapshotRow,
    SectorRow,
    FinancialDatasetBuildRow,
    FinancialMetricSnapshotRow,
)
from mbe.screener.domain import (
    ScreenerCondition,
    ScreenerQuery,
    query_fingerprint,
    validate_query,
)
from mbe.screener.registry import COMPONENT_FIELDS, SCREENER_FIELDS

FINANCIAL_FIELDS = {"revenue_cagr_3y", "roce_3y"}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _condition_payload(condition: ScreenerCondition, actual: Any) -> dict[str, Any]:
    return {
        "condition_id": condition.condition_id,
        "field_id": condition.field_id,
        "operator": condition.operator,
        "actual_value": _json_value(actual),
        "value": condition.value,
        "value_to": condition.value_to,
        "values": condition.values,
    }


def _static_matches(actual: Any, condition: ScreenerCondition) -> bool:
    operator = condition.operator
    if operator == "is_missing":
        return actual is None
    if operator == "is_available":
        return actual is not None
    if operator == "is_true":
        return actual is True
    if operator == "is_false":
        return actual is False
    if actual is None:
        return False
    if operator == "gt":
        return float(actual) > float(condition.value)
    if operator == "gte":
        return float(actual) >= float(condition.value)
    if operator == "lt":
        return float(actual) < float(condition.value)
    if operator == "lte":
        return float(actual) <= float(condition.value)
    if operator == "between":
        return float(condition.value) <= float(actual) <= float(condition.value_to)
    if operator == "any_of":
        return str(actual) in condition.values
    if operator == "none_of":
        return str(actual) not in condition.values
    left = str(actual).casefold()
    right = str(condition.value).casefold()
    if operator == "eq":
        return left == right
    if operator == "ne":
        return left != right
    if operator == "contains":
        return right in left
    if operator == "starts_with":
        return left.startswith(right)
    return False


def evaluate_static_query(
    rows: list[dict[str, Any]], query: ScreenerQuery,
) -> dict[str, Any]:
    """Reference in-memory implementation used by snapshots and parity tests."""
    query, warnings = validate_query(query, SCREENER_FIELDS, mode="static")
    matching = []
    for row in rows:
        values = row.get("values", row)
        if all(_static_matches(values.get(item.field_id), item) for item in query.conditions):
            matching.append(row)

    def compare(left: dict[str, Any], right: dict[str, Any]) -> int:
        left_values = left.get("values", left)
        right_values = right.get("values", right)
        for item in query.sorts:
            a = left_values.get(item.field_id)
            b = right_values.get(item.field_id)
            if a is None and b is None:
                continue
            if a is None:
                return 1
            if b is None:
                return -1
            if isinstance(a, str) or isinstance(b, str):
                result = (str(a).casefold() > str(b).casefold()) - (
                    str(a).casefold() < str(b).casefold()
                )
            else:
                result = (float(a) > float(b)) - (float(a) < float(b))
            if result:
                return result if item.direction == "asc" else -result
        left_id = str(left.get("instrument_id", ""))
        right_id = str(right.get("instrument_id", ""))
        return (left_id > right_id) - (left_id < right_id)

    from functools import cmp_to_key

    matching.sort(key=cmp_to_key(compare))
    total = len(matching)
    total_pages = math.ceil(total / query.page_size) if total else 0
    page = min(query.page, max(total_pages, 1))
    offset = (page - 1) * query.page_size
    selected = [] if query.count_only else matching[offset:offset + query.page_size]
    result_rows = []
    for row in selected:
        values = row.get("values", row)
        result_rows.append({
            "instrument_id": row["instrument_id"],
            "values": {field_id: values.get(field_id) for field_id in query.columns},
            "report_url": row.get("report_url"),
            "matched_conditions": [
                _condition_payload(condition, values.get(condition.field_id))
                for condition in query.conditions
            ],
        })
    return {
        "rows": result_rows,
        "all_matching_rows": matching,
        "pagination": {
            "page": page, "page_size": query.page_size, "total": total,
            "total_pages": total_pages,
        },
        "applied_filters": [item.model_dump(mode="json") for item in query.conditions],
        "effective_sorting": [item.model_dump(mode="json") for item in query.sorts],
        "requested_columns": query.columns,
        "warnings": warnings,
        "query_fingerprint": query_fingerprint(query),
    }


class ScreenerEngine:
    """Compile a validated public query into bounded parameterized SQLAlchemy."""

    def __init__(self, session: Session):
        self.session = session

    def _build(self, build_id: str | None) -> ModelBuildRow | None:
        if build_id:
            return self.session.get(ModelBuildRow, build_id)
        return self.session.scalar(
            select(ModelBuildRow)
            .where(ModelBuildRow.status == "complete")
            .order_by(ModelBuildRow.built_at.desc(), ModelBuildRow.build_id.desc())
            .limit(1)
        )

    def categorical_values(self, build_id: str | None = None) -> dict[str, list[str]]:
        build = self._build(build_id)
        if not build:
            return {"exchange": ["NSE", "BSE"], "technical_trend": []}
        base = (
            select(ScoreSnapshotRow.instrument_id)
            .where(ScoreSnapshotRow.build_id == build.build_id)
            .subquery()
        )
        values: dict[str, list[str]] = {}
        for key, column, join in (
            ("exchange", InstrumentListingRow.exchange_code, InstrumentListingRow),
            ("sector", SectorRow.name, SectorRow),
            ("industry", IndustryRow.name, IndustryRow),
            ("technical_trend", ScoreSnapshotRow.technical_trend, ScoreSnapshotRow),
        ):
            if join is InstrumentListingRow:
                stmt = select(column).join(
                    base, base.c.instrument_id == InstrumentListingRow.instrument_id
                ).where(
                    InstrumentListingRow.is_primary.is_(True),
                    InstrumentListingRow.valid_to.is_(None),
                    column.is_not(None),
                )
            elif join is ScoreSnapshotRow:
                stmt = select(column).where(
                    ScoreSnapshotRow.build_id == build.build_id, column.is_not(None)
                )
            else:
                stmt = (
                    select(column)
                    .join(InstrumentRow, getattr(join, f"{key}_id") == getattr(InstrumentRow, f"{key}_id"))
                    .join(base, base.c.instrument_id == InstrumentRow.instrument_id)
                    .where(column.is_not(None))
                )
            values[key] = sorted(set(self.session.scalars(stmt).all()))
        return values

    def query(self, original: ScreenerQuery) -> tuple[dict[str, Any], ModelBuildRow | None]:
        query, warnings = validate_query(original, SCREENER_FIELDS, mode="dynamic")
        build = self._build(query.build_id)
        if not build:
            return {
                "rows": [], "pagination": {"page": query.page, "page_size": query.page_size,
                "total": 0, "total_pages": 0}, "applied_filters": [],
                "effective_sorting": [], "requested_columns": query.columns,
                "warnings": warnings, "query_fingerprint": query_fingerprint(query),
            }, None

        previous_build = self.session.scalar(
            select(ModelBuildRow)
            .where(
                ModelBuildRow.status == "complete",
                ModelBuildRow.built_at < build.built_at,
            )
            .order_by(ModelBuildRow.built_at.desc(), ModelBuildRow.build_id.desc())
            .limit(1)
        )
        previous = aliased(ScoreSnapshotRow, name="previous_score")
        expressions = {
            "company": CompanyRow.display_name,
            "nse_symbol": InstrumentListingRow.symbol,
            "exchange": InstrumentListingRow.exchange_code,
            "sector": SectorRow.name,
            "industry": IndustryRow.name,
            "rank": ScoreSnapshotRow.rank,
            "previous_rank": previous.rank,
            "rank_change": previous.rank - ScoreSnapshotRow.rank,
            "multibagger_score": ScoreSnapshotRow.multibagger_score,
            "previous_multibagger_score": previous.multibagger_score,
            "score_change": ScoreSnapshotRow.multibagger_score - previous.multibagger_score,
            "investment_score": ScoreSnapshotRow.investment_score,
            "confidence": ScoreSnapshotRow.confidence,
            "risk_score": ScoreSnapshotRow.risk_score,
            "positive_signal_count": ScoreSnapshotRow.positive_signal_count,
            "red_flag_count": ScoreSnapshotRow.red_flag_count,
            "coverage_quality": ScoreSnapshotRow.coverage_quality,
            "has_missing_data": ScoreSnapshotRow.has_missing_data,
            "technical_trend": ScoreSnapshotRow.technical_trend,
            "main_positive_signal": ScoreSnapshotRow.main_positive_signal,
            "main_risk": ScoreSnapshotRow.main_risk,
        }
        for field_id, component_name in COMPONENT_FIELDS.items():
            expressions[field_id] = (
                select(ScoreComponentRow.score)
                .where(
                    ScoreComponentRow.score_id == ScoreSnapshotRow.score_id,
                    ScoreComponentRow.component_name == component_name,
                )
                .correlate(ScoreSnapshotRow)
                .scalar_subquery()
            )

        used_fields = set(query.columns)
        used_fields.update(item.field_id for item in query.conditions)
        used_fields.update(item.field_id for item in query.sorts)
        financial_build = None
        if used_fields & FINANCIAL_FIELDS:
            financial_build = self.session.scalar(
                select(FinancialDatasetBuildRow)
                .where(FinancialDatasetBuildRow.status == "complete",
                       FinancialDatasetBuildRow.source_cutoff <= build.data_cutoff)
                .order_by(FinancialDatasetBuildRow.built_at.desc(), FinancialDatasetBuildRow.financial_dataset_build_id.desc())
                .limit(1)
            )
        for field_id in FINANCIAL_FIELDS:
            expressions[field_id] = (
                select(FinancialMetricSnapshotRow.value)
                .where(FinancialMetricSnapshotRow.financial_dataset_build_id == (
                           financial_build.financial_dataset_build_id if financial_build else "__none__"),
                       FinancialMetricSnapshotRow.instrument_id == ScoreSnapshotRow.instrument_id,
                       FinancialMetricSnapshotRow.metric_id == field_id,
                       FinancialMetricSnapshotRow.quality_status.in_(("valid", "valid_with_warning", "derived")))
                .correlate(ScoreSnapshotRow).scalar_subquery()
            )
        selected_fields = sorted(used_fields)
        stmt = (
            select(
                ScoreSnapshotRow.instrument_id.label("instrument_id"),
                ScoreSnapshotRow.rank.label("_rank"),
                InstrumentListingRow.symbol.label("_symbol"),
                InstrumentListingRow.exchange_code.label("_exchange"),
                *(expressions[field_id].label(field_id) for field_id in selected_fields),
            )
            .join(InstrumentRow, InstrumentRow.instrument_id == ScoreSnapshotRow.instrument_id)
            .join(InstrumentListingRow, and_(
                InstrumentListingRow.instrument_id == InstrumentRow.instrument_id,
                InstrumentListingRow.is_primary.is_(True),
                InstrumentListingRow.valid_to.is_(None),
            ))
            .outerjoin(CompanyRow, CompanyRow.company_id == InstrumentRow.company_id)
            .outerjoin(SectorRow, SectorRow.sector_id == InstrumentRow.sector_id)
            .outerjoin(IndustryRow, IndustryRow.industry_id == InstrumentRow.industry_id)
            .outerjoin(previous, and_(
                previous.instrument_id == ScoreSnapshotRow.instrument_id,
                previous.build_id == (previous_build.build_id if previous_build else "__none__"),
            ))
            .where(ScoreSnapshotRow.build_id == build.build_id)
        )
        for condition in query.conditions:
            stmt = stmt.where(self._sql_condition(expressions[condition.field_id], condition))

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = int(self.session.scalar(count_stmt) or 0)
        total_pages = math.ceil(total / query.page_size) if total else 0
        page = min(query.page, max(total_pages, 1))
        for sort in query.sorts:
            expression = expressions[sort.field_id]
            order = expression.desc() if sort.direction == "desc" else expression.asc()
            stmt = stmt.order_by(order.nulls_last())
        stmt = stmt.order_by(ScoreSnapshotRow.instrument_id.asc())
        mappings = [] if query.count_only else self.session.execute(
            stmt.offset((page - 1) * query.page_size).limit(query.page_size)
        ).mappings().all()
        rows = []
        for mapping in mappings:
            actual = {field_id: _json_value(mapping[field_id]) for field_id in selected_fields}
            suffix = "BO" if mapping["_exchange"] == "BSE" else "NS"
            rows.append({
                "instrument_id": mapping["instrument_id"],
                "values": {field_id: actual.get(field_id) for field_id in query.columns},
                "report_url": (
                    f"/reports/{mapping['_symbol']}_{suffix}.html"
                    if mapping["_rank"] <= 25 else None
                ),
                "matched_conditions": [
                    _condition_payload(condition, actual.get(condition.field_id))
                    for condition in query.conditions
                ],
            })
        return {
            "rows": rows,
            "pagination": {
                "page": page, "page_size": query.page_size, "total": total,
                "total_pages": total_pages,
            },
            "applied_filters": [item.model_dump(mode="json") for item in query.conditions],
            "effective_sorting": [item.model_dump(mode="json") for item in query.sorts],
            "requested_columns": query.columns,
            "warnings": warnings,
            "query_fingerprint": query_fingerprint(query),
            "financial_dataset_build": ({
                "financial_dataset_build_id": financial_build.financial_dataset_build_id,
                "metric_definition_version": financial_build.metric_definition_version,
                "source_cutoff": financial_build.source_cutoff,
                "built_at": financial_build.built_at,
            } if financial_build else None),
        }, build

    @staticmethod
    def _sql_condition(expression, condition: ScreenerCondition):
        operator = condition.operator
        if operator == "is_missing":
            return expression.is_(None)
        if operator == "is_available":
            return expression.is_not(None)
        if operator == "is_true":
            return expression.is_(True)
        if operator == "is_false":
            return expression.is_(False)
        if operator == "gt":
            return expression > condition.value
        if operator == "gte":
            return expression >= condition.value
        if operator == "lt":
            return expression < condition.value
        if operator == "lte":
            return expression <= condition.value
        if operator == "between":
            return expression.between(condition.value, condition.value_to)
        if operator == "any_of":
            return expression.in_(condition.values)
        if operator == "none_of":
            return and_(expression.is_not(None), expression.not_in(condition.values))
        lowered = func.lower(expression)
        value = str(condition.value).casefold()
        if operator == "eq":
            return and_(expression.is_not(None), lowered == value)
        if operator == "ne":
            return and_(expression.is_not(None), lowered != value)
        if operator == "contains":
            return and_(expression.is_not(None), lowered.contains(value, autoescape=True))
        if operator == "starts_with":
            return and_(expression.is_not(None), lowered.startswith(value, autoescape=True))
        raise AssertionError(f"unhandled validated operator: {operator}")
