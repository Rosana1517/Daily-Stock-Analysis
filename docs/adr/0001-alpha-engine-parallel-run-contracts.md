# ADR 0001: Alpha Engine Parallel Run Contracts

## Status

Accepted

## Context

The repository has mature automation, but the operating goal is better short-term trading decisions rather than more infrastructure. New alpha domains were introduced for market regime, probability ranking, capital flow, and trade review. These domains must not replace the existing Hybrid ranking in a single large migration.

## Decision

The alpha engine will run in parallel with the current Hybrid flow through explicit contracts:

- `MarketRegimeResult` for market state and strategy fit.
- `RankingResult` for probability-ranked 3-10 trading day opportunities.
- `CapitalFlowResult` for Taiwan-market capital flow features.
- `TradeReviewReport` for post-trade review, alpha decay, and promotion gates.

The existing Hybrid report and ranking remain the production baseline until parallel-run evidence shows that a new component improves realized trading decisions.

## Alternatives Considered

- Replace Hybrid ranking immediately: rejected because it increases operational risk without live evidence.
- Keep alpha modules as isolated experiments: rejected because outputs would not become measurable decision inputs.
- Add indicators directly to reports: rejected because it increases complexity without clear edge validation.

## Consequences

- New domains can be tested independently and promoted gradually.
- Ranking can consume regime and capital flow outputs through stable contracts.
- Trade review becomes the gate for production promotion or rollback.
- Some duplicate-looking scores may exist temporarily during the shadow-run period.

## Risks

- Parallel outputs may confuse users if the report does not clearly label baseline vs alpha shadow output.
- Missing institutional data can create false confidence if not marked as missing.
- Promotion criteria must remain tied to realized 3-10 trading day performance, not backtest cosmetics.

## Future Reconsideration Triggers

- Probability ranking outperforms Hybrid baseline for multiple market regimes.
- Trade review detects persistent alpha decay in the current Hybrid ranking.
- Capital flow data freshness becomes reliable enough for intraday weighting.
