# Recent News & Policy Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace a three-year-old "arrives in v0.3" stub in every report, and a policy feed that has never tagged an item, with a real dated English news and policy section.

**Architecture:** One new function, `sector_policy`, reuses the working Google News RSS pipeline with a policy-flavoured query built from the stock's industry — so the query *is* the relevance filter and there is no keyword-matching step left to fail silently. `render_report` gains optional `news`/`policy` parameters; callers fetch, the renderer stays pure. The dead PIB path is deleted.

**Tech Stack:** Python 3.12, pydantic v2, jinja2 templates, stdlib `urllib` + `xml.etree` for RSS, pytest. Run tests with `.venv/bin/python -m pytest` (the config already includes `-q`; do not add another).

**Spec:** `docs/superpowers/specs/2026-07-31-news-policy-context-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/mbe/data/news_rss.py` | add `sector_policy`; delete `policy_items`, `PIB_RSS_URL`, `POLICY_KEYWORDS` |
| `src/mbe/report/markdown.py` | the report section + `news`/`policy` params on `render_report` |
| `src/mbe/publish.py` | thread params through `render_report_page`; rename the site policy heading |
| `scripts/build_site.py` | call `sector_policy` per industry; drop today's 0-tagged warning |
| `src/mbe/cli.py` | fetch news + policy for single-ticker `analyze` |
| `tests/test_news_rss.py` | `sector_policy` tests; delete the PIB test |
| `tests/test_pipeline.py` | report section rendering + heading update |

---

## Task 1: `sector_policy` replaces the PIB path

**Files:**
- Modify: `src/mbe/data/news_rss.py` (add `sector_policy`; remove `policy_items`, `PIB_RSS_URL`, `POLICY_KEYWORDS`)
- Test: `tests/test_news_rss.py`

Background: `PIB_RSS_URL` serves Hindi headlines and `POLICY_KEYWORDS` matches lowercase English, so `policy_items` tagged 0 of 12 items in the last build. `Lang=1/2/3` and `Regid=1..6` all return Hindi or an empty feed, so this is not a parameter fix.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_news_rss.py`:

```python
POLICY_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>q</title>
<item><title>Cabinet clears Rs 25,000cr power grid scheme</title>
<link>https://example.com/p1</link>
<pubDate>Fri, 17 Jul 2026 08:00:00 GMT</pubDate>
<source url="https://pib.example">PIB</source></item>
<item><title>PLI scheme extended for electrical equipment</title>
<link>https://example.com/p2</link>
<pubDate>Thu, 16 Jul 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


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
```

- [ ] **Step 2: Delete the PIB test**

In `tests/test_news_rss.py`, delete `test_policy_items_tag_matching_sectors` (lines 110-119) entirely, and remove `policy_items` from the import on line 7 so it reads:

```python
from mbe.data.news_rss import NewsItem, dedupe_recent, parse_rss, company_news
```

Also delete the `PIB_RSS` fixture constant if one exists in the file.

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_news_rss.py`
Expected: the four new tests FAIL with `ImportError: cannot import name 'sector_policy'`.

- [ ] **Step 4: Implement `sector_policy`**

In `src/mbe/data/news_rss.py`, delete the `PIB_RSS_URL` constant (line 27) and the entire `POLICY_KEYWORDS` dict (starting line 30-31, including its `# sector/industry group name -> ...` comment), then delete the whole `policy_items` function. Add in its place:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_news_rss.py`
Expected: all PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest`
Expected: FAIL — `scripts/build_site.py` still imports `policy_items`. That import is fixed in Task 4; if any *test* fails for another reason, stop and report it.

- [ ] **Step 7: Commit**

```bash
git add src/mbe/data/news_rss.py tests/test_news_rss.py
git commit -m "feat(news): sector_policy replaces the PIB path

PIB_RSS_URL served Hindi while POLICY_KEYWORDS matched English, so tagging
returned 0 of 12 items and always would have. The replacement builds a
policy query from the industry, so the query is the relevance filter and no
separate matching step remains to fail silently."
```

---

## Task 2: Report section

**Files:**
- Modify: `src/mbe/report/markdown.py:267-269` (the stub section), `render_report` signature at `:276`, and the `_TEMPLATE.render(...)` call at `:299-319`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
def test_report_renders_news_and_policy_with_ages():
    from datetime import datetime, timezone
    from mbe.data.news_rss import NewsItem
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    pub = datetime(2026, 7, 15, tzinfo=timezone.utc)
    md = render_report(
        bundle,
        news=[NewsItem(title="Wins Rs 400cr order", link="https://x/1",
                       published=pub, source="Economic Times")],
        policy=[NewsItem(title="Cabinet clears grid scheme", link="https://x/2",
                         published=pub, source="PIB", sectors=["Test Industry"])],
    )
    assert "## Recent News & Policy Context" in md
    assert "Wins Rs 400cr order" in md
    assert "Economic Times" in md
    assert "Cabinet clears grid scheme" in md
    assert "not catalysts the engine has identified" in md


