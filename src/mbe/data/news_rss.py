"""RSS news & government-policy ingestion — DESCRIPTIVE ONLY, never scored.

Free feeds, no API keys: Google News RSS per company for pick headlines and
a policy-flavoured query per industry for policy items. External XML goes
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
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"


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
        # feeds are external input: autoescape blocks markup injection in the
        # published page but not scheme abuse — a javascript:/data: link would
        # render as a live clickable URI, so only http(s) survives parsing
        if not link.lower().startswith(("http://", "https://")):
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


def company_news(
    name: str,
    ticker: str,
    cache: DiskCache | None = None,
    fetcher=default_http,
) -> list[NewsItem]:
    """Top recent headlines for one company (Google News RSS)."""
    base = ticker.split(".")[0]
    query = urllib.parse.quote(f'"{name}" OR "{base}"')
    key = f"news_{base}"
    if cache and (hit := cache.get_json(key)):
        return [NewsItem(**i) for i in hit["items"]]
    try:
        items = dedupe_recent(parse_rss(fetcher(GOOGLE_NEWS_URL.format(query=query))))
    except Exception:
        return []  # context must never fail a build; builder prints counts
    if cache:
        cache.set_json(key, {"items": [i.model_dump(mode="json") for i in items]})
    return items


def _policy_slug(key: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in key.lower()).strip("_")


def sector_policy(
    sector: str | None,
    industry: str | None,
    cache: DiskCache | None = None,
    fetcher=default_http,
) -> list[NewsItem]:
    """Recent policy/scheme headlines for one industry, in English.

    Replaces a PIB RSS feed that served Hindi headlines while the tagger
    matched English keywords — it tagged 0 of 12 items in the last build and
    could never have tagged any. The lesson is in the shape of this function:
    the *query* is the relevance filter, so there is no separate matching step
    left that can quietly return nothing while the build reports success.

    `sectors` carries the single key the query was built from. The site
    concatenates policy across industries into one flat list and each report
    filters it back down, so that field is load-bearing rather than decorative.
    """
    key = industry or sector
    if not key:
        return []
    cache_key = f"policy_{_policy_slug(key)}"
    if cache and (hit := cache.get_json(cache_key)):
        return [NewsItem(**i) for i in hit["items"]]
    query = urllib.parse.quote(f"{key} India government policy scheme")
    try:
        items = dedupe_recent(parse_rss(fetcher(GOOGLE_NEWS_URL.format(query=query))))
    except Exception:
        return []  # context must never fail a build; the builder prints counts
    for item in items:
        item.sectors = [key]
    if cache:
        cache.set_json(cache_key, {"items": [i.model_dump(mode="json") for i in items]})
    return items
