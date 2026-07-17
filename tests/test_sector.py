"""P2.4 sector rotation tests: multi-horizon returns, grouping, aggregation,
leave-one-out pillar, augmented score, themes table, screen/harness wiring.
All offline; stub providers follow the tests/test_pipeline.py pattern."""

import numpy as np
import pandas as pd
import pytest

from mbe.analysis.technicals import compute_technicals
from mbe.models.company import PriceHistory


def _price_history(closes) -> PriceHistory:
    closes = pd.Series(closes, dtype=float)
    idx = pd.bdate_range("2022-01-03", periods=len(closes))
    return PriceHistory(
        df=pd.DataFrame(
            {
                "open": closes.values,
                "high": closes.values * 1.01,
                "low": closes.values * 0.99,
                "close": closes.values,
                "volume": 1_000_000.0,
            },
            index=idx,
        )
    )


def test_multi_horizon_returns():
    closes = list(np.linspace(100, 200, 300))
    state = compute_technicals(_price_history(closes), None)
    assert state.return_126d == pytest.approx(closes[-1] / closes[-127] - 1)
    assert state.return_252d == pytest.approx(closes[-1] / closes[-253] - 1)


def test_multi_horizon_returns_none_on_short_history():
    closes = list(np.linspace(100, 120, 130))
    state = compute_technicals(_price_history(closes), None)
    assert state.return_126d is not None
    assert state.return_252d is None


from mbe.scoring.benchmarks import score_metric


def test_sector_benchmark_tables():
    assert score_metric("sector_rel_strength_6m", 0.06)[0] == 75
    assert score_metric("sector_rel_strength_6m", -0.20)[0] == 5  # floor
    assert score_metric("sector_rel_strength_12m", 0.30)[0] == 90
    assert score_metric("sector_rev_accel", 0.03)[0] == 75
    assert score_metric("sector_margin_delta", 0.015)[0] == 75


from mbe.models.scoring import Evidence
from mbe.models.sector import MemberComponents, SectorContext, SectorScore


def test_sector_models_roundtrip():
    score = SectorScore(
        name="Semiconductors", level="industry", n=5, score=72.0,
        confidence=0.8, evidence=[], members=["A.NS", "B.NS"],
    )
    ctx = SectorContext(
        groups={"Semiconductors": score},
        membership={"A.NS": "Semiconductors"},
        member_data={"A.NS": MemberComponents(ret_6m=0.2)},
        universe_median_ret_6m=0.1,
    )
    assert ctx.groups["Semiconductors"].n == 5
    assert ctx.member_data["A.NS"].ret_12m is None


from mbe.analysis.sector import revenue_acceleration
from mbe.models.company import FinancialHistory


def test_revenue_acceleration_hand_computed():
    fin = FinancialHistory(data={"revenue": {2022: 100.0, 2023: 110.0, 2024: 127.6}})
    # g1 = 0.10, g2 = 0.16 -> accel = +0.06
    assert revenue_acceleration(fin) == pytest.approx(0.06, abs=1e-9)


def test_revenue_acceleration_needs_three_years():
    fin = FinancialHistory(data={"revenue": {2023: 100.0, 2024: 120.0}})
    assert revenue_acceleration(fin) is None


def test_revenue_acceleration_rejects_nonpositive_base():
    fin = FinancialHistory(data={"revenue": {2022: -5.0, 2023: 100.0, 2024: 120.0}})
    assert revenue_acceleration(fin) is None


def test_revenue_acceleration_rejects_gap_years():
    # 2022 missing: 2021->2023 is not a YoY comparison; must be None, not -0.35
    fin = FinancialHistory(
        data={"revenue": {2021: 100.0, 2022: None, 2023: 150.0, 2024: 172.5}}
    )
    assert revenue_acceleration(fin) is None


def test_revenue_acceleration_rejects_nonpositive_middle_year():
    fin = FinancialHistory(data={"revenue": {2022: 50.0, 2023: -10.0, 2024: 30.0}})
    assert revenue_acceleration(fin) is None


from datetime import date

