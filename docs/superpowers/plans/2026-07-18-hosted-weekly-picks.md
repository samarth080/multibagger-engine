# Hosted Weekly India Picks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Vercel-hosted static page showing the weekly NIFTY Smallcap 250 multibagger ranking with sector context, week-over-week changes, headlines, policy items, and delayed quotes — rebuilt every Monday by GitHub Actions.

**Architecture:** GitHub Actions runs the ~20-min weekly screen and commits a prebuilt `site/` directory to main; Vercel's git integration auto-deploys it (no CLI, no deploy token — simpler than the spec's original CLI mechanism; the docs task amends the spec). One stdlib-only serverless function (`api/quotes.py`) serves delayed quotes for the published tickers only. News/policy are descriptive layers, never scored.

**Tech Stack:** Python 3.12, uv, pydantic v2, jinja2, `markdown` + `defusedxml` (already deps), GitHub Actions, Vercel static hosting + Python function.

**Spec:** `docs/superpowers/specs/2026-07-18-hosted-weekly-picks-design.md`

## File structure

| File | Responsibility |
|---|---|
| Create `src/mbe/data/news_rss.py` | RSS parsing (defusedxml), Google News per company, PIB policy feed + sector keyword tagging |
| Create `src/mbe/publish.py` | `build_data`, `diff_weeks`, `render_site` (index + report pages), validation footer |
| Create `api/quotes.py` | stdlib-only Vercel function: whitelisted delayed quotes |
| Create `vercel.json` | static output dir + function includeFiles |
| Create `scripts/build_site.py` | orchestration: throttled screen → news → diff → site/ |
| Create `.github/workflows/weekly.yml` | Monday cron: build + commit site/ |
| Create `tests/test_news_rss.py`, `tests/test_publish.py`, `tests/test_quotes_fn.py` | offline tests with fixtures/stubs |
| Modify `.gitignore` | anchor `data/`→`/data/`, `reports/`→`/reports/` (stops false-matching `src/mbe/data`) |
| Modify docs (Task 8) | CHANGELOG v0.10.0, README hosted section, spec deploy-mechanism amendment |

Conventions: offline tests with fixtures/stub fetchers (house pattern), commits `feat(publish): …`, news failures degrade to empty lists (context must never fail a build) but the builder prints counts and **refuses to publish a degraded ranking** (<100 analyzed).

---

### Task 1: RSS parsing + windowing (`news_rss.py` core)

**Files:**
- Create: `src/mbe/data/news_rss.py`
- Test: `tests/test_news_rss.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_news_rss.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_news_rss.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mbe.data.news_rss'`.

- [ ] **Step 3: Implement**

Create `src/mbe/data/news_rss.py`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_news_rss.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add -f src/mbe/data/news_rss.py
git add tests/test_news_rss.py
git commit -m "feat(publish): RSS parsing + recency windowing for news/policy feeds"
```

(The `-f` is needed until Task 7 fixes the unanchored `data/` gitignore line.)

---

### Task 2: Company news + PIB policy fetchers

**Files:**
- Modify: `src/mbe/data/news_rss.py` (append)
- Test: `tests/test_news_rss.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_news_rss.py`:

```python
from mbe.data.cache import DiskCache
from mbe.data.news_rss import company_news, policy_items

PIB_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>PIB</title>
<item><title>Cabinet approves semiconductor fab incentives</title>
<link>https://pib.example/1</link>
<pubDate>Thu, 16 Jul 2026 10:00:00 GMT</pubDate></item>
<item><title>New highway inaugurated</title>
<link>https://pib.example/2</link>
<pubDate>Thu, 16 Jul 2026 11:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_company_news_builds_query_and_caches(tmp_path):
    calls: list[str] = []

    def fake_http(url: str) -> str:
        calls.append(url)
        return GOOGLE_RSS

    cache = DiskCache(tmp_path)
    items = company_news("Natco Pharma", "NATCOPHARM.NS", cache=cache, fetcher=fake_http)
    assert items and "Natco" in items[0].title
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_news_rss.py -v -k "company or policy"`
Expected: FAIL with `ImportError: cannot import name 'company_news'`.

- [ ] **Step 3: Implement**

Append to `src/mbe/data/news_rss.py`:

```python
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


