"""Offline tests for the static-site builder (stub bundles, no network)."""

from datetime import datetime, timedelta, timezone

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


def test_build_data_ages_headlines_against_the_build_and_tolerates_undated():
    """The page is read for a week after it is built, so a bare pubDate is
    not enough — the index has to say how old each headline was at build."""
    news = {"S0.NS": [
        NewsItem(title="three days old", link="https://x/1",
                 published=NOW - timedelta(days=3)),
        NewsItem(title="undated", link="https://x/2"),
    ]}
    policy = [NewsItem(title="scheme", link="https://x/3",
                       published=NOW - timedelta(days=1), sectors=["Semiconductors"])]
    data = build_data(_result(), news, policy=policy, built_at=NOW)
    ages = {n["title"]: n["age_days"] for n in data["top"][0]["news"]}
    assert ages == {"three days old": 3, "undated": None}
    assert data["policy"][0]["age_days"] == 1


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


import json

from mbe.publish import VALIDATION_FOOTER, render_site


def test_render_site_writes_index_reports_and_data(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[
        NewsItem(title="Cabinet approves fab incentives", link="https://pib/1",
                 published=NOW - timedelta(days=2), source="Mint",
                 sectors=["Semiconductors"]),
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
    # PIB is no longer the source; the old label attributed Google News
    # aggregation to a government press office
    assert "Government policy (PIB)" not in index
    assert "Mint" in index and "2d ago" in index  # sourced and dated on the page
    # every descriptive layer on this page says so next to itself
    assert "never scored" in index

    saved = json.loads((tmp_path / "data.json").read_text())
    assert saved["changes"] == changes
    # a static report page exists per published pick
    assert (tmp_path / "reports" / "S0_NS.html").exists()
    report = (tmp_path / "reports" / "S0_NS.html").read_text()
    assert "Multibagger" in report
    # render_site rebuilds NewsItems from data.json and threads them into every
    # report page; the section must survive that JSON round-trip
    assert "Recent News &amp; Policy Context" in report


def test_render_site_prunes_dropped_ticker_pages(tmp_path):
    # a report page for a ticker no longer in the top table must not stay
    # live at its old URL presenting stale analysis as current
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "DROPPED_NS.html").write_text("<html>old</html>")
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": ["DROPPED.NS"]}, result, tmp_path)
    assert not (tmp_path / "reports" / "DROPPED_NS.html").exists()
    assert (tmp_path / "reports" / "S0_NS.html").exists()


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


def test_render_site_index_has_search_form(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    index = (tmp_path / "index.html").read_text()
    assert 'action="/api/analyze"' in index
    assert 'name="ticker"' in index


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


def test_report_shell_is_themed():
    page = render_report_page(make_bundle("S0.NS"))
    assert "#1F2022" in page and "#F3F4F6" in page  # both palettes shipped
    assert "mbe-theme" in page  # boot script present
    assert "theme-toggle" in page  # toggle present
    assert 'class="topnav"' in page
    # content contract unchanged (existing tests also enforce this)
    assert "<title>S0.NS</title>" in page and "Multibagger" in page


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


from mbe.publish import render_error_page


def test_render_error_page_is_themed_and_escapes():
    page = render_error_page("<script>x</script>", "Not a valid ticker format.")
    assert "&lt;script&gt;" in page and "<script>x" not in page
    assert "#1F2022" in page and "theme-toggle" in page
    assert 'href="/"' in page
    assert "Not a valid ticker format." in page