from mbe.analysis.sector import group_bundles
from mbe.models.analysis import (
    FundamentalMetrics,
    RiskAssessment,
    TechnicalState,
    ValuationResult,
)
from mbe.models.company import CompanyInfo
from mbe.models.scoring import PillarScore, ScoreCard
from mbe.pipeline import AnalysisBundle


def make_bundle(
    ticker: str,
    sector: str | None = "Technology",
    industry: str | None = "Semiconductors",
    ret_6m: float | None = 0.10,
    ret_12m: float | None = 0.20,
    revenue: dict[int, float] | None = None,
    margin_trend: float | None = 0.01,
    multibagger: float = 50.0,
    pillars: list[PillarScore] | None = None,
    gates: list[str] | None = None,
) -> AnalysisBundle:
    from mbe.models.company import FinancialHistory

    return AnalysisBundle(
        info=CompanyInfo(ticker=ticker, sector=sector, industry=industry),
        fin=FinancialHistory(
            data={"revenue": revenue or {2022: 100.0, 2023: 110.0, 2024: 121.0}}
        ),
        fund=FundamentalMetrics(margin_trend=margin_trend),
        tech=TechnicalState(return_126d=ret_6m, return_252d=ret_12m),
        val=ValuationResult(),
        risk=RiskAssessment(),
        card=ScoreCard(
            ticker=ticker, investment_score=50.0, multibagger_score=multibagger,
            confidence=0.5, pillars=pillars or [], hard_gate_failures=gates or [],
            verdict="test",
        ),
        as_of=date(2026, 7, 17),
    )


def test_grouping_keeps_large_industries_and_pools_leftovers():
    bundles = (
        [make_bundle(f"SEMI{i}.NS", industry="Semiconductors") for i in range(5)]
        + [make_bundle("APP1.NS", industry="Software - Application"),
           make_bundle("APP2.NS", industry="Software - Application"),
           make_bundle("INF1.NS", industry="Software - Infrastructure"),
           make_bundle("INF2.NS", industry="Software - Infrastructure")]
        + [make_bundle("OIL1.NS", sector="Energy", industry="Oil & Gas Refining"),
           make_bundle("OIL2.NS", sector="Energy", industry="Oil & Gas Refining")]
    )
    groups = group_bundles(bundles)
    assert len(groups["Semiconductors"]) == 5
    # two small Technology industries pool into the sector fallback
    assert len(groups["Technology (other)"]) == 4
    # Energy pool has only 2 members -> dropped entirely
    assert "Energy (other)" not in groups
    assert "Oil & Gas Refining" not in groups


def test_grouping_handles_missing_metadata():
    bundles = [make_bundle("X1.NS", sector=None, industry=None)] + [
        make_bundle(f"S{i}.NS") for i in range(4)
    ]
    groups = group_bundles(bundles)
    assert len(groups["Semiconductors"]) == 4
    assert sum(len(m) for m in groups.values()) == 4  # X1 ungrouped


from mbe.analysis.sector import compute_sector_scores


def test_group_score_hand_computed():
    # Semis: 6m returns .28/.30/.32/.30 (median .30); pool of laggards median .10
    semis = [
        make_bundle(f"SEMI{i}.NS", ret_6m=r, ret_12m=0.40, multibagger=60.0 + i)
        for i, r in enumerate([0.28, 0.30, 0.32, 0.30])
    ]
    laggards = [
        make_bundle(f"LAG{i}.NS", sector="Energy", industry="Oil & Gas Refining",
                    ret_6m=0.10, ret_12m=0.05, margin_trend=-0.02,
                    revenue={2022: 100.0, 2023: 120.0, 2024: 130.0})
        for i in range(4)
    ]
    ctx = compute_sector_scores(semis + laggards)
    semi = ctx.groups["Semiconductors"]
    # universe median 6m return = median(.28,.30,.32,.30,.10x4) = .19 -> rel = +.11
    ev = {e.metric: e for e in semi.evidence}
    assert ev["sector_rel_strength_6m"].value == pytest.approx(0.11)
    assert ev["sector_rel_strength_6m"].points == 75
    assert semi.n == 4
    assert ctx.membership["SEMI0.NS"] == "Semiconductors"
    # members ordered by multibagger score, best first
    assert semi.members[0] == "SEMI3.NS"
    assert semi.score > ctx.groups["Oil & Gas Refining"].score
    assert semi.level == "industry"


