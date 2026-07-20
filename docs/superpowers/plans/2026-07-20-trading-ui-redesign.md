# Trading-Platform UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle every rendered surface (index, report pages, analyze error pages) to Zerodha-dark-default / Groww-light-toggle using the user's exact palette tokens — pure template/CSS work, zero pipeline changes.

**Architecture:** One theme foundation in `src/mbe/publish.py` (CSS custom properties for both palettes, a pre-paint localStorage boot script, a shared toggle button snippet) consumed by all three templates. The analyze error page migrates from a `str.format` template in `api/analyze.py` to a jinja-autoescaped `render_error_page()` in `publish.py` — one rendering module, one escaping mechanism, themed for free.

**Tech Stack:** Jinja2 (already a dep), hand-rolled CSS custom properties (deliberately no Tailwind — no build step exists and none is added), vanilla JS for theme persistence + quotes.

**Spec:** `docs/superpowers/specs/2026-07-20-trading-ui-redesign-design.md`

## File structure

| File | Responsibility |
|---|---|
| Modify `src/mbe/publish.py` | `THEME_BOOT` + `THEME_CSS` + `THEME_TOGGLE` constants; rewritten `_REPORT_SHELL` and `_INDEX`; new `render_error_page()` |
| Modify `api/analyze.py` | Error path calls `render_error_page()`; `_ERROR_PAGE`/`html.escape` removed (jinja autoescape takes over) |
| Modify `tests/test_publish.py`, `tests/test_analyze_fn.py` | New theme/tokens/toggle assertions; existing content-wiring tests must pass unchanged |
| Rebuild `site/` (Task 5) | Regenerated with the new look before deploy |
| Modify `CHANGELOG.md`, `README.md` (Task 6) | v0.12.0 entry |

Execution notes: work on a feature branch `ui-redesign`. Existing tests pin the content contract (form action, footer wording, changes chips, report title) — they are the regression net; do not weaken any existing assertion.

---

### Task 1: Theme foundation — tokens, boot script, toggle

**Files:**
- Modify: `src/mbe/publish.py`
- Test: `tests/test_publish.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_publish.py`:

```python
from mbe.publish import THEME_BOOT, THEME_CSS, THEME_TOGGLE


def test_theme_css_carries_both_palettes():
    # dark defaults on :root, light overrides under [data-theme="light"]
    assert ":root" in THEME_CSS and '[data-theme="light"]' in THEME_CSS
    for token in ("#1F2022", "#38A6F0", "#4CAF50", "#F44336"):
        assert token in THEME_CSS  # Zerodha-dark set
    for token in ("#F3F4F6", "#5076EE", "#039955", "#D32F2F", "#DDE4F0", "#2D343C"):
        assert token in THEME_CSS  # Groww-light set


def test_theme_boot_applies_saved_theme_before_paint():
    assert "localStorage.getItem" in THEME_BOOT
    assert "mbe-theme" in THEME_BOOT
    assert "data-theme" in THEME_BOOT


def test_theme_toggle_persists_choice():
    assert "localStorage.setItem" in THEME_TOGGLE
    assert "theme-toggle" in THEME_TOGGLE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_publish.py -v -k theme`
Expected: FAIL with `ImportError: cannot import name 'THEME_BOOT'`.

- [ ] **Step 3: Implement**

In `src/mbe/publish.py`, add directly after the `VALIDATION_FOOTER` constant:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_publish.py -v`
Expected: PASS (11 tests: 8 existing + 3 new). Full suite `uv run pytest` — expect 201 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/publish.py tests/test_publish.py
git commit -m "feat(ui): theme foundation — dual-palette tokens, pre-paint boot, persistent toggle"
```

---

### Task 2: Report shell redesign

**Files:**
- Modify: `src/mbe/publish.py` (replace `_REPORT_SHELL`)
- Test: `tests/test_publish.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_publish.py`:

```python
def test_report_shell_is_themed():
    page = render_report_page(make_bundle("S0.NS"))
    assert "#1F2022" in page and "#F3F4F6" in page  # both palettes shipped
    assert "mbe-theme" in page  # boot script present
    assert "theme-toggle" in page  # toggle present
    assert 'class="topnav"' in page
    # content contract unchanged (existing tests also enforce this)
    assert "<title>S0.NS</title>" in page and "Multibagger" in page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish.py -v -k shell_is_themed`
