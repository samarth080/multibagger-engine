"""Deterministic, explainable peer selection for one compatible model build."""

from __future__ import annotations

from mbe.research.domain import PEER_POLICY_VERSION


def _distance(left: float | None, right: float | None, *, scale: float) -> float:
    if left is None or right is None:
        return 0.0
    return max(0.0, scale - abs(float(left) - float(right)) * scale)


def select_peers(target: dict, candidates: list[dict], *, limit: int = 6) -> list[dict]:
    """Prefer industry, then sector, with stable compatible-value tie breaks."""
    if limit < 1 or limit > 8:
        raise ValueError("peer limit must be between 1 and 8")
    ranked = []
    for row in candidates:
        if row.get("instrument_id") == target.get("instrument_id"):
            continue
        same_industry = bool(target.get("industry") and row.get("industry") == target.get("industry"))
        same_sector = bool(target.get("sector") and row.get("sector") == target.get("sector"))
        if not same_industry and not same_sector:
            continue
        reasons = ["Same industry" if same_industry else "Same sector"]
        score = 100.0 if same_industry else 65.0
        if target.get("market_cap_category") and row.get("market_cap_category") == target.get("market_cap_category"):
            score += 15.0
            reasons.append("Same market-cap category")
        score_gap = abs(float(target["multibagger_score"]) - float(row["multibagger_score"]))
        score += max(0.0, 20.0 - score_gap)
        if score_gap <= 5:
            reasons.append("Similar Multibagger Score")
        growth_bonus = _distance(target.get("revenue_cagr_3y"), row.get("revenue_cagr_3y"), scale=10.0)
        roce_bonus = _distance(target.get("roce_3y"), row.get("roce_3y"), scale=10.0)
        score += growth_bonus + roce_bonus
        if growth_bonus >= 8:
            reasons.append("Similar accepted revenue growth")
        if roce_bonus >= 8:
            reasons.append("Similar accepted ROCE")
        ranked.append({**row, "selection_score": round(score, 4), "selection_reasons": reasons,
                       "peer_policy_version": PEER_POLICY_VERSION})
    return sorted(
        ranked,
        key=lambda item: (-item["selection_score"], int(item.get("rank") or 10**9), str(item["instrument_id"])),
    )[:limit]
