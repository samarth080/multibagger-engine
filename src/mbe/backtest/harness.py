"""Backtest harness: does the score actually predict forward returns?

For each cutoff date, every ticker is analyzed strictly point-in-time
(see pointintime.py), ranked by the chosen score, and compared against
realized forward returns. Outputs per-cutoff Spearman information
coefficient, top-vs-bottom quantile spread, and hit rate.

This is a validation instrument, not a strategy simulator: no costs,
no slippage, no survivorship correction (today's constituent lists are
used — survivorship bias is real and stated in every report).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from pydantic import BaseModel
from scipy import stats

from mbe.analysis.business import assess_business
from mbe.analysis.fundamentals import compute_fundamentals
from mbe.analysis.risk import assess_risk
from mbe.thesis.engine import build_thesis, critique_thesis
from mbe.analysis.technicals import compute_technicals
from mbe.analysis.valuation import compute_valuation
from mbe.backtest.pointintime import (
    sanitize_info_as_of,
    truncate_financials,
    truncate_prices,
)
from mbe.data.provider import DataProvider, ProviderError
from mbe.models.company import PriceHistory
from mbe.pipeline import AnalysisBundle
from mbe.scoring.engine import build_scorecard

MIN_PRICE_DAYS = 200
MIN_STATEMENT_YEARS = 2
MIN_TICKERS_FOR_IC = 4
PRICE_YEARS = 18  # full available history; enables cutoffs back to ~2012


class CutoffResult(BaseModel):
    cutoff: date
    ic: float | None
    top_q_mean: float | None
    bottom_q_mean: float | None
    spread: float | None
    hit_rate: float | None
    n: int


class BacktestReport(BaseModel):
    universe_name: str
    score_name: str
    horizon_days: int
    cutoffs: list[CutoffResult]
    mean_ic: float | None
    skipped: dict[str, str]
    # cutoff ISO date -> ticker -> (score, forward_return); only when requested
    raw_panel: dict[str, dict[str, tuple[float, float]]] | None = None


def evaluate_cutoff(
    scores: dict[str, float],
    fwd_returns: dict[str, float],
    quantiles: int = 5,
) -> dict:
    common = sorted(set(scores) & set(fwd_returns))
    n = len(common)
    if n < MIN_TICKERS_FOR_IC:
        return {"ic": None, "top_q_mean": None, "bottom_q_mean": None,
                "spread": None, "hit_rate": None, "n": n}

    s = [scores[t] for t in common]
    r = [fwd_returns[t] for t in common]
    if len(set(s)) < 2 or len(set(r)) < 2:
        ic = None  # constant input: rank correlation undefined, no information
    else:
        ic = float(stats.spearmanr(s, r).statistic)

    q = max(2, min(quantiles, n // 2))
    ranked = sorted(common, key=lambda t: scores[t], reverse=True)
    bucket = max(1, n // q)
    top, bottom = ranked[:bucket], ranked[-bucket:]
    top_mean = sum(fwd_returns[t] for t in top) / len(top)
    bottom_mean = sum(fwd_returns[t] for t in bottom) / len(bottom)

    median_ret = sorted(r)[n // 2]
    hit_rate = sum(1 for t in top if fwd_returns[t] > median_ret) / len(top)

    return {
        "ic": ic,
        "top_q_mean": top_mean,
        "bottom_q_mean": bottom_mean,
        "spread": top_mean - bottom_mean,
        "hit_rate": hit_rate,
        "n": n,
    }


def forward_return(
    prices: PriceHistory, cutoff: date, horizon_days: int
) -> float | None:
    df = prices.df
    upto_cutoff = df[df.index <= pd.Timestamp(cutoff)]
    if upto_cutoff.empty:
        return None
    end_ts = pd.Timestamp(cutoff) + pd.Timedelta(days=horizon_days)
    upto_end = df[df.index <= end_ts]
    # require ~90% of the horizon to have elapsed in the data
    if (upto_end.index.max() - pd.Timestamp(cutoff)).days < horizon_days * 0.9:
        return None
    start = float(upto_cutoff["close"].iloc[-1])
    end = float(upto_end["close"].iloc[-1])
    return end / start - 1 if start > 0 else None


def analyze_as_of(
    ticker: str,
    provider: DataProvider,
    cutoff: date,
    require_statements: bool = True,
) -> tuple[AnalysisBundle, PriceHistory]:
    """Point-in-time analysis. Returns the bundle plus the full (untruncated)
    price history so the caller can compute forward returns from the same data.

    Technical-only callers pass require_statements=False: prices reach back
    ~10 years while statements reach ~5, so momentum cutoffs may legitimately
    predate any available fundamentals."""
    from mbe.models.company import FinancialHistory

    info_now = provider.get_info(ticker)
    try:
        fin = truncate_financials(provider.get_financials(ticker), cutoff)
    except ProviderError:
        if require_statements:
            raise
        fin = FinancialHistory(data={})
    full_prices = provider.get_prices(ticker, years=PRICE_YEARS)
    prices = truncate_prices(full_prices, cutoff)

    if len(prices.df) < MIN_PRICE_DAYS:
        raise ProviderError(f"only {len(prices.df)} price days before {cutoff}")
    if require_statements and len(fin.years()) < MIN_STATEMENT_YEARS:
        raise ProviderError(f"only {len(fin.years())} statement years before {cutoff}")

    benchmark = None
    try:
        benchmark = truncate_prices(
            provider.get_prices(provider.benchmark_ticker(ticker), years=PRICE_YEARS),
            cutoff,
        )
    except ProviderError:
        pass

    cutoff_price = prices.last_close()
    info = sanitize_info_as_of(info_now, cutoff_price)

    fund = compute_fundamentals(fin, info)
    tech = compute_technicals(prices, benchmark)
    val = compute_valuation(fin, info, fund, cutoff_price or 0.0)
    risk = assess_risk(fin, fund, tech, val, info)
    card = build_scorecard(info, fund, tech, val, risk, fin, price_days=len(prices.df))
    business = assess_business(fin, info, fund)
    thesis = build_thesis(info, fund, business, val, risk)
    critique = critique_thesis(thesis, fund, business, val, risk)

    bundle = AnalysisBundle(
        info=info, fin=fin, fund=fund, tech=tech, val=val, risk=risk,
        card=card, as_of=cutoff, business=business, thesis=thesis, critique=critique,
    )
    return bundle, full_prices


_TECHNICAL_ONLY_SCORES = {"momentum", "Momentum"}


def _extract_score(bundle: AnalysisBundle, score_name: str) -> float:
    if score_name == "multibagger":
        return bundle.card.multibagger_score
    if score_name == "investment":
        return bundle.card.investment_score
    if score_name == "franchise":
        return bundle.business.franchise_score if bundle.business else 0.0
    if score_name == "momentum":
        score_name = "Momentum"
    pillar = bundle.card.pillar(score_name)
    if pillar is not None:
        return pillar.score
    raise ValueError(f"unknown score {score_name!r}")


def run_backtest_multi(
    tickers: list[str],
    provider: DataProvider,
    cutoffs: list[date],
    horizon_days: int,
    score_names: list[str],
    universe_name: str = "",
    collect_raw: bool = False,
) -> dict[str, BacktestReport]:
    """One point-in-time analysis pass, evaluated against every requested
    score (composites and individual pillars) — pillar attribution without
    re-fetching or re-analyzing per score."""
    per_score_results: dict[str, list[CutoffResult]] = {s: [] for s in score_names}
    raw: dict[str, dict[str, dict[str, tuple[float, float]]]] = {
        s: {} for s in score_names
    }
    skipped: dict[str, str] = {}
    needs_statements = any(s not in _TECHNICAL_ONLY_SCORES for s in score_names)

    for cutoff in cutoffs:
        scores: dict[str, dict[str, float]] = {s: {} for s in score_names}
        fwd: dict[str, float] = {}
        for ticker in tickers:
            try:
                bundle, full_prices = analyze_as_of(
                    ticker, provider, cutoff, require_statements=needs_statements
                )
            except ProviderError as exc:
                skipped[f"{ticker}@{cutoff}"] = str(exc)
                continue
            except Exception as exc:
                skipped[f"{ticker}@{cutoff}"] = f"unexpected: {exc!r}"
                continue
            ret = forward_return(full_prices, cutoff, horizon_days)
            if ret is None:
                skipped[f"{ticker}@{cutoff}"] = "forward window incomplete"
                continue
            fwd[ticker] = ret
            for name in score_names:
                scores[name][ticker] = _extract_score(bundle, name)
        for name in score_names:
            per_score_results[name].append(
                CutoffResult(cutoff=cutoff, **evaluate_cutoff(scores[name], fwd))
            )
            if collect_raw:
                raw[name][cutoff.isoformat()] = {
                    t: (scores[name][t], fwd[t]) for t in scores[name]
                }

    reports: dict[str, BacktestReport] = {}
    for name in score_names:
        ics = [c.ic for c in per_score_results[name] if c.ic is not None]
        reports[name] = BacktestReport(
            universe_name=universe_name,
            score_name=name,
            horizon_days=horizon_days,
            cutoffs=per_score_results[name],
            mean_ic=sum(ics) / len(ics) if ics else None,
            skipped=dict(skipped),
            raw_panel=raw[name] if collect_raw else None,
        )
    return reports


def run_backtest(
    tickers: list[str],
    provider: DataProvider,
    cutoffs: list[date],
    horizon_days: int,
    score_name: str = "multibagger",
    universe_name: str = "",
) -> BacktestReport:
    return run_backtest_multi(
        tickers, provider, cutoffs, horizon_days, [score_name], universe_name
    )[score_name]


def render_backtest_md(report: BacktestReport) -> str:
    def fmt(v, pct=False):
        if v is None:
            return "n/a"
        return f"{v * 100:.1f}%" if pct else f"{v:.3f}"

    lines = [
        f"# Backtest: {report.score_name} score on {report.universe_name}",
        "",
        f"Horizon: {report.horizon_days} days | Mean Information coefficient "
        f"(Spearman IC): **{fmt(report.mean_ic)}**",
        "",
        "| Cutoff | IC | Top-quantile fwd | Bottom-quantile fwd | Spread | Hit rate | N |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in report.cutoffs:
        lines.append(
            f"| {c.cutoff} | {fmt(c.ic)} | {fmt(c.top_q_mean, pct=True)} | "
            f"{fmt(c.bottom_q_mean, pct=True)} | {fmt(c.spread, pct=True)} | "
            f"{fmt(c.hit_rate, pct=True)} | {c.n} |"
        )
    lines += [
        "",
        "## Methodology & caveats",
        "",
        "- Strict point-in-time inputs: statements gated by fiscal-year end + 90-day "
        "filing lag; prices truncated at cutoff; present-day holdings/PE/beta "
        "excluded from inputs (no lookahead).",
        "- Market cap at cutoff approximated as current share count x cutoff price.",
        "- **Survivorship bias:** universe membership is today's list; delisted "
        "losers are absent, which flatters absolute returns. Interpret IC and "
        "relative spreads, not absolute performance.",
        "- Yahoo statement history (~5 fiscal years) limits usable cutoffs; a deeper "
        "fundamentals provider extends this harness without code changes.",
        "- No transaction costs or slippage: a validation instrument, not a strategy sim.",
    ]
    if report.skipped:
        lines += ["", f"## Skipped ({len(report.skipped)})", ""]
        for key, reason in list(report.skipped.items())[:40]:
            lines.append(f"- {key}: {reason}")
        if len(report.skipped) > 40:
            lines.append(f"- … and {len(report.skipped) - 40} more")
    return "\n".join(lines)
