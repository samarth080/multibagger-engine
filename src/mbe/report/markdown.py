"""Institutional-style markdown research report + screener table."""

from __future__ import annotations

from jinja2 import Environment

from mbe.pipeline import AnalysisBundle, ScreenResult


def _pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def _num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def _money(value: float | None, currency: str | None) -> str:
    if value is None:
        return "n/a"
    if currency == "INR":
        return f"Rs {value / 1e7:,.0f} cr"
    return f"${value / 1e9:,.2f}B"


_ENV = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
_ENV.filters["pct"] = _pct
_ENV.filters["num"] = _num

_TEMPLATE = _ENV.from_string("""\
# Equity Research Report: {{ info.name or info.ticker }} ({{ info.ticker }})

*Generated {{ as_of }} by Multibagger Engine v0.1 — evidence-driven, confidence-scored.*

## Executive Summary

| | |
|---|---|
| **Verdict** | {{ card.verdict }} |
| **Investment Score** | {{ card.investment_score }} / 100 |
| **Multibagger Score** | {{ card.multibagger_score }} / 100 |
| **Confidence** | {{ (card.confidence * 100) | round(0) | int }}% |
| **Risk** | {{ risk.risk_score | int }} / 100 ({{ risk.permanent_loss_bucket }} probability of permanent loss) |
| **Price** | {{ val.price | num }} {{ info.currency or "" }} |
| **Base fair value (DCF)** | {{ val.fair_value_base | num }} — margin of safety {{ val.margin_of_safety | pct }} |
| **Market cap** | {{ market_cap_str }} |
{% if card.hard_gate_failures %}
**HARD GATE FAILURES** (multibagger score capped):
{% for failure in card.hard_gate_failures %}
- {{ failure }}
{% endfor %}
{% endif %}

## Investment Thesis

{% for pillar in card.pillars if pillar.evidence %}
- **{{ pillar.name }} {{ pillar.score | round(0) | int }}/100** (data coverage {{ (pillar.confidence * 100) | round(0) | int }}%): {{ pillar.evidence[0].rationale }} — {{ pillar.evidence[0].metric }} = {{ pillar.evidence[0].value }}.
{% endfor %}

## Business Overview

- Sector: {{ info.sector or "n/a" }} | Industry: {{ info.industry or "n/a" }}
- Insider/promoter holding: {{ info.insider_pct | pct }} | Institutional: {{ info.institution_pct | pct }}

{{ (info.description or "No business description available from the current data source.")[:900] }}

{% if thesis %}
## Business & Investment Thesis

**Franchise classification:** {{ business.classification }} — franchise score
{{ business.franchise_score }}/100 over {{ business.history_years }} years of history.
*(Franchise score is descriptive only: backtests found it does not predict
forward returns better than the base score — see Model validation status.)*

{{ thesis.business_summary }}

**Why it might compound:**
{% for p in thesis.bull_pillars %}
- {{ p }}
{% endfor %}

**Key assumptions** — each with the share of the company's own history in which it held:

| Assumption | Historical support | Currently true? |
|---|---|---|
{% for a in thesis.assumptions %}
| {{ a.statement }} | {{ (a.historical_support * 100) | round(0) | int }}% | {{ "yes" if a.currently_true else "**NO**" }} |
{% endfor %}

**What would break the thesis (falsifiers):**
{% for f in thesis.falsifiers %}
- {{ f }}
{% endfor %}

**Business trajectory**
- **Bull:** {{ thesis.trajectory_bull }}
- **Base:** {{ thesis.trajectory_base }}
- **Bear:** {{ thesis.trajectory_bear }}

### Self-critique (devil's advocate)

{% if critique.disconfirmers %}
Before recommending, the platform searched for reasons *not* to invest:
{% for d in critique.disconfirmers %}
- {{ d }}
{% endfor %}
{% else %}
No material disconfirming evidence surfaced by the critique rules.
{% endif %}

**Post-critique recommendation: {{ critique.recommendation }}**
(thesis confidence {{ (thesis.thesis_confidence * 100) | round(0) | int }}%{% if critique.veto %}; **VETOED** — thesis rejected before recommendation{% endif %})

*The critique exists for reasoning transparency. Backtests found the veto does
NOT reliably avoid worse outcomes (vetoed names had higher volatility in both
directions) — treat it as a list of concerns to weigh, not a validated filter.*
{% endif %}

## Financial Analysis

| Metric | Value | Metric | Value |
|---|---|---|---|
| Revenue CAGR 3y | {{ fund.revenue_cagr_3y | pct }} | ROCE (3y avg) | {{ fund.roce_3y | pct }} |
| Profit CAGR 3y | {{ fund.profit_cagr_3y | pct }} | ROE (3y avg) | {{ fund.roe_3y | pct }} |
| FCF CAGR 3y | {{ fund.fcf_cagr_3y | pct }} | ROIC (latest) | {{ fund.roic | pct }} |
| Operating margin | {{ fund.operating_margin | pct }} | Debt / equity | {{ fund.debt_to_equity | num }} |
| Margin trend (3y) | {{ fund.margin_trend | pct }} | Interest coverage | {{ fund.interest_coverage | num(1) }}x |
| Net margin | {{ fund.net_margin | pct }} | Net debt / EBITDA | {{ fund.net_debt_to_ebitda | num }} |
| FCF margin | {{ fund.fcf_margin | pct }} | Current ratio | {{ fund.current_ratio | num }} |
| Cash conversion (CFO/NI) | {{ fund.cash_conversion | num }} | Accruals ratio | {{ fund.accruals_ratio | num(3) }} |
| Reinvestment (capex/CFO) | {{ fund.reinvestment_rate | pct }} | Share count CAGR 3y | {{ fund.share_count_cagr_3y | pct }} |

Statement data completeness: {{ (fund.completeness * 100) | round(0) | int }}%.

## Technical Analysis

- Trend: **{{ tech.trend_state }}** | Volatility regime: {{ tech.volatility_regime }} (ATR {{ tech.atr_pct | num(1) }}%)
- Price vs 200-day MA: {{ tech.price_vs_200sma | pct }} | 200-day MA slope (20d): {{ tech.sma200_slope_20d | pct }}
- RSI(14): {{ tech.rsi14 | num(0) }} | MACD histogram: {{ tech.macd_hist | num(2) }} | ADX(14): {{ tech.adx14 | num(0) }}
- 52-week: {{ tech.dist_52w_high | pct }} from high, {{ tech.dist_52w_low | pct }} above low
- Relative strength vs index (63d): {{ tech.relative_strength_63d | pct }}
- Accumulation: CMF(20) {{ tech.cmf20 | num(2) }}, OBV 20d slope {{ tech.obv_slope_20d | num(2) }}
- Avg daily traded value (20d): {{ tech.avg_traded_value_20d | num(0) }} {{ info.currency or "" }}

## Valuation

| Scenario | Fair value / share | vs price |
|---|---|---|
| Bear (g = {{ val.assumptions.get("g_bear") | pct }}) | {{ val.fair_value_bear | num }} | {{ pct_vs(val.fair_value_bear, val.price) }} |
| Base (g = {{ val.assumptions.get("g_base") | pct }}) | {{ val.fair_value_base | num }} | {{ pct_vs(val.fair_value_base, val.price) }} |
| Bull (g = {{ val.assumptions.get("g_bull") | pct }}) | {{ val.fair_value_bull | num }} | {{ pct_vs(val.fair_value_bull, val.price) }} |

- Reverse DCF: the market is pricing **{{ val.implied_growth | pct }}** FCF growth (delivered: {{ fund.profit_cagr_3y | pct }} profit CAGR).
- Multiples: P/E {{ val.pe | num(1) }} | PEG {{ val.peg | num(2) }} | EV/EBITDA {{ val.ev_ebitda | num(1) }} | P/S {{ val.price_to_sales | num(1) }} | FCF yield {{ val.fcf_yield | pct }}
- Expected 5y CAGR if price converges to base fair value: **{{ val.expected_cagr_5y | pct }}**
- Assumptions: discount {{ val.assumptions.get("discount") | pct }}, terminal {{ val.assumptions.get("terminal") | pct }}{% if val.fcf_proxy_used %}; **FCF proxy used** (0.8 x avg net income — treat DCF with extra skepticism){% endif %}

## Risk Analysis

Risk score: **{{ risk.risk_score | int }}/100** — {{ risk.permanent_loss_bucket }} probability of permanent capital loss.

{% if risk.flags %}
| Flag | Severity | Detail |
|---|---|---|
{% for flag in risk.flags %}
| {{ flag.code }} | {{ ["info", "warning", "CRITICAL"][flag.severity - 1] }} | {{ flag.detail }} |
{% endfor %}
{% else %}
No risk flags triggered by the current rule set.
{% endif %}

## Bull / Base / Bear

- **Bull:** growth sustains at {{ val.assumptions.get("g_bull") | pct }}, fair value {{ val.fair_value_bull | num }} ({{ pct_vs(val.fair_value_bull, val.price) }}).
- **Base:** delivered-growth median of {{ val.assumptions.get("g_base") | pct }} continues 5 years then fades, fair value {{ val.fair_value_base | num }} ({{ pct_vs(val.fair_value_base, val.price) }}).
- **Bear:** growth decays to {{ val.assumptions.get("g_bear") | pct }}, fair value {{ val.fair_value_bear | num }} ({{ pct_vs(val.fair_value_bear, val.price) }}).

## Entry & Exit Framework

- Trend state is **{{ tech.trend_state }}**; {{ entry_guidance }}
- Reference levels: 50-day MA {{ tech.sma50 | num }}, 200-day MA {{ tech.sma200 | num }}.
- Volatility stop suggestion: {{ stop_level }} (2.5 x ATR below current price).
- Invalidation: close below the 200-day MA on rising volume, or any hard-gate metric deteriorating.

## Position Sizing

{{ sizing_guidance }}

## Catalysts & Policy Tailwinds

*Macro, government-policy and news catalyst modules arrive in v0.3 — this section will populate automatically. Until then, verify PLI/policy exposure manually.*

## Score Evidence Appendix

{% for pillar in card.pillars if pillar.evidence %}
### {{ pillar.name }} — {{ pillar.score | round(1) }}/100 (coverage {{ (pillar.confidence * 100) | round(0) | int }}%)

| Metric | Value | Benchmark applied | Points | Weight |
|---|---|---|---|---|
{% for ev in pillar.evidence %}
| {{ ev.metric }} | {{ ev.value }} | {{ ev.benchmark }} | {{ ev.points | int }} | {{ ev.weight }} |
{% endfor %}

{% endfor %}
## Data Gaps & Sources

- Source: Yahoo Finance (statements, prices, holdings). Statement completeness {{ (fund.completeness * 100) | round(0) | int }}%, technical {{ (tech.completeness * 100) | round(0) | int }}%, valuation {{ (val.completeness * 100) | round(0) | int }}%.
- Not yet covered by this engine version: promoter pledging, detailed shareholding pattern (FII/DII), auditor history, con-call analysis, order books, government-policy mapping.

## Model validation status

Backtests to date (US small/large caps 2012-2025, Indian small/midcaps
2021-2025; point-in-time, survivorship-biased current-constituent samples) show
**no demonstrated persistent predictive edge** for these scores; cross-sample
agreement appears only in isolated regimes (2021-22 quality rally). Ablations
additionally found the franchise-durability score does **not** out-predict the
base score, and the self-critique veto does **not** avoid worse outcomes. Treat
scores, classifications, and critiques as a structured evidence summary, not a
return forecast. Full record: `docs/backtest-findings-2026-07.md`.

## Disclaimer

Research tooling output, not investment advice. Scores are model artifacts with
stated assumptions and incomplete data. Verify independently before any decision.
""")


