import json

from mbe.builds.offline import build_coverage_only, build_search_only

MANIFEST = "builds/manifests/phase11-m1-frozen-inputs.json"


def test_coverage_artifact_is_deterministic_across_repeated_builds(tmp_path):
    from pathlib import Path
    out1, out2 = tmp_path / "b1", tmp_path / "b2"
    build_search_only(Path(MANIFEST), out1, write_manifest=False)
    build_search_only(Path(MANIFEST), out2, write_manifest=False)
    build_coverage_only(Path(MANIFEST), out1)
    build_coverage_only(Path(MANIFEST), out2)
    payload1 = json.loads((out1 / "data/research-coverage.json").read_text())
    payload2 = json.loads((out2 / "data/research-coverage.json").read_text())
    assert payload1 == payload2


def test_coverage_artifact_has_required_fields(tmp_path):
    from pathlib import Path
    out = tmp_path / "b"
    build_search_only(Path(MANIFEST), out, write_manifest=False)
    build_coverage_only(Path(MANIFEST), out)
    payload = json.loads((out / "data/research-coverage.json").read_text())
    assert payload["schema_version"] == "1.0"
    assert payload["coverage_policy_version"] == "2026-08-03.11.2a.1"
    assert payload["financial_build_id"] == "34baaa1c-e2f6-508b-b2f0-389669739b2a"
    assert set(payload["level_counts"].keys()) == {"0", "1", "2", "3"}
    assert payload["level_counts"]["3"] == 250
    assert payload["instrument_count"] == sum(payload["level_counts"].values())
    assert "generated_at" in payload
    assert "source_hashes" in payload


def test_coverage_artifact_contains_no_raw_provider_payloads(tmp_path):
    from pathlib import Path
    out = tmp_path / "b"
    build_search_only(Path(MANIFEST), out, write_manifest=False)
    build_coverage_only(Path(MANIFEST), out)
    raw = (out / "data/research-coverage.json").read_text()
    assert "yahoo" not in raw.lower()
    assert "/Users/" not in raw and "/home/" not in raw
