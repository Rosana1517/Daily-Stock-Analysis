from __future__ import annotations

from pathlib import Path


def build_qlib_signal_backtest_config(
    signal_csv: Path,
    market: str,
    benchmark: str,
    output_path: Path,
    topk: int = 50,
    n_drop: int = 5,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# Qlib signal backtest scaffold
# Signal CSV: {signal_csv}

qlib_init:
  provider_uri: ~/.qlib/qlib_data/{market}
  region: cn

market: {market}
benchmark: {benchmark}

strategy:
  class: TopkDropoutStrategy
  module_path: qlib.contrib.strategy
  kwargs:
    topk: {topk}
    n_drop: {n_drop}

executor:
  class: SimulatorExecutor
  module_path: qlib.backtest.executor
  kwargs:
    time_per_step: day
    generate_portfolio_metrics: true

notes:
  - Convert the signal CSV to a Qlib prediction object or load it in a custom Signal class.
  - Evaluate IC, Rank IC, long-short, top-k, turnover, transaction cost, and drawdown.
"""
    output_path.write_text(content, encoding="utf-8")
    return output_path
