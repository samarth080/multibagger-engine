"""RSS news & government-policy ingestion — DESCRIPTIVE ONLY, never scored.

Free feeds, no API keys: Google News RSS per company for pick headlines,
PIB (Press Information Bureau) RSS for policy items. External XML goes
through defusedxml. Cached like every other provider; offline-tested with
canned fixtures. A feed failure degrades to an empty list (context must
never fail a weekly build) — the site builder prints item counts so an
empty feed is visible, not silent. Scoring news requires its own
pre-registered validation (future increment); this module only surfaces
context."""

from __future__ import annotations

import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree
from pydantic import BaseModel

from mbe.data.cache import DiskCache

GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)
PIB_RSS_URL = "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

# sector/industry group name -> lowercase keywords tagging a PIB item as relevant
POLICY_KEYWORDS: dict[str, list[str]] = {
    "Semiconductors": ["semiconductor", "chip", "fab "],
    "Solar": ["solar", "renewable"],
    "Aerospace & Defense": ["defence", "defense", "drdo"],
    "Auto Parts": ["automobile", "electric vehicle", " ev "],
    "Electrical Equipment & Parts": ["transmission", "power grid", "electricity"],
    "Drug Manufacturers - Specialty & Generic": ["pharma", "drug", "medicine"],
    "Capital Markets": ["sebi", "capital market"],
    "Electronic Components": ["electronics manufacturing", "pli"],
    "Steel": ["steel"],
    "Banks - Regional": ["rbi", "banking"],
}


class NewsItem(BaseModel):
    title: str
    link: str
    published: datetime | None = None
    source: str | None = None
    sectors: list[str] = []  # policy items: matched sector keys


def default_http(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_rss(xml_text: str) -> list[NewsItem]:
    """RSS 2.0 channel/item -> NewsItem. Bad dates become None, never crash."""
    root = ElementTree.fromstring(xml_text)
    items: list[NewsItem] = []
    for node in root.iter("item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        if not title or not link:
            continue
        published = None
        raw_date = node.findtext("pubDate")
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date)
            except (TypeError, ValueError):
                published = None
            else:
                if published.tzinfo is None:
                    # zone-less RFC-2822 dates parse as naive datetimes (no
                    # exception); normalize so aware comparisons never crash
                    published = published.replace(tzinfo=timezone.utc)
        items.append(
            NewsItem(
                title=title, link=link, published=published,
                source=node.findtext("source"),
            )
        )
    return items


def dedupe_recent(
    items: list[NewsItem],
    days: int = 7,
    limit: int = 5,
    now: datetime | None = None,
) -> list[NewsItem]:
    """Newest-first, title-deduped, within the window. Undated items are
    kept (missing data is surfaced, not silently dropped) but sort last."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    seen: set[str] = set()
    kept: list[NewsItem] = []
    for item in items:
        key = item.title.lower()
        if key in seen:
            continue
        if item.published is not None and item.published < cutoff:
            continue
        seen.add(key)
        kept.append(item)
    kept.sort(
        key=lambda i: i.published or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return kept[:limit]
