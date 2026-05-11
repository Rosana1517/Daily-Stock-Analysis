# Alpha Engine Parallel Contracts

This repository optimizes for trading edge first and infrastructure second. The alpha engine domains must run beside the existing Hybrid flow until live review proves that replacement improves short-term trading decisions.

## Migration Principle

The current Hybrid report and ranking remain the production baseline. New alpha domains publish stable contracts, collect evidence, and run in parallel for review before they become primary ordering logic.

## Domain Contracts

### market_regime

Owner: Quant Research

Contract: `MarketRegimeResult`

Required fields:
- `report_date`
- `regime`
- `confidence`
- `explanation`
- `suitable_strategies`
- `unsuitable_strategies`
- `transition`
- `metadata`

Consumption rule:
- Ranking may read regime text, confidence, and risk-on/risk-off backtest features.
- Daily pipeline must not import internal scoring modules directly.

### ranking_engine

Owner: Screener

Contract: `RankingResult`

Required fields:
- `stock`
- `composite_score`
- `probability`
- `confidence`
- `setup`
- `expected_holding_period`
- `expected_volatility`
- `risk_reward`
- `components`

Consumption rule:
- Existing Hybrid ranking remains baseline.
- `RankingResult` can be converted to `StockRecommendation` through `ranked_to_recommendations`.
- Production replacement requires parallel-run review against realized 3-10 trading day outcomes.

### capital_flow

Owner: Data Ingestion

Contract: `CapitalFlowResult`

Required fields:
- `record`
- `capital_flow_score`
- `accumulation_score`
- `speculative_activity_score`
- `institutional_conviction_score`
- `sector_rotation_score`
- `labels`
- `warnings`

Consumption rule:
- Capital flow scores are data features, not final buy/sell decisions.
- Ranking may consume symbol-level flow scores after source freshness and missing-data checks.

### trade_review

Owner: Quality / Review

Contract: `TradeReviewReport`

Required fields:
- `reviewed_trades`
- `setup_stats`
- `regime_stats`
- `missed_runners`
- `alpha_decay_alerts`
- `market_behavior_shifts`

Consumption rule:
- Review output decides whether an alpha module gains, loses, or keeps production weight.
- Strategy degradation alerts must block automatic promotion of new ranking logic.

## Parallel Run Gates

1. Shadow run: alpha modules generate outputs without affecting production ordering.
2. Compare: measure Hybrid rank vs probability rank over realized 3-10 trading day returns.
3. Review: trade review identifies false breakouts, missed runners, regime mismatch, and alpha decay.
4. Promote gradually: only promote weights or ordering slices that improve realized decision quality.
5. Roll back: if setup win rate or payoff ratio decays, revert to Hybrid baseline for that slice.

## Non-Goals

- Do not add indicators without a review metric.
- Do not replace Hybrid ranking in one large switch.
- Do not let missing institutional or intraday data silently increase confidence.
- Do not optimize for report complexity over trade decision quality.
