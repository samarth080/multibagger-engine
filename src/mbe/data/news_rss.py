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

import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree
from pydantic import BaseModel, Field

from mbe.data.cache import DiskCache

GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

POLICY_TERMS_AS_OF = date(2026, 7, 31)
NEWS_MATCH_VERSION = "v5"

# Yahoo industry/sector label -> the words Indian policy journalism actually
# uses for it. Measured, not guessed: querying the taxonomy label itself
# ("Software - Application", "Specialty Business Services") returns generic
# national-policy filler, because no journalist writes those phrases. Across
# the 20 industries in the live top-25, hand-scoring every returned headline
# gave 67% relevant on the raw label (and only 7/20 industries returning
# anything at all), 57% on plain-English industry nouns, and 84% across 20/20
# industries once each term was anchored on the *regulator or scheme* — SEBI,
# IRDAI, FSSAI, CEA, NPPA, PLI. That is the rule for extending this table.
#
# This is a query-side table, not the keyword matcher that was deleted in
# v0.14: a missing entry falls through to the raw label and still searches, so
# it degrades to the old behaviour rather than silently matching nothing.
# `scripts/build_site.py` prints unmapped industries on every build.
POLICY_TERMS: dict[str, str] = {
    "Aerospace & Defense": "defence ministry procurement indigenisation",
    "Auto & Truck Dealerships": "road transport ministry vehicle registration",
    "Auto Manufacturers": "heavy industries ministry automobile PLI",
    "Auto Parts": "auto components PLI ministry",
    "Capital Markets": "SEBI",
    "Computer Hardware": "MeitY electronics manufacturing PLI",
    "Copper": "mines ministry copper critical minerals",
    "Diagnostics & Research": "health ministry diagnostics NABL",
    "Drug Manufacturers - Specialty & Generic": "CDSCO NPPA pharmaceutical pricing",
    "Electrical Equipment & Parts": "power ministry transmission CEA",
    "Engineering & Construction": "infrastructure ministry NHAI contracts",
    "Farm & Heavy Construction Machinery": "farm mechanisation subsidy tractor",
    "Information Technology Services": "MeitY IT sector policy",
    "Insurance - Life": "IRDAI life insurance",
    "Lodging": "tourism ministry hotel industry",
    "Other Precious Metals & Mining": "mines ministry mineral auction",
    "Packaged Foods": "FSSAI packaged food",
    "Software - Application": "MeitY software IT rules",
    "Specialty Business Services": "GST services sector ministry",
    "Steel": "steel ministry import duty safeguard",
}


class NewsItem(BaseModel):
    title: str
    link: str
    published: datetime | None = None
    source: str | None = None
    sectors: list[str] = []  # policy items: matched sector keys
    relevance_score: float | None = Field(default=None, ge=0, le=100)
    match_confidence: str = "unscored"
    match_reasons: list[str] = []
    source_quality: float | None = Field(default=None, ge=0, le=1)


# A symbol is only useful identity evidence when a title also carries company
# or Indian-market context. Short symbols are especially collision-prone: BLS
# can mean basic life support, ACE is a generic word and CAMS is an acronym in
# several unrelated fields. The rule intentionally applies to every short
# symbol rather than trying to maintain an inevitably incomplete blacklist.
_LEGAL_SUFFIXES = {
    "inc", "incorporated", "ltd", "limited", "plc", "pvt", "private",
}
_NAME_STOPWORDS = {"and", "of", "the", "india", "indian"}
_TITLE_STOPWORDS = _NAME_STOPWORDS | {
    "a", "an", "for", "from", "in", "on", "to", "with", "says", "new",
}
_MARKET_CONTEXT = {
    "bse", "earnings", "exchange", "investor", "nse", "results", "share",
    "shares", "stock", "stocks", "quarter", "quarterly",
}
_GENERIC_ENTITY_TOKENS = {
    "business", "enterprises", "group", "holdings", "industry", "industries",
    "services", "solutions", "technology", "technologies",
}
_ABBREVIATIONS = {
    "intl": "international",
    "serv": "services",
    "servs": "services",
    "engg": "engineering",
    "engrg": "engineering",
    "fin": "financial",
    "tech": "technology",
}
_HIGH_QUALITY_SOURCES = {
    "bse india", "business standard", "cnbc tv18", "economic times",
    "livemint", "moneycontrol com", "nse india", "press trust of india",
    "reuters", "sebi",
}


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", text.casefold())
    return [_ABBREVIATIONS.get(token, token) for token in raw]


def _phrase(tokens: list[str]) -> str:
    return " ".join(tokens)


def _source_quality(source: str | None) -> float:
    if not source:
        return 0.35
    normalized = _phrase(_tokens(source))
    if any(known in normalized for known in _HIGH_QUALITY_SOURCES):
        return 0.9
    if normalized.endswith(" gov") or "government" in normalized:
        return 0.85
    return 0.55


