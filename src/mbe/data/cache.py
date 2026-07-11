"""On-disk cache: JSON for model payloads, parquet for price frames.
Keeps reruns fast and offline, and keeps us polite to data sources."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd


class DiskCache:
    def __init__(self, directory: str | Path, ttl_hours: float = 24.0):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600

    def _fresh(self, path: Path) -> bool:
        return path.exists() and (time.time() - path.stat().st_mtime) < self.ttl_seconds

    def get_json(self, key: str) -> dict | None:
        path = self.dir / f"{key}.json"
        if not self._fresh(path):
            return None
        return json.loads(path.read_text())

    def set_json(self, key: str, payload: dict) -> None:
        (self.dir / f"{key}.json").write_text(json.dumps(payload))

    def get_df(self, key: str) -> pd.DataFrame | None:
        path = self.dir / f"{key}.parquet"
        if not self._fresh(path):
            return None
        return pd.read_parquet(path)

    def set_df(self, key: str, df: pd.DataFrame) -> None:
        df.to_parquet(self.dir / f"{key}.parquet")
