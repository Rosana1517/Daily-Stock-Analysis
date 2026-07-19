from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from quant_research_platform.data import Bar
from quant_research_platform.universe import (
    MIN_AVG_DAILY_TURNOVER_TWD,
    MIN_UNIVERSE_PRICE,
    passes_chip_breakout,
)


EVAL_HORIZON_SESSIONS = 5
MIN_BAR_HISTORY = 21


@dataclass(frozen=True)
class ChipBacktestTrade:
    signal_date: str
    symbol: str
    entry_close: float
    return_5d: float
    max_return_5d: float
    win: bool


@dataclass(frozen=True)
class ChipBacktestResult:
    signal_dates_scanned: int
    trades: tuple[ChipBacktestTrade, ...]

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float | None:
        if not self.trades:
            return None
        return sum(1 for trade in self.trades if trade.win) / len(self.trades)

    @property
    def average_return_5d(self) -> float | None:
        if not self.trades:
            return None
        return sum(trade.return_5d for trade in self.trades) / len(self.trades)

    @property
    def average_max_return_5d(self) -> float | None:
        if not self.trades:
            return None
        return sum(trade.max_return_5d for trade in self.trades) / len(self.trades)


def run_chip_breakout_backtest(
    chip_snapshot_dir: Path,
    price_snapshot_dir: Path,
    horizon: int = EVAL_HORIZON_SESSIONS,
    min_bar_history: int = MIN_BAR_HISTORY,
) -> ChipBacktestResult:
    """Replay accumulated daily chip/price snapshots through the production
    chip-breakout rules and measure forward returns."""
    prices_by_date = _load_price_snapshots(price_snapshot_dir)
    chips_by_date = _load_chip_snapshots(chip_snapshot_dir)
    price_dates = sorted(prices_by_date)
    trades: list[ChipBacktestTrade] = []
    scanned = 0
    for index, signal_date in enumerate(price_dates):
        history_dates = price_dates[: index + 1]
        forward_dates = price_dates[index + 1 : index + 1 + horizon]
        if len(history_dates) < min_bar_history or len(forward_dates) < horizon:
            continue
        chip_rows = chips_by_date.get(signal_date)
        if not chip_rows:
            continue
        scanned += 1
        day_prices = prices_by_date[signal_date]
        for symbol, chip_row in chip_rows.items():
            price_row = day_prices.get(symbol)
            if price_row is None:
                continue
            close = price_row["close"]
            volume = price_row["volume"]
            if close < MIN_UNIVERSE_PRICE:
                continue
            if close * volume < MIN_AVG_DAILY_TURNOVER_TWD:
                continue
            bars = _bars_for_symbol(symbol, history_dates, prices_by_date)
            if len(bars) < min_bar_history or not bars or bars[-1].close != close:
                continue
            row = {**chip_row, "symbol": symbol}
            if not passes_chip_breakout(row, {symbol.upper(): bars}):
                continue
            forward_closes = [
                prices_by_date[d][symbol]["close"]
                for d in forward_dates
                if symbol in prices_by_date[d] and prices_by_date[d][symbol]["close"] > 0
            ]
            if not forward_closes:
                continue
            return_5d = forward_closes[-1] / close - 1.0
            max_return = max(c / close - 1.0 for c in forward_closes)
            trades.append(
                ChipBacktestTrade(
                    signal_date=signal_date,
                    symbol=symbol,
                    entry_close=close,
                    return_5d=return_5d,
                    max_return_5d=max_return,
                    win=return_5d > 0,
                )
            )
    return ChipBacktestResult(signal_dates_scanned=scanned, trades=tuple(trades))


def save_backtest_report(result: ChipBacktestResult, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["signal_date", "symbol", "entry_close", "return_5d", "max_return_5d", "win"])
        for trade in result.trades:
            writer.writerow(
                [
                    trade.signal_date,
                    trade.symbol,
                    f"{trade.entry_close:.2f}",
                    f"{trade.return_5d:.4f}",
                    f"{trade.max_return_5d:.4f}",
                    "1" if trade.win else "0",
                ]
            )
    return output_path


def _bars_for_symbol(
    symbol: str,
    history_dates: list[str],
    prices_by_date: dict[str, dict[str, dict[str, float]]],
) -> list[Bar]:
    bars: list[Bar] = []
    for snapshot_date in history_dates:
        row = prices_by_date[snapshot_date].get(symbol)
        if row is None or row["close"] <= 0:
            continue
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=datetime.fromisoformat(snapshot_date),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
        )
    return bars


def _load_price_snapshots(snapshot_dir: Path) -> dict[str, dict[str, dict[str, float]]]:
    result: dict[str, dict[str, dict[str, float]]] = {}
    if not snapshot_dir.exists():
        return result
    for path in sorted(snapshot_dir.glob("tw_price_daily_*.csv")):
        snapshot_date = path.stem.replace("tw_price_daily_", "")
        rows: dict[str, dict[str, float]] = {}
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    symbol = str(row.get("symbol", "")).strip()
                    if not symbol:
                        continue
                    rows[symbol] = {
                        "open": _float(row.get("open")),
                        "high": _float(row.get("high")),
                        "low": _float(row.get("low")),
                        "close": _float(row.get("close")),
                        "volume": _float(row.get("volume")),
                    }
        except OSError:
            continue
        if rows:
            result[snapshot_date] = rows
    return result


def _load_chip_snapshots(snapshot_dir: Path) -> dict[str, dict[str, dict[str, str]]]:
    result: dict[str, dict[str, dict[str, str]]] = {}
    if not snapshot_dir.exists():
        return result
    for path in sorted(snapshot_dir.glob("tw_chip_snapshot_*.csv")):
        snapshot_date = path.stem.replace("tw_chip_snapshot_", "")
        rows: dict[str, dict[str, str]] = {}
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    symbol = str(row.get("symbol", "")).strip()
                    if symbol:
                        rows[symbol] = dict(row)
        except OSError:
            continue
        if rows:
            result[snapshot_date] = rows
    return result


def _float(value) -> float:
    text = str(value if value is not None else "").replace(",", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
