from __future__ import annotations

from dataclasses import dataclass

from quant_research_platform.data import Bar
from quant_research_platform.signals import ForecastSignal


@dataclass(frozen=True)
class Position:
    symbol: str
    weight: float
    expected_return: float
    confidence: float


@dataclass(frozen=True)
class BacktestResult:
    selected: list[Position]
    gross_expected_return: float
    net_expected_return: float
    estimated_pnl: float
    benchmark_return: float | None


def run_top_n_backtest(
    signals: list[ForecastSignal],
    bars_by_symbol: dict[str, list[Bar]],
    top_n: int,
    initial_cash: float,
    transaction_cost_bps: float,
    benchmark_symbol: str | None = None,
) -> BacktestResult:
    ranked = sorted(signals, key=lambda item: (item.expected_return, item.confidence), reverse=True)
    winners = [item for item in ranked if item.expected_return > 0][:top_n]
    weight = 1 / len(winners) if winners else 0
    positions = [
        Position(item.symbol, weight, item.expected_return, item.confidence)
        for item in winners
    ]
    gross = sum(position.weight * position.expected_return for position in positions)
    turnover_cost = (transaction_cost_bps / 10_000) * (1 if positions else 0)
    net = gross - turnover_cost
    benchmark_return = _recent_return(bars_by_symbol.get(benchmark_symbol.upper(), [])) if benchmark_symbol else None
    return BacktestResult(
        selected=positions,
        gross_expected_return=gross,
        net_expected_return=net,
        estimated_pnl=initial_cash * net,
        benchmark_return=benchmark_return,
    )


def _recent_return(bars: list[Bar]) -> float | None:
    if len(bars) < 2:
        return None
    return bars[-1].close / bars[0].close - 1
