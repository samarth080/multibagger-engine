"""Phase 11 M1 offline-build, manifest, and preservation contracts."""

from __future__ import annotations

import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mbe.builds.domain import (
    FrozenInputManifest, SiteBuildManifest, sha256_file, sha256_tree,
)
from mbe.builds.network import OfflineNetworkError, deny_network
from mbe.builds.offline import (
    build_coverage_only, build_search_only, render_frontend_only,
    render_site_from_manifest, tree_digest,
)
from mbe.builds.pipeline import (
    build_financials_from_model, build_model_from_source,
    build_research_payloads, refresh_market_data,
)
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
from mbe.models.instrument import stable_instrument_id
from scripts.verify_release import public_value_hashes


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "builds/manifests/phase11-m1-frozen-inputs.json"
VALUE_FIXTURE = json.loads((ROOT / "tests/fixtures/phase8-public-value-hashes.json").read_text())


def test_frozen_manifest_validates_every_artifact() -> None:
    manifest = FrozenInputManifest.model_validate_json(MANIFEST.read_text())
    manifest.validate_artifacts(ROOT)
    assert manifest.model_build_ids["india-small-cap-v1"]
    assert manifest.model_build_ids["india-large-cap-v1"] is None
    assert manifest.model_build_ids["india-mid-cap-v1"] is None


def test_frozen_manifest_rejects_missing_and_changed_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "value.json"
    artifact.write_text("{}")
    raw = json.loads(MANIFEST.read_text())
    raw["artifacts"] = [{
        "path": "value.json", "sha256": "0" * 64, "kind": "file", "role": "test",
    }]
    manifest = FrozenInputManifest.model_validate(raw)
    with pytest.raises(ValueError, match="hash mismatch"):
        manifest.validate_artifacts(tmp_path)
    artifact.unlink()
    with pytest.raises(ValueError, match="missing frozen artifact"):
        manifest.validate_artifacts(tmp_path)


def test_offline_network_guard_fails_immediately() -> None:
    with deny_network() as audit, pytest.raises(OfflineNetworkError):
        urllib.request.urlopen("https://query1.finance.yahoo.com")
    assert audit.attempted is True
    assert "yahoo" in (audit.target or "")


