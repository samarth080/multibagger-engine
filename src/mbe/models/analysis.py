"""Outputs of the analysis engines. All metrics are Optional: a None means
the source data was insufficient — it lowers `completeness`, never guessed."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FundamentalMetrics(BaseModel):
    # Growth
    revenue_cagr_3y: float | None = None
    revenue_cagr_5y: float | None = None
    profit_cagr_3y: float | None = None
    profit_cagr_5y: float | None = None
    fcf_cagr_3y: float | None = None
    # Margins
    gross_margin: float | None = None
    operating_margin: float | None = None
    ebitda_margin: float | None = None
    net_margin: float | None = None
    operating_margin_3y_avg: float | None = None
    margin_trend: float | None = None  # latest op margin minus ~3y-ago op margin
    # Returns on capital
    roe: float | None = None
    roe_3y: float | None = None
    roce: float | None = None
    roce_3y: float | None = None
    roic: float | None = None
    # Balance sheet
    debt_to_equity: float | None = None
    net_debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    current_ratio: float | None = None
    # Cash economics
    fcf_margin: float | None = None
    cash_conversion: float | None = None  # 3y CFO / 3y NI
    accruals_ratio: float | None = None  # (NI - CFO) / assets; high => low earnings quality
    reinvestment_rate: float | None = None  # capex / cfo
    # Ownership / dilution
    share_count_cagr_3y: float | None = None
    completeness: float = Field(ge=0, le=1, default=0.0)


class TechnicalState(BaseModel):
    price: float | None = None
    sma50: float | None = None
    sma150: float | None = None
    sma200: float | None = None
    price_vs_200sma: float | None = None  # pct above/below
    sma200_slope_20d: float | None = None
    rsi14: float | None = None
    macd_hist: float | None = None
    atr_pct: float | None = None
    bollinger_pct_b: float | None = None
    stochastic14: float | None = None
    adx14: float | None = None
    obv_slope_20d: float | None = None
    cmf20: float | None = None
    dist_52w_high: float | None = None  # negative = below high
    dist_52w_low: float | None = None  # positive = above low
    return_63d: float | None = None
    relative_strength_63d: float | None = None  # vs benchmark
    trend_state: str = "unknown"  # strong_up/up/sideways/down/strong_down/unknown
    volatility_regime: str = "unknown"  # low/medium/high/unknown
    avg_traded_value_20d: float | None = None  # in listing currency
    completeness: float = Field(ge=0, le=1, default=0.0)


class ValuationResult(BaseModel):
    price: float | None = None
    fair_value_bear: float | None = None
    fair_value_base: float | None = None
    fair_value_bull: float | None = None
    margin_of_safety: float | None = None  # base fair / price - 1
    implied_growth: float | None = None  # reverse DCF growth priced in
    expected_cagr_5y: float | None = None
    pe: float | None = None
    peg: float | None = None
    ev_ebitda: float | None = None
    price_to_sales: float | None = None
    fcf_yield: float | None = None
    fcf_proxy_used: bool = False  # True when NI stood in for negative/missing FCF
    assumptions: dict[str, float] = {}
    completeness: float = Field(ge=0, le=1, default=0.0)


class RiskFlag(BaseModel):
    code: str
    severity: int = Field(ge=1, le=3)  # 1 info, 2 warning, 3 critical
    detail: str


class RiskAssessment(BaseModel):
    flags: list[RiskFlag] = []
    risk_score: float = Field(ge=0, le=100, default=0.0)  # higher = riskier
    permanent_loss_bucket: str = "unknown"  # low / medium / high
