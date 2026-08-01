"""Offline tests for the RSS news/policy provider (canned fixtures)."""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from mbe.data.cache import DiskCache
from mbe.data.news_rss import (
    NewsItem,
    company_news,
    dedupe_recent,
    filter_company_news,
    parse_rss,
    score_company_news,
)

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


def test_parse_rss_strips_the_publisher_google_appends_to_titles():
    """Google News files the publisher in <source> AND appends it to the
    title, so rendering both gives "… - Mint — Mint, 2d ago"."""
    xml = GOOGLE_RSS.replace(
        "<title>Natco Pharma wins US approval</title>",
        "<title>Natco Pharma wins US approval - Economic Times</title>", 1,
    )
    items = parse_rss(xml)
    assert items[0].title == "Natco Pharma wins US approval"
    assert items[0].source == "Economic Times"


def test_parse_rss_keeps_a_dash_phrase_that_is_not_the_publisher():
    xml = GOOGLE_RSS.replace(
        "<title>Natco Pharma wins US approval</title>",
        "<title>Natco Pharma wins US approval - what it means</title>", 1,
    )
    assert parse_rss(xml)[0].title == "Natco Pharma wins US approval - what it means"


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
        return GOOGLE_RSS.replace(
            "Fri, 17 Jul 2026 08:00:00 GMT", _RECENT
        ).replace(
            "Fri, 17 Jul 2026 09:00:00 GMT", _OLDER
        )

    cache = DiskCache(tmp_path)
    items = company_news("Natco Pharma", "NATCOPHARM.NS", cache=cache, fetcher=fake_http)
    assert items
    assert all("Natco" in item.title for item in items)
    assert "news.google.com" in calls[0]
    assert "%22Natco%20Pharma%22" in calls[0]  # quoted company name in query
    assert "%22NATCOPHARM%22" in calls[0]  # symbol is exchange/country-anchored
    assert "India" in calls[0] and "NSE" in calls[0]
    assert all(item.relevance_score >= 55 for item in items)
    assert all(item.match_confidence in {"medium", "high"} for item in items)
    # second call served from cache: no new fetch
    company_news("Natco Pharma", "NATCOPHARM.NS", cache=cache, fetcher=fake_http)
    assert len(calls) == 1


def test_company_news_feed_failure_degrades_to_empty():
    def boom(url: str) -> str:
        raise OSError("network down")

    assert company_news("X Ltd", "X.NS", cache=None, fetcher=boom) == []


def test_entity_match_rejects_ambiguous_symbol_only_news():
    unrelated = [
        NewsItem(
            title="IAP BLS Course Successfully Conducted at KIMS",
            link="https://example.com/medical",
            source="KIIT",
        ),
        NewsItem(
            title="Balanga team wins BLS Olympics",
            link="https://example.com/sports",
            source="Manila Standard",
        ),
    ]
    assert filter_company_news(
        unrelated,
        name="BLS INTL SERVS LTD",
        ticker="BLS.NS",
        exchange="NSE",
        industry="Specialty Business Services",
    ) == []


def test_entity_match_accepts_expanded_company_name_and_exposes_evidence():
    item = NewsItem(
        title="BLS International Services reports strong quarterly results",
        link="https://example.com/company",
        source="Economic Times",
    )
    scored = score_company_news(
        item,
        name="BLS INTL SERVS LTD",
        ticker="BLS.NS",
        exchange="NSE",
        industry="Specialty Business Services",
    )
    assert scored.relevance_score is not None and scored.relevance_score >= 75
    assert scored.match_confidence == "high"
    assert any("company name" in reason for reason in scored.match_reasons)
    assert scored.source_quality == 0.9


def test_entity_match_requires_extra_corroboration_for_short_symbols():
    item = NewsItem(
        title="CAMS shares rise on NSE after quarterly results",
        link="https://example.com/cams",
        source="Moneycontrol.com",
    )
    scored = score_company_news(
        item,
        name="Computer Age Management Services Limited",
        ticker="CAMS.NS",
        exchange="NSE",
        industry="Capital Markets",
    )
    assert scored.relevance_score is not None and scored.relevance_score >= 55
    assert "ticker appears with market context" in scored.match_reasons


def test_entity_match_rejects_bare_short_ticker_from_unrelated_domain():
    item = NewsItem(
        title="New CAMS imaging method improves medical diagnosis",
        link="https://example.com/medicine",
        source="Medical Journal",
    )
    scored = score_company_news(
        item,
        name="Computer Age Management Services Limited",
        ticker="CAMS.NS",
        exchange="NSE",
    )
    assert scored.match_confidence == "low"
    assert filter_company_news(
        [item],
        name="Computer Age Management Services Limited",
        ticker="CAMS.NS",
    ) == []


