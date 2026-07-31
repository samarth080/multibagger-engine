# Recent News & Policy Context

Date: 2026-07-31
Status: approved, ready for implementation planning

## Problem

Two separate failures, both silent, both shipped to every published report.

**1. The per-stock section is a stub.** `report/markdown.py:267-269` renders the
literal text *"Macro, government-policy and news catalyst modules arrive in v0.3
— this section will populate automatically."* It never populates. Every report
published to date carries that placeholder, which reads to a user like a roadmap
promise rather than an empty feature.

**2. Site policy tagging cannot match, ever.** `policy_items` fetches
`PIB_RSS_URL`, which serves **Hindi** headlines, and tags them against
`POLICY_KEYWORDS`, which is lowercase **English**. In the 2026-07-31 build, **0
of 12** items tagged to any sector. Verified: `Lang=1/2/3` and `Regid=1..6` all
return Hindi or an empty feed, so this is not a parameter fix. The build printed
`12 policy items` and the page rendered them under a "Government policy (PIB)"
heading, implying a sector relevance that had never been computed.

Recorded as Addendum 24 in `docs/backtest-findings-2026-07.md`.

**What already works, and sets the pattern:** `company_news` pulls English
headlines from Google News RSS and attaches to 24/25 picks. `themes_for` renders
curated sector themes with a visible `CURATED_AS_OF` date and is explicitly
descriptive-only.

## Goal

A per-stock section that shows dated, sourced, English headlines for the company
and for its sector's policy environment — accurately labelled as evidence a
reader interprets, not as catalysts the engine has identified.

## Non-goals

- **No catalyst extraction.** Keyword-matching headlines into "candidate
  catalysts" is the same technique that just failed silently on policy, and its
  false positives would look authoritative. An LLM summarisation step would add
  a build-time API dependency whose failures are hard to detect. Neither is in
  scope.
- **Never scored.** No pillar, no weight, no risk flag. Same contract as sector
  themes, franchise and stewardship.
- No new data provider or scraping. The working Google News pipeline is reused.

## Design

### Part 1 — Replace the PIB path

`policy_items`, `PIB_RSS_URL` and `POLICY_KEYWORDS` are **removed**, not left
alongside. Keeping a second policy path that has never produced a tagged item
would leave the codebase with two implementations, one of which is known dead.

New in `src/mbe/data/news_rss.py`:

```python
def sector_policy(
    sector: str | None,
    industry: str | None,
    cache: DiskCache | None = None,
    fetcher=default_http,
) -> list[NewsItem]:
```

Builds a policy-flavoured Google News query from `industry` when present, else
`sector`; returns `[]` when both are absent. Reuses `GOOGLE_NEWS_URL`
(`hl=en-IN&gl=IN&ceid=IN:en` — already English and India-scoped),
`parse_rss` and `dedupe_recent`.

Query shape: `"{industry} India government policy scheme"`. The query *is* the
relevance filter, which is why no keyword tagging step is needed — the failure
mode that killed the PIB path cannot recur, because there is no matching step to
fail.

Cache key `policy_{slug}` where `slug` is the lowercased, non-alphanumeric-
stripped industry or sector, so sectors share one fetch across all their member
stocks. On fetch failure return `[]`, matching `company_news`'s contract that
context must never fail a build.

`NewsItem.sectors` **is** populated, with the single key the query was built
from (`[industry]`, else `[sector]`). This is load-bearing, not decorative: the
site concatenates policy across all sectors into one flat `d.policy` list and
renders `p.sectors` as tags, and the per-stock report needs it to filter that
flat list down to its own industry. Under the old design the field was the
*output* of a keyword matcher that never matched; here it is the *input* the
query was built from, so it cannot silently disagree with the item's relevance.

### Part 2 — Report section

`render_report(bundle)` becomes:

```python
def render_report(
    bundle: AnalysisBundle,
    news: list[NewsItem] | None = None,
    policy: list[NewsItem] | None = None,
) -> str:
```

