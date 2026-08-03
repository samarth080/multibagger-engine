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
    assert data["schema_version"] == "1.1"
    assert top0["instrument_id"] and top0["rank"] == 1
    assert "components" in top0 and "main_positive_signal" in top0
    assert len(data["instruments"]) == 4


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
    news = {"S0.NS": [NewsItem(
        title="S0 reports quarterly earnings",
        link="https://example.com/s0",
        published=NOW - timedelta(days=1),
        source="Economic Times",
        relevance_score=82,
        match_confidence="high",
        match_reasons=["ticker appears with market context"],
        source_quality=0.9,
    )]}
    data = build_data(result, news, policy=[
        NewsItem(title="Cabinet approves fab incentives", link="https://pib/1",
                 published=NOW - timedelta(days=2), source="Mint",
                 sectors=["Semiconductors"]),
    ], built_at=NOW)
    changes = {"entered": ["S0.NS"], "exited": ["Z.NS"]}
    render_site(data, changes, result, tmp_path)

    index = (tmp_path / "index.html").read_text()
    assert "S0.NS" in index and "Semiconductors" in index
    assert "Entered S0.NS" in index  # changes strip: entry rendered
    assert "Exited Z.NS" in index   # changes strip: exit rendered
    assert "research ranking" in index.lower()
    assert 'src="/assets/app.js"' in index
    assert "Cabinet approves fab incentives" in index
    # PIB is no longer the source; the old label attributed Google News
    # aggregation to a government press office
    assert "Government policy (PIB)" not in index
    assert "Mint" in index and "2d old at build" in index  # sourced and dated on the page
    # every descriptive layer on this page says so next to itself
    assert "never scored" in index

    saved = json.loads((tmp_path / "data.json").read_text())
    assert saved["changes"] == changes
    # a static report page exists per published pick
    assert (tmp_path / "reports" / "S0_NS.html").exists()
    assert len(list((tmp_path / "company").glob("*.html"))) == len(result.ranked)
    # Versioned static compatibility contracts are emitted beside the legacy payload.
    rankings_v1 = json.loads((tmp_path / "api" / "v1" / "rankings.json").read_text())
    instruments_v1 = json.loads((tmp_path / "api" / "v1" / "instruments.json").read_text())
    assert rankings_v1["data"][0]["instrument_id"] == saved["top"][0]["instrument_id"]
    assert instruments_v1["warnings"] == [
        "Static instrument master is limited to the pinned Nifty Smallcap 250 universe."
    ]
    assert rankings_v1["data"][0]["technical_trend"] == data["top"][0]["trend"]
    assert "components" in rankings_v1["data"][0]
    canonical_path = tmp_path / "company" / f"{data['top'][0]['instrument_id']}.html"
    assert canonical_path.exists()
    canonical_html = canonical_path.read_text()
    assert "Level 3 — Full Research" in canonical_html
    assert "Included in the Small-Cap research model." in canonical_html
    research_json = tmp_path / "api" / "v1" / "research" / f"{data['top'][0]['instrument_id']}.json"
    assert research_json.exists()
    assert json.loads(research_json.read_text())["data"]["schema_version"] == "1.0"
    report = (tmp_path / "reports" / "S0_NS.html").read_text()
    assert "Multibagger" in report
    # render_site rebuilds NewsItems from data.json and threads them into every
    # report page; the section must survive that JSON round-trip
    assert "Recent News &amp; Policy Context" in report
    assert "S0 reports quarterly earnings" in report