Expected: FAIL — `assert "#1F2022" in page` (old shell has the old colors).

- [ ] **Step 3: Implement**

In `src/mbe/publish.py`, replace the entire `_REPORT_SHELL = _ENV.from_string(...)` definition with:

```python
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
```

(Jinja treats single braces in CSS as literal text — only `{{ }}`/`{% %}` are special, so embedding `THEME_CSS` is safe. The old `.format`-based error page could not do this; that's part of why Task 4 migrates it.)

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_publish.py tests/test_analyze_fn.py -v`
Expected: PASS — including the pre-existing back-link tests (`href="../index.html"` default, `href="/"` custom) and analyze-function tests (success path uses this shell). Full suite: 202 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/publish.py tests/test_publish.py
git commit -m "feat(ui): themed report shell — topnav, carded markdown, dual palette"
```

---

### Task 3: Index page redesign + trading-style quotes

**Files:**
- Modify: `src/mbe/publish.py` (replace `_INDEX`)
- Test: `tests/test_publish.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_publish.py`:

```python
def test_index_is_themed_with_nav_and_daychange_quotes(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    index = (tmp_path / "index.html").read_text()
    assert "#1F2022" in index and "#F3F4F6" in index
    assert "mbe-theme" in index and "theme-toggle" in index
    assert "topnav" in index
    assert "day_change_pct" in index  # quotes JS renders LTP + day change
    assert "since pick" in index      # honest since-pick line kept
    # anchor tabs for the sections
    assert 'href="#picks"' in index and 'href="#sectors"' in index
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish.py -v -k daychange`
Expected: FAIL — `assert "#1F2022" in index`.

- [ ] **Step 3: Implement**

In `src/mbe/publish.py`, replace the entire `_INDEX = _ENV.from_string(...)` definition with:

```python
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
<a class="navlink" href="#policy">Policy</a>
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
{% if r.news %}<details><summary>{{ r.news | length }} headlines</summary>
{% for n in r.news %}<div class="sub">&middot; <a href="{{ n.link }}">{{ n.title }}</a>
{% if n.source %}({{ n.source }}){% endif %}</div>{% endfor %}</details>{% endif %}
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

{% if d.policy %}<h2 class="sec" id="policy">Government policy (PIB)</h2>
<div class="card" style="padding:10px 14px">
{% for p in d.policy %}<div class="sub" style="padding:3px 0">&middot;
<a href="{{ p.link }}">{{ p.title }}</a>
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
```

(The quotes JS deliberately uses `textContent`/`createElement`, never
`innerHTML` — the values are self-computed numbers today, but structural
safety costs five lines and survives future edits. `day_change_pct` comes
from the existing `/api/quotes` response unchanged.)

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_publish.py -v`
Expected: PASS — including every pre-existing content assertion (`+S0.NS` chip, `-Z.NS` chip, footer text, `action="/api/analyze"`, `name="ticker"`, "Cabinet approves fab incentives", "delayed"). Full suite: 203 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/publish.py tests/test_publish.py
git commit -m "feat(ui): trading-style index — sticky nav, carded tables, LTP+day% quotes"
```

---

### Task 4: Themed error page — migrate to jinja autoescape

**Files:**
- Modify: `src/mbe/publish.py` (add `render_error_page`)
- Modify: `api/analyze.py` (use it; delete `_ERROR_PAGE` and the manual `html.escape` calls)
- Test: `tests/test_publish.py` + existing `tests/test_analyze_fn.py` must pass unchanged

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_publish.py`:

```python
from mbe.publish import render_error_page


def test_render_error_page_is_themed_and_escapes():
    page = render_error_page("<script>x</script>", "Not a valid ticker format.")
    assert "&lt;script&gt;" in page and "<script>x" not in page
    assert "#1F2022" in page and "theme-toggle" in page
    assert 'href="/"' in page
    assert "Not a valid ticker format." in page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish.py -v -k error_page`
Expected: FAIL with `ImportError: cannot import name 'render_error_page'`.

- [ ] **Step 3: Implement**

In `src/mbe/publish.py`, add after `render_report_page`:

```python
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
```

In `api/analyze.py`:
1. Delete the entire `_ERROR_PAGE = """..."""` constant.
2. Delete `import html`.
3. Add `render_error_page` to the publish import line:
   `from mbe.publish import render_error_page, render_report_page  # noqa: E402`
4. Replace `render_analysis`'s body branches so every error path calls
   `render_error_page` with RAW strings (autoescape does the escaping):

```python
def render_analysis(ticker: str, provider=None) -> tuple[int, str]:
    """Returns (http_status, html). Pure function, no request/response
    coupling — directly unit-testable with a stub provider.

    Error pages render via publish.render_error_page (jinja, autoescape on):
    ticker/reason are passed RAW and escaped by the template engine.
    _TICKER_RE only constrains a VALID ticker — the 400 branch is reached
    exactly when it does NOT match, so the rejected raw string still flows
    into the page and must never be trusted as pre-sanitized."""
    if not ticker:
        return 400, render_error_page(
            "", "No ticker given — try ?ticker=RELIANCE.NS"
        )
    if not _TICKER_RE.match(ticker):
        return 400, render_error_page(ticker, "Not a valid ticker format.")
    if provider is None:
        provider = _default_provider()
    try:
        bundle = analyze_ticker(ticker, provider)
    except ProviderError as exc:
        return 404, render_error_page(ticker, str(exc))
    except Exception as exc:  # honest error page; real detail stays server-side
        print(f"analyze_ticker unexpected error for {ticker!r}: {exc!r}")
        return 500, render_error_page(
            ticker, "Unexpected error analyzing this ticker."
        )
    return 200, render_report_page(bundle, back_href="/")
```

- [ ] **Step 4: Run tests — the existing analyze security tests are the gate**

Run: `uv run pytest tests/test_analyze_fn.py tests/test_publish.py -v`
Expected: ALL PASS **unchanged** — especially `test_render_analysis_escapes_ticker_in_bad_format_error` (jinja autoescape now produces the `&lt;script&gt;`) and `test_render_analysis_500_never_reflects_exception_repr`. If any existing assertion fails, STOP and report — do not adjust the security tests. Full suite: 204 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/publish.py api/analyze.py tests/test_publish.py
git commit -m "feat(ui): themed error page via jinja autoescape — one rendering module, one escaping mechanism"
```

---

### Task 5: Rebuild site + visual check (controller + user)

- [ ] **Step 1:** `uv run pytest` — full suite green (204).
- [ ] **Step 2:** `uv run python scripts/build_site.py` — rebuild `site/` with the new templates (network; cache warm).
- [ ] **Step 3:** Copy the rebuilt page into the brainstorm companion for the user to see before deploy: `cp site/index.html <screen_dir>/redesign-preview.html` (full-document HTML is served as-is; quotes show "n/a" locally since `/api/quotes` isn't running — expected). Also copy one report page: `cp site/reports/BLS_NS.html <screen_dir>/redesign-report-preview.html` (note: its relative back-link won't resolve in the companion — visual check only). User reviews both, requests tweaks; iterate template + rebuild until approved.
- [ ] **Step 4:** Commit the rebuilt site: `git add site/ && git commit -m "chore(publish): site rebuild with trading-platform UI"`.

### Task 6: Docs + deploy

- [ ] **Step 1:** `CHANGELOG.md` — append `## v0.12.0 — 2026-07-20`: Added (trading-platform UI: Zerodha-dark default + Groww-light toggle with user-specified tokens, sticky nav with in-nav search, carded tables, LTP+day-change quotes with since-pick line kept, themed report + error pages); Changed (analyze error page migrated from str.format to jinja-autoescaped render_error_page — escaping now structural rather than call-site).
- [ ] **Step 2:** `README.md` — update the hosted-picks section's one-line description to mention the dual-theme trading-style UI.
- [ ] **Step 3:** Merge `ui-redesign` → main (ff), push, watch Vercel deploy, verify live: theme toggle works and persists across reloads, quotes populate with day %, report pages and an invalid-ticker error page render themed.
- [ ] **Step 4:** Commit docs with the merge; no Claude co-author trailers (repo-wide rule).
