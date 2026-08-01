from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from mbe.db.base import Base
from mbe.db.models import ModelBuildRow, ProviderSymbolRow, ScoreComponentRow, ScoreSnapshotRow
from mbe.instruments.importer import import_instruments
from mbe.screener.domain import (
    MAX_CONDITIONS,
    ScreenerCondition,
    ScreenerQuery,
    ScreenerSort,
    ScreenerValidationError,
    validate_query,
)
from mbe.screener.engine import ScreenerEngine, evaluate_static_query
from mbe.screener.registry import COMPONENT_FIELDS, FIELD_REGISTRY_VERSION, SCREENER_FIELDS, field_manifest


def _build(build_id, built_at):
    return ModelBuildRow(
        build_id=build_id, model_version="test-v1", factor_config_version="f1",
        factor_config_hash="a" * 64, universe_name="unit", universe_version="u1",
        data_cutoff=built_at, built_at=built_at, status="complete",
        attempted_count=3, scored_count=3, failed_count=0,
        provider_versions={"test": "1"}, validation_status="test fixture",
    )


@pytest.fixture()
def screener_store():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    records = [
        {"company_name": "Good Engineering Limited", "symbol": "GOOD", "exchange": "NSE", "isin": "INE000A01018", "sector": "Industrials", "industry": "Engineering", "listing_status": "active", "provider_symbols": {"yahoo": "GOOD.NS"}},
        {"company_name": "Also Foods Limited", "symbol": "ALSO", "exchange": "NSE", "isin": "INE000B01017", "sector": "Consumer", "industry": "Foods", "listing_status": "active", "provider_symbols": {"yahoo": "ALSO.NS"}},
        {"company_name": "Missing Context Limited", "symbol": "MISS", "exchange": "NSE", "isin": "INE000C01016", "listing_status": "active", "provider_symbols": {"yahoo": "MISS.NS"}},
    ]
    with Session(engine) as session:
        import_instruments(session, records, source_code="fixture", source_version="v1")
        ids = {row.provider_symbol: row.instrument_id for row in session.scalars(select(ProviderSymbolRow))}
        now = datetime(2026, 8, 1, tzinfo=timezone.utc)
        session.add_all([_build("previous", now - timedelta(days=7)), _build("current", now)])
        session.flush()
        previous = [
            ScoreSnapshotRow(build_id="previous", instrument_id=ids["GOOD.NS"], rank=2, multibagger_score=76, investment_score=72, confidence=.9, risk_score=22, investability="candidate", positive_signal_count=4, red_flag_count=1, coverage_quality=.9, has_missing_data=True, technical_trend="sideways"),
            ScoreSnapshotRow(build_id="previous", instrument_id=ids["ALSO.NS"], rank=1, multibagger_score=70, investment_score=68, confidence=.8, risk_score=50, investability="watch", positive_signal_count=2, red_flag_count=3, coverage_quality=.8, has_missing_data=True, technical_trend="down"),
        ]
        current = [
            ScoreSnapshotRow(build_id="current", instrument_id=ids["GOOD.NS"], rank=1, multibagger_score=80, investment_score=75, confidence=.95, risk_score=20, investability="candidate", positive_signal_count=6, red_flag_count=1, coverage_quality=.95, has_missing_data=False, technical_trend="up", main_positive_signal="Strong quality", main_risk="Execution"),
            ScoreSnapshotRow(build_id="current", instrument_id=ids["ALSO.NS"], rank=2, multibagger_score=65, investment_score=62, confidence=.8, risk_score=55, investability="watch", positive_signal_count=2, red_flag_count=4, coverage_quality=.8, has_missing_data=True, technical_trend="down", main_positive_signal="Growth", main_risk="Leverage"),
            ScoreSnapshotRow(build_id="current", instrument_id=ids["MISS.NS"], rank=3, multibagger_score=70, investment_score=60, confidence=.6, risk_score=30, investability="review", positive_signal_count=3, red_flag_count=2, coverage_quality=None, has_missing_data=True, technical_trend=None),
        ]
        session.add_all(previous + current)
        session.flush()
        for score, quality in zip(current, (85, 55, 70), strict=True):
            for field_id, component_name in COMPONENT_FIELDS.items():
                session.add(ScoreComponentRow(
                    score_id=score.score_id, component_name=component_name,
                    score=quality - list(COMPONENT_FIELDS).index(field_id),
                    confidence=.9, contribution=None, evidence_count=3,
                ))
        session.commit()
    return engine, ids


def _condition(field_id, operator, value=None, value_to=None, values=None, condition_id="c1"):
    return ScreenerCondition(
        condition_id=condition_id, field_id=field_id, operator=operator,
        value=value, value_to=value_to, values=values,
    )


def test_registry_is_stable_unique_and_complete():
    manifest = field_manifest()
    ids = [row["field_id"] for row in manifest["fields"]]
    labels = [row["label"] for row in manifest["fields"]]
    assert manifest["field_registry_version"] == FIELD_REGISTRY_VERSION
    assert len(ids) == len(set(ids)) and len(labels) == len(set(labels))
    assert all(row["description"] and row["operators"] is not None for row in manifest["fields"])
    assert {"company", "rank_change", "quality_score", "technical_trend", "revenue_cagr_3y", "roce_3y"} <= set(ids)
    revenue = next(item for item in manifest["fields"] if item["field_id"] == "revenue_cagr_3y")
    assert revenue["preferred_source"] == "Official NSE financial-result filing"
    assert revenue["fallback_source"].startswith("Yahoo compatibility")
    assert revenue["reconciliation_available"] is True
    assert "market_cap" not in ids and "roe" not in ids