def test_group_score_missing_components_renormalize():
    bundles = [
        make_bundle(f"T{i}.NS", ret_6m=None, ret_12m=None,
                    revenue={2024: 100.0}, margin_trend=0.015)
        for i in range(4)
    ]
    ctx = compute_sector_scores(bundles)
    group = ctx.groups["Semiconductors"]
    # only margin_delta present -> confidence = its weight, score = its points
    assert group.confidence == pytest.approx(0.20)
    assert group.score == 75
    assert {e.metric for e in group.evidence} == {"sector_margin_delta"}


def test_pool_fallback_has_sector_level():
    # two small same-sector industries pool into "Technology (other)"
    bundles = [
        make_bundle(f"A{i}.NS", industry="Software - Application") for i in range(2)
    ] + [
        make_bundle(f"B{i}.NS", industry="Software - Infrastructure") for i in range(2)
    ]
    ctx = compute_sector_scores(bundles)
    pool = ctx.groups["Technology (other)"]
    assert pool.level == "sector"
    assert pool.n == 4


from mbe.analysis.sector import (
    apply_sector_pillar,
    augmented_multibagger,
    sector_pillar_for,
)


def _hot_group_ctx():
    """4 semis: one laggard (the LOO subject) among 3 hot peers, plus a cold
    pool so universe medians aren't dominated by the semis."""
    semis = [make_bundle("SELF.NS", ret_6m=0.00, ret_12m=0.00)] + [
        make_bundle(f"PEER{i}.NS", ret_6m=0.30, ret_12m=0.50) for i in range(3)
    ]
    cold = [
        make_bundle(f"C{i}.NS", sector="Energy", industry="Oil & Gas Refining",
                    ret_6m=0.00, ret_12m=0.00)
        for i in range(4)
    ]
    bundles = semis + cold
    return bundles, compute_sector_scores(bundles)


def test_loo_pillar_excludes_self():
    _, ctx = _hot_group_ctx()
    # SELF's pillar sees only the 3 hot peers: median .30 vs universe median .00
    pillar = sector_pillar_for("SELF.NS", ctx)
    ev = {e.metric: e for e in pillar.evidence}
    assert ev["sector_rel_strength_6m"].value == pytest.approx(0.30)
    assert "3 peers (leave-one-out)" in ev["sector_rel_strength_6m"].rationale
    # a hot peer's own pillar loses its own .30 from the median
    peer = sector_pillar_for("PEER0.NS", ctx)
    pev = {e.metric: e for e in peer.evidence}
    assert pev["sector_rel_strength_6m"].value == pytest.approx(0.30)  # median(.00,.30,.30)
    assert pillar.confidence > 0


def test_pillar_confidence_zero_when_ungrouped():
    _, ctx = _hot_group_ctx()
    pillar = sector_pillar_for("NOT_THERE.NS", ctx)
    assert pillar.confidence == 0.0 and pillar.score == 0.0


def test_augmented_multibagger_hand_computed():
    base_pillars = [
        PillarScore(name=n, score=50.0, confidence=1.0)
        for n in ("Growth", "Quality", "Size Runway", "Valuation", "Momentum", "Reinvestment")
    ]
    sector = PillarScore(name="Sector Momentum", score=90.0, confidence=1.0)
    card = ScoreCard(
        ticker="X.NS", investment_score=50.0, multibagger_score=50.0,
        confidence=0.5, pillars=base_pillars + [sector], verdict="test",
    )
    # all base pillars at 50, weights renormalize to 0.88; sector 90 at 0.12
    assert augmented_multibagger(card) == pytest.approx(0.88 * 50 + 0.12 * 90, abs=0.05)


def test_augmented_multibagger_respects_hard_gate_cap():
    pillars_ = [
        PillarScore(name=n, score=80.0, confidence=1.0)
        for n in ("Growth", "Quality", "Size Runway", "Valuation", "Momentum", "Reinvestment")
    ] + [PillarScore(name="Sector Momentum", score=95.0, confidence=1.0)]
    card = ScoreCard(
        ticker="X.NS", investment_score=50.0, multibagger_score=35.0,
        confidence=0.5, pillars=pillars_, hard_gate_failures=["accruals gate"],
        verdict="test",
    )
    assert augmented_multibagger(card) == 35.0


