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
