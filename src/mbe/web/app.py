"""Local research terminal: browse stored runs, open reports, track history.

Server-rendered, zero build step. Design: ink-navy terminal surface, IBM Plex
Mono for data, one marigold accent; every score renders as an instrument-panel
meter (the signature element). Status is never conveyed by color alone.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import markdown as md_lib
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment
from markupsafe import Markup

from mbe.data.provider import DataProvider, ProviderError
from mbe.pipeline import analyze_ticker
from mbe.report.markdown import render_report
from mbe.storage import RunStore

_CSS = """
:root{
  --bg:#0E1520; --panel:#151E2B; --line:#243140;
  --ink:#D8E1EA; --muted:#7A8899;
  --accent:#E8A33D; --good:#3FA97C; --bad:#C4554D;
}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);
  font:15px/1.55 "IBM Plex Sans",system-ui,-apple-system,sans-serif;
  padding:0 0 4rem}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
a:focus-visible,button:focus-visible,input:focus-visible{
  outline:2px solid var(--accent);outline-offset:2px}
code,.mono,table.data{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
header{border-bottom:1px solid var(--line);padding:1.1rem 2rem;
  display:flex;gap:1rem;align-items:baseline;flex-wrap:wrap}
header h1{font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:1.05rem;font-weight:600;letter-spacing:.14em}
header h1 a{color:var(--ink)}
header .tag{color:var(--muted);font-size:.8rem}
main{max-width:1080px;margin:1.6rem auto;padding:0 2rem}
h2{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.8rem;
  font-weight:600;letter-spacing:.18em;text-transform:uppercase;
  color:var(--muted);margin:2rem 0 .8rem}
.panel{background:var(--panel);border:1px solid var(--line);
  border-radius:6px;padding:1rem 1.2rem;margin-bottom:1.2rem}
table.data{width:100%;border-collapse:collapse;font-size:.82rem}
table.data th{color:var(--muted);text-align:left;font-weight:500;
  padding:.45rem .6rem;border-bottom:1px solid var(--line);white-space:nowrap}
table.data td{padding:.45rem .6rem;border-bottom:1px solid var(--line);
  white-space:nowrap;vertical-align:middle}
table.data tr:last-child td{border-bottom:none}
.meter{display:inline-block;width:96px;height:6px;background:var(--line);
  border-radius:3px;vertical-align:middle;margin-right:.5rem}
.meter i{display:block;height:100%;border-radius:3px;background:var(--accent)}
.num{display:inline-block;min-width:2.6em;text-align:right}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;
  vertical-align:middle;margin-right:.4rem}
.dot.low{background:var(--good)} .dot.medium{background:var(--accent)}
.dot.high{background:var(--bad)} .dot.unknown{background:var(--muted)}
form.analyze{display:flex;gap:.6rem}
form.analyze input{flex:1;background:var(--bg);border:1px solid var(--line);
  border-radius:4px;color:var(--ink);padding:.5rem .7rem;
  font-family:"IBM Plex Mono",monospace}
form.analyze button{background:var(--accent);color:#0E1520;border:none;
  border-radius:4px;padding:.5rem 1rem;font-weight:600;cursor:pointer}
.muted{color:var(--muted)} .small{font-size:.8rem}
/* rendered markdown reports */
article.report{background:var(--panel);border:1px solid var(--line);
  border-radius:6px;padding:2rem 2.4rem;overflow-x:auto}
article.report h1{font-size:1.3rem;margin-bottom:.6rem}
article.report h2{font-size:.85rem;color:var(--accent);margin:1.8rem 0 .7rem}
article.report h3{font-size:.85rem;margin:1.2rem 0 .5rem}
article.report p,article.report li{margin:.4rem 0;font-size:.9rem}
article.report table{border-collapse:collapse;font-size:.8rem;margin:.6rem 0;
  font-family:"IBM Plex Mono",ui-monospace,monospace}
article.report th,article.report td{border:1px solid var(--line);
  padding:.35rem .6rem;text-align:left}
article.report strong{color:var(--accent)}
@media(max-width:720px){main{padding:0 1rem}header{padding:1rem}}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

_ENV = Environment(autoescape=True)

_BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} — Multibagger Engine</title><style>""" + _CSS + """</style></head>
<body><header><h1><a href="/">MULTIBAGGER&nbsp;ENGINE</a></h1>
<span class="tag">evidence-driven equity research · local terminal</span></header>
<main>{{ body }}</main></body></html>"""

_HOME = _ENV.from_string("""
<div class="panel">
  <form class="analyze" method="get" action="/analyze">
    <input name="ticker" placeholder="Analyze a ticker, e.g. RELIANCE.NS" required
           aria-label="Ticker symbol">
    <button type="submit">Analyze</button>
  </form>
  <p class="muted small" style="margin-top:.5rem">Runs the full pipeline (fundamentals,
  technicals, valuation, risk, scoring) and opens the research report. First run
  on a ticker fetches live data.</p>
</div>

<h2>Stored screening runs</h2>
{% if runs %}
<div class="panel"><table class="data">
<tr><th>As of</th><th>Universe</th><th>Tickers</th><th>Run</th></tr>
{% for r in runs %}
<tr><td>{{ r.as_of }}</td><td>{{ r.universe }}</td><td>{{ r.n_results }}</td>
<td><a href="/run/{{ r.run_id }}">open ranking →</a></td></tr>
{% endfor %}
</table></div>
{% else %}
<div class="panel"><p class="muted">No runs stored yet. Run
<code>uv run mbe snapshot india-midsmall</code> in a terminal, then refresh.</p></div>
{% endif %}

<h2>Backtest evidence</h2>
{% if backtests %}
<div class="panel"><table class="data">
<tr><th>When</th><th>Universe</th><th>Score</th><th>Horizon</th><th>Mean IC</th></tr>
{% for b in backtests %}
<tr><td>{{ b.created_at.strftime("%Y-%m-%d %H:%M") }}</td><td>{{ b.universe }}</td>
<td>{{ b.score_name }}</td><td>{{ b.horizon_days }}d</td>
<td class="mono">{{ "%.3f"|format(b.mean_ic) }}</td></tr>
{% endfor %}
</table>
<p class="muted small" style="margin-top:.5rem">IC = Spearman rank correlation between
score and forward return. Near zero = no demonstrated edge at that horizon/sample.</p></div>
{% else %}
<div class="panel"><p class="muted">No backtests yet. Run
<code>uv run mbe backtest nifty-midcap150 --limit 60</code>.</p></div>
{% endif %}
""")

_RUN = _ENV.from_string("""
<p class="small"><a href="/">← runs</a></p>
<h2>{{ universe }} · {{ as_of }} · ranked by Multibagger Score</h2>
<div class="panel"><table class="data">
<tr><th>#</th><th>Ticker</th><th>Multibagger</th><th>Investment</th>
<th>Conf</th><th>Risk</th><th>Trend</th><th>Report</th></tr>
{% for r in rows %}
<tr>
<td class="muted">{{ loop.index }}</td>
<td><a href="/history/{{ r.ticker }}">{{ r.ticker }}</a></td>
<td><span class="meter" role="img"
     aria-label="Multibagger score {{ r.multibagger }} of 100"><i
     style="width:{{ r.multibagger }}%"></i></span><span class="num">{{ r.multibagger }}</span></td>
<td><span class="meter" role="img"
     aria-label="Investment score {{ r.investment }} of 100"><i
     style="width:{{ r.investment }}%"></i></span><span class="num">{{ r.investment }}</span></td>
<td class="mono">{{ "%.2f"|format(r.confidence) }}</td>
<td class="mono">{{ r.risk_score|int }}</td>
<td class="muted">{{ r.trend_state }}</td>
<td><a href="/report/{{ r.ticker }}">open →</a></td>
</tr>
{% endfor %}
</table></div>
""")

_HISTORY = _ENV.from_string("""
<p class="small"><a href="/">← runs</a></p>
<h2>{{ ticker }} · score history</h2>
<div class="panel"><table class="data">
<tr><th>As of</th><th>Universe</th><th>Multibagger</th><th>Investment</th>
<th>Conf</th><th>Risk</th><th>Trend</th><th>Verdict</th></tr>
{% for r in rows %}
<tr><td>{{ r.as_of }}</td><td>{{ r.universe }}</td>
<td><span class="meter" role="img"
     aria-label="Multibagger score {{ r.multibagger }} of 100"><i
     style="width:{{ r.multibagger }}%"></i></span><span class="num">{{ r.multibagger }}</span></td>