def policy_items(
    sector_names: list[str],
    cache: DiskCache | None = None,
    fetcher=default_http,
    limit: int = 12,
) -> list[NewsItem]:
    """Latest PIB items, tagged with the sectors whose keywords they match."""
    key = "news_pib"
    if cache and (hit := cache.get_json(key)):
        items = [NewsItem(**i) for i in hit["items"]]
    else:
        try:
            items = dedupe_recent(parse_rss(fetcher(PIB_RSS_URL)), limit=limit)
        except Exception:
            return []
        if cache:
            cache.set_json(key, {"items": [i.model_dump(mode="json") for i in items]})
    for item in items:
        low = f" {item.title.lower()} "
        item.sectors = [
            s for s in sector_names
            if any(k in low for k in POLICY_KEYWORDS.get(s, []))
        ]
    return items
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_news_rss.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add -f src/mbe/data/news_rss.py
git add tests/test_news_rss.py
git commit -m "feat(publish): company headlines + PIB policy feed with sector tagging"
```

---

### Task 3: build_data + diff_weeks (`publish.py` core)

**Files:**
- Create: `src/mbe/publish.py`
- Test: `tests/test_publish.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_publish.py`:

```python
"""Offline tests for the static-site builder (stub bundles, no network)."""

from datetime import datetime, timezone

from mbe.data.news_rss import NewsItem
from mbe.models.sector import SectorScore
from mbe.pipeline import ScreenResult
from mbe.publish import TOP_N, build_data, diff_weeks
from tests.test_sector import make_bundle

NOW = datetime(2026, 7, 18, 3, 0, tzinfo=timezone.utc)


def _result() -> ScreenResult:
    bundles = [
        make_bundle(f"S{i}.NS", multibagger=80.0 - i) for i in range(4)
    ]
    sector = SectorScore(
        name="Semiconductors", level="industry", n=4, score=75.0,
        confidence=1.0, evidence=[], members=[b.card.ticker for b in bundles],
    )
    return ScreenResult(ranked=bundles, failures={}, sector_scores=[sector])


def test_build_data_shape_and_ordering():
    news = {"S0.NS": [NewsItem(title="hi", link="https://x/1", published=NOW)]}
    data = build_data(_result(), news, policy=[], built_at=NOW)
    assert data["built_at"] == NOW.isoformat()
    assert [r["ticker"] for r in data["top"]] == ["S0.NS", "S1.NS", "S2.NS", "S3.NS"]
    top0 = data["top"][0]
    assert top0["mb"] == 80.0
    assert top0["group"] == "Semiconductors"
    assert top0["group_rank"] == 1
    assert top0["news"][0]["title"] == "hi"
    assert any(t["theme"].startswith("AI") for t in top0["tags"])  # semis themes
    assert data["sectors"][0]["name"] == "Semiconductors"


def test_build_data_caps_at_top_n():
    bundles = [make_bundle(f"T{i}.NS", multibagger=90.0 - i) for i in range(TOP_N + 5)]
    result = ScreenResult(ranked=bundles, failures={}, sector_scores=[])
    data = build_data(result, {}, policy=[], built_at=NOW)
    assert len(data["top"]) == TOP_N


