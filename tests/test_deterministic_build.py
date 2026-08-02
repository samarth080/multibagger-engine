"""Phase 11 M1 offline-build, manifest, and preservation contracts."""

from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

import pytest

from mbe.builds.domain import FrozenInputManifest, sha256_file, sha256_tree
from mbe.builds.network import OfflineNetworkError, deny_network
from mbe.builds.offline import (
    build_search_only, render_frontend_only, render_site_from_manifest, tree_digest,
)
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