def test_report_states_absence_explicitly_when_no_news():
    """Silence is what let the old policy section look like it worked."""
    from mbe.report.markdown import render_report

    md = render_report(analyze_ticker("GOOD.NS", StubProvider()))
    assert "## Recent News & Policy Context" in md
    assert "No recent company news found" in md
    assert "No sector policy items found" in md
    assert "arrives in v0.3" not in md


def test_report_filters_policy_to_its_own_industry():
    """build_site hands every report one flat multi-industry list."""
    from mbe.data.news_rss import NewsItem
    from mbe.report.markdown import render_report

    bundle = analyze_ticker("GOOD.NS", StubProvider())
    md = render_report(bundle, policy=[
        NewsItem(title="Mine item", link="https://x/1", sectors=["Test Industry"]),
        NewsItem(title="Someone elses item", link="https://x/2", sectors=["Banks"]),
    ])
    assert "Mine item" in md
    assert "Someone elses item" not in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -k "news or policy or absence"`
Expected: FAIL — `render_report() got an unexpected keyword argument 'news'`.

- [ ] **Step 3: Replace the stub section in the template**

In `src/mbe/report/markdown.py`, replace lines 267-269 exactly:

```jinja
## Catalysts & Policy Tailwinds

*Macro, government-policy and news catalyst modules arrive in v0.3 — this section will populate automatically. Until then, verify PLI/policy exposure manually.*
```

with:

```jinja
## Recent News & Policy Context

*Descriptive only — headlines are evidence to weigh, not catalysts the engine has identified. Never scored.*

**Company**

{% if news %}
{% for n in news %}
- [{{ n.title }}]({{ n.link }}){% if n.source %} — {{ n.source }}{% endif %}{% if n.age_days is not none %}, {{ n.age_days }}d ago{% endif %}
{% endfor %}
{% else %}
*No recent company news found.*
{% endif %}

**Sector policy{% if policy_key %} — {{ policy_key }}{% endif %}**

{% if not policy_key %}
*No sector classification — policy context unavailable.*
{% elif policy %}
{% for p in policy %}
- [{{ p.title }}]({{ p.link }}){% if p.source %} — {{ p.source }}{% endif %}{% if p.age_days is not none %}, {{ p.age_days }}d ago{% endif %}
{% endfor %}
{% else %}
*No sector policy items found.*
{% endif %}
```

- [ ] **Step 4: Add the signature, age helper and filtering**

In `src/mbe/report/markdown.py`, change the `render_report` signature at line 276 from:

```python
def render_report(bundle: AnalysisBundle) -> str:
```

to:

```python
def render_report(
    bundle: AnalysisBundle,
    news: list[NewsItem] | None = None,
    policy: list[NewsItem] | None = None,
) -> str:
```

Add the import at the top of the file, beside the other `mbe` imports:

```python
from mbe.data.news_rss import NewsItem
```

Then inside `render_report`, before the `return _TEMPLATE.render(...)` call, add:

```python
    # Age is attached here rather than on the model: NewsItem is a transport
    # object shared with the site's JSON, and "days old" is only meaningful
    # relative to the report's own as_of date.
    def _dated(items: list[NewsItem]) -> list[dict]:
        out = []
        for i in items:
            age = (bundle.as_of - i.published.date()).days if i.published else None
            out.append({
                "title": i.title, "link": i.link, "source": i.source,
                "age_days": age if age is not None and age >= 0 else None,
            })
        return out

    policy_key = bundle.info.industry or bundle.info.sector
    # build_site hands every report one flat list covering all industries
    own_policy = [p for p in (policy or []) if not p.sectors or policy_key in p.sectors]
```

and add these three entries to the `_TEMPLATE.render(...)` call, after `sector_themes=...`:

```python
        news=_dated(news or []),
        policy=_dated(own_policy),
        policy_key=policy_key,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py`
Expected: all PASS. If `test_report_contains_all_sections` fails on the old heading, update the string it asserts to `Recent News & Policy Context` — that rename is intended.

- [ ] **Step 6: Commit**

```bash
git add src/mbe/report/markdown.py tests/test_pipeline.py
git commit -m "feat(report): Recent News & Policy Context replaces the v0.3 stub

