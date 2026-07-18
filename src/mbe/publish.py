"""Static-site builder for the hosted weekly picks page.

build_data() turns a ScreenResult (+news/policy) into a JSON-serializable
dict; diff_weeks() computes the week-over-week changes strip; render_site()
writes index.html and per-pick report pages. Descriptive layers (sector
ranks, tags, news, policy) are displayed, never scored — the ranking is the
base multibagger score, per the P2.4 ablation verdict."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import markdown as md
from jinja2 import Environment

from mbe.data.news_rss import NewsItem
from mbe.pipeline import ScreenResult
from mbe.report.markdown import render_report
from mbe.scoring.sector_themes import CURATED_AS_OF, themes_for

TOP_N = 25

VALIDATION_FOOTER = (
    "Model validation status: the multibagger score showed a cross-sample-"
    "consistent 2-year IC of +0.16/+0.10 on disjoint Indian smallcap samples "
    "(2016-2023 cutoffs) — a modest, survivorship-biased edge, not a "
    "guarantee. Sector momentum failed its pre-registered ablation and is "
    "shown as context only, never scored. Research tooling, not investment "
    "advice."
)


def build_data(
    result: ScreenResult,
    news_by_ticker: dict[str, list[NewsItem]],
    policy: list[NewsItem],
    built_at: datetime | None = None,
) -> dict:
    built_at = built_at or datetime.now(timezone.utc)
    group_of: dict[str, tuple[str, int, float]] = {}
    for rank, s in enumerate(result.sector_scores, 1):
        for t in s.members:
            group_of[t] = (s.name, rank, s.score)

    top = []
    for b in result.ranked[:TOP_N]:
        t = b.card.ticker
        group, group_rank, group_score = group_of.get(t, ("", 0, 0.0))
        top.append(
            {
                "ticker": t,
                "name": b.info.name or t,
                "mb": b.card.multibagger_score,
                "inv": b.card.investment_score,
                "conf": b.card.confidence,
                "risk": int(b.risk.risk_score),
                "trend": b.tech.trend_state,
                "price_at_build": b.tech.price,
                "group": group,
                "group_rank": group_rank,
                "group_score": group_score,
                "tags": [
                    {"theme": th.theme, "direction": th.direction}
                    for th in themes_for(b.info.sector, b.info.industry)
                ],
                "news": [i.model_dump(mode="json") for i in news_by_ticker.get(t, [])],
                "gated": bool(b.card.hard_gate_failures),
            }
        )
    return {
        "built_at": built_at.isoformat(),
        "universe": "nifty-smallcap250",
        "curated_as_of": CURATED_AS_OF.isoformat(),
        "top": top,
        "sectors": [
            {"rank": i, "name": s.name, "level": s.level, "score": s.score, "n": s.n}
            for i, s in enumerate(result.sector_scores, 1)
        ],
        "policy": [i.model_dump(mode="json") for i in policy],
    }


def diff_weeks(prev: dict | None, new: dict) -> dict:
    """Who entered/left the published top table vs last week's data.json."""
    new_t = [row["ticker"] for row in new["top"]]
    prev_t = [row["ticker"] for row in (prev or {}).get("top", [])]
    return {
        "entered": [t for t in new_t if t not in prev_t],
        "exited": [t for t in prev_t if t not in new_t],
    }
