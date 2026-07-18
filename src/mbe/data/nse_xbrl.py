"""NSE corporate-results XBRL fundamentals — the Indian statement source.

`corporates-financial-results` (openly served, unlike NSE's quote APIs) lists
every annual filing per symbol back to ~FY2005 with **broadcast timestamps**
(exact point-in-time availability) and links each filing's Ind-AS XBRL on
nsearchives. Structure (validated against RELIANCE FY24 to the crore):

- context `FourD` = the 12-month column (P&L + cash flow)
- context `OneI`  = year-end balance sheet
- `ReportingQuarter` must be "Yearly" (Q4 filings carry the annual column)

Point-in-time rule: per fiscal year keep the EARLIEST broadcast (the original
filing; revisions would leak the future). Consolidated preferred, standalone
used only for years with no consolidated filing.

Coverage note: the Ind-AS XBRL schema starts ~FY2017; older filings use a
different taxonomy and are skipped (surfaced as absent years, lowering
confidence — never guessed).
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import date, datetime

import defusedxml.ElementTree as ET
from xml.etree.ElementTree import ParseError

from mbe.data.cache import DiskCache
from mbe.data.provider import ProviderError
from mbe.models.company import FinancialHistory

INDEX_URL = (
    "https://www.nseindia.com/api/corporates-financial-results"
    "?index=equities&symbol={symbol}&period=Annual"
)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# canonical field -> (context kind, ordered tag fallbacks)
_YEAR = "FourD"
_INSTANT = "OneI"
TAG_MAP: dict[str, tuple[str, list[str]]] = {
    "revenue": (_YEAR, ["RevenueFromOperations", "Income"]),
    "net_income": (_YEAR, ["ProfitLossForPeriod", "ProfitLossForPeriodFromContinuingOperations"]),
    "interest_expense": (_YEAR, ["FinanceCosts"]),
    "cfo": (_YEAR, ["CashFlowsFromUsedInOperatingActivities"]),
    "capex": (_YEAR, ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"]),
    "dividends_paid": (_YEAR, ["DividendsPaidClassifiedAsFinancingActivities"]),
    "total_assets": (_INSTANT, ["Assets"]),
    "total_equity": (_INSTANT, ["Equity", "EquityAttributableToOwnersOfParent"]),
    "cash": (_INSTANT, ["CashAndCashEquivalents"]),
    "current_assets": (_INSTANT, ["CurrentAssets"]),
    "current_liabilities": (_INSTANT, ["CurrentLiabilities"]),
}


def default_http(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def parse_results_xbrl(xml_text: str) -> dict[str, float]:
    """Canonical values from one yearly results filing."""
    try:
        root = ET.fromstring(xml_text)
    except (ParseError, ValueError) as exc:
        raise ProviderError(f"unparseable results XBRL: {exc}") from exc

    facts: dict[tuple[str, str], float] = {}
    reporting = None
    for el in root.iter():
        name = _local(el.tag)
        ctx = el.get("contextRef")
        if name == "ReportingQuarter" and el.text:
            reporting = el.text.strip()
        if ctx in (_YEAR, _INSTANT) and el.text:
            try:
                facts[(name, ctx)] = float(el.text.strip())
            except ValueError:
                continue

    if reporting != "Yearly":
        raise ProviderError(f"not a yearly filing (ReportingQuarter={reporting!r})")

    values: dict[str, float] = {}
    for field, (ctx, tags) in TAG_MAP.items():
        for tag in tags:
            if (tag, ctx) in facts:
                values[field] = facts[(tag, ctx)]
                break

    # EBIT proxy: results filings report PBT and finance costs, not EBIT
    pbt = facts.get(("ProfitBeforeTax", _YEAR))
    fin_costs = facts.get(("FinanceCosts", _YEAR))
    if pbt is not None and fin_costs is not None:
        values["operating_income"] = pbt + fin_costs
        dep = facts.get(("DepreciationDepletionAndAmortisationExpense", _YEAR))
        if dep is not None:
            values["ebitda"] = values["operating_income"] + dep

    borrowings = [
        facts.get(("BorrowingsCurrent", _INSTANT)),
        facts.get(("BorrowingsNoncurrent", _INSTANT)),
    ]
    known = [b for b in borrowings if b is not None]
    if known:
        values["total_debt"] = sum(known)

    paid_up = facts.get(("PaidUpValueOfEquityShareCapital", _YEAR))
    face = facts.get(("FaceValueOfEquityShareCapital", _YEAR))
    if paid_up and face:
        values["shares_diluted"] = paid_up / face

    if "cfo" in values and "capex" in values:
        values["fcf"] = values["cfo"] - values["capex"]

    if not values:
        raise ProviderError("yearly filing contained no mappable facts")
    return values


# ---- legacy (pre-Ind-AS, FY2005-2018) results pages: HTML, P&L only ----

_LEGACY_LABELS: dict[str, list[str]] = {
    "revenue": [
        "Total income from operations",
        "Net sales/income from operations",
    ],
    "net_income": [
        "Net Profit / (Loss) for the period",
        "Net Profit / (Loss) from ordinary activities after tax",
    ],
    "_pbt": ["Profit / (Loss) from ordinary activities before tax"],
    "interest_expense": ["Finance costs"],
    "_depreciation": ["Depreciation and amortisation expense"],
    "_paid_up": ["Paid-up equity share capital"],
    "_face": ["Face Value"],
}

_UNIT_MULTIPLIERS = [
    ("in crores", 1e7), ("in crore", 1e7),
    ("in lakhs", 1e5), ("in lakh", 1e5),
    ("in millions", 1e6), ("in thousands", 1e3),
]


def parse_legacy_results_html(html: str) -> dict[str, float]:
    """P&L extraction from NSE's legacy results pages (no XBRL before FY2019).
    Balance sheet and cash flow are absent in this format — those fields stay
    unreported for legacy years, lowering completeness honestly."""
    import re

    text = re.sub(r"<[^>]+>", "|", html)
    text = re.sub(r"[|\s]+", " ", text)

    multiplier = None
    lowered = text.lower()
    for marker, mult in _UNIT_MULTIPLIERS:
        if marker in lowered:
            multiplier = mult
            break
    if multiplier is None:
        raise ProviderError("legacy results page: no recognizable unit marker")

    def grab(labels: list[str]) -> float | None:
        for label in labels:
            m = re.search(
                re.escape(label) + r"[^0-9\-]{0,90}(-?[0-9][0-9,]*(?:\.[0-9]+)?)",
                text,
            )
            if m:
                return float(m.group(1).replace(",", ""))
        return None

    raw = {field: grab(labels) for field, labels in _LEGACY_LABELS.items()}
    values: dict[str, float] = {}
    for field in ("revenue", "net_income", "interest_expense"):
        if raw[field] is not None:
            values[field] = raw[field] * multiplier
    if raw["_pbt"] is not None and raw["interest_expense"] is not None:
        values["operating_income"] = (raw["_pbt"] + raw["interest_expense"]) * multiplier
        if raw["_depreciation"] is not None:
            values["ebitda"] = values["operating_income"] + raw["_depreciation"] * multiplier
    if raw["_paid_up"] and raw["_face"]:
        # paid-up capital is in the page unit; face value is in plain rupees
        values["shares_diluted"] = raw["_paid_up"] * multiplier / raw["_face"]

    if "revenue" not in values or "net_income" not in values:
        raise ProviderError("legacy results page: core P&L labels not found")
    return values


def _real_xbrl_url(entry: dict) -> bool:
    """Pre-FY2019 entries carry the archives base + '-' placeholder, which
    still starts with http — a real file URL must not end in '/-'."""
    url = str(entry.get("xbrl") or "")
    return url.startswith("http") and not url.rstrip().endswith("/-")


def _fy_year(to_date: str) -> int:
    return datetime.strptime(to_date, "%d-%b-%Y").year


def _broadcast(entry: dict) -> datetime:
    return datetime.strptime(entry["broadCastDate"], "%d-%b-%Y %H:%M:%S")


class NseFundamentals:
    """Fundamentals-only provider; pair with Yahoo via CompositeProvider."""

    def __init__(
        self, cache: DiskCache | None = None, fetcher=default_http, sleep_s: float = 0.3
    ):
        self.cache = cache
        self.fetcher = fetcher
        self.sleep_s = sleep_s

    def get_financials(self, ticker: str) -> FinancialHistory:
        symbol = ticker.removesuffix(".NS").removesuffix(".BO").upper()
        key = f"nse_fin_{symbol}"
        if self.cache and (hit := self.cache.get_json(key)):
            return FinancialHistory(
                data={
                    f: {int(y): v for y, v in by_year.items()}
                    for f, by_year in hit["data"].items()
                },
                filed={int(y): date.fromisoformat(d) for y, d in hit["filed"].items()},
            )

        try:
            index = json.loads(self.fetcher(INDEX_URL.format(symbol=symbol)))
        except Exception as exc:
            raise ProviderError(f"NSE results index failed for {symbol}: {exc}") from exc
        if not isinstance(index, list) or not index:
            raise ProviderError(f"no NSE annual results for {symbol}")

        def usable(entry: dict) -> bool:
            has_xbrl = _real_xbrl_url(entry)
            link = entry.get("resultDetailedDataLink")
            has_legacy = bool(link) and str(link).startswith("http")
            return bool(entry.get("toDate")) and (has_xbrl or has_legacy)

        # per year: consolidated preferred; earliest broadcast wins (original filing)
        chosen: dict[int, dict] = {}
        for entry in index:
            if not usable(entry):
                continue
            year = _fy_year(entry["toDate"])
            current = chosen.get(year)
            if current is None:
                chosen[year] = entry
                continue
            cur_consol = current.get("consolidated") == "Consolidated"
            new_consol = entry.get("consolidated") == "Consolidated"
            if new_consol and not cur_consol:
                chosen[year] = entry
            elif new_consol == cur_consol and _broadcast(entry) < _broadcast(current):
                chosen[year] = entry

        data: dict[str, dict[int, float | None]] = {}
        filed: dict[int, date] = {}
        for year, entry in sorted(chosen.items()):
            try:
                if _real_xbrl_url(entry):
                    values = parse_results_xbrl(self.fetcher(entry["xbrl"]))
                else:
                    # pre-FY2019: no XBRL; parse the legacy results page (P&L only)
                    values = parse_legacy_results_html(
                        self.fetcher(entry["resultDetailedDataLink"])
                    )
            except ProviderError:
                continue  # non-yearly / unparseable filing: year stays absent
            except Exception:
                continue
            for field, value in values.items():
                data.setdefault(field, {})[year] = value
            filed[year] = _broadcast(entry).date()
            if self.sleep_s:
                time.sleep(self.sleep_s)

        if not data:
            raise ProviderError(f"no parseable yearly XBRL filings for {symbol}")
        fin = FinancialHistory(data=data, filed=filed)
        if self.cache:
            self.cache.set_json(
                key,
                {
                    "data": fin.data,
                    "filed": {y: d.isoformat() for y, d in fin.filed.items()},
                },
            )
        return fin