Every report published to date carried a placeholder reading 'modules arrive
in v0.3'. The section now renders dated, sourced headlines and states absence
explicitly, since silence is what let the old policy path look like it worked."
```

---

## Task 3: Thread through `publish.py`

**Files:**
- Modify: `src/mbe/publish.py:181-186` (`render_report_page`), and the site policy heading at `:282`

- [ ] **Step 1: Update `render_report_page`**

In `src/mbe/publish.py`, change:

```python
def render_report_page(bundle: AnalysisBundle, back_href: str = "../index.html") -> str:
    """Wrap one AnalysisBundle's markdown report in the shared dark shell.
    Used by render_site() for weekly static reports and by api/analyze.py
    for live single-ticker search — one shell, one back-link parameter."""
    body = md.markdown(render_report(bundle), extensions=["tables"])
```

to:

```python
def render_report_page(
    bundle: AnalysisBundle,
    back_href: str = "../index.html",
    news: list[NewsItem] | None = None,
    policy: list[NewsItem] | None = None,
) -> str:
    """Wrap one AnalysisBundle's markdown report in the shared dark shell.
    Used by render_site() for weekly static reports and by api/analyze.py
    for live single-ticker search — one shell, one back-link parameter."""
    body = md.markdown(render_report(bundle, news=news, policy=policy),
                       extensions=["tables"])
```

`NewsItem` is already imported in this file; confirm with `grep -n "NewsItem" src/mbe/publish.py` and add `from mbe.data.news_rss import NewsItem` beside the other imports only if it is absent.

- [ ] **Step 2: Rename the site policy heading**

In `src/mbe/publish.py:282`, change:

```jinja
{% if d.policy %}<h2 class="sec" id="policy">Government policy (PIB)</h2>
```

to:

```jinja
{% if d.policy %}<h2 class="sec" id="policy">Government policy &amp; sector news</h2>
```

PIB is no longer the source, and leaving the label would attribute Google News aggregation to a government press office.

- [ ] **Step 3: Pass policy through in `render_site`**

At `src/mbe/publish.py:344`, change:

```python
            page = render_report_page(b)
```

to:

```python
            page = render_report_page(
                b, policy=[NewsItem(**p) for p in data.get("policy", [])]
            )
```

`render_site(data, changes, result, out_dir)` does not receive the per-ticker news dict, so company news is not available here. Wiring it in would mean changing `render_site`'s signature, and it is already shown per pick on the index page — out of scope for this plan. Reports on the static site will render the explicit "No recent company news found" line, which is accurate for that build.

`api/analyze.py:64` also calls `render_report_page`, for live single-ticker search. It is deliberately left on the defaults: both parameters are optional, so it keeps working and renders the empty states. Fetching news inside a serverless request would add two network round-trips to a latency-sensitive path.

- [ ] **Step 4: Run the suite**

Run: `.venv/bin/python -m pytest`
Expected: `tests/test_publish.py` and `tests/test_web.py` PASS. `scripts/build_site.py` still imports `policy_items` but is not imported by tests.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/publish.py
git commit -m "feat(publish): thread news/policy into report pages, drop the PIB label"
```

---

## Task 4: `build_site.py` calls `sector_policy`