def _company_name_tokens(name: str) -> list[str]:
    tokens = _tokens(name)
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return [token for token in tokens if token not in _NAME_STOPWORDS]


def _industry_tokens(industry: str | None) -> set[str]:
    if not industry:
        return set()
    return {
        token for token in _tokens(industry)
        if token not in _TITLE_STOPWORDS and len(token) >= 4
    }


def score_company_news(
    item: NewsItem,
    *,
    name: str,
    ticker: str,
    exchange: str | None = "NSE",
    country: str = "India",
    industry: str | None = None,
    aliases: list[str] | None = None,
) -> NewsItem:
    """Attach conservative title-level entity-match evidence to a headline.

    Google News RSS does not provide article bodies, ISINs or exchange entity
    identifiers. That limitation is explicit: this scorer requires either a
    recognisable company-name match or a ticker accompanied by market context.
    A bare ticker never passes, which removes the BLS/ACE/CAMS/IEX class of
    false positives without pretending title matching is full NER.
    """
    title_tokens = _tokens(item.title)
    title_set = set(title_tokens)
    title_text = _phrase(title_tokens)
    symbol = ticker.split(".")[0].casefold()
    declared_symbols = {
        match.casefold()
        for match in re.findall(
            r"\b(?:NSE|BSE)\s*[:\-]\s*([A-Z0-9&-]+)\b",
            item.title.upper(),
        )
    }
    contradictory_symbol = bool(declared_symbols and symbol not in declared_symbols)
    reasons: list[str] = []
    score = 0.0

    names = [name, *(aliases or [])]
    name_variants = []
    for candidate in names:
        tokens = _company_name_tokens(candidate)
        if tokens and tokens not in name_variants:
            name_variants.append(tokens)

    exact_match_tokens = 0
    best_coverage = 0.0
    best_matches: set[str] = set()
    for variant in name_variants:
        phrase = _phrase(variant)
        matched = set(variant) & title_set
        coverage = len(matched) / len(set(variant))
        if phrase and phrase in title_text:
            exact_match_tokens = max(exact_match_tokens, len(set(variant)))
        if coverage > best_coverage:
            best_coverage, best_matches = coverage, matched

    industry_terms = _industry_tokens(industry)
    long_name_matches = {
        token for token in best_matches
        if (
            len(token) >= 5
            and token != symbol
            and token not in _GENERIC_ENTITY_TOKENS
            and token not in industry_terms
        )
    }
    # A one-token core such as "Welspun" is not a legal-entity match: it can
    # identify a sibling group company. One-word companies instead qualify via
    # the guarded ticker + market-context branch below.
    discriminating_matches = (
        best_matches - {symbol} - _GENERIC_ENTITY_TOKENS - industry_terms
    )
    if contradictory_symbol:
        reasons.append("headline declares a different exchange symbol")
    elif exact_match_tokens >= 2:
        score += 72
        reasons.append("company name appears in title")
    elif len(best_matches) >= 2 and discriminating_matches and best_coverage >= 0.75:
        score += 65
        reasons.append("most company-name tokens appear in title")
    elif len(best_matches) >= 2 and discriminating_matches and best_coverage >= 0.5:
        score += 55
        reasons.append("multiple company-name tokens appear in title")
    elif long_name_matches:
        score += 42
        reasons.append("distinctive company-name token appears in title")

    symbol_present = symbol in title_set
    explicit_market_context = bool(title_set & _MARKET_CONTEXT)
    country_context = country.casefold() in title_set
    exchange_context = bool(exchange and exchange.casefold() in title_set)
    if (
        not contradictory_symbol
        and symbol_present
        and (explicit_market_context or exchange_context)
    ):
        # Long exchange symbols are useful corroboration. Short symbols remain
        # weak evidence even with a word like "results" because collisions are
        # common; the source and industry checks below can lift a real item.
        score += 44 if len(symbol) <= 5 else 52
        reasons.append("ticker appears with market context")
    elif not contradictory_symbol and symbol_present and len(symbol) > 5:
        score += 25
        reasons.append("distinctive ticker appears in title")

    industry_overlap = title_set & industry_terms
    if industry_overlap:
        score += 8
        reasons.append("industry context agrees")
    if country_context or exchange_context:
        score += 6
        reasons.append("India/exchange context agrees")

    quality = _source_quality(item.source)
    if score >= 35:
        score += quality * 8
        reasons.append("source quality considered")
    score = min(round(score, 1), 100.0)
    confidence = "high" if score >= 75 else "medium" if score >= 55 else "low"
    return item.model_copy(update={
        "relevance_score": score,
        "match_confidence": confidence,
        "match_reasons": reasons,
        "source_quality": quality,
    })


