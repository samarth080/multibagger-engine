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
CREATE TABLE IF NOT EXISTS backtests (
    created_at TIMESTAMP,
    universe TEXT,
    score_name TEXT,
    horizon_days INTEGER,
    mean_ic DOUBLE,
    details_json TEXT
);
"""


class RunStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def save_run(self, result: ScreenResult, universe: str) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._conn() as conn:
            first = result.ranked[0].as_of if result.ranked else datetime.now().date()
            conn.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?)",
                [run_id, first, universe, datetime.now()],
            )
            for b in result.ranked:
                conn.execute(
                    "INSERT INTO results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
