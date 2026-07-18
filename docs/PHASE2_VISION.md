# Phase 2 — From Financial-Statement Intelligence to Business Intelligence

**Directive (2026-07-12):** stop thinking about stocks, think about businesses.
Build the reasoning of a professional investment committee. Operate autonomously
until "STOP ITERATING". **Binding constraint:** every new module must
demonstrate incremental value (backtest, ablation, or improved thesis quality)
or it does not remain in the system.

## The anti-pattern this document exists to prevent

The vision names ~15 subsystems (knowledge graph, causal engine, document
intelligence, management scoring, 12-persona committee, regime detection,
portfolio engine, market-history engine…). Building all of them at once
produces fifteen shallow stubs and validates nothing — which the directive's
closing paragraph explicitly forbids. Instead: **one deep, validated increment
at a time, each chosen as the current highest-value move, each proven or
removed.**

## Reasoning principle for every increment

1. Deterministic computation wherever possible; AI only for genuinely
   unstructured reasoning (and no LLM is authenticated in this environment, so
   Phase-2 increments are deterministic by necessity *and* by preference).
2. Every module ships with a validation: an ablation backtest (does it add
   information?), a calibration check, or a concrete thesis-quality improvement.
3. Intellectual honesty over impressiveness. A module that fails validation is
   documented as a null and removed or demoted — as was done with the size
   signal in Phase 1.

## Decomposition into validatable increments (value-ordered)

| # | Increment | Why it makes the platform reason like great investors | How it's validated |
|---|---|---|---|
| **P2.1** | **Business-Quality / Franchise-Durability engine + Living Thesis + Self-Critique** (this increment) | Shifts the unit of analysis from a single-year snapshot to a decade-long business trajectory; states falsifiable assumptions and attacks them before recommending | **Ablation**: does a franchise-durability score carry forward-return IC the base score misses? |
| P2.2 | Longitudinal company memory + prediction ledger (thesis persistence, change detection, prediction→outcome tracking) | Institutional memory; the scientific spine that lets every later module be scored | Calibration: are stated confidences borne out by outcomes? |
| P2.3 | Management & capital-allocation intelligence (multi-year: dilution, buybacks, ROIIC, guidance vs delivery, reinvestment quality) | Judges stewardship over years, not quarters | Ablation vs forward returns |
| P2.4 | Sector rotation & tailwind intelligence (industry momentum pillar + curated theme tags) | Ranks industries, not just companies — the quantitative precursor to the causal graph | Ablation: demoted to descriptive-only (1/4 samples); sector table/tags/report context retained |
| P2.5 | Document intelligence (annual-report / con-call language & promise tracking) — *requires text ingestion; deterministic NLP first* | Reads the narrative, tracks promises | Promise-kept rate vs outcomes |
| P2.6 | Causal knowledge graph (policy → beneficiary chains, supply-chain links) | Second/third-order reasoning | Event-study validation on known policy shocks |
| P2.7 | Regime detection + portfolio intelligence | Context-adaptive sizing and correlation-aware construction | Regime-conditional backtest |

Each increment gets its own spec, TDD build, validation, and honest write-up.
This file is the living roadmap; it is updated as increments land or are killed.

## Definition of done for Phase 2 as a whole

The platform can answer, for a company, **"what kind of business will this become
over the next decade, how sure are we, and what would prove us wrong?"** — with
every claim backed by evidence, a stated confidence, an explicit falsifier, and
a track record of whether such claims have historically held.
