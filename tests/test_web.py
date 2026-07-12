import pytest
from fastapi.testclient import TestClient

from mbe.pipeline import screen
from mbe.storage import RunStore
from mbe.web.app import create_app
from tests.test_pipeline import StubProvider


@pytest.fixture
def client(tmp_path):
    store = RunStore(tmp_path / "web.duckdb")
    store.save_run(screen(["GOOD.NS", "ALSO.NS"], StubProvider()), universe="unit-test")
    app = create_app(
        provider=StubProvider(), store=store, reports_dir=tmp_path / "reports"
    )
    return TestClient(app)


def test_home_lists_runs(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Multibagger Engine" in resp.text
    assert "unit-test" in resp.text


def test_run_page_shows_ranked_meters(client):
    store_runs = client.get("/").text
    # follow the first run link
    run_id = store_runs.split('href="/run/')[1].split('"')[0]
    resp = client.get(f"/run/{run_id}")
    assert resp.status_code == 200
    assert "GOOD.NS" in resp.text
    assert 'class="meter"' in resp.text  # signature score meters


def test_report_page_renders_markdown(client):
    resp = client.get("/report/GOOD.NS")
    assert resp.status_code == 200
    assert "Equity Research Report" in resp.text
    assert "<table>" in resp.text  # markdown tables converted to HTML


def test_history_page(client):
    resp = client.get("/history/GOOD.NS")
    assert resp.status_code == 200
    assert "GOOD.NS" in resp.text


def test_unknown_run_404(client):
    assert client.get("/run/nope").status_code == 404


def test_report_sanitizes_stray_characters_in_ticker(client):
    # trailing backslash (key next to Enter) and whitespace must not break analysis
    resp = client.get("/report/GOOD.NS%5C")  # %5C = backslash
    assert resp.status_code == 200
    assert "Equity Research Report" in resp.text
    assert "GOOD.NS\\" not in resp.text  # the backslash must never reach the provider

    resp = client.get("/analyze", params={"ticker": " good.ns\\ "}, follow_redirects=True)
    assert resp.status_code == 200
    assert "(GOOD.NS)" in resp.text
    assert "GOOD.NS\\" not in resp.text


def test_unanalyzable_ticker_gets_friendly_html_not_json(client):
    resp = client.get("/report/BAD.NS")  # StubProvider knows nothing of BAD.NS?
    # our stub analyzes anything; simulate failure via empty ticker instead
    resp = client.get("/report/%5C%5C")  # sanitizes to empty -> must be handled
    assert resp.status_code == 404
    assert "text/html" in resp.headers["content-type"]
    assert "could not" in resp.text.lower() or "check the symbol" in resp.text.lower()
