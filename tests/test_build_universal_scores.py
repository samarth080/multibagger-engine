import json

from mbe.data.provider import ProviderError

from scripts.build_universal_scores import RefreshOutcome, run_refresh


class _StubProvider:
    def __init__(self, fail_tickers=()):
        self._fail_tickers = set(fail_tickers)

    def get_info(self, ticker):
        if ticker in self._fail_tickers:
            raise ProviderError("boom")
        from mbe.models.company import CompanyInfo
        return CompanyInfo(ticker=ticker, sector="Technology", market_cap=1e10)

    def get_financials(self, ticker):
        from mbe.models.company import FinancialHistory
        return FinancialHistory(data={"revenue": {2024: 100.0}, "net_income": {2024: 10.0}})

    def get_prices(self, ticker, years=3):
        import pandas as pd
        from mbe.models.company import PriceHistory
        idx = pd.bdate_range("2024-01-01", periods=60)
        return PriceHistory(ticker=ticker, df=pd.DataFrame({
            "close": [100.0] * len(idx),
            "high": [101.0] * len(idx),
            "low": [99.0] * len(idx),
            "volume": [1000000] * len(idx),
        }, index=idx))

    def benchmark_ticker(self, ticker):
        return "^NSEI"


def test_run_refresh_writes_one_artifact_per_instrument(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}, {"instrument_id": "id-2", "provider_symbol": "BBB.NS"}]
    result = run_refresh(instruments, provider=_StubProvider(), output_dir=tmp_path)
    assert result.succeeded == ["id-1", "id-2"]
    assert result.failed == {}
    assert (tmp_path / "id-1.json").exists()
    assert (tmp_path / "id-2.json").exists()


def test_run_refresh_isolates_per_company_failure(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}, {"instrument_id": "id-2", "provider_symbol": "BAD.NS"}]
    result = run_refresh(instruments, provider=_StubProvider(fail_tickers={"BAD.NS"}), output_dir=tmp_path, retry_backoff_seconds=0)
    assert result.succeeded == ["id-1"]
    assert "id-2" in result.failed
    assert (tmp_path / "id-1.json").exists()
    assert not (tmp_path / "id-2.json").exists()


def test_run_refresh_is_resumable_and_skips_the_expensive_analysis_on_a_cache_hit(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}]
    first = run_refresh(instruments, provider=_StubProvider(), output_dir=tmp_path)
    assert first.succeeded == ["id-1"]
    assert first.skipped_cached == []

    class _NoBenchmarkAllowed(_StubProvider):
        def benchmark_ticker(self, ticker):
            raise AssertionError(
                "a cache hit must never reach the expensive analysis step — "
                "benchmark_ticker is only ever called from inside analyze_universal, "
                "never from the cheap fetch-and-hash step"
            )

    # Same underlying data as the first run, so the freshly-computed hash
    # matches the cached one — this proves genuine staleness detection
    # (info/financials/prices ARE re-fetched to compute a comparison hash)
    # while still skipping the expensive scoring/report-building step
    # (which is the only code path that would ever need a benchmark).
    second = run_refresh(instruments, provider=_NoBenchmarkAllowed(), output_dir=tmp_path)
    assert second.succeeded == ["id-1"]
    assert second.skipped_cached == ["id-1"]


def test_run_refresh_recomputes_when_underlying_data_changes(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}]
    first = run_refresh(instruments, provider=_StubProvider(), output_dir=tmp_path)
    assert first.skipped_cached == []

    class _ChangedDataProvider(_StubProvider):
        def get_financials(self, ticker):
            from mbe.models.company import FinancialHistory
            return FinancialHistory(data={"revenue": {2024: 999.0}, "net_income": {2024: 50.0}})

    second = run_refresh(instruments, provider=_ChangedDataProvider(), output_dir=tmp_path)
    assert second.succeeded == ["id-1"]
    assert second.skipped_cached == []  # hash changed, so it was genuinely recomputed, not skipped


def test_run_refresh_retries_a_transient_failure_before_giving_up(tmp_path):
    calls = {"count": 0}

    class _FlakyThenOkProvider(_StubProvider):
        def get_info(self, ticker):
            calls["count"] += 1
            if calls["count"] < 3:
                raise ProviderError("transient")
            return super().get_info(ticker)

    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}]
    result = run_refresh(instruments, provider=_FlakyThenOkProvider(), output_dir=tmp_path, max_retries=3, retry_backoff_seconds=0)
    assert result.succeeded == ["id-1"]
    assert calls["count"] == 3


def test_run_refresh_gives_up_after_max_retries_and_records_the_failure(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "ALWAYS_FAILS.NS"}]
    result = run_refresh(
        instruments, provider=_StubProvider(fail_tickers={"ALWAYS_FAILS.NS"}), output_dir=tmp_path,
        max_retries=2, retry_backoff_seconds=0,
    )
    assert result.succeeded == []
    assert "id-1" in result.failed


def test_run_refresh_respects_limit(tmp_path):
    instruments = [{"instrument_id": f"id-{i}", "provider_symbol": f"T{i}.NS"} for i in range(5)]
    result = run_refresh(instruments, provider=_StubProvider(), output_dir=tmp_path, limit=2)
    assert len(result.succeeded) == 2


def test_run_refresh_writes_manifest_with_partial_completion_report(tmp_path):
    instruments = [{"instrument_id": "id-1", "provider_symbol": "AAA.NS"}, {"instrument_id": "id-2", "provider_symbol": "BAD.NS"}]
    run_refresh(instruments, provider=_StubProvider(fail_tickers={"BAD.NS"}), output_dir=tmp_path, retry_backoff_seconds=0)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["succeeded_count"] == 1
    assert manifest["failed_count"] == 1
    assert "id-2" in manifest["failures"]
    assert "generated_at" in manifest
