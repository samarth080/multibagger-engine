import json

from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory
import pandas as pd

from mbe.universal.cache import cache_key_for, read_cached_report, write_cached_report, load_universal_scores_summary


def _snapshot():
    info = CompanyInfo(ticker="DIXON.NS", sector="Technology")
    fin = FinancialHistory(data={"revenue": {2024: 100.0}})
    prices = PriceHistory(ticker="DIXON.NS", df=pd.DataFrame({"close": [1.0]}, index=pd.bdate_range("2024-01-01", periods=1)))
    return info, fin, prices


def test_cache_key_is_deterministic_for_identical_inputs():
    info, fin, prices = _snapshot()
    key1 = cache_key_for(info, fin, prices, policy_version="universal-score-v1")
    key2 = cache_key_for(info, fin, prices, policy_version="universal-score-v1")
    assert key1 == key2
    assert len(key1) == 64  # sha256 hex digest


def test_cache_key_changes_when_policy_version_changes():
    info, fin, prices = _snapshot()
    key1 = cache_key_for(info, fin, prices, policy_version="universal-score-v1")
    key2 = cache_key_for(info, fin, prices, policy_version="universal-score-v2")
    assert key1 != key2


def test_cache_key_changes_when_financial_data_changes():
    info, fin, prices = _snapshot()
    key1 = cache_key_for(info, fin, prices, policy_version="universal-score-v1")
    fin2 = FinancialHistory(data={"revenue": {2024: 200.0}})
    key2 = cache_key_for(info, fin2, prices, policy_version="universal-score-v1")
    assert key1 != key2


def test_write_then_read_round_trips(tmp_path):
    path = tmp_path / "abc-123.json"
    payload = {"instrument_id": "abc-123", "cache_key": "deadbeef", "report": {"a": 1}}
    write_cached_report(path, payload)
    loaded = read_cached_report(path)
    assert loaded == payload
    assert json.loads(path.read_text()) == payload


def test_read_missing_artifact_returns_none(tmp_path):
    assert read_cached_report(tmp_path / "missing.json") is None


def test_read_cached_report_rejects_stale_cache_key(tmp_path):
    path = tmp_path / "abc-123.json"
    write_cached_report(path, {"instrument_id": "abc-123", "cache_key": "old-key", "report": {}})
    loaded = read_cached_report(path, expected_cache_key="new-key")
    assert loaded is None


def test_read_cached_report_rejects_non_dict_json(tmp_path):
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps([1, 2, 3]))  # valid JSON, but not a dict
    loaded = read_cached_report(path)
    assert loaded is None


def test_load_universal_scores_summary_reads_every_artifact_except_manifest(tmp_path):
    (tmp_path / "id-1.json").write_text(json.dumps({
        "instrument_id": "id-1", "cache_key": "k1", "policy_version": "universal-score-v1",
        "report": {"executive_summary": {
            "overall_score": 72.5, "confidence": "Medium", "data_coverage_pct": 65.0,
            "report_state": "full_evaluated_report",
        }},
    }))
    (tmp_path / "manifest.json").write_text(json.dumps({"succeeded_count": 1}))
    summary = load_universal_scores_summary(tmp_path)
    assert summary == {
        "id-1": {
            "overall_score": 72.5, "confidence": "Medium", "data_coverage_pct": 65.0,
            "report_state": "full_evaluated_report", "policy_version": "universal-score-v1",
        }
    }


def test_load_universal_scores_summary_on_missing_directory_returns_empty(tmp_path):
    assert load_universal_scores_summary(tmp_path / "does-not-exist") == {}