def test_augmented_falls_back_without_sector_pillar():
    card = ScoreCard(
        ticker="X.NS", investment_score=50.0, multibagger_score=61.5,
        confidence=0.5, pillars=[], verdict="test",
    )
    assert augmented_multibagger(card) == 61.5


def test_apply_sector_pillar_descriptive_mode_leaves_score():
    bundles, ctx = _hot_group_ctx()
    before = {b.info.ticker: b.card.multibagger_score for b in bundles}
    apply_sector_pillar(bundles, ctx, adjust_score=False)
    for b in bundles:
        assert b.card.multibagger_score == before[b.info.ticker]
        assert b.card.pillar("Sector Momentum") is not None


from mbe.scoring.sector_themes import (
    CURATED_AS_OF,
    KNOWN_YAHOO_SECTORS,
    THEMES,
    themes_for,
)


def test_theme_table_is_valid():
    assert CURATED_AS_OF is not None
    for key, themes in THEMES.items():
        assert key.strip() == key and key
        # typo guard: a key that case-insensitively matches a Yahoo sector
        # must match it exactly
        for known in KNOWN_YAHOO_SECTORS:
            if key.lower() == known.lower():
                assert key == known
        assert themes, f"{key} has no themes"
        for t in themes:
            assert t.direction in ("tailwind", "headwind")
            assert t.theme and t.reason


def test_themes_for_industry_beats_sector():
    semis = themes_for("Technology", "Semiconductors")
    assert any("AI" in t.theme for t in semis)
    # unknown industry falls back to sector-level tags if any, else []
    assert themes_for(None, "Nonexistent Industry") == []


def test_it_services_carries_both_directions():
    tags = themes_for("Technology", "Information Technology Services")
    directions = {t.direction for t in tags}
    assert directions == {"tailwind", "headwind"}


from mbe.pipeline import screen


class SectorStubProvider:
    """5 same-industry tickers with full statements and 320 price days."""

    def get_info(self, ticker):
        return CompanyInfo(
            ticker=ticker, name="Stub Co", market_cap=3e10,
            shares_outstanding=1e8, currency="INR",
            sector="Technology", industry="Semiconductors",
        )

    def get_financials(self, ticker):
        from mbe.models.company import FinancialHistory

        years = [2019, 2020, 2021, 2022, 2023, 2024]
        data = {
            "revenue": [100, 115, 132, 152, 175, 200],
            "net_income": [10, 12, 15, 18, 22, 26],
            "operating_income": [15, 17, 20, 24, 28, 33],
            "ebitda": [20, 23, 27, 32, 37, 43],
            "interest_expense": [4, 4, 4, 4, 4, 4],
            "total_assets": [300, 340, 385, 435, 490, 550],
            "total_equity": [60, 70, 82, 96, 112, 130],
            "total_debt": [40, 40, 40, 40, 40, 40],
            "cash": [10, 12, 14, 16, 18, 20],
            "current_assets": [50, 55, 60, 65, 70, 75],
            "current_liabilities": [25, 27, 29, 31, 33, 35],
            "cfo": [12, 14, 18, 22, 26, 30],
            "capex": [5, 6, 7, 8, 9, 10],
            "fcf": [7, 8, 11, 14, 17, 20],
            "shares_diluted": [100, 100, 100, 100, 100, 100],
        }
        return FinancialHistory(
            data={f: dict(zip(years, v)) for f, v in data.items()}
        )

    def get_prices(self, ticker, years: int = 3):
        return _price_history(list(np.linspace(100, 150, 320)))

    def benchmark_ticker(self, ticker):
        return "^NSEI"


def test_screen_attaches_sector_pillar_and_ranking():
    tickers = [f"S{i}.NS" for i in range(5)]
    result = screen(tickers, SectorStubProvider())
    assert len(result.ranked) == 5
    assert result.sector_scores and result.sector_scores[0].name == "Semiconductors"
    for b in result.ranked:
        pillar = b.card.pillar("Sector Momentum")
        assert pillar is not None and pillar.confidence > 0
