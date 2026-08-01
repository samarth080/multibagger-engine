"""Static build regression guard: search-index.json must cover the whole
search universe, independent of instruments.json (which stays scoped to the
pinned research/ranking master and must not change shape).
"""

import json

from mbe.data.news_rss import NewsItem
from mbe.models.instrument import stable_instrument_id
from mbe.publish import build_data, render_site
from tests.test_sector import make_bundle
from tests.test_publish import NOW, _result


def _wide_search_universe_rows():
    rows = [
        {
            "source_record_id": f"INE{i:09d}0", "company_name": f"Master Company {i} Ltd.",
            "symbol": f"MASTER{i}", "exchange": "NSE", "exchange_segment": None,
            "series": "EQ", "isin": f"INE{i:09d}0", "bse_code": None, "industry": None,
            "sector": None, "listing_status": "active", "listing_date": None,
            "delisting_date": None, "is_sme": False, "security_type": "equity",
            "provider_symbols": {"yahoo": f"MASTER{i}.NS"}, "aliases": [],
        }
        for i in range(30)
    ]
    # A large tranche of companies the model has never scored — the actual
    # regression scenario (e.g. Reliance-shaped: real NSE company, no build).
    rows += [
        {
            "source_record_id": f"INE{9000 + i:09d}1", "company_name": f"Unmodeled Co {i} Ltd.",
            "symbol": f"UNMODELED{i}", "exchange": "NSE", "exchange_segment": None,
            "series": "EQ", "isin": f"INE{9000 + i:09d}1", "bse_code": None, "industry": None,
            "sector": None, "listing_status": "active", "listing_date": None,
            "delisting_date": None, "is_sme": False, "security_type": "equity",
            "provider_symbols": {"yahoo": f"UNMODELED{i}.NS"}, "aliases": [],
        }
        for i in range(500)
    ]
    return rows


def _wide_canonical_records():
    return {
        f"MASTER{i}.NS": {
            "company_name": f"Master Company {i} Ltd.", "symbol": f"MASTER{i}",
            "exchange": "NSE", "isin": f"INE{i:09d}0", "industry": "Engineering",
            "listing_status": "active", "provider_symbols": {"yahoo": f"MASTER{i}.NS"},
            "aliases": [],
        }
        for i in range(30)
    }


def test_search_index_covers_far_more_than_the_ranked_and_master_universe(tmp_path):
    # Ranked bundles are a subset of the canonical/search-universe master, as
    # in real production (screened tickers are always instrument-master rows).
    from mbe.pipeline import ScreenResult
    bundles = [make_bundle(f"MASTER{i}.NS", multibagger=80.0 - i) for i in range(4)]
    result = ScreenResult(ranked=bundles, failures={}, sector_scores=[])
    canonical = _wide_canonical_records()
    instrument_ids = {
        ticker: stable_instrument_id(
            exchange_code="NSE", symbol=row["symbol"], isin=row.get("isin"),
        )
        for ticker, row in canonical.items()
    }
    data = build_data(
        result, {}, policy=[], built_at=NOW,
        canonical_records=canonical, instrument_ids=instrument_ids,
    )
    render_site(
        data, {"entered": [], "exited": []}, result, tmp_path,
        search_universe_rows=_wide_search_universe_rows(), bse_rows=[],
    )

    search_index = json.loads((tmp_path / "api" / "v1" / "search-index.json").read_text())
    instruments = json.loads((tmp_path / "api" / "v1" / "instruments.json").read_text())

    assert instruments["meta"]["total"] == 30  # unchanged: research/ranking master only
    assert search_index["meta"]["total"] == 530  # 30 master + 500 unmodeled — the wider universe
    assert search_index["meta"]["research_universe_count"] == 30
    assert search_index["meta"]["ranking_universe_count"] == len(result.ranked)

    by_symbol = {row["symbol"]: row for row in search_index["data"]}
    assert "UNMODELED17" in by_symbol
    unmodeled = by_symbol["UNMODELED17"]
    assert unmodeled["result_type"] == "known"
    assert unmodeled["research_available"] is False
    assert unmodeled["rank"] is None
    assert unmodeled["multibagger_score"] is None
    assert unmodeled["report_url"] == f"/company/{unmodeled['instrument_id']}.html"

    ranked_ticker = result.ranked[0].card.ticker
    ranked_symbol = ranked_ticker.removesuffix(".NS")
    assert ranked_symbol in by_symbol
    modeled = by_symbol[ranked_symbol]
    assert modeled["result_type"] == "modeled"
    assert modeled["research_available"] is True
    assert modeled["rank"] == 1
    assert modeled["multibagger_score"] is not None
    assert modeled["report_url"] == f"/company/{modeled['instrument_id']}.html"


def test_search_index_defaults_to_the_pinned_universe_when_not_overridden(tmp_path):
    """Production build_site.py does not pass search_universe_rows explicitly;
    render_site must fall back to the real pinned search-universe snapshot."""
    result = _result()
    data = build_data(result, {}, policy=[], built_at=NOW)
    render_site(data, {"entered": [], "exited": []}, result, tmp_path)

    search_index = json.loads((tmp_path / "api" / "v1" / "search-index.json").read_text())
    symbols = {row["symbol"] for row in search_index["data"]}
    assert "RELIANCE" in symbols
    assert "TCS" in symbols
    assert search_index["meta"]["total"] > 2000
