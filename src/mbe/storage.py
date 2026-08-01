"""DuckDB persistence for analysis runs and backtest summaries.

Every screen/snapshot becomes a queryable time series — the raw material for
score-vs-outcome calibration and for tracking how a thesis evolves.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import duckdb

from mbe.pipeline import ScreenResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    as_of DATE,
    universe TEXT,
    created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS results (
    run_id TEXT,
    ticker TEXT,
    investment DOUBLE,
    multibagger DOUBLE,
    confidence DOUBLE,
    risk_score DOUBLE,
    trend_state TEXT,
    price DOUBLE,
    market_cap DOUBLE,
    verdict TEXT,
    pillars_json TEXT,
    metrics_json TEXT
);
CREATE TABLE IF NOT EXISTS theses (
    as_of DATE,
    ticker TEXT,
    classification TEXT,
    thesis_confidence DOUBLE,
    veto BOOLEAN,
    recommendation TEXT,
    thesis_json TEXT,
    critique_json TEXT,
    created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS predictions (
    pred_id TEXT PRIMARY KEY,
    ticker TEXT,
    made_on DATE,
    due_on DATE,
    kind TEXT,
    statement TEXT,
    confidence DOUBLE,
    source TEXT,
    resolved_on DATE,
    actual TEXT,
    correct BOOLEAN
);
CREATE TABLE IF NOT EXISTS backtests (
    created_at TIMESTAMP,
    universe TEXT,
    score_name TEXT,
    horizon_days INTEGER,
    mean_ic DOUBLE,
    details_json TEXT
);
"""

# Additive compatibility migrations for the legacy DuckDB research ledger.
# The canonical PostgreSQL schema is managed by Alembic; this small registry
# exists only so old local ``mbe.duckdb`` files remain readable as canonical
# IDs/build IDs are introduced.  Never rewrite or drop research history here.
_MIGRATIONS: list[tuple[int, tuple[str, ...]]] = [
    (1, (
        "ALTER TABLE runs ADD COLUMN IF NOT EXISTS build_id TEXT",
        "ALTER TABLE results ADD COLUMN IF NOT EXISTS instrument_id TEXT",
        "ALTER TABLE results ADD COLUMN IF NOT EXISTS build_id TEXT",
    )),
]


class RunStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(_SCHEMA)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP)"
            )
            applied = {
                row[0] for row in conn.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            }
            for version, statements in _MIGRATIONS:
                if version in applied:
                    continue
                conn.execute("BEGIN TRANSACTION")
                try:
                    for statement in statements:
                        conn.execute(statement)
                    conn.execute(
                        "INSERT INTO schema_migrations VALUES (?, ?)",
                        [version, datetime.now()],
                    )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def save_run(
        self,
        result: ScreenResult,
        universe: str,
        *,
        build_id: str | None = None,
        instrument_ids: dict[str, str] | None = None,
    ) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._conn() as conn:
            first = result.ranked[0].as_of if result.ranked else datetime.now().date()
            conn.execute(
                "INSERT INTO runs (run_id, as_of, universe, created_at, build_id) "
                "VALUES (?, ?, ?, ?, ?)",
                [run_id, first, universe, datetime.now(), build_id],
            )
            for b in result.ranked:
                conn.execute(
                    "INSERT INTO results "
                    "(run_id, ticker, investment, multibagger, confidence, risk_score, "
                    "trend_state, price, market_cap, verdict, pillars_json, metrics_json, "
                    "instrument_id, build_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        run_id,
                        b.card.ticker,
                        b.card.investment_score,
                        b.card.multibagger_score,
                        b.card.confidence,
                        b.risk.risk_score,
                        b.tech.trend_state,
                        b.val.price,
                        b.info.market_cap,
                        b.card.verdict,
                        json.dumps(
                            {p.name: p.score for p in b.card.pillars}
                        ),
                        json.dumps(
                            {
                                "roce_3y": b.fund.roce_3y,
                                "revenue_cagr_3y": b.fund.revenue_cagr_3y,
                                "profit_cagr_3y": b.fund.profit_cagr_3y,
                                "margin_of_safety": b.val.margin_of_safety,
                                "implied_growth": b.val.implied_growth,
                                "peg": b.val.peg,
                            }
                        ),
                        (instrument_ids or {}).get(b.card.ticker),
                        build_id,
                    ],
                )
        return run_id

    def history(self, ticker: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT r.as_of, r.universe, t.ticker, t.investment, t.multibagger,
                       t.confidence, t.risk_score, t.trend_state, t.price, t.verdict
                FROM results t JOIN runs r ON t.run_id = r.run_id
                WHERE t.ticker = ? ORDER BY r.created_at
                """,
                [ticker],
            ).fetchall()
        cols = [
            "as_of", "universe", "ticker", "investment", "multibagger",
            "confidence", "risk_score", "trend_state", "price", "verdict",
        ]
        return [dict(zip(cols, row)) for row in rows]

    def runs(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT r.run_id, r.as_of, r.universe, r.created_at,
                       COUNT(t.ticker) AS n_results
                FROM runs r LEFT JOIN results t ON t.run_id = r.run_id
                GROUP BY r.run_id, r.as_of, r.universe, r.created_at
                ORDER BY r.created_at DESC
                """
            ).fetchall()
        cols = ["run_id", "as_of", "universe", "created_at", "n_results"]
        return [dict(zip(cols, row)) for row in rows]

    def run_results(self, run_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT ticker, investment, multibagger, confidence, risk_score,
                       trend_state, price, market_cap, verdict
                FROM results WHERE run_id = ? ORDER BY multibagger DESC
                """,
                [run_id],
            ).fetchall()
        cols = [
            "ticker", "investment", "multibagger", "confidence", "risk_score",
            "trend_state", "price", "market_cap", "verdict",
        ]
        return [dict(zip(cols, row)) for row in rows]

    def save_thesis(self, thesis, critique, as_of=None) -> None:
        """Longitudinal thesis memory: every snapshot is kept, never overwritten."""
        from datetime import date as _date

        with self._conn() as conn:
            conn.execute(
                "INSERT INTO theses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    as_of or _date.today(),
                    thesis.ticker,
                    thesis.classification,
                    thesis.thesis_confidence,
                    critique.veto,
                    critique.recommendation,
                    thesis.model_dump_json(),
                    critique.model_dump_json(),
                    datetime.now(),
                ],
            )

    def thesis_history(self, ticker: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT as_of, classification, thesis_confidence, veto, "
                "recommendation, thesis_json, critique_json FROM theses "
                "WHERE ticker = ? ORDER BY created_at",
                [ticker],
            ).fetchall()
        return [
            {
                "as_of": r[0],
                "classification": r[1],
                "thesis_confidence": r[2],
                "veto": r[3],
                "recommendation": r[4],
                "thesis": json.loads(r[5]),
                "critique": json.loads(r[6]),
            }
            for r in rows
        ]

    # ---- prediction ledger (append-only; outcomes fill in, never overwrite) ----

    @staticmethod
    def _pred_id(p) -> str:
        import hashlib

        key = f"{p.ticker}|{p.made_on}|{p.kind}|{p.statement}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    def save_predictions(self, predictions) -> int:
        """Insert new predictions; duplicates (same ticker/date/claim) skipped."""
        saved = 0
        with self._conn() as conn:
            for p in predictions:
                pid = self._pred_id(p)
                exists = conn.execute(
                    "SELECT 1 FROM predictions WHERE pred_id = ?", [pid]
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO predictions VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)",
                    [pid, p.ticker, p.made_on, p.due_on, p.kind,
                     p.statement, p.confidence, p.source],
                )
                saved += 1
        return saved

    def due_predictions(self, as_of) -> list:
        from mbe.models.prediction import Prediction

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT ticker, made_on, due_on, kind, statement, confidence, source "
                "FROM predictions WHERE due_on <= ? AND resolved_on IS NULL "
                "ORDER BY due_on, ticker",
                [as_of],
            ).fetchall()
        cols = ["ticker", "made_on", "due_on", "kind", "statement", "confidence", "source"]
        return [Prediction(**dict(zip(cols, r))) for r in rows]

    def record_outcome(self, prediction, outcome) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE predictions SET resolved_on = ?, actual = ?, correct = ? "
                "WHERE pred_id = ? AND resolved_on IS NULL",
                [outcome.resolved_on, outcome.actual, outcome.correct,
                 self._pred_id(prediction)],
            )

    def resolved_predictions(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT ticker, made_on, due_on, kind, statement, confidence, "
                "resolved_on, actual, correct FROM predictions "
                "WHERE resolved_on IS NOT NULL ORDER BY resolved_on",
            ).fetchall()
        cols = ["ticker", "made_on", "due_on", "kind", "statement", "confidence",
                "resolved_on", "actual", "correct"]
        return [dict(zip(cols, r)) for r in rows]

    def save_backtest(
        self,
        universe: str,
        score_name: str,
        horizon_days: int,
        mean_ic: float,
        details: dict,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO backtests VALUES (?, ?, ?, ?, ?, ?)",
                [
                    datetime.now(), universe, score_name,
                    horizon_days, mean_ic, json.dumps(details),
                ],
            )

    def backtests(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT created_at, universe, score_name, horizon_days, mean_ic, "
                "details_json FROM backtests ORDER BY created_at"
            ).fetchall()
        return [
            {
                "created_at": row[0],
                "universe": row[1],
                "score_name": row[2],
                "horizon_days": row[3],
                "mean_ic": row[4],
                "details": json.loads(row[5]),
            }
            for row in rows
        ]
