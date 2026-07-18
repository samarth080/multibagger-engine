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
