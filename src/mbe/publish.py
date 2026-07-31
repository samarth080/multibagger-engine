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
from mbe.pipeline import AnalysisBundle, ScreenResult
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

# ---------------------------------------------------------------------------
# Theme foundation (spec: Zerodha-dark default, Groww-light toggle — the
# user's exact palette tokens). Shared by the index, report shell, and the
# analyze error page. Deliberately hand-rolled CSS custom properties, not
# Tailwind: this pipeline has no build step and adding one (or a CDN script
# with its render flash) isn't worth it for ~150 lines of CSS.
# ---------------------------------------------------------------------------

THEME_BOOT = """<script>(function(){try{
if(localStorage.getItem("mbe-theme")==="light")
document.documentElement.setAttribute("data-theme","light");
}catch(e){}})()</script>"""

THEME_TOGGLE = """<button class="theme-toggle" title="Toggle light/dark"
onclick="(function(){var r=document.documentElement;
var light=r.getAttribute('data-theme')==='light';
if(light){r.removeAttribute('data-theme')}else{r.setAttribute('data-theme','light')}
try{localStorage.setItem('mbe-theme',light?'dark':'light')}catch(e){}})()"
>&#9788;/&#9789;</button>"""

THEME_CSS = """<style>
:root{--bg:#1F2022;--surface:#252629;--text:#E4E6EB;--muted:#9B9EA4;
--border:#333333;--border-soft:#2C2D30;--accent:#38A6F0;
--gain:#4CAF50;--loss:#F44336;
--chip-gain-bg:rgba(76,175,80,.15);--chip-loss-bg:rgba(244,67,54,.15)}
[data-theme="light"]{--bg:#F3F4F6;--surface:#FFFFFF;--text:#2D343C;
--muted:#6B7280;--border:#DDE4F0;--border-soft:#EEF1F6;--accent:#5076EE;
--gain:#039955;--loss:#D32F2F;
--chip-gain-bg:#E7F6EF;--chip-loss-bg:#FBEAEA}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
nav.topnav{position:sticky;top:0;z-index:10;display:flex;align-items:center;
gap:18px;padding:10px 20px;background:var(--surface);
border-bottom:1px solid var(--border)}
.brand{font-weight:700;color:var(--accent);font-size:16px;letter-spacing:.02em}
.navlink{color:var(--muted);font-size:13px;font-weight:500}
.navlink:hover{color:var(--text);text-decoration:none}
.theme-toggle{background:none;border:1px solid var(--border);border-radius:6px;
color:var(--muted);padding:4px 10px;cursor:pointer;font-size:12px}
main{max-width:1080px;margin:0 auto;padding:16px 20px 40px}
.card{background:var(--surface);border:1px solid var(--border);
border-radius:10px;overflow:hidden;margin:14px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:var(--muted);font-size:11px;text-transform:uppercase;
letter-spacing:.05em;text-align:left;font-weight:600}
th,td{padding:9px 12px;border-bottom:1px solid var(--border-soft)}
tr:last-child td{border-bottom:none}
.gain{color:var(--gain)}.loss{color:var(--loss)}
.muted{color:var(--muted)}.small{font-size:11px}
.chip{display:inline-block;border-radius:5px;padding:2px 9px;
font-size:11px;font-weight:600}
.chip.gain{background:var(--chip-gain-bg)}.chip.loss{background:var(--chip-loss-bg)}
.accent{color:var(--accent);font-weight:600}
h2.sec{font-size:13px;text-transform:uppercase;letter-spacing:.06em;
color:var(--muted);margin:26px 0 4px}
footer{margin:32px 0 0;padding:14px 16px;border:1px solid var(--border);
border-radius:10px;color:var(--muted);font-size:12px;line-height:1.6}
</style>"""