Defaults are `None` so every existing caller keeps working and the offline path
renders the explicit empty states rather than crashing. **No network inside the
renderer** — the caller fetches. This keeps reports deterministic and testable
without mocking HTTP.

The section at `markdown.py:267-269` is renamed from *Catalysts & Policy
Tailwinds* to **Recent News & Policy Context** and renders:

```
## Recent News & Policy Context

*Descriptive only — headlines are evidence to weigh, not catalysts the engine
has identified. Never scored.*

**Company**
- {title} — {source}, {age}d ago

**Sector policy — {industry or sector}**
- {title} — {source}, {age}d ago
```

Empty states render as explicit text, never as an absent block:
`*No recent company news found.*` and `*No sector policy items found.*` A
missing industry/sector renders `*No sector classification — policy context
unavailable.*`

Age is computed from `NewsItem.published` against `bundle.as_of`; items with no
`published` render without an age rather than being dropped.

### Part 3 — Callers

- **`scripts/build_site.py`**: replaces the `policy_items` call with one
  `sector_policy` call per distinct industry across the top N, concatenating the
  results into the flat list `build_data` already expects. Each item carries its
  industry in `sectors`, so nothing is lost in the flattening. The 0-tagged
  warning added earlier today is removed — its cause is gone. The printed count
  becomes `{n} policy items across {k} sectors`.
- **`src/mbe/publish.py` site template**: the heading `Government policy (PIB)`
  becomes `Government policy & sector news`, since PIB is no longer the source.
  Leaving it would attribute Google News aggregation to a government press
  office.
- **`src/mbe/cli.py` (`analyze`)**: fetches `company_news` and `sector_policy`
  for the single ticker before rendering, so `mbe analyze` produces the same
  section as the published report. Fetch failures degrade to the empty states.
- **`src/mbe/publish.py`**: `render_report_page` threads the same two arguments
  through to `render_report`.

## Testing

`tests/test_news_rss.py`, `tests/test_pipeline.py`, `tests/test_publish.py`.

- Query is built from `industry` when present, from `sector` when industry is
  `None`, and returns `[]` when both are `None`.
- Cache key is shared across two stocks in the same industry (one fetch, two
  callers).
- A fetcher that raises returns `[]` rather than propagating.
- `render_report(bundle)` with no news arguments renders both empty states and
  does not raise — this is the `mbe analyze` offline path.
- A report with company news renders each title, source and age.
- A report whose `info.industry` and `info.sector` are both `None` renders the
  no-classification text.
- Items with `published=None` render without an age rather than being dropped.
- `sector_policy` sets `sectors` to the single key the query was built from, and
  the report renders only the policy items whose `sectors` match its own
  industry when handed a flat multi-sector list.
- `test_report_contains_all_sections` in `tests/test_pipeline.py` is updated for
  the new heading. `test_policy_items_tag_matching_sectors` in
  `tests/test_news_rss.py` is **deleted** along with the function it covers.

## Files touched

| file | change |
|---|---|
| `src/mbe/data/news_rss.py` | add `sector_policy`; remove `policy_items`, `PIB_RSS_URL`, `POLICY_KEYWORDS` |
| `src/mbe/report/markdown.py` | section rewrite, `news`/`policy` params |
| `src/mbe/publish.py` | thread arguments through `render_report_page` |
| `scripts/build_site.py` | call `sector_policy`; drop the 0-tagged warning |
| `src/mbe/cli.py` | fetch news + policy for single-ticker analyze |
| `tests/test_news_rss.py` | new `sector_policy` tests; delete the PIB test |
| `tests/test_pipeline.py`, `tests/test_publish.py` | heading + rendering tests |

## Expected effect

Every report gains a real, dated, English news and policy block in place of a
three-year-old placeholder. The site's policy section carries sector-relevant
English items for the first time. One dead code path and one silently-failing
keyword matcher leave the codebase.
