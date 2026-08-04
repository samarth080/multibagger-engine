"""Source-data-hash + policy-version cache keys, and JSON artifact
read/write for the Universal Research Score refresh pipeline. A cache hit
means the underlying financial/price snapshot and the scoring policy are
both byte-identical to what produced the cached report — anything else
(a new financial period, a metric formula fix, a policy version bump)
invalidates it deterministically."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory


def cache_key_for(
    info: CompanyInfo, fin: FinancialHistory, prices: PriceHistory, *, policy_version: str,
) -> str:
    payload = {
        "policy_version": policy_version,
        "info": info.model_dump(mode="json"),
        "financials": fin.model_dump(mode="json"),
        "last_close": prices.last_close(),
        "price_rows": len(prices.df),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_cached_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True))


def read_cached_report(path: Path, *, expected_cache_key: str | None = None) -> dict | None:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if expected_cache_key is not None and payload.get("cache_key") != expected_cache_key:
        return None
    return payload


def load_universal_scores_summary(artifacts_dir: Path) -> dict[str, dict]:
    """Reads every pre-warmed artifact in artifacts_dir into the small
    summary shape mbe.search.catalog.build_search_index needs — never the
    full report payload (that stays lazily loaded per company page)."""
    summary: dict[str, dict] = {}
    if not artifacts_dir.exists():
        return summary
    for path in sorted(artifacts_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        payload = read_cached_report(path)
        if not payload:
            continue
        instrument_id = payload.get("instrument_id")
        if not instrument_id:
            continue
        report = payload.get("report") or {}
        exec_summary = report.get("executive_summary") or {}
        summary[instrument_id] = {
            "overall_score": exec_summary.get("overall_score"),
            "confidence": exec_summary.get("confidence"),
            "data_coverage_pct": exec_summary.get("data_coverage_pct"),
            "report_state": exec_summary.get("report_state"),
            "policy_version": payload.get("policy_version"),
        }
    return summary
