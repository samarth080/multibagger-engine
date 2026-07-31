"""Primitives are dumb on purpose: no stock knowledge, two hard rules."""

import re

from mbe.report import svg


def test_esc_neutralises_markup_and_ampersands():
    # company names come from Yahoo; "AT&T" alone breaks an unescaped SVG
    assert svg.esc("AT&T") == "AT&amp;T"
    out = svg.esc('<script>alert(1)</script>')
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert svg.esc('a"b') == "a&quot;b"


def test_scale_maps_clamps_and_survives_a_flat_domain():
    assert svg.scale(0, 0, 10, 0, 100) == 0
    assert svg.scale(10, 0, 10, 0, 100) == 100
    assert svg.scale(5, 0, 10, 0, 100) == 50
    assert svg.scale(99, 0, 10, 0, 100) == 100     # clamped, not extrapolated
    assert svg.scale(-99, 0, 10, 0, 100) == 0
    # every value identical: midpoint beats ZeroDivisionError
    assert svg.scale(7, 7, 7, 0, 100) == 50


def test_document_never_contains_a_blank_line():
    """python-markdown splits a blank line inside a tag into paragraphs,
    turning one chart into '<p><svg></p>'. This is the load-bearing test."""
    doc = svg.document(100, 50, "T", [svg.text(1, 2, "a"), "", svg.rect(0, 0, 5, 5, svg.PEER)])
    assert "\n\n" not in doc
    assert doc.startswith("<svg") and doc.endswith("</svg>")


def test_document_is_labelled_for_screen_readers():
    doc = svg.document(100, 50, "Revenue by year", [])
    assert 'role="img"' in doc
    assert "<title>Revenue by year</title>" in doc
    assert 'aria-label="Revenue by year"' in doc


def test_document_escapes_its_title():
    assert "<script>" not in svg.document(10, 10, "<script>x</script>", [])


def test_no_primitive_emits_a_literal_colour():
    """The site has dark and light palettes; a hex literal is invisible in one."""
    out = "".join([
        svg.text(1, 2, "a"), svg.rect(0, 0, 1, 1, svg.SUBJECT),
        svg.line(0, 0, 1, 1), svg.circle(1, 1, 1, svg.GAIN),
        svg.document(10, 10, "t", []),
    ])
    assert not re.search(r"#[0-9a-fA-F]{3,6}", out)


def test_rect_never_gets_a_negative_dimension():
    assert 'width="0.0"' in svg.rect(0, 0, -5, 10, svg.PEER)
    assert 'height="0.0"' in svg.rect(0, 0, 10, -5, svg.PEER)
