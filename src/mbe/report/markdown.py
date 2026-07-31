"""Institutional-style markdown research report + screener table."""

from __future__ import annotations

from jinja2 import Environment

from mbe.data.news_rss import NewsItem
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
- Sector momentum: {{ sector_momentum_line }}
{% if sector_themes %}- Sector themes (curated {{ themes_curated_as_of }}, descriptive only — not scored):
{% for t in sector_themes %}  - {{ "▲" if t.direction == "tailwind" else "▼" }} {{ t.theme }} — {{ t.reason }}
{% endfor %}{% endif %}
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

{% if stewardship %}
### Management & capital allocation (stewardship)

**{{ stewardship.classification }}** — stewardship score {{ stewardship.stewardship_score }}/100
over {{ stewardship.history_years }} years. {{ stewardship.allocation_fit_label | capitalize }}.

| Signal | Value |
|---|---|
| Full-history share count CAGR | {{ stewardship.share_cagr_full | pct }} |
| Years diluting >2% | {{ stewardship.dilution_years_frac | pct(0) }} |
| Years buying back | {{ stewardship.buyback_years_frac | pct(0) }} |
| Debt CAGR minus EBIT CAGR | {{ stewardship.debt_ebit_gap | pct }} |
| Years with interest coverage < 2 | {{ stewardship.coverage_stress_frac | pct(0) }} |
| Years returning cash (dividends) | {{ stewardship.dividend_consistency | pct(0) }} |

*(Descriptive assessment of the capital-allocation record; like all scores here,
not a validated return predictor — see Model validation status.)*
{% endif %}

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

## Ownership

{% if charts.ownership %}
{{ charts.ownership }}
{% if charts.ownership_note %}
**⚠ {{ charts.ownership_note }}.**
{% endif %}

*Yahoo's "insider" is not SEBI's promoter category, and this is not the promoter/FII/DII/public breakdown an Indian investor expects — that data is not in this pipeline. Descriptive only, never scored.*
{% else %}
*Ownership split not reported by the data source.*
{% endif %}

## Financial Analysis

{% if charts.trend %}
{{ charts.trend }}
{% endif %}

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

