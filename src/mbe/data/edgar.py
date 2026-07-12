"""SEC EDGAR XBRL fundamentals (companyfacts API). US listings, 10-15+ years
of annual statements with exact filing dates -> honest point-in-time gating.

Point-in-time rule: for every fiscal year we keep the value from the
EARLIEST filing that reported it (the original 10-K). Restatements filed
later would leak future knowledge into a backtest, so they are ignored.

SEC API policy: descriptive User-Agent required, <=10 requests/second
(we make ~1 per ticker and cache for 7 days).

Known gaps (surfaced, not hidden): no reliable EBITDA tag (dependent metrics
degrade to None); total_debt approximated from long-term debt tags.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime

from mbe.data.cache import DiskCache
from mbe.data.provider import ProviderError
from mbe.models.company import FinancialHistory

CIK_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
USER_AGENT = "MultibaggerEngine/0.3 research tool (contact: singhamlittle895@gmail.com)"

# canonical field -> ordered us-gaap tag fallbacks
TAG_MAP: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonoperating"],
    "total_assets": ["Assets"],
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "total_debt": [
        "DebtLongtermAndShorttermCombinedAmount",
        "LongTermDebt",
        "LongTermDebtNoncurrent",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "cfo": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "dividends_paid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
}

_ABS_FIELDS = {"capex", "dividends_paid"}
_ANNUAL_DURATION = (340, 390)  # days; excludes quarterly/comparative stubs


def default_http(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()


def resolve_cik(ticker: str, cache: DiskCache | None, fetcher=default_http) -> int:
    payload = cache.get_json("edgar_cik_map") if cache else None
    if payload is None:
        try:
            payload = json.loads(fetcher(CIK_MAP_URL))
        except Exception as exc:
            raise ProviderError(f"CIK map download failed: {exc}") from exc
        if cache:
            cache.set_json("edgar_cik_map", payload)
    wanted = ticker.upper()
    for entry in payload.values():
        if entry["ticker"] == wanted:
            return int(entry["cik_str"])
    raise ProviderError(f"no CIK found for ticker {ticker!r}")


def _annual_facts(tag_payload: dict) -> list[dict]:
    """All USD facts from 10-K filings that represent a full fiscal year."""
    out = []
    for fact in tag_payload.get("units", {}).get("USD", []):
        if not str(fact.get("form", "")).startswith("10-K"):
            continue
        if "start" in fact and fact["start"]:
            days = (
                datetime.fromisoformat(fact["end"])
                - datetime.fromisoformat(fact["start"])
            ).days
            if not (_ANNUAL_DURATION[0] <= days <= _ANNUAL_DURATION[1]):
                continue
        out.append(fact)
    return out


def parse_companyfacts(payload: dict) -> FinancialHistory:
    gaap = payload.get("facts", {}).get("us-gaap", {})
    data: dict[str, dict[int, float | None]] = {}
    filed: dict[int, date] = {}

    for field, tags in TAG_MAP.items():
        for tag in tags:
            if tag not in gaap:
                continue
            by_year: dict[int, tuple[date, float]] = {}  # year -> (filed, value)
            for fact in _annual_facts(gaap[tag]):
                year = datetime.fromisoformat(fact["end"]).year
                filed_on = date.fromisoformat(fact["filed"])
                # keep the ORIGINAL (earliest-filed) value; amendments leak the future
                if year not in by_year or filed_on < by_year[year][0]:
                    val = float(fact["val"])
                    if field in _ABS_FIELDS:
                        val = abs(val)
                    by_year[year] = (filed_on, val)
            if by_year:
                data[field] = {y: v for y, (_, v) in by_year.items()}
                for year, (filed_on, _) in by_year.items():
                    if year not in filed or filed_on < filed[year]:
                        filed[year] = filed_on
                break  # first tag with data wins

    # derive fcf = cfo - capex (capex stored positive)
    if "cfo" in data:
        fcf: dict[int, float | None] = {}
        for year, cfo_val in data["cfo"].items():
            capex_val = data.get("capex", {}).get(year)
            if cfo_val is not None and capex_val is not None:
                fcf[year] = cfo_val - capex_val
        if fcf:
            data["fcf"] = fcf

    return FinancialHistory(data=data, filed=filed)


class EdgarFundamentals:
    """Fundamentals-only provider; pair with Yahoo via CompositeProvider."""

    def __init__(self, cache: DiskCache | None = None, fetcher=default_http):
        self.cache = cache
        self.fetcher = fetcher

    def get_financials(self, ticker: str) -> FinancialHistory:
        key = f"edgar_fin_{ticker.upper()}"
        if self.cache and (hit := self.cache.get_json(key)):
            return FinancialHistory(
                data={
                    f: {int(y): v for y, v in by_year.items()}
                    for f, by_year in hit["data"].items()
                },
                filed={int(y): date.fromisoformat(d) for y, d in hit["filed"].items()},
            )
        cik = resolve_cik(ticker, self.cache, self.fetcher)
        try:
            payload = json.loads(self.fetcher(FACTS_URL.format(cik=cik)))
        except Exception as exc:
            raise ProviderError(f"companyfacts fetch failed for {ticker}: {exc}") from exc
        fin = parse_companyfacts(payload)
        if not fin.data:
            raise ProviderError(f"no annual us-gaap facts for {ticker}")
        if self.cache:
            self.cache.set_json(
                key,
                {
                    "data": fin.data,
                    "filed": {y: d.isoformat() for y, d in fin.filed.items()},
                },
            )
        return fin
