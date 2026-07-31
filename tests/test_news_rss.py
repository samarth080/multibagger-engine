"""Offline tests for the RSS news/policy provider (canned fixtures)."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from mbe.data.cache import DiskCache
from mbe.data.news_rss import NewsItem, dedupe_recent, parse_rss, company_news

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


# Dynamic fixtures to prevent rot as the calendar advances: dedupe_recent
# windows against datetime.now(), so a hardcoded pubDate silently ages out of
# the 7-day window and every item disappears.
_RECENT = format_datetime(datetime.now(timezone.utc) - timedelta(days=1))
_OLDER = format_datetime(datetime.now(timezone.utc) - timedelta(days=2))

POLICY_RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>q</title>
<item><title>Cabinet clears Rs 25,000cr power grid scheme</title>
<link>https://example.com/p1</link>
<pubDate>{_RECENT}</pubDate>
<source url="https://pib.example">PIB</source></item>
<item><title>PLI scheme extended for electrical equipment</title>
<link>https://example.com/p2</link>
<pubDate>{_OLDER}</pubDate></item>
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


def test_sector_policy_queries_industry_and_tags_it(tmp_path):
    """The query IS the relevance filter — there is no keyword-matching step
    left that can silently fail, which is what killed the PIB path."""
    from mbe.data.news_rss import sector_policy

    seen = {}

    def fake(url):
        seen["url"] = url
        return POLICY_RSS

    items = sector_policy(
        "Industrials", "Electrical Equipment & Parts",
        cache=DiskCache(tmp_path), fetcher=fake,
    )
    assert "Electrical+Equipment" in seen["url"] or "Electrical%20Equipment" in seen["url"]
    assert "Industrials" not in seen["url"]  # industry wins over sector
    assert [i.title for i in items] == [
        "Cabinet clears Rs 25,000cr power grid scheme",
        "PLI scheme extended for electrical equipment",
    ]
    # sectors carries the key the query was built from, so a flat multi-sector
    # list can be filtered back per stock
    assert all(i.sectors == ["Electrical Equipment & Parts"] for i in items)


def test_sector_policy_falls_back_to_sector_then_gives_up(tmp_path):
    from mbe.data.news_rss import sector_policy

    seen = {}

    def fake(url):
        seen["url"] = url
        return POLICY_RSS

    items = sector_policy("Industrials", None, cache=DiskCache(tmp_path), fetcher=fake)
    assert "Industrials" in seen["url"]
    assert all(i.sectors == ["Industrials"] for i in items)

    def explode(url):
        raise AssertionError("must not fetch without a classification")

    assert sector_policy(None, None, cache=DiskCache(tmp_path), fetcher=explode) == []


def test_sector_policy_shares_one_fetch_across_an_industry(tmp_path):
    """Stocks in the same industry must not each hit the network."""
    from mbe.data.news_rss import sector_policy

    cache = DiskCache(tmp_path)
    calls = []

    def fake(url):
        calls.append(url)
        return POLICY_RSS

    a = sector_policy("Industrials", "Electrical Equipment & Parts", cache=cache, fetcher=fake)
    b = sector_policy("Industrials", "Electrical Equipment & Parts", cache=cache, fetcher=fake)
    assert len(calls) == 1
    assert [i.title for i in a] == [i.title for i in b]


def test_sector_policy_survives_a_dead_feed(tmp_path):
    """Context must never fail a build — same contract as company_news."""
    from mbe.data.news_rss import sector_policy

    def explode(url):
        raise RuntimeError("feed down")

    assert sector_policy("Industrials", "Steel", cache=DiskCache(tmp_path), fetcher=explode) == []


def test_parse_rss_drops_non_http_link_schemes():
    # external feeds are untrusted: a javascript: URI would survive HTML
    # autoescaping as a live clickable link on the published page
    xml = GOOGLE_RSS.replace(
        "https://example.com/a", "javascript:alert(document.cookie)//"
    )
    items = parse_rss(xml)
    assert all(i.link.startswith(("http://", "https://")) for i in items)
    assert not any("javascript" in i.link for i in items)