{# spike == spike is a NaN test, not a tautology: fcf_spike_ratio is stored as
   NaN when no 3-year mean is definable, and NaN != NaN. Do not "simplify" it.
   The `is not none` is a separate guard, for an assumptions dict that never had
   the key at all (ValuationResult() defaults to {}) — None == None is True, so
   the NaN test alone lets a missing key through into format() and raises.
   The blank lines are load-bearing too: trim_blocks eats the newline after
   every block tag, so without them this paragraph is glued onto the
   Assumptions bullet above and renders inside it. #}
{% set spike = val.assumptions.get("fcf_spike_ratio") %}
{% if spike is not none and spike == spike %}

Base FCF is the latest year's, not a trailing average — it stands at {{ "%.1f" | format(spike) }}x the 3-year mean. The risk that it does not repeat is carried by the bear scenario in the 3-Year Price Forecast below, not by a haircut to all three.
{% endif %}

## Peer Comparison

{% if charts.peer_table %}
{{ charts.peer_table }}
{% if charts.peer_scatter %}
{{ charts.peer_scatter }}
{% endif %}

*The peer group is this stock's industry cohort from the same screen. Descriptive only, never scored.*
{% else %}
*Peer comparison requires a universe screen — single-ticker analysis has no peer group.*
{% endif %}

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

## 3-Year Price Forecast

{% if forecast %}
Where the price could be in {{ forecast.horizon_years }} years, projected from FY{{ forecast.base_fiscal_year }} revenue and net margin against an exit multiple. Each scenario moves growth, margin **and** the multiple — not one knob three ways.

{% if charts.scenarios %}
{{ charts.scenarios }}

| Scenario | Prob. | Revenue growth | Net margin | Exit multiple | FY+3 EPS |
|---|---|---|---|---|---|
{% for s in forecast.scenarios %}
| **{{ s.name | capitalize }}** | {{ s.probability | pct }} | {{ s.growth_start | pct }} → {{ s.growth_end | pct }} | {{ s.terminal_net_margin | pct }} | {{ "%.1f" | format(s.exit_multiple) }}x | {{ s.eps_fy3 | num }} |
{% endfor %}
{% else %}
| Scenario | Prob. | Revenue growth | Net margin | Exit multiple | FY+3 EPS | Target | 3y CAGR |
|---|---|---|---|---|---|---|---|
{% for s in forecast.scenarios %}
| **{{ s.name | capitalize }}** | {{ s.probability | pct }} | {{ s.growth_start | pct }} → {{ s.growth_end | pct }} | {{ s.terminal_net_margin | pct }} | {{ "%.1f" | format(s.exit_multiple) }}x | {{ s.eps_fy3 | num }} | {{ s.target_price | num }} | {{ s.cagr_3y | pct }} |
{% endfor %}
{% endif %}

**Probability-weighted:** target {{ forecast.expected_target | num }}, expected 3y CAGR {{ forecast.expected_cagr_3y | pct }}. Probability of a target below today's price: {{ forecast.downside_probability | pct }}.

**Exit multiple anchor — {{ "%.1f" | format(forecast.anchor.anchor) }}x**

| Input | Value |
|---|---|
| Peer median P/E ({{ forecast.anchor.peer_n }} peers, leave-one-out) | {% if forecast.anchor.peer_pe %}{{ "%.1f" | format(forecast.anchor.peer_pe) }}x{% else %}not available{% endif %} |
| Own history median P/E | {% if forecast.anchor.own_pe_median %}{{ "%.1f" | format(forecast.anchor.own_pe_median) }}x{% else %}not available{% endif %} |
| Today's P/E within own history | {% if forecast.anchor.own_pe_percentile_now is not none %}{{ forecast.anchor.own_pe_percentile_now | pct }} percentile{% else %}not available{% endif %} |
| Quality multiplier (franchise score) | {{ "%.2f" | format(forecast.anchor.quality_multiplier) }}x |

{% for note in forecast.anchor.notes %}
- {{ note }}
{% endfor %}

**Scenario assumptions**

{# The blank lines are load-bearing: trim_blocks eats the newline after every
   block tag, so without them all three scenarios collapse into one paragraph
   with literal "- " dashes instead of three labelled lists. #}
{% for s in forecast.scenarios %}
*{{ s.name | capitalize }}:*

{% for e in s.evidence %}
- {{ e }}
{% endfor %}

{% endfor %}
*Forecast completeness {{ forecast.completeness | pct }}. A scenario model with
stated assumptions, not a prediction — see Model validation status.*
{% else %}
No forecast: no exit multiple could be anchored to either peer or own-history
multiples, and a forecast without an anchor would be arithmetic dressed up as a
view.
{% endif %}

## Entry & Exit Framework

- Trend state is **{{ tech.trend_state }}**; {{ entry_guidance }}
- Reference levels: 50-day MA {{ tech.sma50 | num }}, 200-day MA {{ tech.sma200 | num }}.
- Volatility stop suggestion: {{ stop_level }} (2.5 x ATR below current price).
- Invalidation: close below the 200-day MA on rising volume, or any hard-gate metric deteriorating.

## Position Sizing

{{ sizing_guidance }}

## Recent News & Policy Context

*Descriptive only — headlines are evidence to weigh, not catalysts the engine has identified. Never scored.*

**Company**

{% if news %}
{% for n in news %}
- [{{ n.title }}]({{ n.link }}){% if n.source %} — {{ n.source }}{% endif %}{% if n.age_days is not none %}, {{ n.age_days }}d ago{% endif +%}
{% endfor %}
{% else %}
*No recent company news found.*
{% endif +%}

**Sector policy{% if policy_key %} — {{ policy_key }}{% endif %}**

{% if not policy_key %}
*No sector classification — policy context unavailable.*
{% elif policy %}
{% for p in policy %}
- [{{ p.title }}]({{ p.link }}){% if p.source %} — {{ p.source }}{% endif %}{% if p.age_days is not none %}, {{ p.age_days }}d ago{% endif +%}
{% endfor %}
{% else %}
*No sector policy items found.*
{% endif +%}

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


def render_report(
    bundle: AnalysisBundle,
    news: list[NewsItem] | None = None,
    policy: list[NewsItem] | None = None,
    charts: dict[str, str] | None = None,
) -> str:
    def pct_vs(fair: float | None, price: float | None) -> str:
        if fair is None or not price:
            return "n/a"
        return f"{(fair / price - 1) * 100:+.0f}%"

    stop = "n/a"
    if bundle.tech.price and bundle.tech.atr_pct:
        stop = f"{bundle.tech.price * (1 - 2.5 * bundle.tech.atr_pct / 100):,.2f}"

    from mbe.scoring.sector_themes import CURATED_AS_OF, themes_for

    sector_pillar = bundle.card.pillar("Sector Momentum")
    if sector_pillar is not None and sector_pillar.confidence > 0:
        sector_momentum_line = (
            f"{sector_pillar.score:.0f}/100 vs screened peers "
            f"(coverage {sector_pillar.confidence:.0%})"
        )
    else:
        sector_momentum_line = (
            "n/a — computed in universe screens, not single-ticker analysis"
        )

    # Age is attached here rather than on the model: NewsItem is a transport
    # object shared with the site's JSON, and "days old" is only meaningful
    # relative to the report's own as_of date.
    def _dated(items: list[NewsItem]) -> list[dict]:
        out = []
        for i in items:
            age = (bundle.as_of - i.published.date()).days if i.published else None
            out.append({
                "title": i.title, "link": i.link, "source": i.source,
                "age_days": age if age is not None and age >= 0 else None,
            })
        return out

    policy_key = bundle.info.industry or bundle.info.sector
    # build_site hands every report one flat list covering all industries
    own_policy = [p for p in (policy or []) if not p.sectors or policy_key in p.sectors]

    return _TEMPLATE.render(
        info=bundle.info,
        fund=bundle.fund,
        tech=bundle.tech,
        val=bundle.val,
        risk=bundle.risk,
        card=bundle.card,
        business=bundle.business,
        stewardship=bundle.stewardship,
        thesis=bundle.thesis,
        critique=bundle.critique,
        forecast=bundle.forecast,
        as_of=bundle.as_of,
        market_cap_str=_money(bundle.info.market_cap, bundle.info.currency),
        pct_vs=pct_vs,
        entry_guidance=_entry_guidance(bundle),
        sizing_guidance=sizing_guidance(bundle),
        stop_level=stop,
        sector_momentum_line=sector_momentum_line,
        sector_themes=themes_for(bundle.info.sector, bundle.info.industry),
        themes_curated_as_of=CURATED_AS_OF,
        news=_dated(news or []),
        policy=_dated(own_policy),
        policy_key=policy_key,
        charts=charts or {},
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
