"""Official Nifty index constituent instrument-master adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel

from mbe.data.provider import ProviderError
from mbe.data.universe_nse import NSE_SOURCES, default_http
from mbe.instruments.importer import SourceInstrumentRow, parse_nifty_instrument_csv


class InstrumentMasterSnapshot(BaseModel):
    source: str
    source_url: str
    source_version: str
    retrieved_at: datetime
    records: list[SourceInstrumentRow]


class NiftyIndexInstrumentProvider:
    """Documented public constituent CSV; covers index members, not all NSE."""

    name = "nifty_indices"

    def __init__(
        self, index_name: str = "nifty-smallcap250",
        fetcher: Callable[[str], str] = default_http,
    ):
        if index_name not in NSE_SOURCES:
            raise KeyError(f"unsupported Nifty index {index_name!r}")
        self.index_name = index_name
        self.url = NSE_SOURCES[index_name]
        self.fetcher = fetcher

    def fetch_instruments(self) -> InstrumentMasterSnapshot:
        try:
            payload = self.fetcher(self.url)
            raw_rows = parse_nifty_instrument_csv(payload)
            records = [SourceInstrumentRow(**row) for row in raw_rows]
        except Exception as exc:
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError(f"instrument-master fetch failed for {self.index_name}") from exc
        digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return InstrumentMasterSnapshot(
            source=f"nifty_indices:{self.index_name}", source_url=self.url,
            source_version=f"sha256:{digest}", retrieved_at=datetime.now(timezone.utc),
            records=records,
        )

    def health(self) -> dict:
        return {
            "provider": self.name, "status": "configured",
            "capability": "instrument_master", "index": self.index_name,
        }
