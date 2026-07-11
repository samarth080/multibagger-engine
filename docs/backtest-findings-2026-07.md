# Backtest findings — July 2026 (first calibration evidence)

Setup: NIFTY Midcap 150 (first 60 constituents), point-in-time cutoffs
2024-07-15 and 2025-07-15, 365-day forward returns, n = 54/57 per cutoff
(9 ticker-cutoffs skipped for insufficient point-in-time data).

| Score | IC @2024-07 | IC @2025-07 | Mean IC | Spread @2024 | Spread @2025 |
|---|---|---|---|---|---|
| multibagger | 0.007 | 0.024 | **0.016** | -7.6% | +0.7% |
| investment | 0.038 | -0.021 | **0.009** | -1.1% | +0.7% |
| momentum | -0.138 | +0.083 | **-0.027** | -20.0% | +13.6% |

## Honest interpretation

1. **No demonstrated 1-year edge.** All mean ICs are indistinguishable from zero
   at this sample size (2 cutoffs, ~55 names). This is the truthful baseline,
   not a failure of the harness — it ran exactly as designed.
2. **The momentum sign-flip is informative.** Momentum crashed in the 2024→2025
   window (the midcap correction: top momentum quintile -20% vs bottom) and
   worked in 2025→2026 (+13.6%). Classic factor-crash signature; single-factor
   momentum is regime-dependent, which supports keeping its weight moderate
   (currently 14% of Investment Score) rather than increasing it.
3. **Structural caveats bound what these numbers can say:** multibagger theses
   play out over 3-5+ years but Yahoo's ~5-year statement depth only allows
   1-2 year forward windows; the 2024 cutoff had only ~3 statement years, so
   growth CAGRs were largely absent from scoring; survivorship bias (today's
   index list) flatters everything.

## Decisions taken

- **No recalibration on this evidence.** Two cutoffs is curve-fitting territory.
  Benchmark tables stay as documented priors until the evidence base grows.
- The harness + DuckDB store now accumulate every run; each future snapshot and
  backtest extends the evidence base for a properly-powered calibration.
- Priority raised for a deeper fundamentals provider (10+ years of statements)
  — it directly multiplies usable cutoffs and enables the 3-5y horizons the
  multibagger thesis actually claims.

## Addendum: powered momentum backtest (8 annual cutoffs, 2018-2025)

Momentum score, 60 NIFTY Midcap 150 names, 365-day forward returns,
n = 45-57 per cutoff (72 ticker-cutoffs skipped: young listings / short windows).

| Cutoff | IC | Top-bottom spread |
|---|---|---|
| 2018-07 | +0.120 | +14.2% |
| 2019-07 | -0.065 | -15.3% |
| 2020-07 | -0.051 | +56.9% |
| 2021-07 | +0.066 | -10.6% |
| 2022-07 | -0.299 | -12.7% |
| 2023-07 | +0.203 | +77.0% |
| 2024-07 | -0.138 | -20.0% |
| **Mean** | **-0.010** | — |

Interpretation (with 2025-07 included, mean IC -0.010):

1. **No stable 1-year momentum edge in Indian midcaps at annual rebalance.**
   IC whipsaws between -0.30 and +0.20 across regimes — momentum decays over
   months, so annual sampling aliases the signal badly.
2. This is consistent with the decision to keep Momentum at a moderate 14%
   of the Investment Score rather than raising it.
3. The harness is now demonstrably capable of powered multi-cutoff tests —
   the constraint for testing the core quality/growth thesis remains
   statement depth, not tooling.
