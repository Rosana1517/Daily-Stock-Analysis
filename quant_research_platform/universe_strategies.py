"""Pass/fail strategy predicates and chip-flow scoring used to rank the
candidate universe: revised (platform-breakout) strategy, chip-breakout
strategy, and chip-radar strategy."""

from __future__ import annotations

from quant_research_platform.universe_platform_geometry import _platform_breakout_strength


def _platform_symbol(row: dict) -> str:
    symbol = str(row.get("symbol", "")).strip().upper()
    if not symbol:
        return ""
    if "." in symbol:
        return symbol
    market = str(row.get("market", "")).strip().lower()
    if market in {"otc", "tpex", "two"} or "tpex" in str(row.get("notes", "")).lower():
        return f"{symbol}.TWO"
    return f"{symbol}.TW"


def _bars_for_row(row: dict, bars_by_symbol: dict[str, list]) -> list:
    symbol = str(row.get("symbol", "")).strip().upper()
    platform_symbol = _platform_symbol(row).upper()
    return bars_by_symbol.get(symbol) or bars_by_symbol.get(platform_symbol) or []


def _optional_float(row: dict, *keys: str) -> float | None:
    for key in keys:
        value = str(row.get(key, "")).replace(",", "").strip()
        if not value:
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return None


def _bool_flag(row: dict, *keys: str) -> bool | None:
    truthy = {"1", "true", "yes", "y", "pass", "passed"}
    falsy = {"0", "false", "no", "n", "fail", "failed"}
    for key in keys:
        value = str(row.get(key, "")).strip().lower()
        if not value:
            continue
        if value in truthy:
            return True
        if value in falsy:
            return False
    return None


def _stochastic_k_value(bars: list) -> float | None:
    if len(bars) < 9:
        return None
    window = bars[-9:]
    highest_high = max(bar.high for bar in window)
    lowest_low = min(bar.low for bar in window)
    if highest_high <= lowest_low:
        return 50.0
    return (window[-1].close - lowest_low) / (highest_high - lowest_low) * 100.0


def _is_ma20_rising(bars: list) -> bool:
    closes = [bar.close for bar in bars if getattr(bar, "close", 0) > 0]
    if len(closes) < 21:
        return False
    latest = sum(closes[-20:]) / 20.0
    previous = sum(closes[-21:-1]) / 20.0
    return latest > previous


def _breaks_platform_consolidation(row: dict, bars: list) -> bool:
    explicit = _bool_flag(
        row,
        "platform_breakout",
        "platform_breakout_flag",
        "breakout_platform",
        "breakout_of_platform",
    )
    if explicit is not None:
        return explicit
    return _platform_breakout_strength(bars) >= 18.0


def _top10_main_force_strength(row: dict) -> float:
    score = _optional_float(row, "top10_main_force_buy_strength", "top10_main_force_strength")
    if score is None:
        score = _optional_float(row, "top10_main_force_buy_strength_proxy", "institutional_main_force_strength_proxy")
    if score is not None:
        return score
    ratio = _optional_float(
        row,
        "top10_main_force_buy_ratio",
        "top10_main_force_ratio",
        "top10_buy_share_pct",
        "top10_main_force_share_pct",
    )
    if ratio is None:
        return 0.0
    normalized = ratio * 100.0 if abs(ratio) <= 1.0 else ratio
    return max(0.0, min(100.0, normalized * 2.0))


def _top10_main_force_strong(row: dict) -> bool:
    rank = _optional_float(row, "top10_main_force_buy_rank", "top10_main_force_rank")
    if rank is not None and rank > 0 and rank <= 10:
        return True
    strength = _top10_main_force_strength(row)
    if strength >= 60.0:
        return True
    net_buy = _optional_float(row, "top10_main_force_net_buy", "main_force_top10_net_buy")
    return net_buy is not None and net_buy > 0


def _foreign_buy_streak_days(row: dict) -> float:
    return _optional_float(row, "foreign_buy_streak_days", "foreign_net_buy_streak_days", "foreign_buy_days") or 0.0


def _branch_buy_streak_days(row: dict) -> float:
    return _optional_float(
        row,
        "branch_main_force_buy_streak_days",
        "main_broker_buy_streak_days",
        "broker_buy_streak_days",
        "branch_buy_streak_days",
    ) or 0.0


def _passes_revised_strategy(
    row: dict,
    bars_by_symbol: dict[str, list],
    require_margin: bool,
    margin_top_100: set[str],
) -> bool:
    bars = _bars_for_row(row, bars_by_symbol)
    k_value = _stochastic_k_value(bars)
    if k_value is None or k_value >= 40:
        return False
    if not _is_ma20_rising(bars):
        return False
    if not _breaks_platform_consolidation(row, bars):
        return False
    if require_margin:
        symbol = str(row.get("symbol", "")).strip().upper()
        return symbol in margin_top_100
    return True


def _passes_chip_breakout_strategy(row: dict, bars_by_symbol: dict[str, list]) -> bool:
    bars = _bars_for_row(row, bars_by_symbol)
    if not _breaks_platform_consolidation(row, bars):
        return False
    if not _top10_main_force_strong(row):
        return False
    return _foreign_buy_streak_days(row) >= 3 or _branch_buy_streak_days(row) >= 2


def passes_chip_breakout(row: dict, bars_by_symbol: dict[str, list]) -> bool:
    """Public wrapper so backtests replay the exact production chip-breakout rule."""
    return _passes_chip_breakout_strategy(row, bars_by_symbol)


def _passes_chip_radar_strategy(row: dict) -> bool:
    return _top10_main_force_strong(row) or _foreign_buy_streak_days(row) >= 3 or _branch_buy_streak_days(row) >= 2


def _passes_chip_confirmation_strategy(
    row: dict,
    bars_by_symbol: dict[str, list],
    require_margin: bool,
    margin_top_100: set[str],
) -> bool:
    if not _passes_chip_radar_strategy(row):
        return False
    bars = _bars_for_row(row, bars_by_symbol)
    if not bars:
        return False
    if not _is_ma20_rising(bars):
        return False
    if not _breaks_platform_consolidation(row, bars):
        return False
    if require_margin:
        symbol = str(row.get("symbol", "")).strip().upper()
        if symbol not in margin_top_100:
            return False
    return True


def _chip_breakout_score(row: dict, bars_by_symbol: dict[str, list]) -> float:
    bars = _bars_for_row(row, bars_by_symbol)
    breakout_strength = _platform_breakout_strength(bars)
    top10_strength = _top10_main_force_strength(row)
    foreign_streak = min(10.0, _foreign_buy_streak_days(row)) * 6.0
    branch_streak = min(10.0, _branch_buy_streak_days(row)) * 7.0
    return top10_strength + foreign_streak + branch_streak + breakout_strength


def _chip_radar_score(row: dict) -> float:
    top10_strength = _top10_main_force_strength(row)
    foreign_streak = min(10.0, _foreign_buy_streak_days(row)) * 7.0
    branch_streak = min(10.0, _branch_buy_streak_days(row)) * 8.0
    return top10_strength + foreign_streak + branch_streak