def test_render_site_groups_policy_under_its_industry(tmp_path):
    """The regulator-anchored query returns ~90 items across 20 industries;
    as one flat list that is an unreadable wall, so the page groups it."""
    result = _result()
    data = build_data(result, {}, policy=[
        NewsItem(title="SEBI eases norms", link="https://x/1",
                 published=NOW, sectors=["Capital Markets"]),
        NewsItem(title="SEBI clears AIF route", link="https://x/2",
                 published=NOW, sectors=["Capital Markets"]),
        NewsItem(title="FSSAI notice to energy drinks", link="https://x/3",
                 published=NOW, sectors=["Packaged Foods"]),
    ], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    index = (tmp_path / "index.html").read_text()

    # each industry names itself once, not once per headline
    assert index.count(">Capital Markets<") == 1
    assert index.count(">Packaged Foods<") == 1
    for title in ("SEBI eases norms", "SEBI clears AIF route",
                  "FSSAI notice to energy drinks"):
        assert title in index
    # and both of Capital Markets' items sit under its heading, before the next
    start = index.index(">Capital Markets<")
    assert index.index("SEBI clears AIF route") > start
    assert index.index("SEBI eases norms") > start


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
    assert "<title>S0.NS research report | Multibagger Engine</title>" in page


def test_render_report_page_custom_back_link():
    bundle = make_bundle("S0.NS")
    page = render_report_page(bundle, back_href="/")
    assert 'href="/"' in page
    assert 'href="../index.html"' not in page


def test_report_source_lineage_distinguishes_official_revision_from_fallback():
    from mbe.financials.projection import project_history
    bundle = make_bundle("S0.NS")
    financial = project_history(bundle.fin, instrument_id="instrument", cutoff=NOW)
    financial.update({
        "selected_source": "nse_financial_results",
        "source_quality_tier": "A",
        "source_selection_status": "official_selected",
        "source_selection_reason": "Valid official consolidated filing passed period and unit checks.",
        "basis": "consolidated",
        "official_filing_date": "2026-05-20",
        "official_source_url": "https://nsearchives.nseindia.com/fixture.xml",
        "restated": True,
        "reconciliation_status": "within_rounding_tolerance",
        "financial_dataset_build_id": "financial-build",
    })
    page = render_report_page(bundle, financial=financial)
    assert "Official NSE filing" in page
    assert "Consolidated" in page
    assert "Restated or revised" in page
    assert "Within Rounding Tolerance" in page
    assert '<details class="source-lineage">' in page
    assert 'rel="noopener noreferrer"' in page


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
    for token in ("#1f2022", "#38a6f0", "#63c968", "#ff6b68"):
        assert token in THEME_CSS  # Zerodha-dark set
    for token in ("#f3f4f6", "#3f64d8", "#087f49", "#bd2929", "#d8e0eb", "#20262d"):
        assert token in THEME_CSS  # Groww-light set


def test_theme_boot_applies_saved_theme_before_paint():
    assert 'src="/assets/theme.js"' in THEME_BOOT
    assert "<script>" not in THEME_BOOT


def test_theme_toggle_persists_choice():
    assert "data-theme-toggle" in THEME_TOGGLE
    assert "onclick" not in THEME_TOGGLE


def test_report_shell_is_themed():
    page = render_report_page(make_bundle("S0.NS"))
    assert '../assets/theme.js' in page  # external boot script present
    assert "data-theme-toggle" in page  # toggle present
    assert 'class="app-header"' in page
    assert 'href="../assets/app.css"' in page
    # content contract unchanged (existing tests also enforce this)
    assert "S0.NS research report" in page and "Multibagger" in page


def test_index_is_themed_with_nav_and_daychange_quotes(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    index = (tmp_path / "index.html").read_text()
    assert '/assets/theme.js' in index and "data-theme-toggle" in index
    assert "app-header" in index
    assert (tmp_path / "assets" / "app.css").exists()
    # Quote wire-shape field names live in the shared quote-controller.js
    # (Phase 11 Milestone 2B) rather than duplicated inline in app.js.
    quote_controller_js = (tmp_path / "assets" / "quote-controller.js").read_text()
    assert "percentage_change" in quote_controller_js and "day_change_pct" in quote_controller_js
    # stable application routes and working section links
    assert 'href="/#rankings"' in index and 'href="/#sectors"' in index


from mbe.publish import render_error_page


def test_render_error_page_is_themed_and_escapes():
    page = render_error_page("<script>x</script>", "Not a valid ticker format.")
    assert "&lt;script&gt;" in page and "<script>x" not in page
    assert 'href="/assets/app.css"' in page and "data-theme-toggle" in page
    assert 'href="/"' in page
    assert "Not a valid ticker format." in page


def test_peer_bundles_returns_the_group_containing_the_ticker():
    from mbe.publish import peer_bundles

    result = _result()   # 4 bundles, one "Semiconductors" group
    peers = peer_bundles(result, "S0.NS")
    assert {b.card.ticker for b in peers} == {"S0.NS", "S1.NS", "S2.NS", "S3.NS"}


def test_peer_bundles_is_empty_for_an_ungrouped_ticker():
    from mbe.publish import peer_bundles

    assert peer_bundles(_result(), "NOTINANYGROUP.NS") == []


def test_render_site_puts_charts_on_report_pages(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    report = (tmp_path / "reports" / "S0_NS.html").read_text()

    assert "<svg" in report
    assert "Peer Comparison" in report
    # the group's other members are named on the page
    assert "S1.NS" in report or "S1" in report
    # and no svg was split across paragraphs by markdown
    import re
    svgs = re.findall(r"<svg\b.*?</svg>", report, re.S)
    assert len(svgs) == report.count("<svg")
    assert all("</p>" not in s for s in svgs)


def test_application_shell_search_table_and_methodology_are_accessible(tmp_path):
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    index = (tmp_path / "index.html").read_text()

    assert 'class="skip-link" href="#main-content"' in index
    assert '<header class="app-header">' in index
    assert '<nav class="primary-nav" aria-label="Primary navigation">' in index
    assert '<main id="main-content"' in index
    assert '<dialog class="dialog" id="instrument-search"' in index
    assert 'role="listbox"' in index and 'aria-live="polite"' in index
    assert 'aria-controls="mobile-navigation"' in index
    assert '<caption class="sr-only">Multibagger ranking results.' in index
    assert 'scope="col"' in index and 'aria-sort="ascending"' in index
    assert 'data-filter-form' in index and 'data-column-trigger' in index
    assert 'data-density' in index and 'data-export' in index

    methodology = (tmp_path / "methodology.html").read_text()
    assert "Methodology &amp; limitations" in methodology
    assert "Confidence reflects coverage" in methodology
    assert "Static versus live data" in methodology
    assert '<link rel="canonical"' in methodology


def test_static_search_snapshot_can_cover_full_master_not_only_rankings(tmp_path):
    result = _result()
    canonical = {
        f"MASTER{i}.NS": {
            "company_name": f"Master Company {i} Ltd.",
            "symbol": f"MASTER{i}",
            "exchange": "NSE",
            "isin": f"INE{i:09d}"[:11] + str(i % 10),
            "industry": "Engineering",
            "listing_status": "active",
            "provider_symbols": {"yahoo": f"MASTER{i}.NS"},
            "aliases": [],
        }
        for i in range(30)
    }
    instrument_ids = {
        ticker: f"00000000-0000-0000-0000-{i:012d}"
        for i, ticker in enumerate(canonical)
    }
    data = build_data(
        result, {}, policy=[], built_at=NOW,
        canonical_records=canonical, instrument_ids=instrument_ids,
    )
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    instruments = json.loads(
        (tmp_path / "api" / "v1" / "instruments.json").read_text()
    )
    rankings = json.loads(
        (tmp_path / "api" / "v1" / "rankings.json").read_text()
    )
    assert instruments["meta"]["total"] == 30
    assert rankings["meta"]["total"] == 4
    assert instruments["data"][0]["instrument_id"]


def test_static_screener_uses_full_scored_universe_and_registry(tmp_path):
    bundles = [make_bundle(f"T{i}.NS", multibagger=90.0 - i) for i in range(TOP_N + 5)]
    result = ScreenResult(ranked=bundles, failures={}, sector_scores=[])
    first = build_data(result, {}, policy=[], built_at=NOW)
    previous = first["_screener_rows"]
    data = build_data(
        result, {}, policy=[], built_at=NOW + timedelta(days=7),
        previous_screener_rows=previous,
    )
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    snapshot = json.loads((tmp_path / "api" / "v1" / "screener.json").read_text())
    fields = json.loads((tmp_path / "api" / "v1" / "screener-fields.json").read_text())
    public_data = json.loads((tmp_path / "data.json").read_text())
    assert len(snapshot["data"]["rows"]) == TOP_N + 5
    assert snapshot["data"]["rows"][0]["values"]["rank_change"] == 0
    assert len(fields["data"]["fields"]) == 30
    assert "_screener_rows" not in public_data
    assert (tmp_path / "screener.html").exists()
    assert "Advanced Stock Screener" in (tmp_path / "screener.html").read_text()


def test_frontend_assets_stay_within_documented_uncompressed_budgets():
    from mbe.publish import ASSET_DIR

    # app.js budget raised from 60 KiB to 64 KiB in Phase 11 Milestone 2B,
    # which added dynamic quote-refresh wiring (shared quote-controller.js
    # integration) to the rankings table.
    assert (ASSET_DIR / "app.js").stat().st_size < 64 * 1024
    assert (ASSET_DIR / "screener.js").stat().st_size < 50 * 1024
    assert (ASSET_DIR / "app.css").stat().st_size < 40 * 1024


def test_frontend_data_mode_is_validated(monkeypatch, tmp_path):
    monkeypatch.setenv("MBE_FRONTEND_DATA_MODE", "static")
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)
    assert 'body data-data-mode="static"' in (tmp_path / "index.html").read_text()

    monkeypatch.setenv("MBE_FRONTEND_DATA_MODE", "unsafe")
    import pytest
    with pytest.raises(ValueError, match="auto, api or static"):
        render_site(data, {"entered": [], "exited": []}, result, tmp_path)
