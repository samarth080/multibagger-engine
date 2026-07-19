# Live Search-Any-Stock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A search box on the hosted site that lets a visitor type any ticker and get the full `mbe analyze` report back, live, via a free Vercel serverless function — additive only, the existing weekly-picks pipeline is untouched.

**Architecture:** `api/analyze.py` runs the real `analyze_ticker()` + `render_report()` pipeline per request, bundling `src/mbe/**` via a `sys.path` shim (no package install step) and a new root `requirements.txt` scoped to exactly what that code path needs (pandas, numpy, yfinance, pydantic, jinja2, markdown, defusedxml — not scipy/duckdb/fastapi/typer/rich, confirmed unreachable from this path by grep). The report shell already built for weekly static reports (`src/mbe/publish.py`'s `_REPORT_SHELL`) is extracted into a small public `render_report_page()` wrapper with a parametrized back-link, shared by both the weekly builder and this new function.

**Tech Stack:** Python 3.12, pydantic v2, jinja2, Vercel Python serverless runtime.

**Spec:** `docs/superpowers/specs/2026-07-19-live-search-analyze-design.md`

## File structure

| File | Responsibility |
|---|---|
| Create `requirements.txt` | Root-level, Vercel's Python function dependency list — scoped to the analyze path only |
| Modify `vercel.json` | New `api/analyze.py` entry: `includeFiles` bundling `src/mbe/**`, raised `maxDuration` |
| Modify `src/mbe/publish.py` | Extract `render_report_page(bundle, back_href=...)`; `_REPORT_SHELL`'s back-link becomes a template variable; `render_site()`'s report loop calls the new wrapper instead of inlining |
| Create `api/analyze.py` | Ticker validation, `render_analysis(ticker, provider=None)` pure function, `handler` (Vercel entry point) |
| Modify `src/mbe/publish.py` (`_INDEX` template) | Search form pointing at `/api/analyze` |
| Create `tests/test_analyze_fn.py` | Offline tests via the same importlib file-path loading pattern as `tests/test_quotes_fn.py` |
| Modify `tests/test_publish.py` | Tests for `render_report_page` and the search-form markup |
| Modify `CHANGELOG.md`, `README.md` (Task 5) | v0.11.0 entry, hosted-search section |

Conventions: same house patterns as the weekly-picks build — offline tests with stub providers/fixtures, `feat(publish): …` / `fix(publish): …` commits, honest error pages instead of raw crashes, no silent scope changes.

---

### Task 1: Packaging — requirements.txt + vercel.json

**Files:**
- Create: `requirements.txt`
- Modify: `vercel.json`

No TDD here (pure config) — verified by JSON/text validation and, at Task 6, a real deploy.

- [ ] **Step 1: Create `requirements.txt`** at the repo root:

```
pandas>=2.2
numpy>=1.26
yfinance>=0.2.50
pydantic>=2.7
jinja2>=3.1
markdown>=3.10.2
defusedxml>=0.7.1
```

(Version floors mirror `pyproject.toml`. Deliberately excludes `scipy`, `duckdb`, `pyarrow`, `fastapi`, `uvicorn`, `typer`, `rich`, `lxml` — confirmed by grepping every import reachable from `analyze_ticker`/`render_report`/`render_report_page` that none of those are needed; `defusedxml` is required transitively because `mbe.publish` imports `mbe.data.news_rss`, which imports `defusedxml`, even though the analyze path never calls a news function.)

- [ ] **Step 2: Update `vercel.json`** — add the `api/analyze.py` function entry alongside the existing `api/quotes.py` one:

```json
{
  "buildCommand": "",
  "outputDirectory": "site",
  "functions": {
    "api/quotes.py": { "includeFiles": "site/data.json" },
    "api/analyze.py": { "includeFiles": "src/mbe/**", "maxDuration": 60 }
  }
}
```

(If your Vercel plan rejects `maxDuration: 60`, lower it to the highest value it accepts — commonly 10-30s on some Hobby tiers — and redeploy; this is a real, stated unknown resolved at Task 6's live deploy, same as the weekly build's Yahoo-rate-limit unknown was.)

- [ ] **Step 3: Validate**

Run: `uv run python -c "import json; json.load(open('vercel.json')); print('vercel.json ok')"`
Expected: `vercel.json ok`.
Run: `wc -l requirements.txt`
Expected: `7 requirements.txt`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt vercel.json
git commit -m "feat(publish): package the analyze function's dependencies (scoped, not the full project)"
```

---

### Task 2: Shared report shell — `render_report_page()`

**Files:**
- Modify: `src/mbe/publish.py`
- Test: `tests/test_publish.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_publish.py`:

```python
from mbe.publish import render_report_page


def test_render_report_page_default_back_link():
    bundle = make_bundle("S0.NS")
    page = render_report_page(bundle)
    assert 'href="../index.html"' in page
    assert "Multibagger" in page
    assert "<title>S0.NS</title>" in page


def test_render_report_page_custom_back_link():
    bundle = make_bundle("S0.NS")
    page = render_report_page(bundle, back_href="/")
    assert 'href="/"' in page
    assert 'href="../index.html"' not in page
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_publish.py -v -k render_report_page`
Expected: FAIL with `ImportError: cannot import name 'render_report_page'`.

- [ ] **Step 3: Implement**

In `src/mbe/publish.py`, change the `_REPORT_SHELL` template's back-link line from:

```
<p><a href="../index.html">&larr; back to rankings</a></p>
```

to:

```
<p><a href="{{ back_href }}">&larr; back to rankings</a></p>
```

Then add a new public function directly after the `_REPORT_SHELL` template definition (before `_INDEX`):

```python
def render_report_page(bundle: AnalysisBundle, back_href: str = "../index.html") -> str:
    """Wrap one AnalysisBundle's markdown report in the shared dark shell.
    Used by render_site() for weekly static reports and by api/analyze.py
    for live single-ticker search — one shell, one back-link parameter."""
    body = md.markdown(render_report(bundle), extensions=["tables"])
    return _REPORT_SHELL.render(title=bundle.card.ticker, body=body, back_href=back_href)
```

Add `AnalysisBundle` to the existing pipeline import line:

```python
from mbe.pipeline import AnalysisBundle, ScreenResult
```

Then replace `render_site()`'s inline report-rendering lines:

```python
            body = md.markdown(render_report(b), extensions=["tables"])
            page = _REPORT_SHELL.render(title=b.card.ticker, body=body)
            name = b.card.ticker.replace(".", "_") + ".html"
```

with:

```python
            page = render_report_page(b)
            name = b.card.ticker.replace(".", "_") + ".html"
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_publish.py -v`
Expected: PASS (8 tests: 6 existing + 2 new). Full suite `uv run pytest` — expect 190 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/publish.py tests/test_publish.py
git commit -m "refactor(publish): extract render_report_page — shared shell for weekly and live-search reports"
```

---

### Task 3: `api/analyze.py` — live single-ticker analysis

**Files:**
- Create: `api/analyze.py`
- Test: `tests/test_analyze_fn.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_analyze_fn.py`:

```python
"""Offline tests for the live search-analyze Vercel function (loaded from
file path — api/ sits outside the mbe package)."""

import importlib.util
from pathlib import Path

from tests.test_pipeline import StubProvider

spec = importlib.util.spec_from_file_location(
    "analyze_fn", Path(__file__).parent.parent / "api" / "analyze.py"
)
analyze_fn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze_fn)


def test_render_analysis_empty_ticker_is_400():
    status, html = analyze_fn.render_analysis("", provider=StubProvider())
    assert status == 400
    assert "No ticker given" in html


def test_render_analysis_rejects_bad_format():
    status, html = analyze_fn.render_analysis(
        "../etc/passwd", provider=StubProvider()
    )
    assert status == 400
    assert "valid ticker format" in html


def test_render_analysis_provider_error_is_404():
    status, html = analyze_fn.render_analysis(
        "BAD.NS", provider=StubProvider(bad={"BAD.NS"})
    )
    assert status == 404
    assert "BAD.NS" in html
    assert "boom BAD.NS" in html


def test_render_analysis_success_renders_report():
    status, html = analyze_fn.render_analysis("GOOD.NS", provider=StubProvider())
    assert status == 200
    assert "GOOD.NS" in html
    assert "Multibagger" in html
    assert 'href="/"' in html  # back-link points at the search page, not ../index.html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_analyze_fn.py -v`
Expected: FAIL — `FileNotFoundError` (`api/analyze.py` doesn't exist).

- [ ] **Step 3: Implement**

Create `api/analyze.py`:

```python
"""Vercel serverless function: live full-report analysis for any ticker.

Unlike api/quotes.py, this needs the real analysis engine (pandas, numpy,
yfinance, pydantic) — see /requirements.txt. It bundles src/mbe/** (see
vercel.json includeFiles) and imports it via a sys.path shim rather than a
package-install step.

No caching at all — YahooProvider(cache=None). DiskCache.set_df() writes
parquet, which needs a parquet engine (pyarrow/fastparquet) that isn't in
the deliberately minimal requirements.txt; adding one just for a
best-effort, warm-instance-only cache isn't worth the extra deployment
weight, so every search is a fresh Yahoo fetch. No prediction-ledger
persistence either (that needs a real database, which stateless serverless
doesn't have) — this is an honest one-shot report: full thesis, critique,
evidence, same validation footer as everywhere else, just no history.
"""

import re
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mbe.data.provider import ProviderError  # noqa: E402
from mbe.data.yahoo import YahooProvider  # noqa: E402
from mbe.pipeline import analyze_ticker  # noqa: E402
from mbe.publish import render_report_page  # noqa: E402

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,15}$")

_ERROR_PAGE = """<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Analyze - error</title>
<style>
body{{background:#0d1220;color:#d7dce6;font-family:ui-monospace,Menlo,monospace;
max-width:700px;margin:60px auto;padding:0 16px;line-height:1.6}}
a{{color:#e3b34c}} h1{{color:#e0605e}}
</style></head><body>
<p><a href="/">&larr; back to rankings</a></p>
<h1>Could not analyze &quot;{ticker}&quot;</h1>
<p>{reason}</p>
</body></html>"""


def _default_provider():
    return YahooProvider(cache=None)


def render_analysis(ticker: str, provider=None) -> tuple[int, str]:
    """Returns (http_status, html). Pure function, no request/response
    coupling — directly unit-testable with a stub provider."""
    if not ticker:
        return 400, _ERROR_PAGE.format(
            ticker="", reason="No ticker given &mdash; try ?ticker=RELIANCE.NS"
        )
    if not _TICKER_RE.match(ticker):
        return 400, _ERROR_PAGE.format(
            ticker=ticker, reason="Not a valid ticker format."
        )
    if provider is None:
        provider = _default_provider()
    try:
        bundle = analyze_ticker(ticker, provider)
    except ProviderError as exc:
        return 404, _ERROR_PAGE.format(ticker=ticker, reason=str(exc))
    except Exception as exc:  # honest error page, never a raw 500 blob
        return 500, _ERROR_PAGE.format(
            ticker=ticker, reason=f"Unexpected error: {exc!r}"
        )
    return 200, render_report_page(bundle, back_href="/")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        ticker = qs.get("ticker", [""])[0].strip()
        status, html = render_analysis(ticker)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_analyze_fn.py -v`
Expected: 4 PASS. Full suite `uv run pytest` — expect 194 passed.

- [ ] **Step 5: Commit**

```bash
git add api/analyze.py tests/test_analyze_fn.py
git commit -m "feat(publish): live search-any-stock serverless analyze function"
```

---

### Task 4: Search form on the hosted page

**Files:**
- Modify: `src/mbe/publish.py` (`_INDEX` template)
- Test: `tests/test_publish.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_publish.py` (pytest's `tmp_path` fixture is already used elsewhere in this file — no new import needed):

```python
def test_render_site_index_has_search_form(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    index = (tmp_path / "index.html").read_text()
    assert 'action="/api/analyze"' in index
    assert 'name="ticker"' in index
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_publish.py -v -k search_form`
Expected: FAIL — `assert 'action="/api/analyze"' in index` is False (form doesn't exist yet).

- [ ] **Step 3: Implement**

In `src/mbe/publish.py`'s `_INDEX` template string, add to the `<style>` block (after the existing `.tag-t{color:#5dd39e}.tag-h{color:#e0605e}` line):

```
.search{background:#161d33;border:1px solid #2a3350;border-radius:8px;padding:10px 14px;margin:14px 0}
.search input{background:#0d1220;color:#d7dce6;border:1px solid #2a3350;border-radius:6px;padding:6px 10px;font-family:inherit}
.search button{background:#e3b34c;color:#0d1220;border:none;border-radius:6px;padding:6px 14px;font-weight:700;cursor:pointer;font-family:inherit}
```

Then insert this block right after the `<p class="muted">Universe: ...</p>` line and before the `<div class="chg">` changes strip:

```html
<div class="search"><form action="/api/analyze" method="get">
<b>Search any stock:</b>
<input name="ticker" placeholder="e.g. RELIANCE.NS or AAPL" required>
<button type="submit">Analyze</button>
<span class="muted">&mdash; live, not part of the weekly ranking, can take 10-30s</span>
</form></div>
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_publish.py -v`
Expected: PASS (9 tests). Full suite `uv run pytest` — expect 195 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mbe/publish.py tests/test_publish.py
git commit -m "feat(publish): search-any-stock form on the hosted index page"
```

---

### Task 5: Docs — CHANGELOG, README

**Files:**
- Modify: `CHANGELOG.md` (append `## v0.11.0 — <today>` at the end)
- Modify: `README.md`

- [ ] **Step 1: CHANGELOG** — Added: live search-any-stock serverless function (`api/analyze.py`), shared `render_report_page()` report shell (weekly + live search), search form on the hosted index page, scoped `requirements.txt`. Note explicitly: no prediction-ledger persistence in the hosted live-search path (stateless serverless has no database) — an honest one-shot report, not a regression.

- [ ] **Step 2: README** — extend the `## Hosted weekly picks (v0.10)` section (or add a short `## Live search (v0.11)` subsection right after it): what it does (type any ticker, get the full live report), the honest limitations (no cross-request cache, no history/ledger, cold starts may be slow — first live search will tell us how slow), and that it's fully additive to the weekly picks page.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md README.md
git commit -m "docs(publish): v0.11.0 changelog + README live-search section"
```

---

### Task 6: Full suite + deploy + first live search (with the user)

No new files — this is the go-live sequence.

- [ ] **Step 1: Full offline suite**

Run: `uv run pytest`
Expected: 195 passed.

- [ ] **Step 2: Push to the already-connected GitHub repo**

```bash
git push origin main
```

Vercel's git integration picks up the push automatically (already connected from the weekly-picks deploy) and builds using the new `requirements.txt` + `vercel.json` function entries.

- [ ] **Step 3: Watch the Vercel deploy log** for the `requirements.txt` install step — this is where the untested-in-practice risk lives (package size, install time). If it fails or times out, the fallback documented in the spec is the persistent-host pivot; report back with the exact Vercel error rather than guessing at a fix.

- [ ] **Step 4: First live search** — open `https://<your-vercel-domain>/` and search a real ticker (e.g. `RELIANCE.NS`). Note the response time (cold start vs. a second search on the same still-warm instance). Confirm: the report renders correctly, the back-link returns to `/`, an invalid ticker (e.g. `xyz123notreal`) shows the clean error page rather than a raw error, and a real-but-unlisted ticker shows the 404 error page with a readable reason.

- [ ] **Step 5: Record the outcome** — this is the moment the spec's stated cold-start/timeout risk resolves one way or the other, same discipline as the weekly build's Yahoo-rate-limit unknown. Note the result (comfortable / borderline / broken) so the fallback decision, if needed, is informed rather than guessed.