def _entry_guidance(bundle: AnalysisBundle) -> str:
    trend = bundle.tech.trend_state
    if trend in ("strong_up", "up"):
        return "pullbacks toward the 50-day MA within an intact uptrend are the preferred accumulation zone."
    if trend == "sideways":
        return "wait for a base breakout on above-average volume before committing capital."
    return "no technical entry — falling knife; wait for a confirmed trend reversal above the 200-day MA."


def sizing_guidance(bundle: AnalysisBundle) -> str:
    if bundle.card.investment_score < 45:
        return ("**No new position** — the overall verdict is Avoid at current "
                "evidence; sizing is moot until fundamentals, technicals, or "
                "price improve.")
    bucket = bundle.risk.permanent_loss_bucket
    if bucket == "low":
        return ("Risk bucket **low**: up to a full position (3-5% of portfolio), "
                "built in 2-3 tranches.")
    if bucket == "medium":
        return ("Risk bucket **medium**: half position maximum (1.5-2.5% of portfolio); "
                "add only after risk flags resolve.")
    return ("Risk bucket **high**: speculative sizing only (<=1% of portfolio) "
            "or avoid entirely; multiple critical flags active.")


def render_report(bundle: AnalysisBundle) -> str:
    def pct_vs(fair: float | None, price: float | None) -> str:
        if fair is None or not price:
            return "n/a"
        return f"{(fair / price - 1) * 100:+.0f}%"

    stop = "n/a"
    if bundle.tech.price and bundle.tech.atr_pct:
        stop = f"{bundle.tech.price * (1 - 2.5 * bundle.tech.atr_pct / 100):,.2f}"

    return _TEMPLATE.render(
        info=bundle.info,
        fund=bundle.fund,
        tech=bundle.tech,
        val=bundle.val,
        risk=bundle.risk,
        card=bundle.card,
        business=bundle.business,
        thesis=bundle.thesis,
        critique=bundle.critique,
        as_of=bundle.as_of,
        market_cap_str=_money(bundle.info.market_cap, bundle.info.currency),
        pct_vs=pct_vs,
        entry_guidance=_entry_guidance(bundle),
        sizing_guidance=sizing_guidance(bundle),
        stop_level=stop,
    )


def render_screen_table(result: ScreenResult) -> str:
    lines = [
        "| Rank | Ticker | Name | Multibagger | Investment | Confidence | Risk | Trend | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, b in enumerate(result.ranked, 1):
        lines.append(
            f"| {i} | {b.card.ticker} | {(b.info.name or '')[:24]} | "
            f"{b.card.multibagger_score} | {b.card.investment_score} | "
            f"{b.card.confidence:.2f} | {int(b.risk.risk_score)} | "
            f"{b.tech.trend_state} | {b.card.verdict[:48]} |"
        )
    if result.failures:
        lines.append("")
        lines.append("**Failed tickers:** " + ", ".join(
            f"{t} ({msg[:60]})" for t, msg in result.failures.items()
        ))
    return "\n".join(lines)
