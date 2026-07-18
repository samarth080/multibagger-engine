"""Offline tests for the RSS news/policy provider (canned fixtures)."""

from datetime import datetime, timezone

from mbe.data.news_rss import NewsItem, dedupe_recent, parse_rss

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
