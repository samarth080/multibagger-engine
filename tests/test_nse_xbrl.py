import json
from datetime import date

import pytest

from mbe.data.cache import DiskCache
from mbe.data.nse_xbrl import NseFundamentals, parse_results_xbrl
from mbe.data.provider import ProviderError


def _xbrl(reporting="Yearly", revenue="9000", pat="800", suffix=""):
    """Miniature NSE Ind-AS results XBRL: quarter column (OneD), year column
    (FourD), balance sheet (OneI) — mirroring the real file structure."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:in-bse-fin="http://www.bseindia.com/xbrl/fin/2020-03-31/in-bse-fin">
  <xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="s">X</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-03-31</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="FourD"><xbrli:entity><xbrli:identifier scheme="s">X</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2023-04-01</xbrli:startDate><xbrli:endDate>2024-03-31</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:context id="OneI"><xbrli:entity><xbrli:identifier scheme="s">X</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2024-03-31</xbrli:instant></xbrli:period></xbrli:context>
  <in-bse-fin:ReportingQuarter contextRef="OneD">{reporting}</in-bse-fin:ReportingQuarter>
  <in-bse-fin:RevenueFromOperations contextRef="OneD">2400</in-bse-fin:RevenueFromOperations>
  <in-bse-fin:RevenueFromOperations contextRef="FourD">{revenue}</in-bse-fin:RevenueFromOperations>
  <in-bse-fin:ProfitLossForPeriod contextRef="FourD">{pat}</in-bse-fin:ProfitLossForPeriod>
  <in-bse-fin:ProfitBeforeTax contextRef="FourD">1000</in-bse-fin:ProfitBeforeTax>
  <in-bse-fin:FinanceCosts contextRef="FourD">100</in-bse-fin:FinanceCosts>
  <in-bse-fin:DepreciationDepletionAndAmortisationExpense contextRef="FourD">200</in-bse-fin:DepreciationDepletionAndAmortisationExpense>
  <in-bse-fin:CashFlowsFromUsedInOperatingActivities contextRef="FourD">900</in-bse-fin:CashFlowsFromUsedInOperatingActivities>
  <in-bse-fin:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities contextRef="FourD">300</in-bse-fin:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities>
  <in-bse-fin:DividendsPaidClassifiedAsFinancingActivities contextRef="FourD">50</in-bse-fin:DividendsPaidClassifiedAsFinancingActivities>
  <in-bse-fin:PaidUpValueOfEquityShareCapital contextRef="FourD">100</in-bse-fin:PaidUpValueOfEquityShareCapital>
  <in-bse-fin:FaceValueOfEquityShareCapital contextRef="FourD">10</in-bse-fin:FaceValueOfEquityShareCapital>
  <in-bse-fin:Assets contextRef="OneI">17000</in-bse-fin:Assets>
  <in-bse-fin:Equity contextRef="OneI">9000</in-bse-fin:Equity>
  <in-bse-fin:BorrowingsCurrent contextRef="OneI">1000</in-bse-fin:BorrowingsCurrent>
  <in-bse-fin:BorrowingsNoncurrent contextRef="OneI">2000</in-bse-fin:BorrowingsNoncurrent>
  <in-bse-fin:CashAndCashEquivalents contextRef="OneI">900</in-bse-fin:CashAndCashEquivalents>
  <in-bse-fin:CurrentAssets contextRef="OneI">4700</in-bse-fin:CurrentAssets>
  <in-bse-fin:CurrentLiabilities contextRef="OneI">3900</in-bse-fin:CurrentLiabilities>{suffix}
</xbrli:xbrl>"""


def test_parse_results_xbrl_year_column_and_balance_sheet():
    values = parse_results_xbrl(_xbrl())
    assert values["revenue"] == 9000.0  # FourD year column, not the 2400 quarter
    assert values["net_income"] == 800.0
    assert values["interest_expense"] == 100.0
    assert values["operating_income"] == 1000.0 + 100.0  # PBT + finance costs (EBIT proxy)
    assert values["ebitda"] == 1100.0 + 200.0
    assert values["cfo"] == 900.0
    assert values["capex"] == 300.0
    assert values["fcf"] == 600.0
    assert values["total_assets"] == 17000.0
    assert values["total_equity"] == 9000.0
    assert values["total_debt"] == 3000.0  # current + noncurrent borrowings
    assert values["cash"] == 900.0
    assert values["shares_diluted"] == 10.0  # paid-up / face value
    assert values["dividends_paid"] == 50.0


def test_parse_rejects_non_yearly_filing():
    with pytest.raises(ProviderError):
        parse_results_xbrl(_xbrl(reporting="First Quarter"))


INDEX = [
    {  # FY2024 consolidated — preferred
        "consolidated": "Consolidated", "toDate": "31-Mar-2024",
        "broadCastDate": "22-Apr-2024 19:47:12", "period": "Annual",
        "xbrl": "https://x/con2024.xml",
    },
    {  # FY2024 standalone — ignored (consolidated exists)
        "consolidated": "Non-Consolidated", "toDate": "31-Mar-2024",
        "broadCastDate": "22-Apr-2024 19:40:30", "period": "Annual",
        "xbrl": "https://x/std2024.xml",
    },
    {  # FY2023 revised filing — must lose to the original below
        "consolidated": "Consolidated", "toDate": "31-Mar-2023",
        "broadCastDate": "10-Jun-2023 10:00:00", "period": "Annual",
        "xbrl": "https://x/con2023rev.xml",
    },
    {  # FY2023 original
        "consolidated": "Consolidated", "toDate": "31-Mar-2023",
        "broadCastDate": "21-Apr-2023 19:59:35", "period": "Annual",
        "xbrl": "https://x/con2023.xml",
    },
    {  # FY2022 standalone only — used as fallback
        "consolidated": "Non-Consolidated", "toDate": "31-Mar-2022",
        "broadCastDate": "06-May-2022 12:00:00", "period": "Annual",
        "xbrl": "https://x/std2022.xml",
    },
]


def _fetcher(url: str) -> str:
    if "corporates-financial-results" in url:
        return json.dumps(INDEX)
    return {
        "https://x/con2024.xml": _xbrl(revenue="9000", pat="800"),
        "https://x/con2023.xml": _xbrl(revenue="8000", pat="700"),
        "https://x/con2023rev.xml": _xbrl(revenue="8888", pat="777"),
        "https://x/std2022.xml": _xbrl(revenue="7000", pat="600"),
    }[url]


def test_nse_fundamentals_end_to_end(tmp_path):
    provider = NseFundamentals(DiskCache(tmp_path), fetcher=_fetcher, sleep_s=0)
    fin = provider.get_financials("RELIANCE.NS")
    assert fin.value("revenue", 2024) == 9000.0
    assert fin.value("revenue", 2023) == 8000.0  # original, not the revision
    assert fin.value("revenue", 2022) == 7000.0  # standalone fallback
    assert fin.filed[2024] == date(2024, 4, 22)  # exact broadcast date
    assert fin.filed[2023] == date(2023, 4, 21)
    assert fin.value("total_debt", 2024) == 3000.0
