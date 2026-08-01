from pathlib import Path

from scripts.verify_release import verify


ROOT = Path(__file__).resolve().parents[1]


def test_generated_release_contract() -> None:
    result = verify(ROOT / "site", ROOT, ROOT / "tests/fixtures/phase8-public-value-hashes.json")
    assert result["errors"] == []
    assert result["status"] == "pass"
