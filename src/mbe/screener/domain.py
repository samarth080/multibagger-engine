"""Public screener contracts, limits and registry-driven validation."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCREENER_SCHEMA_VERSION = "1.0"
MAX_CONDITIONS = 12
MAX_COLUMNS = 16
MAX_SORTS = 3
MAX_PAGE_SIZE = 100
MAX_EXPORT_ROWS = 250
MAX_CATEGORICAL_VALUES = 20
MAX_TEXT_LENGTH = 80
MAX_COMPLEXITY = 80


class ScreenerField(BaseModel):
    """Presentation-neutral description of one safe public field."""

    model_config = ConfigDict(frozen=True)

    field_id: str
    label: str
    description: str
    category: str
    data_type: Literal["number", "categorical", "boolean", "text"]
    unit: str | None = None
    operators: tuple[str, ...]
    allowed_values: tuple[str, ...] | None = None
    null_behavior: str = (
        "Comparisons exclude missing values; use is_missing or is_available explicitly."
    )
    sortable: bool = True
    filterable: bool = True
    exportable: bool = True
    availability: Literal["ready", "ready_with_caveat"] = "ready"
    data_source: str
    freshness_category: Literal["model_build", "instrument_master", "financial_dataset"]
    display_format: str = "text"
    default_width: str = "10rem"
    static_support: bool = True
    dynamic_support: bool = True
    minimum: float | None = None
    maximum: float | None = None
    caveat: str | None = None
    period: str | None = None
    formula: str | None = None
    consolidation_rule: str | None = None
    quality_rule: str | None = None
    preferred_source: str | None = None
    fallback_source: str | None = None
    source_quality_tiers: str | None = None
    reconciliation_available: bool = False


class ScreenerCondition(BaseModel):
    condition_id: str = Field(min_length=1, max_length=64)
    field_id: str = Field(min_length=1, max_length=80)
    operator: str = Field(min_length=1, max_length=32)
    value: Any | None = None
    value_to: Any | None = None
    values: list[Any] | None = None


class ScreenerSort(BaseModel):
    field_id: str = Field(min_length=1, max_length=80)
    direction: Literal["asc", "desc"] = "asc"


class ScreenerQuery(BaseModel):
    schema_version: str = SCREENER_SCHEMA_VERSION
    logic: Literal["and"] = "and"
    conditions: list[ScreenerCondition] = Field(default_factory=list)
    sorts: list[ScreenerSort] = Field(
        default_factory=lambda: [ScreenerSort(field_id="rank")]
    )
    columns: list[str] = Field(default_factory=lambda: [
        "company", "nse_symbol", "sector", "rank", "multibagger_score",
        "confidence", "risk_score", "technical_trend",
        "main_positive_signal", "main_risk",
    ])
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1)
    build_id: str | None = Field(default=None, max_length=64)
    count_only: bool = False


class ScreenerValidationError(ValueError):
    def __init__(self, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


def _number(value: Any, field_id: str) -> float:
    if isinstance(value, bool):
        raise ScreenerValidationError(
            "invalid_value_type", "A numeric value is required.", field_id
        )
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ScreenerValidationError(
            "invalid_value_type", "A numeric value is required.", field_id
        ) from None
    if not math.isfinite(result):
        raise ScreenerValidationError(
            "invalid_value_type", "A finite numeric value is required.", field_id
        )
    return result


def _bounded_number(value: Any, field: ScreenerField) -> float:
    result = _number(value, field.field_id)
    if field.minimum is not None and result < field.minimum:
        raise ScreenerValidationError(
            "invalid_value", f"Value must be at least {field.minimum:g}.", field.field_id
        )
    if field.maximum is not None and result > field.maximum:
        raise ScreenerValidationError(
            "invalid_value", f"Value must be at most {field.maximum:g}.", field.field_id
        )
    return result


def validate_query(
    query: ScreenerQuery,
    registry: dict[str, ScreenerField],
    *,
    mode: Literal["dynamic", "static"] = "dynamic",
) -> tuple[ScreenerQuery, list[str]]:
    """Validate and coerce against the registry; never ignore bad input."""
    if query.schema_version != SCREENER_SCHEMA_VERSION:
        raise ScreenerValidationError(
            "incompatible_schema_version",
            f"Screener schema {query.schema_version!r} is not supported.",
            "schema_version",
        )
    if len(query.conditions) > MAX_CONDITIONS:
        raise ScreenerValidationError(
            "too_many_conditions", f"At most {MAX_CONDITIONS} conditions are allowed.",
            "conditions",
        )
    if len(query.columns) > MAX_COLUMNS:
        raise ScreenerValidationError(
            "too_many_columns", f"At most {MAX_COLUMNS} columns are allowed.", "columns"
        )
    if len(query.sorts) > MAX_SORTS:
        raise ScreenerValidationError(
            "too_many_sorts", f"At most {MAX_SORTS} sort fields are allowed.", "sorts"
        )
    if query.page_size > MAX_PAGE_SIZE:
        raise ScreenerValidationError(
            "page_size_exceeded", f"Page size cannot exceed {MAX_PAGE_SIZE}.", "page_size"
        )
    if len(set(query.columns)) != len(query.columns):
        raise ScreenerValidationError(
            "duplicate_column", "Requested columns must be unique.", "columns"
        )
    if not query.columns and not query.count_only:
        raise ScreenerValidationError(
            "empty_columns", "At least one result column is required.", "columns"
        )

    warnings: list[str] = []
    normalized = query.model_copy(deep=True)
    seen_conditions: set[str] = set()
    seen_condition_payloads: set[str] = set()
    numeric_bounds: dict[str, dict[str, float]] = {}

    for index, condition in enumerate(normalized.conditions):
        path = f"conditions.{index}"
        if condition.condition_id in seen_conditions:
            raise ScreenerValidationError(
                "duplicate_condition_id", "Condition IDs must be unique.", path
            )
        seen_conditions.add(condition.condition_id)
        field = registry.get(condition.field_id)
        if not field:
            raise ScreenerValidationError(
                "unknown_field", f"Unknown screener field {condition.field_id!r}.", path
            )
        if not field.filterable:
            raise ScreenerValidationError(
                "field_not_filterable", f"{field.label} cannot be filtered.", path
            )
        if mode == "static" and not field.static_support:
            raise ScreenerValidationError(
                "unsupported_static_field", f"{field.label} is unavailable in static mode.", path
            )
        if mode == "dynamic" and not field.dynamic_support:
            raise ScreenerValidationError(
                "unsupported_dynamic_field", f"{field.label} is unavailable in API mode.", path
            )
        if condition.operator not in field.operators:
            raise ScreenerValidationError(
                "unsupported_operator",
                f"Operator {condition.operator!r} is not allowed for {field.label}.", path,
            )

        if condition.operator in {"is_available", "is_missing", "is_true", "is_false"}:
            condition.value = None
            condition.value_to = None
            condition.values = None
        elif field.data_type == "number":
            condition.value = _bounded_number(condition.value, field)
            if condition.operator == "between":
                condition.value_to = _bounded_number(condition.value_to, field)
                if condition.value > condition.value_to:
                    raise ScreenerValidationError(
                        "invalid_range", "Range endpoints must be in ascending order.", path
                    )
            else:
                condition.value_to = None
            condition.values = None
        elif condition.operator in {"any_of", "none_of"}:
            if not condition.values:
                raise ScreenerValidationError(
                    "empty_categorical_selection", "Select at least one value.", path
                )
            if len(condition.values) > MAX_CATEGORICAL_VALUES:
                raise ScreenerValidationError(
                    "too_many_values",
                    f"At most {MAX_CATEGORICAL_VALUES} values may be selected.", path,
                )
            values = [str(item).strip() for item in condition.values]
            if any(not item for item in values):
                raise ScreenerValidationError(
                    "invalid_value", "Selected values cannot be empty.", path
                )
            if field.allowed_values and any(item not in field.allowed_values for item in values):
                raise ScreenerValidationError(
                    "invalid_value", f"One or more values are invalid for {field.label}.", path
                )
            condition.values = list(dict.fromkeys(values))
            condition.value = None
            condition.value_to = None
        else:
            value = str(condition.value or "").strip()
            if not value:
                raise ScreenerValidationError("invalid_value", "A value is required.", path)
            if len(value) > MAX_TEXT_LENGTH:
                raise ScreenerValidationError(
                    "invalid_value", f"Text values cannot exceed {MAX_TEXT_LENGTH} characters.", path
                )
            if field.allowed_values and value not in field.allowed_values:
                raise ScreenerValidationError(
                    "invalid_value", f"{value!r} is not valid for {field.label}.", path
                )
            condition.value = value
            condition.value_to = None
            condition.values = None

        payload = json.dumps(condition.model_dump(mode="json"), sort_keys=True)
        payload_without_id = json.dumps(
            {k: v for k, v in condition.model_dump(mode="json").items() if k != "condition_id"},
            sort_keys=True,
        )
        if payload_without_id in seen_condition_payloads:
            raise ScreenerValidationError(
                "duplicate_condition", "An identical condition already exists.", path
            )
        seen_condition_payloads.add(payload_without_id)

        if field.data_type == "number":
            bounds = numeric_bounds.setdefault(field.field_id, {})
            if condition.operator in {"gt", "gte"}:
                bounds["minimum"] = max(bounds.get("minimum", -math.inf), condition.value)
            elif condition.operator in {"lt", "lte"}:
                bounds["maximum"] = min(bounds.get("maximum", math.inf), condition.value)
            elif condition.operator == "between":
                bounds["minimum"] = max(bounds.get("minimum", -math.inf), condition.value)
                bounds["maximum"] = min(bounds.get("maximum", math.inf), condition.value_to)

    for field_id, bounds in numeric_bounds.items():
        if bounds.get("minimum", -math.inf) > bounds.get("maximum", math.inf):
            warnings.append(
                f"Conditions on {registry[field_id].label} are contradictory and will return no rows."
            )

    for index, column in enumerate(normalized.columns):
        field = registry.get(column)
        if not field:
            raise ScreenerValidationError(
                "unknown_field", f"Unknown result column {column!r}.", f"columns.{index}"
            )
        if not field.exportable:
            raise ScreenerValidationError(
                "field_not_exportable", f"{field.label} cannot be returned as a column.",
                f"columns.{index}",
            )
        if mode == "static" and not field.static_support:
            raise ScreenerValidationError(
                "unsupported_static_field", f"{field.label} is unavailable in static mode.",
                f"columns.{index}",
            )

    seen_sorts: set[str] = set()
    for index, sort in enumerate(normalized.sorts):
        field = registry.get(sort.field_id)
        if not field:
            raise ScreenerValidationError(
                "unknown_field", f"Unknown sort field {sort.field_id!r}.", f"sorts.{index}"
            )
        if not field.sortable:
            raise ScreenerValidationError(
                "field_not_sortable", f"{field.label} cannot be sorted.", f"sorts.{index}"
            )
        if sort.field_id in seen_sorts:
            raise ScreenerValidationError(
                "duplicate_sort", "Sort fields must be unique.", f"sorts.{index}"
            )
        seen_sorts.add(sort.field_id)

    complexity = (
        len(normalized.conditions) * 4 + len(normalized.columns)
        + len(normalized.sorts) * 3
        + sum(len(item.values or []) for item in normalized.conditions)
    )
    if complexity > MAX_COMPLEXITY:
        raise ScreenerValidationError(
            "query_too_complex", f"Query complexity {complexity} exceeds {MAX_COMPLEXITY}.",
            "conditions",
        )
    return normalized, warnings


def query_fingerprint(query: ScreenerQuery) -> str:
    payload = json.dumps(
        query.model_dump(mode="json", exclude={"page", "count_only"}),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def limits_manifest() -> dict[str, int]:
    return {
        "max_conditions": MAX_CONDITIONS,
        "max_columns": MAX_COLUMNS,
        "max_sorts": MAX_SORTS,
        "max_page_size": MAX_PAGE_SIZE,
        "max_export_rows": MAX_EXPORT_ROWS,
        "max_categorical_values": MAX_CATEGORICAL_VALUES,
        "max_text_length": MAX_TEXT_LENGTH,
        "max_complexity": MAX_COMPLEXITY,
    }
