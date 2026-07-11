"""Yahoo Finance provider (via yfinance). First concrete DataProvider.

Known limitations, surfaced rather than hidden:
- No Indian promoter-holding / pledging detail (insider_pct is a weak proxy).
- Statement history is typically 4-5 annual periods.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from mbe.data.cache import DiskCache
from mbe.data.provider import ProviderError
from mbe.models.company import CompanyInfo, FinancialHistory, PriceHistory

# canonical field -> ordered fallback row names in yfinance statements
FIELD_MAP: dict[str, list[str]] = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "EBIT"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "total_assets": ["Total Assets"],
    "total_equity": [
        "Stockholders Equity",
        "Common Stock Equity",
        "Total Equity Gross Minority Interest",
    ],
    "total_debt": ["Total Debt"],
    "cash": [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "End Cash Position",
    ],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "cfo": ["Operating Cash Flow"],
    "capex": ["Capital Expenditure", "Capital Expenditure Reported"],
    "fcf": ["Free Cash Flow"],
    "shares_diluted": [
        "Diluted Average Shares",
        "Basic Average Shares",
        "Ordinary Shares Number",
    ],
    "dividends_paid": ["Cash Dividends Paid"],
}

# yfinance reports these as negative outflows; we store positive magnitudes
_ABS_FIELDS = {"capex", "dividends_paid"}

_INFO_MAP = {
    "name": "shortName",
    "exchange": "exchange",
    "currency": "currency",
    "sector": "sector",
    "industry": "industry",
    "market_cap": "marketCap",
    "shares_outstanding": "sharesOutstanding",
    "float_shares": "floatShares",
    "insider_pct": "heldPercentInsiders",
    "institution_pct": "heldPercentInstitutions",
    "beta": "beta",
    "trailing_pe": "trailingPE",
    "price": "currentPrice",
    "dividend_yield": "dividendYield",
    "description": "longBusinessSummary",
}


def _extract(frame: pd.DataFrame, field: str) -> dict[int, float | None]:
    if frame is None or frame.empty:
        return {}
    for row_name in FIELD_MAP[field]:
        if row_name in frame.index:
            out: dict[int, float | None] = {}
            for col, val in frame.loc[row_name].items():
                year = pd.Timestamp(col).year
                if pd.isna(val):
                    out[year] = None
                else:
                    v = float(val)
                    out[year] = abs(v) if field in _ABS_FIELDS else v
            return out
    return {}


def map_statements(
    income: pd.DataFrame, balance: pd.DataFrame, cashflow: pd.DataFrame
) -> FinancialHistory:
    """Map yfinance statement frames into canonical FinancialHistory."""
    frames = {
        "revenue": income,
        "gross_profit": income,
        "operating_income": income,
        "ebitda": income,
        "net_income": income,
        "interest_expense": income,
        "shares_diluted": income,
        "total_assets": balance,
        "total_equity": balance,
        "total_debt": balance,
        "cash": balance,
        "current_assets": balance,
        "current_liabilities": balance,
        "cfo": cashflow,
        "capex": cashflow,
        "fcf": cashflow,
        "dividends_paid": cashflow,
    }
    data = {field: _extract(frame, field) for field, frame in frames.items()}

    # derive fcf = cfo - capex for years where the reported row is missing
    fcf = dict(data.get("fcf") or {})
    for year, cfo_val in (data.get("cfo") or {}).items():
        if year in fcf and fcf[year] is not None:
            continue
        capex_val = (data.get("capex") or {}).get(year)
        if cfo_val is not None and capex_val is not None:
            fcf[year] = cfo_val - capex_val
    data["fcf"] = fcf

    return FinancialHistory(data={k: v for k, v in data.items() if v})


class YahooProvider:
    def __init__(self, cache: DiskCache | None = None):
        self.cache = cache

    def _ticker(self, ticker: str) -> yf.Ticker:
        return yf.Ticker(ticker)

    def get_info(self, ticker: str) -> CompanyInfo:
        if self.cache and (hit := self.cache.get_json(f"info_{ticker}")):
            return CompanyInfo(**hit)
        try:
            raw = self._ticker(ticker).info or {}
        except Exception as exc:  # yfinance raises many exception types
            raise ProviderError(f"info fetch failed for {ticker}: {exc}") from exc
        if not raw.get("shortName") and not raw.get("marketCap"):
            raise ProviderError(f"no usable info for {ticker}")
        fields = {ours: raw.get(theirs) for ours, theirs in _INFO_MAP.items()}
        info = CompanyInfo(ticker=ticker, **fields)
        if self.cache:
            self.cache.set_json(f"info_{ticker}", info.model_dump())
        return info

    def get_financials(self, ticker: str) -> FinancialHistory:
        if self.cache and (hit := self.cache.get_json(f"fin_{ticker}")):
            return FinancialHistory(
                data={
                    f: {int(y): v for y, v in by_year.items()}
                    for f, by_year in hit["data"].items()
                }
            )
        try:
            t = self._ticker(ticker)
            fin = map_statements(t.income_stmt, t.balance_sheet, t.cashflow)
        except Exception as exc:
            raise ProviderError(f"financials fetch failed for {ticker}: {exc}") from exc
        if not fin.data:
            raise ProviderError(f"no financial statements for {ticker}")
        if self.cache:
            self.cache.set_json(f"fin_{ticker}", fin.model_dump())
        return fin

    def get_prices(self, ticker: str, years: int = 3) -> PriceHistory:
        key = f"prices_{ticker}_{years}y"
        if self.cache is not None and (hit := self.cache.get_df(key)) is not None:
            return PriceHistory(df=hit)
        try:
            df = self._ticker(ticker).history(period=f"{years}y", auto_adjust=True)
        except Exception as exc:
            raise ProviderError(f"price fetch failed for {ticker}: {exc}") from exc
        if df is None or df.empty:
            raise ProviderError(f"no price history for {ticker}")
        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )[["open", "high", "low", "close", "volume"]]
        df.index = pd.to_datetime(df.index).tz_localize(None)
        if self.cache:
            self.cache.set_df(key, df)
        return PriceHistory(df=df)

    def benchmark_ticker(self, ticker: str) -> str:
        if ticker.endswith(".NS") or ticker.endswith(".BO"):
            return "^NSEI"  # NIFTY 50
        return "^GSPC"  # S&P 500
