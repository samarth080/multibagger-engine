# Report Charts: peers, ownership, trends, scenarios

Date: 2026-08-01
Status: approved, ready for implementation planning

## Problem

Per-stock report pages carry the engine's densest output as unbroken prose and
tables. Three things a reader wants at a glance are either invisible or buried:

1. **How this company compares to its actual competitors.** The engine already
   screens 250 names and groups them into industries of 4-13, and already
   computes a leave-one-out peer P/E for the forecast anchor — but a report
   never shows the peer set. HBL Engineering has the best ROCE (32.9%) *and*
   the best revenue growth (34.5%) in its 8-name group at the second-cheapest
   P/E (24.5x), and none of that appears on its page.
2. **Who owns the company.** `CompanyInfo` carries `insider_pct` and
   `institution_pct` (present for 25/25 live picks) and they are never rendered.
3. **Trend and forecast shape.** Financial history and the bull/base/bear
   forecast are tables of numbers; the *shape* is what a reader is after.

## Goal

Charts on the per-stock report pages that make comparison, ownership, trend and
forecast readable at a glance — without lengthening the page, adding a
dependency, or introducing anything scored.

## Non-goals

- **The index page.** Separate surface, separate spec.
- **The price/technical chart.** The report's technical section is unchanged.
- **Any JavaScript, interactivity or tooltips.** The page stays static.
- **Any new data source.** Charts present what the engine already computes.
- **Never scored.** No pillar, no weight, no risk flag — the same contract as
  sector themes, news/policy, franchise and stewardship.

## Design

### Architecture

New module `src/mbe/report/charts.py`. One pure function per chart, taking
plain data and returning an **SVG string, or `None`** when the data cannot
support it. No I/O, no network, no template access, so each chart unit-tests on
its output string.

Plumbing mirrors the v0.14 news/policy work:

```python
def render_report(
    bundle: AnalysisBundle,
    news: list[NewsItem] | None = None,
    policy: list[NewsItem] | None = None,
    charts: dict[str, str] | None = None,
) -> str:
```

`publish.render_report_page` builds the SVGs and passes them; `mbe analyze`
and `api/analyze.py` pass nothing and keep working.

**Chart-or-table, one conditional.** "Chart replaces the table" taken literally
would leave CLI markdown with neither. So each section is
`{% if charts.<name> %}` SVG `{% else %}` today's table `{% endif %}`. The site
renders charts only — more readable, not longer — and the `.md` file keeps
every number. One template branch, not two documents. **The scenario section is
the deliberate exception**: its chart renders *in addition to* its assumptions
table, for the reason given under chart 4.

**Placement.** Existing headings are unchanged except as noted:

| chart | section |
|---|---|
| peer scatter + peer table | new `## Peer Comparison`, after `## Valuation` |
| shareholding donut | new `## Ownership`, after `## Business & Investment Thesis` |
| financial trend bars | inside `## Financial Analysis` |
| scenario chart | inside `## 3-Year Price Forecast`, above its table |

**Peer data comes from the screen, not the ticker.** `render_site` already
receives `result: ScreenResult` with all 250 bundles and
`sector_scores[].members`, so the peer set is a lookup. Single-ticker paths
(`mbe analyze`, `/api/analyze`) have no peer group; those two charts are absent
there with a line saying peer comparison requires a universe screen — the
behaviour the Sector Momentum line already has.

**Theme.** The site ships dark and light palettes with a live toggle, so SVGs
use `currentColor` and the existing CSS custom properties. Hardcoded hex would
make every chart invisible in one theme.

### The four charts

**1 — Peer comparison: scatter + inline-bar table.**
Peer group = the `SectorScore` whose `members` contain this ticker (`MIN_GROUP`
guarantees ≥4). Metrics: `fund.roce_3y`, `fund.revenue_cagr_3y`,
`info.trailing_pe`, `card.multibagger_score`.

- *Scatter:* ROCE (x) × revenue CAGR (y), bubble area = market cap, subject
  highlighted against greyed peers.
- *Table:* one row per peer, a mini-bar per metric, subject row highlighted,
  sorted by multibagger score.

A peer missing a metric gets a blank cell and no scatter point — never a zero,
because imputation is banned engine-wide. The P/E column is labelled "lower is
cheaper", since bar length otherwise implies longer = better.

