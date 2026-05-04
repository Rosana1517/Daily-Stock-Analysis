from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import mean
from typing import Iterable, Sequence


@dataclass(frozen=True)
class InlineQlibMetrics:
    ic: float | None
    rank_ic: float | None
    topk_return: float | None
    turnover: float
    observations: int


@dataclass(frozen=True)
class QlibEngineBacktestResult:
    executed: bool
    provider_uri: str | None
    report_path: Path | None
    start_time: str | None
    end_time: str | None
    symbols: tuple[str, ...]
    portfolio_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    annualized_return: float | None = None
    volatility: float | None = None
    information_ratio: float | None = None
    max_drawdown: float | None = None
    average_turnover: float | None = None
    average_cost: float | None = None
    observations: int = 0
    error: str | None = None


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


def run_qlib_engine_portfolio_backtest(
    rows: Sequence[object],
    bars_by_symbol: dict[str, list[object]],
    provider_dir: Path,
    output_path: Path,
    benchmark_symbol: str | None,
    top_n: int,
    initial_cash: float,
    transaction_cost_bps: float,
) -> QlibEngineBacktestResult:
    symbols = tuple(str(getattr(row, "symbol", "")).upper() for row in rows if getattr(row, "symbol", ""))
    usable_symbols = tuple(symbol for symbol in symbols if len(bars_by_symbol.get(symbol, ())) >= 30)
    if len(usable_symbols) < 2:
        return QlibEngineBacktestResult(
            executed=False,
            provider_uri=None,
            report_path=None,
            start_time=None,
            end_time=None,
            symbols=usable_symbols,
            error="Qlib engine requires at least two symbols with 30+ daily bars.",
        )

    try:
        import numpy as np
        import pandas as pd
        import qlib
        from qlib.backtest.executor import SimulatorExecutor
        from qlib.contrib.evaluate import backtest_daily
        from qlib.contrib.strategy import TopkDropoutStrategy
    except Exception as exc:
        return QlibEngineBacktestResult(
            executed=False,
            provider_uri=None,
            report_path=None,
            start_time=None,
            end_time=None,
            symbols=usable_symbols,
            error=f"pyqlib runtime unavailable: {exc}",
        )

    try:
        calendar = _write_qlib_file_provider(provider_dir, usable_symbols, bars_by_symbol)
        signal = _build_daily_prediction_signal(pd, usable_symbols, bars_by_symbol, calendar)
        if signal.empty:
            return QlibEngineBacktestResult(
                executed=False,
                provider_uri=str(provider_dir.resolve()),
                report_path=None,
                start_time=None,
                end_time=None,
                symbols=usable_symbols,
                error="Qlib prediction signal is empty after lookback filtering.",
            )

        start_time = str(signal.index.get_level_values("datetime").min().date())
        end_time = str(signal.index.get_level_values("datetime").max().date())
        cost = float(transaction_cost_bps) / 10000
        benchmark = _normalize_symbol(benchmark_symbol or usable_symbols[0])
        if benchmark not in usable_symbols:
            benchmark = usable_symbols[0]

        qlib.init(provider_uri=str(provider_dir.resolve()), region="cn", clear_mem_cache=True)
        strategy = TopkDropoutStrategy(signal=signal, topk=max(1, min(top_n, len(usable_symbols))), n_drop=1)
        executor = SimulatorExecutor(time_per_step="day", generate_portfolio_metrics=True)
        report, _positions = backtest_daily(
            start_time=start_time,
            end_time=end_time,
            strategy=strategy,
            executor=executor,
            account=initial_cash,
            benchmark=benchmark,
            exchange_kwargs={
                "freq": "day",
                "codes": list(usable_symbols),
                "deal_price": "close",
                "open_cost": cost,
                "close_cost": cost,
                "min_cost": 0,
            },
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report.to_csv(output_path, encoding="utf-8-sig")
        returns = report["return"].dropna()
        bench = report["bench"].dropna() if "bench" in report else pd.Series(dtype="float64")
        portfolio_return = _compound(returns)
        benchmark_return = _compound(bench) if not bench.empty else None
        excess_return = portfolio_return - benchmark_return if benchmark_return is not None else None
        annualized_return = (1 + portfolio_return) ** (252 / max(1, len(returns))) - 1 if returns.size else None
        volatility = float(returns.std() * np.sqrt(252)) if returns.size > 1 else None
        information_ratio = (
            float(returns.mean() / returns.std() * np.sqrt(252))
            if returns.size > 1 and float(returns.std()) > 0
            else None
        )
        max_drawdown = _max_drawdown(returns)
        return QlibEngineBacktestResult(
            executed=True,
            provider_uri=str(provider_dir.resolve()),
            report_path=output_path,
            start_time=start_time,
            end_time=end_time,
            symbols=usable_symbols,
            portfolio_return=portfolio_return,
            benchmark_return=benchmark_return,
            excess_return=excess_return,
            annualized_return=annualized_return,
            volatility=volatility,
            information_ratio=information_ratio,
            max_drawdown=max_drawdown,
            average_turnover=float(report["turnover"].mean()) if "turnover" in report else None,
            average_cost=float(report["cost"].mean()) if "cost" in report else None,
            observations=int(len(report)),
        )
    except Exception as exc:
        return QlibEngineBacktestResult(
            executed=False,
            provider_uri=str(provider_dir.resolve()),
            report_path=None,
            start_time=None,
            end_time=None,
            symbols=usable_symbols,
            error=f"Qlib engine backtest failed: {exc}",
        )


def run_inline_signal_diagnostics(rows: list[object], bars_by_symbol: dict[str, list[object]], top_n: int) -> InlineQlibMetrics:
    observations = []
    for row in rows:
        symbol = str(getattr(row, "symbol", ""))
        bars = bars_by_symbol.get(symbol, [])
        if len(bars) < 2:
            continue
        current = getattr(row, "current_close", None)
        predicted = getattr(row, "predicted_close", None)
        if not current or not predicted:
            continue
        signal_return = float(predicted) / float(current) - 1
        trailing_return = float(getattr(bars[-1], "close")) / float(getattr(bars[-2], "close")) - 1
        observations.append((signal_return, trailing_return))
    if len(observations) < 2:
        return InlineQlibMetrics(None, None, None, 0.0, len(observations))

    signals = [item[0] for item in observations]
    realized = [item[1] for item in observations]
    ranked = sorted(observations, key=lambda item: item[0], reverse=True)[: max(1, top_n)]
    return InlineQlibMetrics(
        ic=_pearson(signals, realized),
        rank_ic=_pearson(_ranks(signals), _ranks(realized)),
        topk_return=mean(item[1] for item in ranked),
        turnover=0.0,
        observations=len(observations),
    )


def _write_qlib_file_provider(provider_dir: Path, symbols: Sequence[str], bars_by_symbol: dict[str, list[object]]) -> list[date]:
    import numpy as np

    calendar = sorted(
        {
            _bar_date(bar)
            for symbol in symbols
            for bar in bars_by_symbol.get(symbol, ())
            if _valid_bar(bar)
        }
    )
    (provider_dir / "calendars").mkdir(parents=True, exist_ok=True)
    (provider_dir / "instruments").mkdir(parents=True, exist_ok=True)
    (provider_dir / "calendars" / "day.txt").write_text(
        "\n".join(item.isoformat() for item in calendar) + "\n",
        encoding="utf-8",
    )
    (provider_dir / "calendars" / "day_future.txt").write_text(
        "\n".join(item.isoformat() for item in calendar) + "\n",
        encoding="utf-8",
    )

    instrument_lines = []
    index_by_day = {item: index for index, item in enumerate(calendar)}
    for symbol in symbols:
        bars = [bar for bar in bars_by_symbol.get(symbol, ()) if _valid_bar(bar)]
        if not bars:
            continue
        symbol_dir = provider_dir / "features" / symbol.lower()
        symbol_dir.mkdir(parents=True, exist_ok=True)
        bar_by_date = {_bar_date(bar): bar for bar in bars}
        start = min(bar_by_date)
        end = max(bar_by_date)
        instrument_lines.append(f"{symbol}\t{start.isoformat()}\t{end.isoformat()}")
        for field in ("open", "high", "low", "close", "volume"):
            values = np.full(len(calendar), np.nan, dtype="<f4")
            for day, bar in bar_by_date.items():
                values[index_by_day[day]] = float(getattr(bar, field))
            np.hstack([np.array([0], dtype="<f4"), values]).astype("<f4").tofile(symbol_dir / f"{field}.day.bin")
        factor = np.ones(len(calendar), dtype="<f4")
        np.hstack([np.array([0], dtype="<f4"), factor]).astype("<f4").tofile(symbol_dir / "factor.day.bin")
    (provider_dir / "instruments" / "custom_tw.txt").write_text("\n".join(instrument_lines) + "\n", encoding="utf-8")
    return calendar


def _build_daily_prediction_signal(pd, symbols: Sequence[str], bars_by_symbol: dict[str, list[object]], calendar: Sequence[date]):
    score_rows = []
    calendar_index = {day: index for index, day in enumerate(calendar)}
    for symbol in symbols:
        bars = [bar for bar in bars_by_symbol.get(symbol, ()) if _valid_bar(bar)]
        close_by_date = {_bar_date(bar): float(getattr(bar, "close")) for bar in bars}
        dates = sorted(close_by_date)
        for day in dates:
            idx = calendar_index.get(day, -1)
            if idx < 20 or idx >= len(calendar) - 1:
                continue
            prior_5 = _prior_close(close_by_date, calendar, idx, 5)
            prior_20 = _prior_close(close_by_date, calendar, idx, 20)
            current = close_by_date.get(day)
            if not current or not prior_5 or not prior_20:
                continue
            momentum_5 = current / prior_5 - 1
            momentum_20 = current / prior_20 - 1
            score = momentum_5 + momentum_20 * 0.35
            score_rows.append((pd.Timestamp(day), symbol, score))
    if not score_rows:
        return pd.DataFrame(columns=["score"], index=pd.MultiIndex.from_arrays([[], []], names=["datetime", "instrument"]))
    frame = pd.DataFrame(score_rows, columns=["datetime", "instrument", "score"])
    return frame.set_index(["datetime", "instrument"]).sort_index()


def _prior_close(close_by_date: dict[date, float], calendar: Sequence[date], index: int, lookback: int) -> float | None:
    for cursor in range(index - lookback, -1, -1):
        value = close_by_date.get(calendar[cursor])
        if value:
            return value
    return None


def _compound(values: Iterable[float]) -> float:
    result = 1.0
    for value in values:
        result *= 1 + float(value)
    return result - 1


def _max_drawdown(returns) -> float | None:
    if returns.empty:
        return None
    curve = (1 + returns).cumprod()
    drawdown = curve / curve.cummax() - 1
    return float(drawdown.min())


def _valid_bar(bar: object) -> bool:
    try:
        return float(getattr(bar, "close")) > 0
    except (TypeError, ValueError):
        return False


def _bar_date(bar: object) -> date:
    value = getattr(bar, "timestamp")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


def _normalize_symbol(symbol: str) -> str:
    return str(symbol).upper().replace(".TW", "").replace(".TWO", "").strip()


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_var = sum((x - left_mean) ** 2 for x in left)
    right_var = sum((y - right_mean) ** 2 for y in right)
    if left_var <= 0 or right_var <= 0:
        return None
    return numerator / (left_var**0.5 * right_var**0.5)


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    for rank, (index, _value) in enumerate(ordered, start=1):
        ranks[index] = float(rank)
    return ranks