def test_diff_weeks_entered_exited_and_first_week():
    prev = {"top": [{"ticker": "A.NS"}, {"ticker": "B.NS"}]}
    new = {"top": [{"ticker": "B.NS"}, {"ticker": "C.NS"}]}
    changes = diff_weeks(prev, new)
    assert changes == {"entered": ["C.NS"], "exited": ["A.NS"]}
    assert diff_weeks(None, new) == {"entered": ["B.NS", "C.NS"], "exited": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_publish.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mbe.publish'`.

- [ ] **Step 3: Implement**

Create `src/mbe/publish.py`:

```python
"""Static-site builder for the hosted weekly picks page.

build_data() turns a ScreenResult (+news/policy) into a JSON-serializable
dict; diff_weeks() computes the week-over-week changes strip; render_site()
writes index.html and per-pick report pages. Descriptive layers (sector
ranks, tags, news, policy) are displayed, never scored — the ranking is the
base multibagger score, per the P2.4 ablation verdict."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import markdown as md
from jinja2 import Environment

from mbe.data.news_rss import NewsItem
from mbe.pipeline import ScreenResult
from mbe.report.markdown import render_report
from mbe.scoring.sector_themes import CURATED_AS_OF, themes_for

TOP_N = 25

VALIDATION_FOOTER = (
    "Model validation status: the multibagger score showed a cross-sample-"
    "consistent 2-year IC of +0.16/+0.10 on disjoint Indian smallcap samples "
    "(2016-2023 cutoffs) — a modest, survivorship-biased edge, not a "
    "guarantee. Sector momentum failed its pre-registered ablation and is "
    "shown as context only, never scored. Research tooling, not investment "
    "advice."
)


def build_data(
    result: ScreenResult,
    news_by_ticker: dict[str, list[NewsItem]],
    policy: list[NewsItem],
    built_at: datetime | None = None,
) -> dict:
    built_at = built_at or datetime.now(timezone.utc)
    group_of: dict[str, tuple[str, int, float]] = {}
    for rank, s in enumerate(result.sector_scores, 1):
        for t in s.members:
            group_of[t] = (s.name, rank, s.score)

    top = []
    for b in result.ranked[:TOP_N]:
        t = b.card.ticker
        group, group_rank, group_score = group_of.get(t, ("", 0, 0.0))
        top.append(
            {
                "ticker": t,
                "name": b.info.name or t,
                "mb": b.card.multibagger_score,
                "inv": b.card.investment_score,
                "conf": b.card.confidence,
                "risk": int(b.risk.risk_score),
                "trend": b.tech.trend_state,
                "price_at_build": b.tech.price,
                "group": group,
                "group_rank": group_rank,
                "group_score": group_score,
                "tags": [
                    {"theme": th.theme, "direction": th.direction}
                    for th in themes_for(b.info.sector, b.info.industry)
                ],
                "news": [i.model_dump(mode="json") for i in news_by_ticker.get(t, [])],
                "gated": bool(b.card.hard_gate_failures),
            }
        )
    return {
        "built_at": built_at.isoformat(),
        "universe": "nifty-smallcap250",
        "curated_as_of": CURATED_AS_OF.isoformat(),
        "top": top,
        "sectors": [
            {"rank": i, "name": s.name, "level": s.level, "score": s.score, "n": s.n}
            for i, s in enumerate(result.sector_scores, 1)
        ],
        "policy": [i.model_dump(mode="json") for i in policy],
    }


def diff_weeks(prev: dict | None, new: dict) -> dict:
    """Who entered/left the published top table vs last week's data.json."""
    new_t = [row["ticker"] for row in new["top"]]
    prev_t = [row["ticker"] for row in (prev or {}).get("top", [])]
    return {
        "entered": [t for t in new_t if t not in prev_t],
        "exited": [t for t in prev_t if t not in new_t],
    }
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_publish.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add -f src/mbe/publish.py
git add tests/test_publish.py
git commit -m "feat(publish): build_data + week-over-week diff"
```

(`src/mbe/publish.py` is not under the ignored path; plain `git add` works — use it. The `-f` is only needed for `src/mbe/data/` paths until Task 7.)

---

### Task 4: render_site — index page + static report pages

**Files:**
- Modify: `src/mbe/publish.py` (append templates + `render_site`)
- Test: `tests/test_publish.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_publish.py`:

```python
import json

from mbe.publish import VALIDATION_FOOTER, render_site


def test_render_site_writes_index_reports_and_data(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[
        NewsItem(title="Cabinet approves fab incentives", link="https://pib/1",
                 published=NOW, sectors=["Semiconductors"]),
    ], built_at=NOW)
    changes = {"entered": ["S0.NS"], "exited": ["Z.NS"]}
    render_site(data, changes, result, tmp_path)

    index = (tmp_path / "index.html").read_text()
    assert "S0.NS" in index and "Semiconductors" in index
    assert "+S0.NS" in index  # changes strip: entry rendered
    assert "-Z.NS" in index   # changes strip: exit rendered
    assert VALIDATION_FOOTER[:40] in index
    assert "delayed" in index.lower()  # quotes honesty label
    assert "/api/quotes" in index  # quotes fetch wired
    assert "Cabinet approves fab incentives" in index

    saved = json.loads((tmp_path / "data.json").read_text())
    assert saved["changes"] == changes
    # a static report page exists per published pick
    assert (tmp_path / "reports" / "S0_NS.html").exists()
    report = (tmp_path / "reports" / "S0_NS.html").read_text()
    assert "Multibagger" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish.py -v -k render`
Expected: FAIL with `ImportError: cannot import name 'render_site'`.

- [ ] **Step 3: Implement**

Append to `src/mbe/publish.py`:

```python
_ENV = Environment(autoescape=True)

_REPORT_SHELL = _ENV.from_string("""<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }}</title>
<style>
body{background:#0d1220;color:#d7dce6;font-family:ui-monospace,Menlo,monospace;
max-width:900px;margin:24px auto;padding:0 16px;line-height:1.5}
a{color:#e3b34c} table{border-collapse:collapse;width:100%;overflow-x:auto;display:block}
td,th{border:1px solid #2a3350;padding:4px 8px;text-align:left}
h1,h2,h3{color:#e3b34c}
</style></head><body>
<p><a href="../index.html">&larr; back to rankings</a></p>
{{ body | safe }}
</body></html>""")

_INDEX = _ENV.from_string("""<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly India Multibagger Picks</title>
<style>
body{background:#0d1220;color:#d7dce6;font-family:ui-monospace,Menlo,monospace;
max-width:1080px;margin:24px auto;padding:0 16px;line-height:1.45}
a{color:#e3b34c;text-decoration:none} a:hover{text-decoration:underline}
h1,h2{color:#e3b34c;letter-spacing:.06em}
table{border-collapse:collapse;width:100%} td,th{border-bottom:1px solid #2a3350;
padding:6px 8px;text-align:left;font-size:14px}
.up{color:#5dd39e}.down{color:#e0605e}.muted{color:#7c869c;font-size:12px}
.chg{background:#161d33;border:1px solid #2a3350;border-radius:8px;padding:10px 14px;margin:14px 0}
details{margin:2px 0} summary{cursor:pointer}
footer{margin:32px 0;padding:14px;border:1px solid #2a3350;border-radius:8px;
color:#9aa4ba;font-size:13px}
.tag-t{color:#5dd39e}.tag-h{color:#e0605e}
</style></head><body>
<h1>WEEKLY INDIA MULTIBAGGER PICKS</h1>
<p class="muted">Universe: {{ d.universe }} · built {{ d.built_at[:16] }}Z ·
quotes are delayed ~15 min · themes curated {{ d.curated_as_of }}</p>

<div class="chg"><b>Changes this week:</b>
{% if changes.entered %}{% for t in changes.entered %}<span class="up">+{{ t }}</span> {% endfor %}{% endif %}
{% if changes.exited %}{% for t in changes.exited %}<span class="down">-{{ t }}</span> {% endfor %}{% endif %}
{% if not changes.entered and not changes.exited %}<span class="muted">no changes vs last week</span>{% endif %}
</div>

<h2>TOP {{ d.top | length }} BY MULTIBAGGER SCORE</h2>
<table><tr><th>#</th><th>Ticker</th><th>Name</th><th>MB</th><th>Inv</th>
<th>Conf</th><th>Risk</th><th>Trend</th><th>Quote</th><th>Industry (mom rank)</th></tr>
{% for r in d.top %}
<tr><td>{{ loop.index }}</td>
<td><a href="reports/{{ r.ticker.replace('.', '_') }}.html">{{ r.ticker }}</a></td>
<td>{{ r.name[:26] }}</td><td>{{ r.mb }}</td><td>{{ r.inv }}</td>
<td>{{ "%.2f" | format(r.conf) }}</td><td>{{ r.risk }}</td><td>{{ r.trend }}</td>
<td><span data-quote="{{ r.ticker }}" data-base="{{ r.price_at_build or '' }}"
class="muted">…</span></td>
<td>{% if r.group %}{{ r.group[:30] }} (#{{ r.group_rank }}, {{ "%.0f" | format(r.group_score) }}){% else %}<span class="muted">ungrouped</span>{% endif %}</td></tr>
{% if r.tags or r.news %}<tr><td></td><td colspan="9">
{% for t in r.tags %}<span class="{{ 'tag-t' if t.direction == 'tailwind' else 'tag-h' }}">{{ '▲' if t.direction == 'tailwind' else '▼' }} {{ t.theme }}</span> &nbsp;{% endfor %}
{% if r.news %}<details><summary class="muted">{{ r.news | length }} headlines</summary>
{% for n in r.news %}<div class="muted">· <a href="{{ n.link }}">{{ n.title }}</a>
{% if n.source %}({{ n.source }}){% endif %}</div>{% endfor %}</details>{% endif %}
</td></tr>{% endif %}
{% endfor %}</table>

<h2>SECTOR MOMENTUM <span class="muted">(descriptive — failed its ablation as a
score input; shown as context)</span></h2>
<table><tr><th>#</th><th>Group</th><th>Level</th><th>Score</th><th>N</th></tr>
{% for s in d.sectors[:12] %}
<tr><td>{{ s.rank }}</td><td>{{ s.name }}</td><td>{{ s.level }}</td>
<td>{{ "%.0f" | format(s.score) }}</td><td>{{ s.n }}</td></tr>
{% endfor %}</table>

{% if d.policy %}<h2>GOVERNMENT POLICY (PIB)</h2>
{% for p in d.policy %}<div>· <a href="{{ p.link }}">{{ p.title }}</a>
{% for s in p.sectors %}<span class="tag-t">[{{ s }}]</span>{% endfor %}</div>
{% endfor %}{% endif %}

<footer>{{ footer }}<br><span class="muted">Rebuilt every Monday by GitHub
Actions. Quotes delayed ~15 min via Yahoo Finance.</span></footer>

<script>
const spans = document.querySelectorAll('[data-quote]');
const symbols = Array.from(spans).map(s => s.dataset.quote);
fetch('/api/quotes?symbols=' + symbols.join(','))
  .then(r => r.json())
  .then(j => spans.forEach(s => {
    const q = j.quotes[s.dataset.quote];
    if (!q) { s.textContent = 'n/a'; return; }
    let txt = q.price.toFixed(2);
    const base = parseFloat(s.dataset.base);
    if (base > 0) {
      const pct = (q.price / base - 1) * 100;
      txt += ' (' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)';
      s.className = pct >= 0 ? 'up' : 'down';
    }
    s.textContent = txt;
  }))
  .catch(() => spans.forEach(s => s.textContent = 'n/a'));
</script>
</body></html>""")


def render_site(data: dict, changes: dict, result: ScreenResult, out_dir) -> None:
    out = Path(out_dir)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps({**data, "changes": changes}, indent=1))
    published = {row["ticker"] for row in data["top"]}
    for b in result.ranked:
        if b.card.ticker in published:
            body = md.markdown(render_report(b), extensions=["tables"])
            page = _REPORT_SHELL.render(title=b.card.ticker, body=body)
            name = b.card.ticker.replace(".", "_") + ".html"
            (out / "reports" / name).write_text(page)
    (out / "index.html").write_text(
        _INDEX.render(d=data, changes=changes, footer=VALIDATION_FOOTER)
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_publish.py tests/test_news_rss.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/publish.py tests/test_publish.py
git commit -m "feat(publish): render index + static report pages with quotes strip"
```

---

### Task 5: Quotes serverless function + vercel.json

**Files:**
- Create: `api/quotes.py`
- Create: `vercel.json`
- Test: `tests/test_quotes_fn.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_quotes_fn.py`:

```python
"""Offline tests for the Vercel quotes function (loaded from file path —
api/ is deliberately outside the mbe package; it must stay stdlib-only)."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "quotes_fn", Path(__file__).parent.parent / "api" / "quotes.py"
)
quotes_fn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quotes_fn)


def test_parse_chart_extracts_price_and_change():
    payload = {"chart": {"result": [{"meta": {
        "regularMarketPrice": 105.0, "chartPreviousClose": 100.0}}]}}
    q = quotes_fn.parse_chart(payload)
    assert q == {"price": 105.0, "day_change_pct": 5.0}


def test_parse_chart_bad_payload_is_none():
    assert quotes_fn.parse_chart({}) is None
    assert quotes_fn.parse_chart({"chart": {"result": []}}) is None


def test_build_response_filters_symbols():
    whitelist = {"GOOD.NS", "ALSO.NS"}
    fetched: list[str] = []

    def fake_fetch(sym):
        fetched.append(sym)
        return {"price": 10.0}

    out = quotes_fn.build_response(
        ["GOOD.NS", "EVIL.US", "NOTLISTED.NS", "lower.ns"], whitelist, fetch=fake_fetch
    )
    assert set(out["quotes"]) == {"GOOD.NS"}
    assert fetched == ["GOOD.NS"]  # non-whitelisted/malformed never fetched
    assert out["delayed"] == "~15 min"


def test_build_response_open_when_no_whitelist_but_ns_only_and_capped():
    out = quotes_fn.build_response(
        [f"T{i}.NS" for i in range(40)], set(), fetch=lambda s: {"price": 1.0}
    )
    assert len(out["quotes"]) == 30  # hard cap
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_quotes_fn.py -v`
Expected: FAIL — `FileNotFoundError` (api/quotes.py doesn't exist).

- [ ] **Step 3: Implement**

Create `api/quotes.py`:

```python
"""Vercel serverless function: delayed (~15 min) quotes for published tickers.

Whitelist = tickers in site/data.json (bundled via vercel.json includeFiles)
— this is not an open proxy: .NS symbols only, whitelist-filtered, capped at
30. Stdlib only; the mbe package is not installed in this runtime."""

import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

CHART_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?interval=1d&range=1d"
)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
_SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]{1,20}\.NS$")
_MAX_SYMBOLS = 30


def load_whitelist() -> set[str]:
    for candidate in (
        Path(__file__).resolve().parent.parent / "site" / "data.json",
        Path("site/data.json"),
    ):
        try:
            data = json.loads(candidate.read_text())
            return {row["ticker"] for row in data.get("top", [])}
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
    return set()


def parse_chart(payload: dict) -> dict | None:
    try:
        meta = payload["chart"]["result"][0]["meta"]
        price = meta["regularMarketPrice"]
    except (KeyError, IndexError, TypeError):
        return None
    if price is None:
        return None
    out = {"price": price}
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if prev:
        out["day_change_pct"] = round((price / prev - 1) * 100, 2)
    return out


def fetch_quote(symbol: str) -> dict | None:
    req = urllib.request.Request(
        CHART_URL.format(symbol=symbol), headers={"User-Agent": _UA}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return parse_chart(json.loads(resp.read()))
    except Exception:
        return None


def build_response(symbols: list[str], whitelist: set[str], fetch=fetch_quote) -> dict:
    wanted = [
        s for s in symbols
        if _SYMBOL_RE.match(s) and (not whitelist or s in whitelist)
    ][:_MAX_SYMBOLS]
    quotes: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for sym, q in zip(wanted, pool.map(fetch, wanted)):
            if q:
                quotes[sym] = q
    return {"quotes": quotes, "delayed": "~15 min"}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        symbols = [
            s for chunk in qs.get("symbols", []) for s in chunk.split(",") if s
        ]
        body = json.dumps(build_response(symbols, load_whitelist())).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "s-maxage=300, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(body)
```

Create `vercel.json`:

```json
{
  "buildCommand": "",
  "outputDirectory": "site",
  "functions": {
    "api/quotes.py": { "includeFiles": "site/data.json" }
  }
}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_quotes_fn.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add api/quotes.py vercel.json tests/test_quotes_fn.py
git commit -m "feat(publish): whitelisted delayed-quotes serverless function"
```

---

### Task 6: build_site orchestration + first live build

**Files:**
- Create: `scripts/build_site.py`

- [ ] **Step 1: Write the script**

Create `scripts/build_site.py`:

```python
"""Weekly site build: screen nifty-smallcap250, pull news/policy, write site/.

Run locally or from GitHub Actions (.github/workflows/weekly.yml).
Env: MBE_CACHE_TTL_HOURS (default 24; CI sets 144 so the restored Actions
cache is actually reused), MBE_THROTTLE_SECS (default 0; CI sets ~0.8 to be
polite to Yahoo from datacenter IPs). Refuses to publish a degraded ranking
(<100 names analyzed) — a rate-limited half-universe must fail loudly, not
ship as if it were the real ranking."""

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from mbe.data.cache import DiskCache
from mbe.data.news_rss import company_news, policy_items
from mbe.data.universe_nse import CACHE_TTL_HOURS
from mbe.data.yahoo import YahooProvider
from mbe.pipeline import screen
from mbe.publish import TOP_N, build_data, diff_weeks, render_site
from mbe.storage import RunStore
from mbe.universe import get_universe

SITE = Path("site")
UNIVERSE = "nifty-smallcap250"
MIN_ANALYZED = 100


def _with_retry(call, attempts: int = 3, base_sleep: float = 20.0):
    """Retry transient rate-limit failures with linear backoff; anything
    else (or the final attempt) re-raises so screen() records the failure."""
    for i in range(attempts):
        try:
            return call()
        except Exception as exc:
            transient = "429" in str(exc) or "Too Many" in str(exc)
            if not transient or i == attempts - 1:
                raise
            time.sleep(base_sleep * (i + 1))


class ThrottledProvider:
    """Politeness wrapper: jittered sleep at the start of each ticker's
    fetch chain (get_info is always the first call per ticker), plus
    backoff-retries on 429s from datacenter IPs."""

    def __init__(self, inner, secs: float):
        self.inner, self.secs = inner, secs

    def get_info(self, ticker):
        if self.secs:
            time.sleep(self.secs * (0.5 + random.random()))
        return _with_retry(lambda: self.inner.get_info(ticker))

    def get_financials(self, ticker):
        return _with_retry(lambda: self.inner.get_financials(ticker))

    def get_prices(self, ticker, years: int = 3):
        return _with_retry(lambda: self.inner.get_prices(ticker, years=years))

    def benchmark_ticker(self, ticker):
        return self.inner.benchmark_ticker(ticker)


def main() -> None:
    ttl = float(os.environ.get("MBE_CACHE_TTL_HOURS", "24"))
    throttle = float(os.environ.get("MBE_THROTTLE_SECS", "0"))
    cache = DiskCache("data/cache", ttl_hours=ttl)
    provider = ThrottledProvider(YahooProvider(cache), throttle)

    universe_cache = DiskCache("data/cache", ttl_hours=max(ttl, CACHE_TTL_HOURS))
    tickers = get_universe(UNIVERSE, cache=universe_cache)
    print(f"screening {len(tickers)} (ttl={ttl}h throttle={throttle}s)...", flush=True)
    result = screen(tickers, provider)
    print(f"analyzed {len(result.ranked)} | failed {len(result.failures)}", flush=True)
    if len(result.ranked) < MIN_ANALYZED:
        raise SystemExit(
            f"only {len(result.ranked)} analyzed (< {MIN_ANALYZED}) — refusing "
            f"to publish a degraded ranking. Failures: "
            f"{list(result.failures.items())[:5]}"
        )
    RunStore("data/mbe.duckdb").save_run(result, UNIVERSE)

    news = {
        b.card.ticker: company_news(
            b.info.name or b.card.ticker, b.card.ticker, cache=cache
        )
        for b in result.ranked[:TOP_N]
    }
    policy = policy_items([s.name for s in result.sector_scores], cache=cache)
    with_news = sum(1 for v in news.values() if v)
    print(f"news for {with_news}/{TOP_N} picks | {len(policy)} policy items", flush=True)

    prev_path = SITE / "data.json"
    prev = json.loads(prev_path.read_text()) if prev_path.exists() else None
    data = build_data(result, news, policy, built_at=datetime.now(timezone.utc))
    changes = diff_weeks(prev, data)
    render_site(data, changes, result, SITE)
    print(
        f"site built: {SITE}/index.html | entered {changes['entered']} | "
        f"exited {changes['exited']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Syntax + import check (no network)**

Run: `uv run python -c "import ast; ast.parse(open('scripts/build_site.py').read())"`
Expected: silence.

- [ ] **Step 3: First live build (network; cache warm from this week's screen)**

Run: `uv run python scripts/build_site.py`
Expected: `analyzed 250 | failed 0` (or close), news counts printed, `site built: site/index.html`. Open `site/index.html` in a browser: dark ranking table, sector table, policy items (if PIB reachable), changes strip showing all 25 as entered (first build has no previous week), footer present. Quote cells will show `n/a` locally (no /api route without Vercel) — expected.

- [ ] **Step 4: Full offline suite still green**

Run: `uv run pytest`
Expected: all pass (site build touches no test surface).

- [ ] **Step 5: Commit script + built site**

```bash
git add scripts/build_site.py site/
git commit -m "feat(publish): weekly build_site orchestration + first built site"
```

---

### Task 7: GitHub Actions workflow + .gitignore anchoring

**Files:**
- Create: `.github/workflows/weekly.yml`
- Modify: `.gitignore`

- [ ] **Step 1: Fix the .gitignore false-positive**

Replace the `data/` and `reports/` lines in `.gitignore` with anchored versions (the unanchored `data/` matches `src/mbe/data/`, which has forced `-f` adds all week):

```gitignore
.venv/
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
/data/
/reports/
.DS_Store
```

(Also remove the now-redundant `data/cache/` line — `/data/` covers it.)
Verify: `git check-ignore src/mbe/data/yahoo.py` → exits 1 (not ignored); `git check-ignore data/mbe.duckdb` → still ignored; `git check-ignore site/index.html` → exits 1 (site/ stays tracked).

- [ ] **Step 2: Write the workflow**

Create `.github/workflows/weekly.yml`:

```yaml
name: weekly-picks
on:
  schedule:
    - cron: "30 2 * * 1"   # Mondays 02:30 UTC = 08:00 IST, before market open
  workflow_dispatch: {}
permissions:
  contents: write
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - uses: actions/cache@v4
        with:
          path: |
            data/cache
            data/mbe.duckdb
          key: mbe-data-${{ github.run_id }}
          restore-keys: mbe-data-
      - run: uv sync
      - name: Build site
        run: uv run python scripts/build_site.py
        env:
          MBE_CACHE_TTL_HOURS: "144"
          MBE_THROTTLE_SECS: "0.8"
      - name: Commit site (triggers Vercel deploy)
        run: |
          git config user.name "mbe-weekly-bot"
          git config user.email "actions@users.noreply.github.com"
          git add site/
          git diff --cached --quiet && echo "no site changes" && exit 0
          git commit -m "chore(publish): weekly site build $(date -u +%F)"
          git push
```

- [ ] **Step 3: Validate YAML locally**

Run: `uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/weekly.yml')); print('yaml ok')"` — if PyYAML isn't available, `uvx --from pyyaml python -c ...` or skip with a careful eyeball; the first `workflow_dispatch` run is the real validation.

- [ ] **Step 4: Full suite**

Run: `uv run pytest`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add .gitignore .github/workflows/weekly.yml
git commit -m "feat(publish): weekly GitHub Actions build + anchored gitignore"
```

---

### Task 8: Docs — CHANGELOG, README, spec amendment

**Files:**
- Modify: `CHANGELOG.md` (append `## v0.10.0 — <today>` at END, file is chronological)
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-18-hosted-weekly-picks-design.md`

- [ ] **Step 1: CHANGELOG** — Added: hosted weekly picks pipeline (news_rss provider with PIB policy tagging, publish.py static-site builder with week-over-week diff and validation footer, whitelisted delayed-quotes Vercel function, build_site orchestration with degraded-publish guard, weekly GitHub Actions workflow with Vercel git-integration deploy); Fixed: anchored `.gitignore` `data/`→`/data/` (was false-matching `src/mbe/data/`).

- [ ] **Step 2: README** — add a `## Hosted weekly picks (v0.10)` section: what the page shows, the GH Actions + Vercel architecture in 3 sentences, `uv run python scripts/build_site.py` for a local build, and the honesty note (descriptive layers never scored; degraded builds refuse to publish).

- [ ] **Step 3: Spec amendment** — in the spec's pipeline section and prerequisites, replace the "Deploy `site/` to Vercel (CLI + `VERCEL_TOKEN` secret)" mechanism with: "Actions commits `site/` to main; Vercel's git integration auto-deploys (no token/CLI)". Adjust the prerequisites line accordingly (no `VERCEL_TOKEN`).

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md README.md docs/superpowers/specs/2026-07-18-hosted-weekly-picks-design.md
git commit -m "docs(publish): v0.10.0 changelog, README hosted section, spec deploy amendment"
```

---

### Task 9: Deploy runbook (user-in-the-loop)

No new files — this is the go-live sequence, run interactively with the user.

- [ ] **Step 1: Merge to main**

```bash
git checkout main && git merge p2.4-sector-rotation
uv run pytest   # green on main
```

- [ ] **Step 2: Create the GitHub repo and push** (user has an account)

```bash
gh auth status || gh auth login          # if gh CLI available
gh repo create multibagger-engine --private --source=. --push
# — or manually: create an empty private repo in the GitHub UI, then:
# git remote add origin git@github.com:<user>/multibagger-engine.git
# git push -u origin main
```

- [ ] **Step 3: Connect Vercel** (user has an account) — in the Vercel dashboard: **Add New → Project → Import** the `multibagger-engine` repo. Framework preset: **Other**. Root directory: repo root (vercel.json supplies `outputDirectory: site` and the function config). Deploy. Expected: first deployment serves the Task-6 built site at `https://<project>.vercel.app`, and `/api/quotes?symbols=<a-top-ticker>.NS` returns JSON with a price.

- [ ] **Step 4: First Actions run** — GitHub → Actions tab → `weekly-picks` → **Run workflow** (manual dispatch). Watch it: cache restore, build (~20-40 min with throttle), site commit, Vercel auto-deploy of that commit. If Yahoo rate-limits the runner (the stated risk), the degraded-publish guard fails the job loudly — then enable the fallback: run `scripts/build_site.py` locally via a Monday launchd job and `git push` (documented in README as the fallback trigger).

- [ ] **Step 5: Verify the live page** — open the Vercel URL on a phone: ranking renders, quotes populate with the delayed label, report links work, footer present. Done — the cron owns Mondays from here.

---

## Execution notes

- Tasks 1–5 are fully offline. Task 6 Step 3 and Task 9 touch network/accounts.
- Task 9 requires the user (GitHub/Vercel logins) — do it together, not via subagent.
- The Yahoo-from-datacenter risk is resolved empirically at Task 9 Step 4; both outcomes are handled (guard fails loudly → documented local fallback).