def test_entity_match_does_not_confuse_a_group_sibling_company():
    item = NewsItem(
        title="Welspun Living: WCPGL Becomes Associate Company",
        link="https://example.com/welspun-living",
        source="Market News",
    )
    assert filter_company_news(
        [item],
        name="Welspun Corp Limited",
        ticker="WELCORP.NS",
        industry="Steel",
    ) == []


def test_entity_match_does_not_treat_industry_noun_as_company_identity():
    item = NewsItem(
        title="Why India EV and Green Energy Push Is a Windfall for Copper Stocks",
        link="https://example.com/copper-sector",
        source="Economic Times",
    )
    assert filter_company_news(
        [item],
        name="Hindustan Copper Limited",
        ticker="HINDCOPPER.NS",
        industry="Copper",
    ) == []


def test_entity_match_does_not_treat_india_as_enough_ticker_context():
    items = [
        NewsItem(
            title="Neeraj Chopra, India's javelin ace, wins silver",
            link="https://example.com/ace-sport",
            source="Hindustan Times",
        ),
        NewsItem(
            title="Sri Vijaya Puram hosts young professionals roundtable in India",
            link="https://example.com/vijaya-place",
            source="Local News",
        ),
    ]
    assert filter_company_news(
        items[:1], name="Action Construction Equipment Ltd", ticker="ACE.NS"
    ) == []
    assert filter_company_news(
        items[1:], name="Vijaya Diagnostic Centre Ltd", ticker="VIJAYA.NS"
    ) == []


def test_entity_match_rejects_a_different_declared_exchange_symbol():
    item = NewsItem(
        title="BLS E-Services Limited Revenue Breakdown – NSE:BLSE",
        link="https://example.com/blse",
        source="Market Data",
    )
    scored = score_company_news(
        item,
        name="BLS International Services Limited",
        ticker="BLS.NS",
        exchange="NSE",
    )
    assert scored.match_confidence == "low"
    assert "different exchange symbol" in scored.match_reasons[0]


def test_sector_policy_queries_the_regulator_not_the_taxonomy_label(tmp_path):
    """The query IS the relevance filter — there is no keyword-matching step
    left that can silently fail, which is what killed the PIB path. Which
    makes the query wording the whole ballgame: "Electrical Equipment & Parts"
    is a Yahoo label no journalist writes, so it returns national-policy
    filler. POLICY_TERMS swaps in the words the regulator is named by."""
    from mbe.data.news_rss import sector_policy

    seen = {}

    def fake(url):
        seen["url"] = url
        return POLICY_RSS

    items = sector_policy(
        "Industrials", "Electrical Equipment & Parts",
        cache=DiskCache(tmp_path), fetcher=fake,
    )
    assert "CEA" in seen["url"] and "transmission" in seen["url"]
    assert "Electrical" not in seen["url"]  # the taxonomy label is not searched
    assert "Industrials" not in seen["url"]  # industry wins over sector
    assert "when%3A7d" in seen["url"]  # feed window matches dedupe_recent's
    assert [i.title for i in items] == [
        "Cabinet clears Rs 25,000cr power grid scheme",
        "PLI scheme extended for electrical equipment",
    ]
    # sectors carries the INDUSTRY, not the search term: the report filters a
    # flat multi-industry list by its own info.industry, and the page shows a
    # reader the industry rather than the query internals
    assert all(i.sectors == ["Electrical Equipment & Parts"] for i in items)


def test_sector_policy_falls_back_to_the_raw_label_when_unmapped(tmp_path):
    """A missing POLICY_TERMS entry must still search. This is what makes the
    table safe to leave stale: it degrades to the old behaviour rather than
    silently matching nothing, which is how the deleted PIB tagger failed."""
    from mbe.data.news_rss import POLICY_TERMS, sector_policy

    seen = {}

    def fake(url):
        seen["url"] = url
        return POLICY_RSS

    assert "Underwater Basket Weaving" not in POLICY_TERMS
    items = sector_policy(
        None, "Underwater Basket Weaving", cache=DiskCache(tmp_path), fetcher=fake
    )
    assert "Underwater" in seen["url"] and "Weaving" in seen["url"]
    assert all(i.sectors == ["Underwater Basket Weaving"] for i in items)


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
