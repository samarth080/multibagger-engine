"""Point-in-time discipline for backtesting.

A backtest is only honest if the engine sees exactly what an investor could
have seen at the cutoff date:
- statements appear only after fiscal-year end + a 90-day filing lag;
- prices stop at the cutoff;
- present-day fields that have no historical record (holdings %, trailing PE,
  beta, market cap) are nulled; market cap is re-derived from current share
  count x cutoff price (documented approximation — ignores later buybacks).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import pandas as pd

from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory

FILING_LAG_DAYS = 90


def availability_date(fy_year: int, fy_end_month: int = 3) -> date:
    """Date on which fiscal year `fy_year`'s annual statements become public."""
    last_day = calendar.monthrange(fy_year, fy_end_month)[1]
    return date(fy_year, fy_end_month, last_day) + timedelta(days=FILING_LAG_DAYS)


def truncate_financials(
    fin: FinancialHistory, cutoff: date, fy_end_month: int = 3
) -> FinancialHistory:
    def visible(year: int) -> bool:
        # exact first-public date when the provider recorded one (XBRL filings)
        if year in fin.filed:
            return fin.filed[year] <= cutoff
        return availability_date(year, fy_end_month) <= cutoff

    return FinancialHistory(
        data={
            field: {
                year: value for year, value in by_year.items() if visible(year)
            }
            for field, by_year in fin.data.items()
        },
        filed={y: d for y, d in fin.filed.items() if visible(y)},
    )


def truncate_prices(prices: PriceHistory, cutoff: date) -> PriceHistory:
    df = prices.df
    return PriceHistory(df=df[df.index <= pd.Timestamp(cutoff)])


def sanitize_info_as_of(info: CompanyInfo, cutoff_price: float | None) -> CompanyInfo:
    market_cap = None
    if info.shares_outstanding and cutoff_price:
        market_cap = info.shares_outstanding * cutoff_price
    return CompanyInfo(
        ticker=info.ticker,
        name=info.name,
        exchange=info.exchange,
        currency=info.currency,
        sector=info.sector,
        industry=info.industry,
        market_cap=market_cap,
        shares_outstanding=info.shares_outstanding,
        price=cutoff_price,
        description=info.description,
        # deliberately dropped (no historical record -> would leak the present):
        # insider_pct, institution_pct, float_shares, beta, trailing_pe, dividend_yield
    )