@pytest.mark.parametrize(("query", "code"), [
    (ScreenerQuery(schema_version="2.0"), "incompatible_schema_version"),
    (ScreenerQuery(conditions=[_condition("unknown", "eq", "x")]), "unknown_field"),
    (ScreenerQuery(conditions=[_condition("risk_score", "contains", "2")]), "unsupported_operator"),
    (ScreenerQuery(conditions=[_condition("risk_score", "between", 50, 10)]), "invalid_range"),
    (ScreenerQuery(conditions=[_condition("sector", "any_of", values=[])]), "empty_categorical_selection"),
    (ScreenerQuery(conditions=[_condition("rank", "gte", 1, condition_id=f"c{i}") for i in range(MAX_CONDITIONS + 1)]), "too_many_conditions"),
])
def test_registry_driven_validation_rejects_unsafe_queries(query, code):
    with pytest.raises(ScreenerValidationError) as raised:
        validate_query(query, SCREENER_FIELDS)
    assert raised.value.code == code


def test_sql_engine_numeric_categorical_boolean_null_and_components(screener_store):
    engine, ids = screener_store
    query = ScreenerQuery(
        conditions=[
            _condition("multibagger_score", "gte", 70, condition_id="score"),
            _condition("sector", "any_of", values=["Industrials"], condition_id="sector"),
            _condition("has_missing_data", "is_false", condition_id="missing"),
            _condition("quality_score", "gte", 80, condition_id="quality"),
        ],
        sorts=[ScreenerSort(field_id="confidence", direction="desc")],
        columns=["company", "rank", "rank_change", "score_change", "quality_score"],
    )
    with Session(engine) as session:
        result, build = ScreenerEngine(session).query(query)
    assert build.build_id == "current"
    assert result["pagination"]["total"] == 1
    assert result["rows"][0]["instrument_id"] == ids["GOOD.NS"]
    assert result["rows"][0]["values"]["rank_change"] == 1
    assert result["rows"][0]["values"]["score_change"] == 4
    assert len(result["rows"][0]["matched_conditions"]) == 4

    missing = ScreenerQuery(
        conditions=[_condition("technical_trend", "is_missing")],
        columns=["company", "technical_trend"],
    )
    with Session(engine) as session:
        missing_result, _ = ScreenerEngine(session).query(missing)
    assert [row["instrument_id"] for row in missing_result["rows"]] == [ids["MISS.NS"]]


@pytest.mark.parametrize("query", [
    ScreenerQuery(conditions=[_condition("multibagger_score", "gte", 70), _condition("risk_score", "lte", 30, condition_id="c2")], sorts=[ScreenerSort(field_id="rank")], columns=["company", "rank"]),
    ScreenerQuery(conditions=[_condition("sector", "any_of", values=["Industrials", "Consumer"]), _condition("technical_trend", "none_of", values=["down"], condition_id="c2")], columns=["company", "sector"]),
    ScreenerQuery(conditions=[_condition("rank_change", "gte", 1)], columns=["company", "rank_change"]),
    ScreenerQuery(conditions=[_condition("technical_trend", "is_missing")], columns=["company", "technical_trend"]),
    ScreenerQuery(conditions=[_condition("rank", "between", 1, 2)], sorts=[ScreenerSort(field_id="multibagger_score", direction="desc"), ScreenerSort(field_id="company")], columns=["company", "rank"]),
])
def test_sqlite_and_reference_static_semantics_match(screener_store, query):
    engine, _ = screener_store
    needed_columns = list(dict.fromkeys([
        *query.columns,
        *(condition.field_id for condition in query.conditions),
        *(sort.field_id for sort in query.sorts),
    ]))
    full_query = query.model_copy(update={"columns": needed_columns, "page_size": 100})
    with Session(engine) as session:
        dynamic, _ = ScreenerEngine(session).query(full_query)
    static_rows = [{"instrument_id": row["instrument_id"], "values": row["values"]} for row in dynamic["rows"]]
    # Re-evaluate the unfiltered current build so membership/order is independently checked.
    with Session(engine) as session:
        universe, _ = ScreenerEngine(session).query(ScreenerQuery(columns=needed_columns, page_size=100))
    reference = evaluate_static_query(
        [{"instrument_id": row["instrument_id"], "values": row["values"]} for row in universe["rows"]],
        query.model_copy(update={"page_size": 100}),
    )
    assert [row["instrument_id"] for row in dynamic["rows"]] == [row["instrument_id"] for row in reference["rows"]]
    assert static_rows


def test_negative_filters_exclude_nulls(screener_store):
    engine, ids = screener_store
    query = ScreenerQuery(
        conditions=[_condition("technical_trend", "ne", "down")],
        columns=["company", "technical_trend"], page_size=100,
    )
    with Session(engine) as session:
        result, _ = ScreenerEngine(session).query(query)
    assert [row["instrument_id"] for row in result["rows"]] == [ids["GOOD.NS"]]


def test_python_static_evaluator_uses_shared_browser_parity_fixture():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "screener-parity.json").read_text()
    )
    result = evaluate_static_query(fixture["rows"], ScreenerQuery(**fixture["query"]))
    assert [row["instrument_id"] for row in result["rows"]] == fixture["expected_instrument_ids"]


def test_component_screen_is_bounded_without_n_plus_one_queries(screener_store):
    engine, _ = screener_store
    statements = []
    event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    query = ScreenerQuery(
        conditions=[_condition("quality_score", "gte", 50)],
        columns=["company", "quality_score"], page_size=100,
    )
    with Session(engine) as session:
        result, _ = ScreenerEngine(session).query(query)
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert result["pagination"]["total"] == 3
    assert len(selects) == 4  # current build, previous build, count, page
