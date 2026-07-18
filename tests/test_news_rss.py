"""Offline tests for the RSS news/policy provider (canned fixtures)."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from mbe.data.cache import DiskCache
from mbe.data.news_rss import NewsItem, dedupe_recent, parse_rss, company_news, policy_items

GOOGLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>q</title>
<item><title>Natco Pharma wins US approval</title>
<link>https://example.com/a</link>
<pubDate>Fri, 17 Jul 2026 08:00:00 GMT</pubDate>
<source url="https://et.example">Economic Times</source></item>
<item><title>Natco Pharma wins US approval</title>
<link>https://example.com/dup</link>
<pubDate>Fri, 17 Jul 2026 09:00:00 GMT</pubDate></item>
<item><title>Old story</title><link>https://example.com/old</link>
<pubDate>Mon, 01 Jun 2026 08:00:00 GMT</pubDate></item>
<item><title>Undated story</title><link>https://example.com/u</link></item>
<item><title></title><link>https://example.com/empty</link></item>
</channel></rss>"""

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


def test_parse_rss_extracts_items_and_skips_empty_titles():
    items = parse_rss(GOOGLE_RSS)
    assert len(items) == 4  # empty-title item skipped
    assert items[0].title == "Natco Pharma wins US approval"
    assert items[0].source == "Economic Times"
    assert items[0].published is not None
    assert items[3].published is None  # undated survives parsing


def test_dedupe_recent_windows_dedupes_and_sorts():
    items = dedupe_recent(parse_rss(GOOGLE_RSS), days=7, limit=5, now=NOW)
    titles = [i.title for i in items]
    # duplicate title dropped, out-of-window dropped, undated kept but last
    assert titles == ["Natco Pharma wins US approval", "Undated story"]


def test_dedupe_recent_respects_limit():
    many = [
        NewsItem(title=f"t{i}", link=f"https://x/{i}",
                 published=datetime(2026, 7, 17, i, tzinfo=timezone.utc))
        for i in range(9)
    ]
    assert len(dedupe_recent(many, days=7, limit=5, now=NOW)) == 5


def test_parse_rss_bad_date_becomes_none_not_crash():
    xml = GOOGLE_RSS.replace("Fri, 17 Jul 2026 08:00:00 GMT", "not-a-date")
    items = parse_rss(xml)
    assert items[0].published is None


def test_parse_rss_naive_date_normalized_to_utc_not_crash():
    # a pubDate with no zone parses to a NAIVE datetime (stdlib behavior,
    # no exception) — it must be normalized so dedupe_recent's aware
    # comparison never raises
    xml = GOOGLE_RSS.replace(
        "Fri, 17 Jul 2026 08:00:00 GMT", "Fri, 17 Jul 2026 08:00:00"
    )
    items = dedupe_recent(parse_rss(xml), days=7, limit=5, now=NOW)
    assert items[0].title == "Natco Pharma wins US approval"
    assert items[0].published is not None
    assert items[0].published.tzinfo is not None


# Dynamic fixture to prevent rot as calendar advances
_RECENT = format_datetime(datetime.now(timezone.utc) - timedelta(days=1))

PIB_RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>PIB</title>
<item><title>Cabinet approves semiconductor fab incentives</title>
<link>https://pib.example/1</link>
<pubDate>{_RECENT}</pubDate></item>
<item><title>New highway inaugurated</title>
<link>https://pib.example/2</link>
<pubDate>{_RECENT}</pubDate></item>
</channel></rss>"""


def test_company_news_builds_query_and_caches(tmp_path):
    calls: list[str] = []

    def fake_http(url: str) -> str:
        calls.append(url)
        return GOOGLE_RSS

    cache = DiskCache(tmp_path)
    items = company_news("Natco Pharma", "NATCOPHARM.NS", cache=cache, fetcher=fake_http)
    assert items  # something survived (undated items always do)
    assert any("Natco" in i.title or "Undated" in i.title for i in items)
    assert "news.google.com" in calls[0]
    assert "%22Natco%20Pharma%22" in calls[0]  # quoted company name in query
    # second call served from cache: no new fetch
    company_news("Natco Pharma", "NATCOPHARM.NS", cache=cache, fetcher=fake_http)
    assert len(calls) == 1


def test_company_news_feed_failure_degrades_to_empty():
    def boom(url: str) -> str:
        raise OSError("network down")

    assert company_news("X Ltd", "X.NS", cache=None, fetcher=boom) == []


def test_policy_items_tag_matching_sectors(tmp_path):
    items = policy_items(
        ["Semiconductors", "Steel"], cache=DiskCache(tmp_path),
        fetcher=lambda url: PIB_RSS,
    )
    by_title = {i.title: i for i in items}
    assert by_title["Cabinet approves semiconductor fab incentives"].sectors == [
        "Semiconductors"
    ]
    assert by_title["New highway inaugurated"].sectors == []


def test_parse_rss_drops_non_http_link_schemes():
    # external feeds are untrusted: a javascript: URI would survive HTML
    # autoescaping as a live clickable link on the published page
    xml = GOOGLE_RSS.replace(
        "https://example.com/a", "javascript:alert(document.cookie)//"
    )
    items = parse_rss(xml)
    assert all(i.link.startswith(("http://", "https://")) for i in items)
    assert not any("javascript" in i.link for i in items)
