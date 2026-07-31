import json

import pytest

from mbe import universe as uni


def test_curated_universes_are_already_pinned():
    """Curated lists live in source, so the flag is a no-op for them."""
    assert uni.get_universe("us-tech") == uni.get_universe("us-tech", pinned=True)


def test_pinned_snapshot_is_used_and_never_fetches(tmp_path, monkeypatch):
    """The point of pinning: an ablation re-run must compare the same companies,
    not whatever the index happens to hold this week."""
    snap = tmp_path / "nifty-smallcap250.json"
    snap.write_text(json.dumps({
        "pinned_at": "2026-07-31",
        "source": "nse",
        "tickers": ["AAA.NS", "BBB.NS"],
    }))
    monkeypatch.setattr(uni, "PINNED_DIR", tmp_path)

    def explode(*a, **k):  # any network call is a test failure
        raise AssertionError("pinned universe must not hit the network")

    monkeypatch.setattr("mbe.data.universe_nse.fetch_universe", explode)
    assert uni.get_universe("nifty-smallcap250", pinned=True) == ["AAA.NS", "BBB.NS"]


def test_pinned_requested_but_absent_fails_loudly(tmp_path, monkeypatch):
    """Silently falling back to a live fetch would reintroduce exactly the drift
    pinning exists to prevent, and the run would look reproducible when it is
    not. Refuse instead."""
    monkeypatch.setattr(uni, "PINNED_DIR", tmp_path)
    with pytest.raises(KeyError, match="no pinned snapshot"):
        uni.get_universe("nifty-smallcap250", pinned=True)


def test_unpinned_is_the_default_and_still_fetches_live(tmp_path, monkeypatch):
    """Production screening wants today's index, not a frozen one."""
    monkeypatch.setattr(uni, "PINNED_DIR", tmp_path)
    called = {}

    def fake_fetch(name, cache=None):
        called["hit"] = name
        return ["LIVE.NS"]

    monkeypatch.setattr("mbe.data.universe_nse.fetch_universe", fake_fetch)
    assert uni.get_universe("nifty-smallcap250") == ["LIVE.NS"]
    assert called["hit"] == "nifty-smallcap250"


def test_pin_universe_writes_a_dated_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(uni, "PINNED_DIR", tmp_path)
    monkeypatch.setattr(
        "mbe.data.universe_nse.fetch_universe", lambda name, cache=None: ["X.NS", "Y.NS"]
    )
    path = uni.pin_universe("nifty-smallcap250")
    saved = json.loads(path.read_text())
    assert saved["tickers"] == ["X.NS", "Y.NS"]
    assert saved["pinned_at"]
    assert uni.get_universe("nifty-smallcap250", pinned=True) == ["X.NS", "Y.NS"]