**2 — Shareholding donut.**
Three slices: insider/promoter, institutions, public (the remainder).

Yahoo's two ownership fields **contradict each other for 4 of 25 live picks**:
HBL reports 8.1% insider while its own float (104.4M of 277.2M shares) implies
~62%. Measured gaps against `1 - float_shares/shares_outstanding`: 21/25 agree
within 10pp, 4 exceed it (HBL 54pp, KFINTECH 21pp, LEMONTREE 15pp, NIVABUPA
11pp).

**Decision (user, 2026-08-01): always draw the donut, and state the conflict on
the chart itself** — *"Yahoo reports 8.1% insider; its own float implies 62%"* —
as chart furniture, not a footnote. The conflict line appears when
`abs(insider_pct - (1 - float_shares/shares_outstanding)) > 0.10`; the 10pp
threshold is the value the measurement above was taken at, and it separates the
21 consistent picks from the 4 inconsistent ones with a wide margin (largest
"agree" gap 7.4pp, smallest "disagree" gap 10.6pp). When either float field is
missing, the cross-check cannot run and says so rather than passing silently.

Two further labels, always shown:

- Yahoo's "insider" is not SEBI's promoter category.
- This is **not** the promoter/FII/DII/public breakdown an Indian investor
  expects; that data is not in the pipeline.

If insider + institutions exceeds 100% (0/25 today, but possible), the public
slice is dropped rather than drawn negative.

**3 — Financial trend bars.**
Revenue, net income and FCF as three small multiples over the 4-5 years Yahoo
provides, values labelled on the bars. Loss years render below a zero line
rather than being dropped.

**4 — Forecast scenarios, with its table kept.**
Bull/base/bear `target_price` against today's price, labelled with `cagr_3y`
and `probability`. Unlike the other three, **the assumptions table stays below
the chart**: it carries growth start/end, terminal margin and exit multiple —
the engine's reasoning. A chart holds the "what"; deleting the table would
delete the "why", which cuts against how the rest of the report works.

### Failure and degradation

Every chart returns `None` when its data is insufficient. That is not an error
and never a zero — it is an absent chart, with the template falling back to the
table or to explicit text naming what is missing. No chart renders a partial or
empty frame.

### Security

Company names, tickers and industry labels originate from Yahoo and are written
into SVG `<text>` nodes. This is the same class of bug as the reflected XSS
found in the error page in v0.11: an unescaped `&` or `<` breaks the SVG
outright, and worse is possible. Every interpolated string is escaped at the
chart-builder boundary.

## Testing

`tests/test_charts.py` (new), plus additions to `tests/test_pipeline.py` and
`tests/test_publish.py`.

- Each chart's values actually appear in its SVG output.
- A `None` metric leaves a gap; it never renders as 0.
- A loss year draws below the zero line rather than being dropped.
- A 4-name group still produces a usable scatter.
- `insider + institutions > 100%` drops the public slice instead of drawing it
  negative.
- The ownership cross-check text appears when the two Yahoo fields disagree by
  more than 10pp (HBL's real numbers), does not when they agree (BLS's), and
  reports that it could not run when `float_shares` is `None`.
- No hardcoded hex colours in output (which would break the light theme).
- A company name containing `<script>` and `&` comes out inert.
- `render_report(bundle)` with no `charts` renders every existing table
  unchanged — the CLI path.
- `render_report(bundle, charts={...})` renders the SVG and omits the replaced
  table, except the scenario table, which remains.
- A report page for a single-ticker analysis (no peer group) renders the
  "requires a universe screen" text rather than raising.

## Files touched

| file | change |
|---|---|
| `src/mbe/report/charts.py` | new — one pure SVG builder per chart |
| `src/mbe/report/markdown.py` | `charts` param; chart-or-table conditionals |
| `src/mbe/publish.py` | build SVGs in `render_report_page`; pass peer bundles |
| `tests/test_charts.py` | new |
| `tests/test_pipeline.py`, `tests/test_publish.py` | rendering + fallback tests |

## Expected effect

A report page shows, at a glance, where the company sits against its real
competitors, who owns it (with the source's own contradictions surfaced rather
than smoothed), how revenue/profit/cash have moved, and what the three-year
scenarios imply — without a new dependency, without JavaScript, and without
anything new being scored.