**Files:**
- Modify: `scripts/build_site.py:18` (import), `:92-113` (the policy call and today's warning)

- [ ] **Step 1: Replace the import**

In `scripts/build_site.py` line 18, change:

```python
from mbe.data.news_rss import company_news, policy_items
```

to:

```python
from mbe.data.news_rss import company_news, sector_policy
```

- [ ] **Step 2: Replace the policy fetch and delete the warning**

Replace the whole block from `policy = policy_items(...)` through the end of the `if policy and not tagged:` warning (added earlier today, roughly lines 92-113) with:

```python
    industries = {
        b.info.industry or b.info.sector
        for b in result.ranked[:TOP_N]
        if (b.info.industry or b.info.sector)
    }
    policy = [
        item
        for key in sorted(industries)
        for item in sector_policy(None, key, cache=cache)
    ]
    with_news = sum(1 for v in news.values() if v)
    print(
        f"news for {with_news}/{TOP_N} picks | "
        f"{len(policy)} policy items across {len(industries)} sectors",
        flush=True,
    )
```

The 0-tagged warning is deleted because its cause is gone: there is no tagging step any more, and an empty result now means the feed returned nothing rather than that matching silently failed.

- [ ] **Step 3: Verify the script parses and the suite passes**

Run:

```bash
python3 -c "import ast; ast.parse(open('scripts/build_site.py').read()); print('parses OK')"
.venv/bin/python -m pytest
```

Expected: `parses OK`, and the full suite PASSES with no remaining `policy_items` references. Confirm with `grep -rn "policy_items\|POLICY_KEYWORDS\|PIB_RSS_URL" src/ scripts/ tests/` returning nothing.

- [ ] **Step 4: Commit**

```bash
git add scripts/build_site.py
git commit -m "feat(site): per-industry sector_policy replaces the dead PIB fetch"
```

---

## Task 5: `mbe analyze` fetches its own context

**Files:**
- Modify: `src/mbe/cli.py:44-55` (the `analyze` command)

- [ ] **Step 1: Fetch and pass news + policy**

In `src/mbe/cli.py`, inside `analyze`, replace:

```python
    path.write_text(render_report(bundle))
```

with:

```python
    from mbe.data.news_rss import company_news, sector_policy

    cache = DiskCache(CACHE_DIR)
    news = company_news(bundle.info.name or ticker, ticker, cache=cache)
    policy = sector_policy(bundle.info.sector, bundle.info.industry, cache=cache)
    path.write_text(render_report(bundle, news=news, policy=policy))
```

Both functions return `[]` on any fetch failure, so an offline run still writes a report with the explicit empty states rather than failing.

Confirm `DiskCache` and `CACHE_DIR` are already imported in `cli.py` with `grep -n "DiskCache\|CACHE_DIR" src/mbe/cli.py`; add the import beside the others only if absent.

- [ ] **Step 2: Verify against real cached data**

Run:

```bash
.venv/bin/python -m mbe.cli analyze HBLENGINE.NS --out /tmp/news-check
```

Then read the generated markdown and confirm by eye: the section is headed `Recent News & Policy Context`, the disclaimer line is present, company headlines render with source and age, and the sector policy block is keyed to `Electrical Equipment & Parts`. If the network is unavailable, both empty-state lines must render instead — that is a pass, not a failure.

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add src/mbe/cli.py
git commit -m "feat(cli): analyze fetches its own news and policy context"
```

---

## Task 6: Rebuild the site and verify

**Files:**
- Modify: `site/` (generated), `CHANGELOG.md`

- [ ] **Step 1: Rebuild**

Run: `.venv/bin/python scripts/build_site.py`

Expected: the printed line now reads `... | N policy items across K sectors` with **N > 0 and K > 0**, and no warning. If N is 0, the Google News policy query returned nothing for every industry — investigate before committing rather than shipping an empty section.

- [ ] **Step 2: Verify a real report**

Run:

```bash
.venv/bin/python -c "
import re, html
t = open('site/reports/HBLENGINE_NS.html').read()
t = html.unescape(re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style).*?</\1>', '', t, flags=re.S)))
i = t.find('Recent News & Policy Context')
print(t[i:i+900] if i >= 0 else 'SECTION MISSING')
"
```

Expected: the section renders with real headlines, or explicit empty-state text. `SECTION MISSING` means the rebuild did not pick up the template change.

- [ ] **Step 3: Update the changelog**

Insert this into `CHANGELOG.md` immediately above the `## v0.13.0` heading:

```markdown
## v0.14.0 — 2026-07-31 (news & policy context)

### Fixed
- **Every report shipped a placeholder.** `Catalysts & Policy Tailwinds`
  rendered the literal text "modules arrive in v0.3 — this section will
  populate automatically" in every report ever published. It never populated.
- **Site policy tagging could never match.** `PIB_RSS_URL` served Hindi
  headlines while `POLICY_KEYWORDS` matched lowercase English, so 0 of 12 items
  tagged in the last build. `Lang=1/2/3` and `Regid=1..6` all return Hindi or an
  empty feed — not a parameter fix. The build printed "12 policy items" either
  way, so the failure was invisible.

### Added
- **Recent News & Policy Context** in every report: dated, sourced, English
  headlines for the company and for its industry's policy environment, with
  explicit "none found" text on every empty branch — silence is what let the
  old version look like it worked.
- `sector_policy()` builds a policy query from the stock's industry against the
  Google News pipeline that already works. **The query is the relevance
  filter**, so no separate keyword-matching step remains that can fail quietly.

### Removed
- `policy_items`, `PIB_RSS_URL`, `POLICY_KEYWORDS` and their test. A second
  policy path that has never produced a tagged item is worse than none.

### Validation status
Descriptive only. No pillar, no weight, no risk flag — the same contract as
sector themes, franchise and stewardship. Headlines are evidence a reader
weighs, not catalysts the engine has identified.
```

- [ ] **Step 4: Commit**

```bash
git add site/ CHANGELOG.md
git commit -m "chore(publish): site rebuild with real news and policy context"
```

---

## Notes for the implementer

**Do not reintroduce keyword matching.** The whole point of building the query from the industry is that there is no separate matching step left to fail silently. If policy results look off-topic, fix the *query string*, not by filtering results afterwards.

**Empty states are a feature.** Every branch that could render nothing renders text instead. The previous version's defining failure was that it looked identical whether it worked or not.

**Do not weaken an assertion to get a green suite.** If a test cannot pass, find the cause and report it. Two of this codebase's plans have had factually wrong fixtures, and in both cases the implementer was right and the root cause sat a layer below the test.
