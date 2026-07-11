"""Core company data models: identity, financial statements, prices."""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, ConfigDict

# Canonical statement fields every provider must map to. Values may be None
# when the source doesn't report them — missing data is surfaced, not imputed.
CANONICAL_FIELDS = [
    "revenue",
    "gross_profit",
    "operating_income",
    "ebitda",
    "net_income",
    "interest_expense",
    "total_assets",
    "total_equity",
    "total_debt",
    "cash",
    "current_assets",
    "current_liabilities",
    "cfo",
    "capex",
    "fcf",
    "shares_diluted",
    "dividends_paid",
]


class CompanyInfo(BaseModel):
    ticker: str
    name: str | None = None
    exchange: str | None = None
    currency: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    shares_outstanding: float | None = None
    float_shares: float | None = None
    insider_pct: float | None = None
    institution_pct: float | None = None
    beta: float | None = None
    trailing_pe: float | None = None
    price: float | None = None
    dividend_yield: float | None = None
    description: str | None = None


class FinancialHistory(BaseModel):
    """Annual statement history: canonical field -> {fiscal year -> value}."""

    data: dict[str, dict[int, float | None]] = {}

    def years(self) -> list[int]:
        ys: set[int] = set()
        for by_year in self.data.values():
            ys.update(by_year.keys())
        return sorted(ys)

    def series(self, field: str) -> list[tuple[int, float]]:
        """(year, value) pairs sorted ascending, None values skipped."""
        by_year = self.data.get(field, {})
        return sorted((y, v) for y, v in by_year.items() if v is not None)

    def latest(self, field: str) -> float | None:
        s = self.series(field)
        return s[-1][1] if s else None

    def value(self, field: str, year: int) -> float | None:
        return self.data.get(field, {}).get(year)


class PriceHistory(BaseModel):
    """OHLCV price history with a DatetimeIndex DataFrame."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    df: pd.DataFrame  # columns: open, high, low, close, volume

    def last_close(self) -> float | None:
        if self.df.empty:
            return None
        return float(self.df["close"].iloc[-1])
