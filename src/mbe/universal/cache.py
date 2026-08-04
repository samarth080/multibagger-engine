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
