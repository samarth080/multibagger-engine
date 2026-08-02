"""Explicit acquisition, model, and financial build stages.

These operations deliberately exchange immutable JSON artifacts. Rendering
never imports or calls a live provider.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from mbe import __version__
from mbe.builds.domain import (
    FrozenFinancialBuildManifest, FrozenModelBuildManifest, SourceDataManifest,
    canonical_json, sha256_file,
)
from mbe.data.cache import DiskCache
from mbe.data.yahoo import YahooProvider
from mbe.financials.projection import financial_build, project_history
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.models.instrument import BuildManifest, stable_instrument_id
from mbe.pipeline import AnalysisBundle, ScreenResult, screen
from mbe.publish import build_data
from mbe.research.static import build_static_research
from mbe.universe import get_universe
from mbe.versioning import (
    FACTOR_CONFIG_VERSION, MODEL_VERSION, VALIDATION_STATUS,
    factor_configuration, universe_version,
)


def _frame_payload(frame: pd.DataFrame) -> dict:
    return json.loads(frame.to_json(
        orient="split", date_format="iso", date_unit="ns", double_precision=15,
    ))


def _frame_from_payload(payload: dict) -> pd.DataFrame:
    frame = pd.read_json(io.StringIO(json.dumps(payload)), orient="split")
    frame.index = pd.to_datetime(frame.index)
    return frame


def refresh_market_data(
    *, universe_id: str, out: Path, cutoff: datetime | None = None,
    cache_dir: Path = Path("data/cache"), provider=None,
) -> SourceDataManifest:
    """Fetch provider inputs explicitly and freeze their normalized values."""
    cutoff = (cutoff or datetime.now(timezone.utc)).astimezone(timezone.utc)
    tickers = get_universe(universe_id, pinned=True)
    provider = provider or YahooProvider(DiskCache(cache_dir, ttl_hours=0))
    records = {}
    benchmarks = {}
    failures = {}
    for ticker in tickers:
        try:
            info = provider.get_info(ticker)
            fin = provider.get_financials(ticker)
            prices = provider.get_prices(ticker)
            benchmark_ticker = provider.benchmark_ticker(ticker)
            if benchmark_ticker not in benchmarks:
                benchmarks[benchmark_ticker] = _frame_payload(
                    provider.get_prices(benchmark_ticker).df
                )
            records[ticker] = {
                "info": info.model_dump(mode="json"),
                "financials": fin.model_dump(mode="json"),
                "prices": _frame_payload(prices.df),
                "benchmark_ticker": benchmark_ticker,
            }
        except Exception as exc:
            failures[ticker] = f"{type(exc).__name__}: {exc}"
    if failures:
        raise RuntimeError(
            f"source refresh failed for {len(failures)}/{len(tickers)} instruments: "
            f"{list(failures.items())[:5]}"
        )
    payload = {
        "schema_version": "2026-08-02.11.1",
        "provider_cutoff": cutoff.isoformat(),
        "universe_id": universe_id,
        "tickers": tickers,
        "records": records,
        "benchmarks": benchmarks,
    }
    out.mkdir(parents=True, exist_ok=True)
    artifact_path = out / "source-data.json"
    artifact_path.write_bytes(canonical_json(payload) + b"\n")
    artifact_hash = sha256_file(artifact_path)
    source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mbe-source:{artifact_hash}"))
    manifest = SourceDataManifest(
        source_data_build_id=source_id, generated_at=cutoff, provider_cutoff=cutoff,
        universe_id=universe_id,
        universe_version=universe_version(universe_id, tickers),
        membership_count=len(tickers),
        provider_versions={"mbe": __version__, "yfinance": "runtime"},
        source_hashes={"source-data.json": artifact_hash}, network_used=True,
        status="complete",
        warnings=[
            "Yahoo compatibility data is unofficial and its statement basis may be unknown."
        ],
    )
    (out / "source-manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return manifest


class FrozenProvider:
    def __init__(self, payload: dict):
        self.payload = payload

    def _record(self, ticker: str) -> dict:
        try:
            return self.payload["records"][ticker]
        except KeyError as exc:
            raise KeyError(f"ticker absent from frozen source data: {ticker}") from exc

    def get_info(self, ticker: str) -> CompanyInfo:
        return CompanyInfo(**self._record(ticker)["info"])

    def get_financials(self, ticker: str) -> FinancialHistory:
        return FinancialHistory(**self._record(ticker)["financials"])

    def get_prices(self, ticker: str, years: int = 3) -> PriceHistory:
        if ticker in self.payload.get("benchmarks", {}):
            raw = self.payload["benchmarks"][ticker]
        else:
            raw = self._record(ticker)["prices"]
        return PriceHistory(df=_frame_from_payload(raw))

    def benchmark_ticker(self, ticker: str) -> str:
        return self._record(ticker)["benchmark_ticker"]


def build_model_from_source(*, source_dir: Path, out: Path) -> FrozenModelBuildManifest:
    source_manifest_path = source_dir / "source-manifest.json"
    source_artifact_path = source_dir / "source-data.json"
    source_manifest = SourceDataManifest.model_validate_json(source_manifest_path.read_text())
    if sha256_file(source_artifact_path) != source_manifest.source_hashes["source-data.json"]:
        raise ValueError("source-data.json hash does not match its frozen manifest")
    payload = json.loads(source_artifact_path.read_text())
    cutoff = source_manifest.provider_cutoff
    result = screen(
        payload["tickers"], FrozenProvider(payload), as_of=cutoff.date(),
    )
    bundles = []
    for bundle in result.ranked:
        bundles.append({
            "bundle": bundle.model_dump(mode="json", exclude={"prices"}),
            "prices": payload["records"][bundle.card.ticker]["prices"],
        })
    model_payload = {
        "schema_version": "2026-08-02.11.1",
        "data_cutoff": cutoff.isoformat(),
        "universe_id": source_manifest.universe_id,
        "universe_version": source_manifest.universe_version,
        "model_version": MODEL_VERSION,
        "bundles": bundles,
        "failures": result.failures,
        "sector_scores": [row.model_dump(mode="json") for row in result.sector_scores],
    }
    out.mkdir(parents=True, exist_ok=True)
    artifact = out / "model-results.json"
    artifact.write_bytes(canonical_json(model_payload) + b"\n")
    artifact_hash = sha256_file(artifact)
    model_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mbe-model:{artifact_hash}"))
    manifest = FrozenModelBuildManifest(
        model_build_id=model_id, generated_at=cutoff, data_cutoff=cutoff,
        universe_id=source_manifest.universe_id,
        universe_version=source_manifest.universe_version,
        model_version=MODEL_VERSION,
        source_data_build_id=source_manifest.source_data_build_id,
        source_manifest_hash=sha256_file(source_manifest_path),
        model_artifact_path=artifact.name, model_artifact_hash=artifact_hash,
        attempted_count=len(payload["tickers"]), scored_count=len(result.ranked),
        failed_count=len(result.failures), network_used=False,
        status="complete" if result.ranked else "failed",
    )
    (out / "model-manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return manifest


def load_model_result(model_dir: Path) -> tuple[FrozenModelBuildManifest, ScreenResult]:
    manifest = FrozenModelBuildManifest.model_validate_json(
        (model_dir / "model-manifest.json").read_text()
    )
    artifact = model_dir / manifest.model_artifact_path
    if sha256_file(artifact) != manifest.model_artifact_hash:
        raise ValueError("model artifact hash does not match its frozen manifest")
    payload = json.loads(artifact.read_text())
    bundles = []
    for row in payload["bundles"]:
        raw = dict(row["bundle"])
        raw["prices"] = PriceHistory(df=_frame_from_payload(row["prices"]))
        bundles.append(AnalysisBundle.model_validate(raw))
    from mbe.models.sector import SectorScore
    return manifest, ScreenResult(
        ranked=bundles, failures=payload.get("failures", {}),
        sector_scores=[SectorScore(**row) for row in payload.get("sector_scores", [])],
    )


def build_financials_from_model(
    *, model_dir: Path, out: Path, instrument_ids: dict[str, str],
) -> FrozenFinancialBuildManifest:
    model_manifest, result = load_model_result(model_dir)
    cutoff = model_manifest.data_cutoff
    projections = [
        project_history(
            bundle.fin, instrument_id=instrument_ids[bundle.card.ticker], cutoff=cutoff,
        )
        for bundle in result.ranked
    ]
    dataset = financial_build(projections, cutoff=cutoff, built_at=cutoff)
    for projection in projections:
        projection["financial_dataset_build_id"] = dataset["financial_dataset_build_id"]
    payload = {"dataset": dataset, "projections": projections}
    out.mkdir(parents=True, exist_ok=True)
    artifact = out / "financial-results.json"
    artifact.write_bytes(canonical_json(payload) + b"\n")
    artifact_hash = sha256_file(artifact)
    manifest = FrozenFinancialBuildManifest(
        financial_build_id=dataset["financial_dataset_build_id"],
        generated_at=cutoff, data_cutoff=cutoff,
        source_data_build_id=model_manifest.source_data_build_id,
        model_build_id=model_manifest.model_build_id,
        financial_artifact_path=artifact.name,
        financial_artifact_hash=artifact_hash, network_used=False, status="complete",
    )
    (out / "financial-manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    )
    return manifest


def build_research_payloads(
    *, model_dir: Path, financial_dir: Path, instrument_master: Path,
    out: Path, context_path: Path | None = None,
) -> dict:
    """Generate frozen company-research payloads without rendering HTML."""
    model_manifest, result = load_model_result(model_dir)
    financial_manifest = FrozenFinancialBuildManifest.model_validate_json(
        (financial_dir / "financial-manifest.json").read_text()
    )
    financial_artifact = financial_dir / financial_manifest.financial_artifact_path
    if sha256_file(financial_artifact) != financial_manifest.financial_artifact_hash:
        raise ValueError("financial artifact hash does not match its frozen manifest")
    financial_payload = json.loads(financial_artifact.read_text())
    master = json.loads(instrument_master.read_text())
    canonical_records = {
        row["provider_symbols"]["yahoo"]: row for row in master["records"]
    }
    instrument_ids = {
        ticker: stable_instrument_id(
            exchange_code=row["exchange"], symbol=row["symbol"], isin=row.get("isin"),
        )
        for ticker, row in canonical_records.items()
    }
    context = json.loads(context_path.read_text()) if context_path else {}
    from mbe.data.news_rss import NewsItem
    news = {
        ticker: [NewsItem(**item) for item in items]
        for ticker, items in context.get("company_news", {}).items()
    }
    policy = [NewsItem(**item) for item in context.get("policy", [])]
    factor_hash = BuildManifest.configuration_hash(factor_configuration())
    build = BuildManifest(
        build_id=model_manifest.model_build_id,
        model_version=model_manifest.model_version,
        factor_config_version=FACTOR_CONFIG_VERSION,
        factor_config_hash=factor_hash,
        universe_name=model_manifest.universe_id,
        universe_version=model_manifest.universe_version,
        data_cutoff=model_manifest.data_cutoff,
        built_at=model_manifest.generated_at,
        provider_versions={"frozen_source": model_manifest.source_data_build_id},
        validation_status=VALIDATION_STATUS, status="complete",
        attempted_count=model_manifest.attempted_count,
        scored_count=model_manifest.scored_count,
        failed_count=model_manifest.failed_count,
        source_data_version=model_manifest.source_data_build_id,
    )
    data = build_data(
        result, news, policy, built_at=model_manifest.generated_at, manifest=build,
        instrument_ids=instrument_ids, canonical_records=canonical_records,
        previous_screener_rows=context.get("previous_screener_rows", []),
    )
    projections = financial_payload["projections"]
    dataset = financial_payload["dataset"]
    by_id = {row["instrument_id"]: row for row in projections}
    data["_financial_summaries"] = projections
    data["financial_dataset_build"] = dataset
    for row in data["top"]:
        row["financial_summary"] = by_id[row["instrument_id"]]
    research_pages = build_static_research(data, result)
    payload = {
        "schema_version": "2026-08-02.11.1",
        "model_build_id": model_manifest.model_build_id,
        "financial_build_id": financial_manifest.financial_build_id,
        "data": data,
        "research_pages": research_pages,
    }
    out.mkdir(parents=True, exist_ok=True)
    artifact = out / "research-render-input.json"
    artifact.write_bytes(canonical_json(payload) + b"\n")
    manifest = {
        "schema_version": "2026-08-02.11.1",
        "generated_at": model_manifest.generated_at.isoformat(),
        "model_build_id": model_manifest.model_build_id,
        "financial_build_id": financial_manifest.financial_build_id,
        "research_count": len(research_pages),
        "artifact": artifact.name,
        "artifact_sha256": sha256_file(artifact),
        "network_used": False,
        "status": "complete",
    }
    (out / "research-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest
