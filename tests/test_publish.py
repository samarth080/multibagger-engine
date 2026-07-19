"""Offline tests for the static-site builder (stub bundles, no network)."""

from datetime import datetime, timezone

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
                 published=NOW, sectors=["Semiconductors"]),
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

    saved = json.loads((tmp_path / "data.json").read_text())
    assert saved["changes"] == changes
    # a static report page exists per published pick
    assert (tmp_path / "reports" / "S0_NS.html").exists()
    report = (tmp_path / "reports" / "S0_NS.html").read_text()
    assert "Multibagger" in report


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
