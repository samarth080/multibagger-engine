"""Official NSE corporate financial-result discovery with preserved lineage."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

from mbe.data.provider import ProviderError
from mbe.financials.document_fetch import SafeDocumentFetcher, validate_official_url
from mbe.financials.domain import ConsolidationBasis, FinancialPeriod, PeriodType
from mbe.financials.official_domain import (
    AttachmentFormat,
    DiscoveredAttachment,
    DiscoveredOfficialFiling,
    NSE_DISCOVERY_ADAPTER_VERSION,
)


NSE_RESULTS_URL = (
    "https://www.nseindia.com/api/corporates-financial-results"
    "?index=equities&symbol={symbol}&period={period}"
)
IST = ZoneInfo("Asia/Kolkata")


def _nse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=IST).astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def _nse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d-%b-%Y").date()
    except ValueError:
        return None


def _basis(value: str | None) -> ConsolidationBasis:
    lowered = (value or "").strip().lower()
    if lowered == "consolidated":
        return ConsolidationBasis.CONSOLIDATED
    if lowered == "standalone":
        return ConsolidationBasis.STANDALONE
    return ConsolidationBasis.UNKNOWN


def _format_hint(url: str) -> AttachmentFormat:
    suffix = Path(urlsplit(url).path).suffix.lower()
    return {
        ".xml": AttachmentFormat.XBRL_XML,
        ".json": AttachmentFormat.JSON,
        ".csv": AttachmentFormat.CSV,
        ".xls": AttachmentFormat.XLS,
        ".xlsx": AttachmentFormat.XLSX,
        ".html": AttachmentFormat.HTML,
        ".htm": AttachmentFormat.HTML,
        ".pdf": AttachmentFormat.TEXT_PDF,
        ".zip": AttachmentFormat.ZIP,
    }.get(suffix, AttachmentFormat.OTHER)


def _period(entry: dict) -> FinancialPeriod:
    start = _nse_date(entry.get("fromDate"))
    end = _nse_date(entry.get("toDate"))
    if end is None:
        raise ProviderError("NSE filing metadata has no valid period end")
    label = " ".join(str(entry.get(key) or "") for key in ("period", "relatingTo")).lower()
    cumulative_label = str(entry.get("cumulative") or "").strip().lower()
    if "annual" in label:
        period_type = PeriodType.ANNUAL
        quarter = None
    elif "nine" in label or "9 month" in label or "six" in label or "6 month" in label or (
        "cumulative" in cumulative_label and not cumulative_label.startswith("non")
    ):
        period_type = PeriodType.YEAR_TO_DATE
        quarter = {6: 2, 9: 3}.get(((end - start).days + 1) // 30 if start else 0)
    else:
        period_type = PeriodType.QUARTER
        quarter = {6: 1, 9: 2, 12: 3, 3: 4}.get(end.month)
        if quarter is None:
            raise ProviderError("NSE quarter metadata has a non-standard period end")
    fiscal_year = end.year if end.month <= 3 else end.year + 1
    duration = (end - start).days + 1 if start else None
    return FinancialPeriod(
        period_type=period_type,
        fiscal_year=fiscal_year,
        fiscal_quarter=quarter,
        period_start=start,
        period_end=end,
        duration_days=duration,
        source_label=entry.get("financialYear") or entry.get("period"),
    )


def _revision_hint(entry: dict) -> str:
    text = " ".join(str(entry.get(key) or "") for key in (
        "resultDescription", "relatingTo", "subject", "reInd"
    )).lower()
    if any(word in text for word in ("revised", "revision", "corrigendum", "replacement")) or entry.get("reInd") == "Y":
        return "revised"
    return "original"


def parse_discovery_entry(
    entry: dict,
    *,
    retrieved_at: datetime,
    source_url: str,
    raw_response_hash: str | None = None,
) -> DiscoveredOfficialFiling:
    if not isinstance(entry, dict):
        raise ProviderError("NSE filing discovery row is not an object")
    symbol = str(entry.get("symbol") or "").strip().upper()
    company_name = str(entry.get("companyName") or "").strip()
    publication = _nse_datetime(entry.get("broadCastDate") or entry.get("filingDate"))
    filing_timestamp = _nse_datetime(entry.get("filingDate")) or publication
    if not symbol or not company_name or publication is None or filing_timestamp is None:
        raise ProviderError("NSE filing discovery row is missing identity or publication time")
    period = _period(entry)
    attachments: list[DiscoveredAttachment] = []
    seen_urls: set[str] = set()
    for key, declared in (("xbrl", "application/xml"), ("resultDetailedDataLink", "text/html")):
        url = str(entry.get(key) or "").strip()
        if not url.startswith("https://") or url.rstrip().endswith("/-") or url in seen_urls:
            continue
        validate_official_url(url)
        seen_urls.add(url)
        filename = Path(urlsplit(url).path).name or f"{symbol}-{period.period_end.isoformat()}"
        attachments.append(DiscoveredAttachment(
            sequence=len(attachments) + 1,
            source_url=url,
            filename=filename,
            declared_content_type=declared,
            format_hint=_format_hint(url),
        ))
    metadata_json = json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)
    raw_hash = hashlib.sha256(metadata_json.encode()).hexdigest()
    filing_type = "annual_results" if period.period_type == PeriodType.ANNUAL else "quarterly_results"
    source_filing_id = str(entry.get("seqNumber") or entry.get("params") or raw_hash)
    basis = _basis(entry.get("consolidated"))
    canonical_payload = {
        "symbol": symbol,
        "filing_type": filing_type,
        "period_end": period.period_end.isoformat(),
        "publication_timestamp": publication.isoformat(),
        "basis": basis.value,
        "source_filing_id": source_filing_id,
    }
    canonical_hash = hashlib.sha256(json.dumps(canonical_payload, sort_keys=True).encode()).hexdigest()
    return DiscoveredOfficialFiling(
        source_filing_id=source_filing_id,
        company_name=company_name,
        nse_symbol=symbol,
        isin=(str(entry.get("isin") or "").strip() or None),
        subject=str(entry.get("resultDescription") or entry.get("relatingTo") or entry.get("period") or "Financial results"),
        category="corporate_financial_results",
        filing_type=filing_type,
        filing_date=filing_timestamp.date(),
        publication_timestamp=publication,
        source_timestamp=publication,
        retrieved_at=retrieved_at,
        period=period,
        basis_hint=basis,
        audited_status=str(entry.get("audited") or "unknown").strip().lower(),
        revision_hint=_revision_hint(entry),
        source_url=source_url,
        raw_metadata_hash=raw_hash,
        raw_response_hash=raw_response_hash or raw_hash,
        canonical_identity_hash=canonical_hash,
        attachments=tuple(attachments),
        raw_metadata=entry,
    )


class NseOfficialFilingProvider:
    """Discover official result announcements; attachment parsing is separate."""

    name = "nse_financial_results"
    version = NSE_DISCOVERY_ADAPTER_VERSION

    def __init__(self, fetcher: SafeDocumentFetcher | None = None):
        self.fetcher = fetcher or SafeDocumentFetcher()

    def discover_symbol(
        self,
        symbol: str,
        *,
        date_from: date,
        date_to: date,
        periods: tuple[str, ...] = ("Annual", "Quarterly"),
        max_pages: int = 2,
        max_filings: int = 100,
        force: bool = False,
    ) -> list[DiscoveredOfficialFiling]:
        if date_from > date_to:
            raise ValueError("date_from must not follow date_to")
        clean_symbol = symbol.removesuffix(".NS").upper()
        if not clean_symbol or len(clean_symbol) > 40 or not all(ch.isalnum() or ch in "&-_" for ch in clean_symbol):
            raise ValueError("invalid NSE symbol")
        if len(periods) > max_pages:
            raise ValueError("discovery page cap exceeded")
        if not periods or any(period not in {"Annual", "Quarterly"} for period in periods):
            raise ValueError("periods must contain only Annual and/or Quarterly")
        retrieved_at = datetime.now(timezone.utc)
        discovered: list[DiscoveredOfficialFiling] = []
        seen: set[tuple[str, str]] = set()
        for period in periods:
            url = NSE_RESULTS_URL.format(symbol=quote(clean_symbol, safe="&-_"), period=quote(period))
            document = self.fetcher.fetch_document(
                url,
                filename=f"discovery-{clean_symbol}-{period.lower()}.json",
                declared_content_type="application/json",
                force=force,
            )
            if document.attachment_format != AttachmentFormat.JSON:
                raise ProviderError("NSE discovery response was not JSON")
            try:
                payload = json.loads(document.content)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProviderError("NSE discovery JSON was invalid") from exc
            rows = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                raise ProviderError("NSE discovery JSON has an unsupported shape")
            for row in rows:
                try:
                    filing = parse_discovery_entry(
                        row,
                        retrieved_at=retrieved_at,
                        source_url=url,
                        raw_response_hash=document.sha256,
                    )
                except ProviderError:
                    continue
                if not date_from <= filing.filing_date <= date_to:
                    continue
                identity = (filing.source_filing_id, filing.raw_metadata_hash)
                if identity in seen:
                    continue
                seen.add(identity)
                discovered.append(filing)
                if len(discovered) >= max_filings:
                    return sorted(discovered, key=lambda item: item.publication_timestamp)
        return sorted(discovered, key=lambda item: item.publication_timestamp)

    def list_filings(self, instrument_id: str, *, as_of=None):
        raise ProviderError(
            "canonical instrument lookup is required; use discover_symbol with the stored NSE mapping"
        )

    def fetch_filing(self, source_filing_id: str):
        raise ProviderError(
            "source filing IDs are metadata identities; fetch a validated discovered attachment URL"
        )
