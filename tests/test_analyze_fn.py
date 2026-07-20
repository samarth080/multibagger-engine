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


def test_render_analysis_escapes_ticker_in_bad_format_error():
    # the 400 branch fires exactly when the ticker did NOT pass validation,
    # so the raw rejected string must never be echoed back unescaped.
    # (Themed pages legitimately carry ONE script of their own — the theme
    # boot — so the assertion targets the attacker payload specifically
    # rather than banning <script> outright.)
    payload = "<script>alert(1)</script>"
    status, html_out = analyze_fn.render_analysis(payload, provider=StubProvider())
    assert status == 400
    assert payload not in html_out  # raw attacker string never reflected
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out  # escaped form shown
    assert html_out.count("<script>") == 1  # only our theme-boot script exists


def test_render_analysis_500_never_reflects_exception_repr():
    class BoomProvider(StubProvider):
        def get_info(self, ticker):
            raise ValueError("<img src=x onerror=alert(1)>")

    status, html_out = analyze_fn.render_analysis("GOOD.NS", provider=BoomProvider())
    assert status == 500
    assert "onerror" not in html_out
    assert "<img" not in html_out
