import time

import pandas as pd
import pytest

from mbe.data.cache import DiskCache
from mbe.data.yahoo import map_statements


def _yf_frame(rows: dict[str, list[float | None]], years: list[int]) -> pd.DataFrame:
    """Build a yfinance-shaped statement frame: rows = line items,
    columns = fiscal-year-end Timestamps, newest first (as yfinance returns)."""
    cols = [pd.Timestamp(f"{y}-03-31") for y in sorted(years, reverse=True)]
    return pd.DataFrame(rows, index=cols).T


def test_map_statements_canonical_fields():
    income = _yf_frame(
        {
            "Total Revenue": [200.0, 100.0],
            "Net Income": [20.0, 10.0],
            "Operating Income": [30.0, 15.0],
        },
        years=[2024, 2023],
    )
    balance = _yf_frame(
        {"Total Assets": [500.0, 400.0], "Stockholders Equity": [250.0, 200.0]},
        years=[2024, 2023],
    )
    cashflow = _yf_frame(
        {"Operating Cash Flow": [25.0, 12.0], "Capital Expenditure": [-8.0, -5.0]},
        years=[2024, 2023],
    )
    fin = map_statements(income, balance, cashflow)
    assert fin.value("revenue", 2024) == 200.0
    assert fin.value("revenue", 2023) == 100.0
    assert fin.value("net_income", 2024) == 20.0
    assert fin.value("total_equity", 2023) == 200.0
    # capex normalized to positive magnitude
    assert fin.value("capex", 2024) == 8.0
    # fcf derived from cfo - capex when "Free Cash Flow" row missing
    assert fin.value("fcf", 2024) == 25.0 - 8.0
    # unreported fields are absent/None, never invented
    assert fin.latest("interest_expense") is None


def test_map_statements_prefers_reported_fcf():
    cashflow = _yf_frame(
        {
            "Free Cash Flow": [17.0],
            "Operating Cash Flow": [25.0],
            "Capital Expenditure": [-8.0],
        },
        years=[2024],
    )
    fin = map_statements(pd.DataFrame(), pd.DataFrame(), cashflow)
    assert fin.value("fcf", 2024) == 17.0


def test_map_statements_fallback_row_names():
    income = _yf_frame(
        {"Operating Revenue": [50.0], "Net Income Common Stockholders": [5.0]},
        years=[2024],
    )
    fin = map_statements(income, pd.DataFrame(), pd.DataFrame())
    assert fin.value("revenue", 2024) == 50.0
    assert fin.value("net_income", 2024) == 5.0


def test_disk_cache_roundtrip_and_ttl(tmp_path):
    cache = DiskCache(tmp_path, ttl_hours=24)
    assert cache.get_json("info_X") is None
    cache.set_json("info_X", {"a": 1})
    assert cache.get_json("info_X") == {"a": 1}

    df = pd.DataFrame(
        {"close": [1.0, 2.0]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )
    cache.set_df("prices_X", df)
    out = cache.get_df("prices_X")
    assert list(out["close"]) == [1.0, 2.0]


def test_disk_cache_expiry(tmp_path):
    cache = DiskCache(tmp_path, ttl_hours=0)  # everything instantly stale
    cache.set_json("k", {"a": 1})
    time.sleep(0.01)
    assert cache.get_json("k") is None