def filter_company_news(
    items: list[NewsItem],
    *,
    name: str,
    ticker: str,
    exchange: str | None = "NSE",
    country: str = "India",
    industry: str | None = None,
    aliases: list[str] | None = None,
    minimum_score: float = 55,
    limit: int = 5,
) -> list[NewsItem]:
    scored = [
        score_company_news(
            item,
            name=name,
            ticker=ticker,
            exchange=exchange,
            country=country,
            industry=industry,
            aliases=aliases,
        )
        for item in items
    ]
    accepted = [
        item for item in scored
        if item.relevance_score is not None and item.relevance_score >= minimum_score
    ]
    accepted.sort(
        key=lambda item: (
            item.relevance_score or 0,
            item.published or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return accepted[:limit]


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
        source = node.findtext("source")
        # Google News appends " - Publisher" to every title while also filing
        # it in <source>, so rendering both reads "… - Mint — Mint, 2d ago".
        # Stripped only on an exact match, so a title that genuinely ends in a
        # dash phrase survives.
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].rstrip()
        items.append(
            NewsItem(
                title=title, link=link, published=published, source=source,
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
    seen: list[set[str]] = []
    kept: list[NewsItem] = []
    for item in items:
        signature = {
            token for token in _tokens(item.title)
            if token not in _TITLE_STOPWORDS
        }
        # News syndication commonly changes one or two words while retaining
        # the same story. Cluster near-identical token sets, not just byte-for-
        # byte titles, so duplicate wire stories do not crowd out other news.
        duplicate = any(
            signature and prior
            and len(signature & prior) / len(signature | prior) >= 0.82
            for prior in seen
        )
        if duplicate:
            continue
        if item.published is not None and item.published < cutoff:
            continue
        seen.append(signature)
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
    *,
    exchange: str | None = "NSE",
    country: str = "India",
    industry: str | None = None,
    aliases: list[str] | None = None,
) -> list[NewsItem]:
    """Entity-matched recent headlines for one company (Google News RSS).

    Query construction reduces noise, but it is not trusted as the final
    match. Every returned title is independently scored and low-confidence
    results are removed before caching or publication.
    """
    base = ticker.split(".")[0]
    expanded_name = _phrase(_company_name_tokens(name))
    # The symbol is useful for common market shorthand (CAMS/IEX), but only
    # inside the India/exchange-anchored query and still has to pass the
    # independent title scorer below. It is never accepted merely because the
    # feed echoed the symbol.
    quoted_names = [f'"{name}"', f'"{base}"']
    if expanded_name and expanded_name.casefold() != name.casefold():
        quoted_names.append(f'"{expanded_name}"')
    for alias in aliases or []:
        if alias.strip():
            quoted_names.append(f'"{alias.strip()}"')
    identity_context = " OR ".join(
        term for term in (country, exchange, "BSE") if term
    )
    query = urllib.parse.quote(
        f"({' OR '.join(dict.fromkeys(quoted_names))}) "
        f"({identity_context}) when:7d"
    )
    # The version is an intentional cache break: old matcher outputs can be
    # cached for up to six days in CI, so a code fix alone would not clean the
    # published site.
    key = f"news_entity_{NEWS_MATCH_VERSION}_{_policy_slug(base)}"
    if cache and (hit := cache.get_json(key)):
        return [NewsItem(**i) for i in hit["items"]]
    try:
        recent = dedupe_recent(
            parse_rss(fetcher(GOOGLE_NEWS_URL.format(query=query))),
            limit=20,
        )
        items = filter_company_news(
            recent,
            name=name,
            ticker=ticker,
            exchange=exchange,
            country=country,
            industry=industry,
            aliases=aliases,
        )
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

    `sectors` carries the industry key, not the search term — the report
    filters a flat multi-industry list by its own `info.industry`, and the
    page shows the reader the industry rather than the query internals.
    """
    key = industry or sector
    if not key:
        return []
    cache_key = f"policy_{_policy_slug(key)}"
    if cache and (hit := cache.get_json(cache_key)):
        return [NewsItem(**i) for i in hit["items"]]
    # `when:7d` matches dedupe_recent's window, so the feed stops returning
    # months-old items that are only going to be discarded after parsing.
    query = urllib.parse.quote(f"{POLICY_TERMS.get(key, key)} India when:7d")
    try:
        items = dedupe_recent(parse_rss(fetcher(GOOGLE_NEWS_URL.format(query=query))))
    except Exception:
        return []  # context must never fail a build; the builder prints counts
    for item in items:
        item.sectors = [key]
    if cache:
        cache.set_json(cache_key, {"items": [i.model_dump(mode="json") for i in items]})
    return items
