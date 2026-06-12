# TW Hybrid Selection Strategy

## Legacy reference

Saved on 2026-06-11 before the production rule update.

- Candidate universe source: `data/tw_listed_otc_stocks.csv`
- Legacy ranking basis:
- `score = price_bucket_bonus + log10(max(volume, avg_volume_20d))`
- Price bucket bonus:
- `< 30`: `12.0`
- `<= 100`: `10.0`
- `<= 200`: `4.0`
- `> 200`: `0.0`
- Seed behavior:
- Preserve a small set of symbols from `config.symbols`
- Fill remaining slots by legacy score order
- Report ranking still applies downstream hybrid / recommendation scoring

## Current production rule

- `K 值 < 40`
- `近 5 日融資增加前 100 大`
- `收盤價 20 日均線上升`

## Selective reuse from legacy logic

- Keep the current three rules as the primary filter.
- Reuse only `volume / avg_volume_20d`, revenue growth, PE sanity check, and industry-news alignment as tie-break support.
- Do not restore the old `price_bucket_bonus` as a primary ranking rule.
- The current code now heavily downweights the old price bucket and lets liquidity/basic quality act only after the revised filters.

## Data note

- The current daily snapshot already comes from live TWSE / TPEx APIs, and OHLCV comes from OpenBB.
- The remaining gap is that the TWSE / TPEx merged snapshot does not yet carry a standard `5-day margin financing change` field.
- The production code now supports these column names when they become available:
- `margin_financing_change_5d`
- `margin_change_5d`
- `margin_5d_change`
- `five_day_margin_financing_change`
- `five_day_margin_change`
- When that field is absent, the production flow still enforces `K 值 < 40` and `20MA 上升`, then falls back to the lighter legacy tie-break rules instead of the old full heuristic.
