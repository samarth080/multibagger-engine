"""Reproducible model/universe build manifests without changing score math."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from mbe import __version__
from mbe.models.instrument import BuildManifest
from mbe.scoring.benchmarks import HIGHER_BETTER, LOWER_BETTER, TREND_POINTS
from mbe.scoring.engine import (
    HARD_GATE_CAP, INVESTMENT_WEIGHTS, MULTIBAGGER_WEIGHTS, RISK_HAIRCUT,
)

MODEL_VERSION = "multibagger-score-v1"
FACTOR_CONFIG_VERSION = "factor-config-v1"
VALIDATION_STATUS = (
    "modest positive 2-year Indian small-cap IC; survivorship-biased; "
    "sector momentum descriptive only"
)


def factor_configuration() -> dict:
    return {
        "investment_weights": INVESTMENT_WEIGHTS,
        "multibagger_weights": MULTIBAGGER_WEIGHTS,
        "risk_haircut": RISK_HAIRCUT,
        "hard_gate_cap": HARD_GATE_CAP,
        "higher_better": HIGHER_BETTER,
        "lower_better": LOWER_BETTER,
        "trend_points": TREND_POINTS,
    }


def universe_version(name: str, tickers: list[str], source_date: str | None = None) -> str:
    digest = hashlib.sha256(
        json.dumps(sorted(tickers), separators=(",", ":")).encode()
    ).hexdigest()[:12]
    return f"{source_date or 'undated'}:{digest}"


def build_manifest(
    *, universe_name: str, tickers: list[str], built_at: datetime,
    source_date: str | None = None, attempted: int = 0, scored: int = 0,
    failed: int = 0, duration_seconds: float | None = None,
) -> BuildManifest:
    return BuildManifest.create(
        model_version=MODEL_VERSION,
        factor_config_version=FACTOR_CONFIG_VERSION,
        factor_config=factor_configuration(),
        universe_name=universe_name,
        universe_version=universe_version(universe_name, tickers, source_date),
        data_cutoff=built_at,
        built_at=built_at,
        provider_versions={"mbe": __version__, "yfinance": "runtime"},
        validation_status=VALIDATION_STATUS,
        status="complete" if scored else "running",
        duration_seconds=duration_seconds,
        attempted_count=attempted,
        scored_count=scored,
        failed_count=failed,
        source_data_version=source_date,
    )