def _dump_news(items: list[NewsItem], built_at: datetime) -> list[dict]:
    """Serialize headlines with an age in days relative to this build.

    Age is computed here rather than in the template because "days old" is
    only meaningful against the moment the page was built, and a published
    page is read for a week after that. Date arithmetic, not datetime, so a
    zone-less `published` can never raise mid-build."""
    out = []
    for i in items:
        row = i.model_dump(mode="json")
        age = (built_at.date() - i.published.date()).days if i.published else None
        row["age_days"] = age if age is not None and age >= 0 else None
        out.append(row)
    return out


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
                "news": _dump_news(news_by_ticker.get(t, []), built_at),
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
        "policy": _dump_news(policy, built_at),
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
""" + THEME_BOOT + THEME_CSS + """<style>
.report{padding:6px 22px 22px}
.report h1,.report h2,.report h3{color:var(--text);letter-spacing:.01em}
.report h1{font-size:20px;border-bottom:1px solid var(--border);padding-bottom:8px}
.report h2{font-size:15px;margin-top:26px}
.report h3{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.report table{display:block;overflow-x:auto;margin:10px 0}
.report td,.report th{border:1px solid var(--border-soft);white-space:nowrap}
.report hr{border:none;border-top:1px solid var(--border)}
.report blockquote{border-left:3px solid var(--accent);margin:10px 0;
padding:2px 14px;color:var(--muted)}
.report code{background:var(--bg);border-radius:4px;padding:1px 5px}
</style></head><body>
<nav class="topnav"><span class="brand">&#9670; MBE</span>
<a class="navlink" href="{{ back_href }}">&larr; back to rankings</a>
<span style="margin-left:auto"></span>""" + THEME_TOGGLE + """</nav>
<main><div class="card report">{{ body | safe }}</div></main>
</body></html>""")


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
    return _REPORT_SHELL.render(title=bundle.card.ticker, body=body, back_href=back_href)


_ERROR_SHELL = _ENV.from_string("""<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Analyze - error</title>
""" + THEME_BOOT + THEME_CSS + """</head><body>
<nav class="topnav"><span class="brand">&#9670; MBE</span>
<a class="navlink" href="/">&larr; back to rankings</a>
<span style="margin-left:auto"></span>""" + THEME_TOGGLE + """</nav>
<main><div class="card" style="padding:18px 22px">
<h1 style="color:var(--loss);font-size:18px">Could not analyze &quot;{{ ticker }}&quot;</h1>
<p class="muted">{{ reason }}</p>
</div></main></body></html>""")


def render_error_page(ticker: str, reason: str) -> str:
    """Themed analyze-error page. Autoescape handles ticker/reason — callers
    pass RAW strings (the api/analyze.py manual html.escape calls moved here
    structurally: one rendering module, one escaping mechanism)."""
    return _ERROR_SHELL.render(ticker=ticker, reason=reason)


_INDEX = _ENV.from_string("""<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly India Multibagger Picks</title>
""" + THEME_BOOT + THEME_CSS + """<style>
.searchpill{display:flex;align-items:center;gap:6px;background:var(--bg);
border:1px solid var(--border);border-radius:20px;padding:2px 4px 2px 14px}
.searchpill input{background:none;border:none;outline:none;color:var(--text);
font:inherit;font-size:12px;width:180px}
.searchpill button{background:var(--accent);color:#fff;border:none;
border-radius:16px;padding:5px 14px;font-weight:600;font-size:12px;cursor:pointer}
.sr-label{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.metaline{color:var(--muted);font-size:12px;margin:14px 0 0}
.changes{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:12px 0}
.sub{color:var(--muted);font-size:11px}
.tag-t{color:var(--gain);font-size:11px}.tag-h{color:var(--loss);font-size:11px}
details{margin:2px 0}summary{cursor:pointer;color:var(--muted);font-size:11px}
.num{text-align:right;padding-right:14px}
@media (max-width:720px){.searchpill input{width:90px}
th:nth-child(5),td:nth-child(5),th:nth-child(6),td:nth-child(6){display:none}}
</style></head><body>
<nav class="topnav"><span class="brand">&#9670; MBE</span>
<a class="navlink" href="#picks">Picks</a>
<a class="navlink" href="#sectors">Sectors</a>
<a class="navlink" href="#policy">News &amp; policy</a>
<form class="searchpill" style="margin-left:auto" action="/api/analyze" method="get">
<label class="sr-label" for="ticker-input">Search any stock</label>
<input id="ticker-input" name="ticker" placeholder="Search any stock&hellip; e.g. RELIANCE.NS" required>
<button type="submit">Analyze</button>
</form>""" + THEME_TOGGLE + """</nav>
<main>
<p class="metaline">Universe: {{ d.universe }} &middot; built {{ d.built_at[:16] }}Z
&middot; quotes delayed ~15 min &middot; themes curated {{ d.curated_as_of }}
&middot; live search is not part of the weekly ranking and can take 10-30s</p>

<div class="changes"><b style="font-size:12px">Changes this week:</b>
{% for t in changes.entered %}<span class="chip gain">+{{ t }}</span>{% endfor %}
{% for t in changes.exited %}<span class="chip loss">-{{ t }}</span>{% endfor %}
{% if not changes.entered and not changes.exited %}<span class="muted small">no changes vs last week</span>{% endif %}
</div>

<h2 class="sec" id="picks">Top {{ d.top | length }} by Multibagger Score</h2>
<div class="card"><table>
<tr><th>#</th><th>Company</th><th>MB</th><th>Inv</th><th>Conf</th><th>Risk</th>
<th>Trend</th><th class="num">Quote</th><th>Industry (mom rank)</th></tr>
{% for r in d.top %}
<tr><td class="muted">{{ loop.index }}</td>
<td><a href="reports/{{ r.ticker.replace('.', '_') }}.html"><b>{{ r.name[:28] }}</b></a><br>
<span class="sub">{{ r.ticker }}{% if r.group %} &middot; {{ r.group[:26] }} (#{{ r.group_rank }}){% endif %}{% if r.gated %} &middot; GATED{% endif %}</span></td>
<td><span class="accent">{{ r.mb }}</span></td>
<td>{{ r.inv }}</td><td>{{ "%.2f" | format(r.conf) }}</td><td>{{ r.risk }}</td>
<td class="sub">{{ r.trend }}</td>
<td class="num"><span data-quote="{{ r.ticker }}" data-base="{{ r.price_at_build or '' }}"
class="muted">&hellip;</span></td>
<td class="sub">{% if r.group %}{{ "%.0f" | format(r.group_score) }}{% else %}ungrouped{% endif %}</td></tr>
{% if r.tags or r.news %}<tr><td></td><td colspan="8">
{% for t in r.tags %}<span class="{{ 'tag-t' if t.direction == 'tailwind' else 'tag-h' }}">{{ '▲' if t.direction == 'tailwind' else '▼' }} {{ t.theme }}</span> &nbsp;{% endfor %}
{% if r.news %}<details><summary>{{ r.news | length }} headline{{ '' if r.news | length == 1 else 's' }}</summary>
{% for n in r.news %}<div class="sub">&middot; <a href="{{ n.link }}">{{ n.title }}</a>
{% if n.source %}({{ n.source }}){% endif %}{% if n.age_days is not none %} <span class="muted">{{ n.age_days }}d ago</span>{% endif %}</div>{% endfor %}</details>{% endif %}
</td></tr>{% endif %}
{% endfor %}</table></div>

<h2 class="sec" id="sectors">Sector momentum
<span class="sub">(descriptive &mdash; failed its ablation as a score input; shown as context)</span></h2>
<div class="card"><table>
<tr><th>#</th><th>Group</th><th>Level</th><th>Score</th><th>N</th></tr>
{% for s in d.sectors[:12] %}
<tr><td class="muted">{{ s.rank }}</td><td>{{ s.name }}</td>
<td class="sub">{{ s.level }}</td>
<td><span class="accent">{{ "%.0f" | format(s.score) }}</span></td>
<td>{{ s.n }}</td></tr>
{% endfor %}</table></div>

{% if d.policy %}<h2 class="sec" id="policy">Government policy &amp; sector news
<span class="sub">(descriptive &mdash; headlines to weigh, not catalysts the engine identified; never scored)</span></h2>
<div class="card" style="padding:10px 14px">
{% for p in d.policy %}<div class="sub" style="padding:3px 0">&middot;
<a href="{{ p.link }}">{{ p.title }}</a>
<span class="muted">{% if p.source %}{{ p.source }}{% endif %}{% if p.source and p.age_days is not none %} &middot; {% endif %}{% if p.age_days is not none %}{{ p.age_days }}d ago{% endif %}</span>
{% for s in p.sectors %}<span class="tag-t">[{{ s }}]</span>{% endfor %}</div>
{% endfor %}</div>{% endif %}

<footer>{{ footer }}<br><span class="small">Rebuilt every Monday by GitHub
Actions. Quotes delayed ~15 min via Yahoo Finance.</span></footer>
</main>
<script>
const spans = document.querySelectorAll('[data-quote]');
const symbols = Array.from(spans).map(s => s.dataset.quote);
fetch('/api/quotes?symbols=' + symbols.join(','))
  .then(r => r.json())
  .then(j => spans.forEach(s => {
    const q = j.quotes[s.dataset.quote];
    if (!q) { s.textContent = 'n/a'; return; }
    const day = q.day_change_pct;
    let l1 = q.price.toFixed(2);
    let cls = 'muted';
    if (typeof day === 'number') {
      l1 += ' ' + (day >= 0 ? '+' : '') + day.toFixed(2) + '%';
      cls = day >= 0 ? 'gain' : 'loss';
    }
    let l2 = '';
    const base = parseFloat(s.dataset.base);
    if (base > 0) {
      const p = (q.price / base - 1) * 100;
      l2 = 'since pick ' + (p >= 0 ? '+' : '') + p.toFixed(1) + '%';
    }
    s.textContent = '';
    const top = document.createElement('span');
    top.className = cls;
    top.textContent = l1;
    s.appendChild(top);
    if (l2) {
      s.appendChild(document.createElement('br'));
      const sub = document.createElement('span');
      sub.className = 'sub';
      sub.textContent = l2;
      s.appendChild(sub);
    }
  }))
  .catch(() => spans.forEach(s => s.textContent = 'n/a'));
</script>
</body></html>""")


def render_site(data: dict, changes: dict, result: ScreenResult, out_dir) -> None:
    out = Path(out_dir)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps({**data, "changes": changes}, indent=1))
    published = {row["ticker"] for row in data["top"]}
    # prune pages for tickers that dropped out: a stale report reachable at a
    # live URL would present last week's analysis as current
    expected = {t.replace(".", "_") + ".html" for t in published}
    for old in (out / "reports").glob("*.html"):
        if old.name not in expected:
            old.unlink()
    for b in result.ranked:
        if b.card.ticker in published:
            page = render_report_page(
                b, policy=[NewsItem(**p) for p in data.get("policy", [])]
            )
            name = b.card.ticker.replace(".", "_") + ".html"
            (out / "reports" / name).write_text(page)
    (out / "index.html").write_text(
        _INDEX.render(d=data, changes=changes, footer=VALIDATION_FOOTER)
    )
