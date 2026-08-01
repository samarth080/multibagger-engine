"""mbe.search.ranking: quality-ordered search over the merged index.

Mirrors mbe.instruments.resolution.InstrumentResolver's tiering (exact
symbol > exact name > alias > former name > prefix > word match > fuzzy) but
operates over the wider search index instead of only DB-imported (research
universe) instruments, and adds a "word match" tier per the Phase 10A spec.
"""

from mbe.search.catalog import build_search_index
from mbe.search.domain import SearchResultType
from mbe.search.ranking import rank_search_candidates


def _row(symbol, name, isin, *, aliases=None):
    return {
        "source_record_id": isin, "company_name": name, "symbol": symbol,
        "exchange": "NSE", "exchange_segment": None, "series": "EQ", "isin": isin,
        "bse_code": None, "industry": None, "sector": None, "listing_status": "active",
        "listing_date": None, "delisting_date": None, "is_sme": False,
        "security_type": "equity", "provider_symbols": {"yahoo": f"{symbol}.NS"},
        "aliases": aliases or [],
    }


UNIVERSE = [
    _row("RELIANCE", "Reliance Industries Limited", "INE002A01018"),
    _row("RPOWER", "Reliance Power Limited", "INE614G01033"),
    _row("RCOM", "Reliance Communications Limited", "INE330H01018"),
    _row("TCS", "Tata Consultancy Services Limited", "INE467B01029"),
    _row("INFY", "Infosys Limited", "INE009A01021"),
    _row("HDFCBANK", "HDFC Bank Limited", "INE040A01034"),
    _row("HDFCAMC", "HDFC Asset Management Company Limited", "INE127D01025"),
    _row("HAL", "Hindustan Aeronautics Limited", "INE066F01020"),
    _row("BEL", "Bharat Electronics Limited", "INE263A01024"),
    _row("DIXON", "Dixon Technologies (India) Limited", "INE935N01020"),
    _row("POLYCAB", "Polycab India Limited", "INE455K01017"),
    _row("BLS", "BLS International Services Limited", "INE153T01027"),
    # Decoys that would win on naive substring/fuzzy matching but must lose
    # to the exact-symbol BLS International match (Phase 0 disambiguation).
    _row("BLSDECOY", "Bhavna Lal Sons Limited", "INE000B01001"),
    _row("ACE", "Action Construction Equipment Limited", "INE731H01025"),
    _row("ACEDECOY", "Acer Consolidated Enterprises Limited", "INE000A01002"),
    _row("VIJAYA", "Vijaya Diagnostic Centre Limited", "INE325P01023"),
    _row("VIJAYADECOY", "Vijayawada General Traders Limited", "INE000C01003"),
]


def _index():
    return build_search_index(UNIVERSE, [], [])


def test_exact_symbol_beats_everything_for_reliance_family():
    results = rank_search_candidates("RELIANCE", _index())
    assert results[0].record.symbol == "RELIANCE"
    assert results[0].matched_by == "exact_nse_symbol"
    assert results[0].score == 100


def test_reliance_industries_is_discoverable_by_name_prefix():
    results = rank_search_candidates("Reliance", _index())
    names = [r.record.display_name for r in results]
    assert "Reliance Industries Limited" in names


def test_tcs_resolves_to_tata_consultancy_services():
    results = rank_search_candidates("TCS", _index())
    assert results[0].record.display_name == "Tata Consultancy Services Limited"


def test_infosys_resolves_by_name():
    results = rank_search_candidates("Infosys", _index())
    assert results[0].record.symbol == "INFY"


def test_hdfc_bank_ranks_before_hdfc_amc():
    results = rank_search_candidates("HDFC", _index())
    symbols_in_order = [r.record.symbol for r in results if r.record.symbol in {"HDFCBANK", "HDFCAMC"}]
    assert symbols_in_order == ["HDFCBANK", "HDFCAMC"]


def test_dixon_resolves_to_dixon_technologies():
    results = rank_search_candidates("Dixon", _index())
    assert results[0].record.symbol == "DIXON"


def test_bel_resolves_to_bharat_electronics_without_abbreviation_collision():
    results = rank_search_candidates("BEL", _index())
    assert results[0].record.symbol == "BEL"
    assert results[0].record.display_name == "Bharat Electronics Limited"


def test_hal_resolves_to_hindustan_aeronautics():
    results = rank_search_candidates("HAL", _index())
    assert results[0].record.symbol == "HAL"


def test_polycab_resolves_to_polycab_india():
    results = rank_search_candidates("Polycab", _index())
    assert results[0].record.symbol == "POLYCAB"


def test_bls_collision_is_resolved_by_exact_symbol_not_fuzzy_decoy():
    results = rank_search_candidates("BLS", _index())
    assert results[0].record.symbol == "BLS"
    assert results[0].record.display_name == "BLS International Services Limited"


def test_ace_collision_is_resolved_by_exact_symbol_not_fuzzy_decoy():
    results = rank_search_candidates("ACE", _index())
    assert results[0].record.symbol == "ACE"
    assert results[0].record.display_name == "Action Construction Equipment Limited"


def test_vijaya_collision_is_resolved_by_exact_symbol_not_fuzzy_decoy():
    results = rank_search_candidates("VIJAYA", _index())
    assert results[0].record.symbol == "VIJAYA"
    assert results[0].record.display_name == "Vijaya Diagnostic Centre Limited"


def test_unknown_company_returns_no_candidates():
    results = rank_search_candidates("Zzznotarealcompanyxyz123", _index())
    assert results == []


def test_word_match_tier_finds_a_non_leading_token():
    # "Industries" is not a prefix of any name here but is a whole-word token
    # inside "Reliance Industries Limited" — should surface via word match.
    results = rank_search_candidates("Industries", _index())
    assert any(r.record.symbol == "RELIANCE" for r in results)


def test_result_limit_is_honored_and_bounded():
    results = rank_search_candidates("a", _index(), limit=3)
    assert len(results) <= 3


def test_short_query_below_two_characters_returns_nothing():
    results = rank_search_candidates("R", _index())
    assert results == []


def test_modeled_result_carries_score_and_type_modeled(monkeypatch=None):
    universe = [_row("SUNPHARMA", "Sun Pharmaceutical Industries Limited", "INE044A01036")]
    research = [{
        "instrument_id": None, "display_name": "Sun Pharmaceutical Industries Ltd.",
        "symbol": "SUNPHARMA", "isin": "INE044A01036", "exchange": "NSE",
        "sector": "Healthcare", "industry": "Pharmaceuticals",
    }]
    from mbe.models.instrument import stable_instrument_id
    research[0]["instrument_id"] = stable_instrument_id(exchange_code="NSE", symbol="SUNPHARMA", isin="INE044A01036")
    screener = [{"instrument_id": research[0]["instrument_id"], "values": {
        "rank": 5, "multibagger_score": 70.0, "confidence": 0.6, "risk_score": 30.0,
    }}]
    index = build_search_index(universe, research, screener)
    results = rank_search_candidates("SUNPHARMA", index)
    assert results[0].record.result_type == SearchResultType.MODELED
    assert results[0].record.rank == 5
    assert results[0].record.multibagger_score == 70.0
