from datetime import date

import numpy as np
import pandas as pd

from mbe.backtest.pointintime import (
    availability_date,
    sanitize_info_as_of,
    truncate_financials,
    truncate_prices,
)
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory


def test_availability_date_india_fy():
    # FY2024 ends 2024-03-31; +90 days filing lag => 2024-06-29
    assert availability_date(2024, fy_end_month=3) == date(2024, 6, 29)


def test_truncate_financials_drops_unavailable_years():
    fin = FinancialHistory(
        data={"revenue": {2022: 1.0, 2023: 2.0, 2024: 3.0, 2025: 4.0}}
    )
    # cutoff 2024-07-01: FY2024 available (2024-06-29), FY2025 not
    out = truncate_financials(fin, date(2024, 7, 1), fy_end_month=3)
    assert sorted(out.data["revenue"]) == [2022, 2023, 2024]
    # cutoff 2024-06-01: FY2024 not yet filed
    out = truncate_financials(fin, date(2024, 6, 1), fy_end_month=3)
    assert sorted(out.data["revenue"]) == [2022, 2023]


def test_truncate_prices_exact():
    idx = pd.bdate_range("2024-01-01", periods=300)
    df = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": np.arange(300.0), "volume": 1.0},
        index=idx,
    )
    out = truncate_prices(PriceHistory(df=df), date(2024, 6, 30))
    assert out.df.index.max() <= pd.Timestamp("2024-06-30")
    assert len(out.df) < 300


def test_sanitize_info_blocks_leakage_and_rederives_mcap():
    info = CompanyInfo(
        ticker="X.NS",
        name="X",
        market_cap=999.0,
        shares_outstanding=100.0,
        insider_pct=0.5,
        institution_pct=0.3,
        trailing_pe=30.0,
        price=50.0,
        beta=1.2,
    )
    as_of = sanitize_info_as_of(info, cutoff_price=8.0)
    assert as_of.insider_pct is None  # current holdings must not leak into the past
    assert as_of.institution_pct is None
    assert as_of.trailing_pe is None
    assert as_of.beta is None
    assert as_of.market_cap == 800.0  # shares x cutoff price
    assert as_of.price == 8.0
    assert as_of.name == "X"  # identity fields kept


def test_sanitize_info_without_shares_gives_no_mcap():
    info = CompanyInfo(ticker="X.NS", market_cap=999.0)
    as_of = sanitize_info_as_of(info, cutoff_price=8.0)
    assert as_of.market_cap is None


def test_truncate_prefers_real_filed_dates():
    """EDGAR supplies exact first-public dates; they beat the +90d heuristic."""
    fin = FinancialHistory(
        data={"revenue": {2022: 1.0, 2023: 2.0, 2024: 3.0}},
        filed={2023: date(2024, 2, 1), 2024: date(2025, 1, 25)},
    )
    # cutoff 2024-03-01: FY2023 filed 2024-02-01 (visible), FY2024 not yet.
    # FY2022 has no filed date -> heuristic (avail 2022-06-29, visible).
    out = truncate_financials(fin, date(2024, 3, 1), fy_end_month=3)
    assert sorted(out.data["revenue"]) == [2022, 2023]
    # filed map itself must be truncated consistently
    assert 2024 not in out.filed


def test_filed_date_can_be_later_than_heuristic():
    """A company that filed late must not be visible at the heuristic date."""
    fin = FinancialHistory(
        data={"revenue": {2024: 3.0}},
        filed={2024: date(2024, 12, 15)},  # late filer
    )
    out = truncate_financials(fin, date(2024, 8, 1), fy_end_month=3)
    assert out.data.get("revenue", {}) == {}