<td class="mono">{{ r.investment }}</td>
<td class="mono">{{ "%.2f"|format(r.confidence) }}</td>
<td class="mono">{{ r.risk_score|int }}</td>
<td class="muted">{{ r.trend_state }}</td>
<td class="small">{{ r.verdict[:60] }}</td></tr>
{% endfor %}
</table></div>
<p class="small"><a href="/report/{{ ticker }}">Open full research report →</a></p>
""")


def _page(title: str, body_html: str, status_code: int = 200) -> HTMLResponse:
    # body_html is trusted output of our own autoescaped templates
    html = _ENV.from_string(_BASE).render(title=title, body=Markup(body_html))
    return HTMLResponse(html, status_code=status_code)


def _clean_ticker(raw: str) -> str:
    """Keep only characters that occur in real symbols (letters, digits,
    '.', '-', '^', '&'). Strips stray backslashes/whitespace from user input."""
    return re.sub(r"[^A-Za-z0-9.\-^&]", "", raw).upper()


def _error_page(title: str, message: str, status_code: int) -> HTMLResponse:
    body = (
        '<p class="small"><a href="/">← back to terminal</a></p>'
        f'<div class="panel"><h2 style="margin-top:0">{_ENV.from_string("{{ t }}").render(t=title)}</h2>'
        f"<p>{_ENV.from_string('{{ m }}').render(m=message)}</p>"
        '<p class="muted small">Check the symbol (Indian listings need the .NS suffix, '
        "e.g. TCS.NS) and try again from the analyze box.</p></div>"
    )
    return _page(title, body, status_code=status_code)


def create_app(
    provider: DataProvider,
    store: RunStore,
    reports_dir: str | Path = "reports",
) -> FastAPI:
    app = FastAPI(title="Multibagger Engine", docs_url=None, redoc_url=None)
    reports_dir = Path(reports_dir)

    @app.get("/", response_class=HTMLResponse)
    def home():
        body = _HOME.render(runs=store.runs(), backtests=store.backtests())
        return _page("Terminal", body)

    @app.get("/run/{run_id}", response_class=HTMLResponse)
    def run_view(run_id: str):
        rows = store.run_results(run_id)
        if not rows:
            raise HTTPException(404, f"no stored run {run_id}")
        meta = next((r for r in store.runs() if r["run_id"] == run_id), {})
        body = _RUN.render(
            rows=rows,
            universe=meta.get("universe", "?"),
            as_of=meta.get("as_of", ""),
        )
        return _page("Ranking", body)

    @app.get("/history/{ticker}", response_class=HTMLResponse)
    def history_view(ticker: str):
        rows = store.history(ticker)
        if not rows:
            # no stored history yet — still offer the report link
            rows = []
        body = _HISTORY.render(ticker=ticker, rows=rows)
        return _page(ticker, body)

    @app.get("/analyze")
    def analyze_redirect(ticker: str):
        return RedirectResponse(f"/report/{_clean_ticker(ticker)}")

    @app.get("/report/{ticker}", response_class=HTMLResponse)
    def report_view(ticker: str):
        ticker = _clean_ticker(ticker)
        if not ticker:
            return _error_page("Invalid symbol", "That input contained no usable ticker symbol.", 404)
        try:
            bundle = analyze_ticker(ticker, provider)
        except ProviderError as exc:
            return _error_page(
                f"Could not analyze {ticker}",
                f"The data source returned nothing usable: {exc}",
                404,
            )
        reports_dir.mkdir(parents=True, exist_ok=True)
        md_text = render_report(bundle)
        (reports_dir / f"{ticker.replace('.', '_')}_{date.today()}.md").write_text(md_text)
        report_html = md_lib.markdown(md_text, extensions=["tables"])
        body = f'<p class="small"><a href="/">← runs</a></p><article class="report">{report_html}</article>'
        return _page(ticker, body)

    return app