def test_same_frozen_site_build_is_byte_deterministic(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    one = render_site_from_manifest(MANIFEST, first)
    two = render_site_from_manifest(MANIFEST, second)
    assert one.site_build_id == two.site_build_id
    assert one.generated_at == two.generated_at
    assert one.network_used is False and two.network_used is False
    assert tree_digest(first) == tree_digest(second)
    assert public_value_hashes(first) == VALUE_FIXTURE
    assert public_value_hashes(second) == VALUE_FIXTURE
    assert len(list((first / "company").glob("*.html"))) == 250
    assert len(list((first / "reports").glob("*.html"))) == 25


def test_search_only_does_not_change_model_or_financial_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "site"
    shutil.copytree(ROOT / "site", out)
    protected_before = {
        "rankings": sha256_file(out / "api/v1/rankings.json"),
        "screener": sha256_file(out / "api/v1/screener.json"),
        "research": sha256_tree(out / "api/v1/research"),
        "financials": sha256_tree(out / "api/v1/financials"),
    }
    result = build_search_only(MANIFEST, out)
    protected_after = {
        "rankings": sha256_file(out / "api/v1/rankings.json"),
        "screener": sha256_file(out / "api/v1/screener.json"),
        "research": sha256_tree(out / "api/v1/research"),
        "financials": sha256_tree(out / "api/v1/financials"),
    }
    search = json.loads((out / "api/v1/search-index.json").read_text())
    assert protected_after == protected_before
    assert search["meta"]["search_ranking_policy_version"] == "2026-08-02.10c.2"
    assert result.build_mode == "search-only" and result.network_used is False


def test_frontend_only_does_not_change_any_public_json(tmp_path: Path) -> None:
    out = tmp_path / "site"
    shutil.copytree(ROOT / "site", out)
    before = sha256_tree(out / "api/v1")
    result = render_frontend_only(MANIFEST, out, write_manifest=False)
    assert sha256_tree(out / "api/v1") == before
    assert (out / "assets/app.js").read_bytes() == (
        ROOT / "src/mbe/frontend/assets/app.js"
    ).read_bytes()
    assert result.build_mode == "frontend-only" and result.network_used is False


def test_checked_site_manifest_has_required_multi_universe_slots() -> None:
    manifest = SiteBuildManifest.model_validate_json(
        (ROOT / "site/build-manifest.json").read_text()
    )
    assert manifest.large_cap_model_build_id is None
    assert manifest.mid_cap_model_build_id is None
    assert manifest.small_cap_model_build_id == "1bd53d15-67c6-4b02-b830-0eb0bb1d582b"
    assert manifest.financial_build_id == "34baaa1c-e2f6-508b-b2f0-389669739b2a"


def test_checked_site_manifest_records_current_policy_versions() -> None:
    manifest = SiteBuildManifest.model_validate_json(
        (ROOT / "site/build-manifest.json").read_text()
    )
    assert manifest.search_ranking_policy_version == "2026-08-02.10c.2"
    assert manifest.classification_policy_version == "2026-08-02.10c.1"
    assert manifest.quote_mode == "frozen-build-close"


def test_checked_site_manifest_output_hashes_are_complete() -> None:
    manifest = SiteBuildManifest.model_validate_json(
        (ROOT / "site/build-manifest.json").read_text()
    )
    assert set(manifest.output_artifact_hashes) == {
        "data", "rankings", "screener", "search", "financials", "research",
        "company_pages", "legacy_pages", "frontend_assets", "index_html",
        "screener_html", "methodology_html",
    }


def test_frozen_manifest_rejects_duplicate_artifact_paths() -> None:
    raw = json.loads(MANIFEST.read_text())
    raw["artifacts"].append(dict(raw["artifacts"][0], role="duplicate"))
    with pytest.raises(ValueError, match="paths must be unique"):
        FrozenInputManifest.model_validate(raw)


def test_tree_digest_excludes_only_the_self_describing_manifest(tmp_path: Path) -> None:
    (tmp_path / "value.txt").write_text("fixed")
    before = tree_digest(tmp_path)
    (tmp_path / "build-manifest.json").write_text('{"site_build_id":"one"}')
    assert tree_digest(tmp_path) == before
    (tmp_path / "value.txt").write_text("changed")
    assert tree_digest(tmp_path) != before


def test_site_build_id_is_stable_for_identical_identity() -> None:
    checked = SiteBuildManifest.model_validate_json(
        (ROOT / "site/build-manifest.json").read_text()
    )
    rebuilt = SiteBuildManifest.create(
        generated_at=checked.generated_at,
        search_build_id=checked.search_build_id,
        search_ranking_policy_version=checked.search_ranking_policy_version,
        classification_policy_version=checked.classification_policy_version,
        small_cap_model_build_id=checked.small_cap_model_build_id,
        financial_build_id=checked.financial_build_id,
        universe_versions=checked.universe_versions,
        input_artifact_hashes=checked.input_artifact_hashes,
        output_artifact_hashes=checked.output_artifact_hashes,
        build_configuration_hash=checked.build_configuration_hash,
        build_mode=checked.build_mode,
        news_cutoff=checked.news_cutoff,
        quote_mode=checked.quote_mode,
        warnings=checked.warnings,
    )
    assert rebuilt.site_build_id == checked.site_build_id


def test_explicit_source_model_financial_research_pipeline_is_reproducible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubProvider:
        def get_info(self, ticker):
            return CompanyInfo(
                ticker=ticker, name="Test Industries Ltd.", exchange="NSE",
                currency="INR", sector="Industrials", industry="Engineering",
                market_cap=10_000_000_000, shares_outstanding=10_000_000, price=100,
            )

        def get_financials(self, ticker):
            return FinancialHistory(data={
                "revenue": {2022: 100, 2023: 120, 2024: 150, 2025: 180},
                "net_income": {2022: 10, 2023: 13, 2024: 17, 2025: 21},
                "operating_income": {2022: 15, 2023: 18, 2024: 23, 2025: 28},
                "total_equity": {2022: 50, 2023: 60, 2024: 70, 2025: 80},
                "total_debt": {2022: 10, 2023: 9, 2024: 8, 2025: 7},
                "cfo": {2022: 12, 2023: 15, 2024: 19, 2025: 24},
                "fcf": {2022: 8, 2023: 10, 2024: 14, 2025: 18},
                "interest_expense": {2022: 1, 2023: 1, 2024: 1, 2025: 1},
                "shares_diluted": {2022: 10, 2023: 10, 2024: 10, 2025: 10},
            })

        def get_prices(self, ticker, years=3):
            index = pd.date_range("2023-01-01", periods=800, freq="D")
            close = np.linspace(80 if ticker == "^NSEI" else 60, 100, len(index))
            return PriceHistory(df=pd.DataFrame({
                "open": close, "high": close * 1.01, "low": close * .99,
                "close": close, "volume": 10_000,
            }, index=index))

        def benchmark_ticker(self, ticker):
            return "^NSEI"

    monkeypatch.setattr("mbe.builds.pipeline.get_universe", lambda *args, **kwargs: ["TEST.NS"])
    cutoff = datetime(2026, 8, 1, 3, 0, tzinfo=timezone.utc)
    source = tmp_path / "source"
    source_manifest = refresh_market_data(
        universe_id="nifty-smallcap250", out=source, cutoff=cutoff,
        provider=StubProvider(),
    )
    first_model, second_model = tmp_path / "model-one", tmp_path / "model-two"
    first = build_model_from_source(source_dir=source, out=first_model)
    second = build_model_from_source(source_dir=source, out=second_model)
    assert source_manifest.network_used is True
    assert first.network_used is False and first.scored_count == 1
    assert first.model_build_id == second.model_build_id
    assert first.model_artifact_hash == second.model_artifact_hash

    financials = tmp_path / "financials"
    instrument_id = stable_instrument_id(
        exchange_code="NSE", symbol="TEST", isin="INE000A01000",
    )
    financial = build_financials_from_model(
        model_dir=first_model, out=financials,
        instrument_ids={"TEST.NS": instrument_id},
    )
    assert financial.network_used is False
    assert financial.data_cutoff == cutoff

    master = tmp_path / "master.json"
    master.write_text(json.dumps({"records": [{
        "source_record_id": "INE000A01000", "company_name": "Test Industries Ltd.",
        "symbol": "TEST", "exchange": "NSE", "isin": "INE000A01000",
        "provider_symbols": {"yahoo": "TEST.NS"}, "aliases": [],
    }]}))
    research = build_research_payloads(
        model_dir=first_model, financial_dir=financials,
        instrument_master=master, out=tmp_path / "research",
    )
    assert research["network_used"] is False
    assert research["research_count"] == 1


def test_coverage_artifact_does_not_change_the_preserved_public_hashes(tmp_path):
    """The score/financial hash gates only cover screener.json and
    research/*.json — adding research-coverage.json must not perturb them.

    build_coverage_only's own docstring requires build_search_only to have
    run first against the same `out` (it only tallies fields already written
    there, never recomputes them). render_site_from_manifest alone copies
    the *frozen* search-index.json verbatim rather than recomputing it, so
    build_search_only is run here too to reproduce the real 3-stage
    site/search/coverage build sequence (see scripts/build_site.py,
    scripts/build_search_assets.py, scripts/build_coverage_artifact.py)."""
    from mbe.builds.offline import build_coverage_only, build_search_only, render_site_from_manifest
    out = tmp_path / "site"
    render_site_from_manifest(MANIFEST, out)
    build_search_only(MANIFEST, out, write_manifest=False)
    before = public_value_hashes(out)
    build_coverage_only(MANIFEST, out)
    after = public_value_hashes(out)
    assert before == after == VALUE_FIXTURE
