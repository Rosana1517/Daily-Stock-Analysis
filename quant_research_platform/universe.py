from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from quant_research_platform.data import load_csv_ohlcv
from stock_signal_system.data.csv_sources import load_news
from stock_signal_system.data.regulatory_flags import load_regulatory_flag_symbols


@dataclass(frozen=True)
class CandidateSelectionPlan:
    selected_symbols: tuple[str, ...]
    analysis_symbols: tuple[str, ...]
    chip_radar_symbols: tuple[str, ...]
    chip_breakout_symbols: tuple[str, ...]
    revised_symbols: tuple[str, ...]
    legacy_watch_symbols: tuple[str, ...]
    legacy_pool_symbols: tuple[str, ...]


def select_candidate_symbols(
    universe_path: Path | None,
    fallback_symbols: tuple[str, ...],
    limit: int,
    news_path: Path | None = None,
    ohlcv_path: Path | None = None,
) -> tuple[str, ...]:
    plan = build_candidate_selection_plan(universe_path, fallback_symbols, limit, news_path, ohlcv_path)
    return plan.selected_symbols


def build_candidate_selection_plan(
    universe_path: Path | None,
    fallback_symbols: tuple[str, ...],
    limit: int,
    news_path: Path | None = None,
    ohlcv_path: Path | None = None,
) -> CandidateSelectionPlan:
    if not universe_path or not universe_path.exists():
        selected = fallback_symbols[:limit] if limit > 0 else fallback_symbols
        return CandidateSelectionPlan(selected, selected, (), (), (), selected, selected)
    rows = _load_universe_rows(universe_path)
    if not rows:
        selected = fallback_symbols[:limit] if limit > 0 else fallback_symbols
        return CandidateSelectionPlan(selected, selected, (), (), (), selected, selected)
    news_terms = _news_terms(news_path)
    bars_by_symbol = _load_price_bars(ohlcv_path)
    margin_ready = [row for row in rows if _margin_change_5d(row) is not None]
    margin_top_100 = {
        str(row.get("symbol", "")).strip().upper()
        for row in sorted(margin_ready, key=lambda row: float(_margin_change_5d(row) or 0.0), reverse=True)[:100]
        if float(_margin_change_5d(row) or 0.0) > 0
    }
    chip_radar_rows = _rank_chip_radar_rows(rows, news_terms, bars_by_symbol)
    chip_rows = [
        row
        for row in chip_radar_rows
        if _passes_chip_confirmation_strategy(
            row,
            bars_by_symbol,
            require_margin=bool(margin_ready),
            margin_top_100=margin_top_100,
        )
    ]
    legacy_ranked_rows = _rank_legacy_rows(rows, news_terms)
    legacy_pool_rows = legacy_ranked_rows[:limit] if limit > 0 else legacy_ranked_rows
    chip_watch_rows = [row for row in chip_radar_rows if row not in chip_rows]
    mother_symbols = {
        str(row.get("symbol", "")).strip().upper()
        for row in legacy_ranked_rows
    } | {
        str(row.get("symbol", "")).strip().upper()
        for row in chip_radar_rows
    }
    revised_rows = _rank_revised_rows(
        [row for row in rows if str(row.get("symbol", "")).strip().upper() in mother_symbols],
        news_terms,
        bars_by_symbol,
    )
    radar_symbols = {
        str(row.get("symbol", "")).strip().upper()
        for row in chip_radar_rows
    }
    legacy_rows = [
        row
        for row in legacy_ranked_rows
        if str(row.get("symbol", "")).strip().upper() not in radar_symbols
    ]
    selected_symbols: list[str] = []
    analysis_symbols: list[str] = []
    chip_radar_symbols: list[str] = []
    chip_breakout_symbols: list[str] = []
    revised_symbols: list[str] = []
    legacy_watch_symbols: list[str] = []
    legacy_pool_symbols: list[str] = []

    def add_symbols(source_rows: list[dict], target: list[str]) -> None:
        for row in source_rows:
            symbol = _platform_symbol(row)
            if not symbol or symbol in selected_symbols:
                continue
            selected_symbols.append(symbol)
            target.append(symbol)
            if limit > 0 and len(selected_symbols) >= limit:
                break

    add_symbols(chip_rows, chip_breakout_symbols)
    if limit <= 0 or len(selected_symbols) < limit:
        add_symbols(revised_rows, revised_symbols)
    if limit <= 0 or len(selected_symbols) < limit:
        add_symbols(chip_watch_rows, chip_radar_symbols)
    if limit <= 0 or len(selected_symbols) < limit:
        add_symbols(legacy_rows, legacy_watch_symbols)

    for row in chip_radar_rows:
        symbol = _platform_symbol(row)
        if symbol and symbol not in chip_radar_symbols:
            chip_radar_symbols.append(symbol)
    for row in revised_rows:
        symbol = _platform_symbol(row)
        if symbol and symbol not in revised_symbols:
            revised_symbols.append(symbol)

    for row in legacy_pool_rows:
        symbol = _platform_symbol(row)
        if not symbol or symbol in legacy_pool_symbols:
            continue
        legacy_pool_symbols.append(symbol)
        if limit > 0 and len(legacy_pool_symbols) >= limit:
            break

    for symbol in (*legacy_pool_symbols, *chip_radar_symbols, *revised_symbols):
        if symbol and symbol not in analysis_symbols:
            analysis_symbols.append(symbol)

    if not selected_symbols:
        selected_symbols = list(fallback_symbols[:limit] if limit > 0 else fallback_symbols)
        legacy_watch_symbols = list(selected_symbols)
        legacy_pool_symbols = list(selected_symbols)
        analysis_symbols = list(selected_symbols)

    return CandidateSelectionPlan(
        tuple(selected_symbols),
        tuple(analysis_symbols),
        tuple(chip_radar_symbols),
        tuple(chip_breakout_symbols),
        tuple(revised_symbols),
        tuple(legacy_watch_symbols),
        tuple(legacy_pool_symbols),
    )


def _load_price_bars(path: Path | None) -> dict[str, list]:
    if not path or not path.exists():
        return {}
    try:
        return load_csv_ohlcv(path)
    except OSError:
        return {}


def _rank_revised_rows(rows: list[dict], news_terms: set[str], bars_by_symbol: dict[str, list]) -> list[dict]:
    filtered = [
        row
        for row in rows
        if _passes_revised_strategy(row, bars_by_symbol, require_margin=False, margin_top_100=set())
    ]
    return sorted(
        filtered,
        key=lambda row: (
            _platform_breakout_strength(_bars_for_row(row, bars_by_symbol)),
            100.0 - (_stochastic_k_value(_bars_for_row(row, bars_by_symbol)) or 100.0),
            _candidate_score(row, news_terms),
        ),
        reverse=True,
    )


def _rank_legacy_rows(rows: list[dict], news_terms: set[str]) -> list[dict]:
    return sorted(rows, key=lambda row: _candidate_score(row, news_terms), reverse=True)


def _rank_chip_breakout_rows(rows: list[dict], news_terms: set[str], bars_by_symbol: dict[str, list]) -> list[dict]:
    filtered = [row for row in rows if _passes_chip_breakout_strategy(row, bars_by_symbol)]
    return sorted(
        filtered,
        key=lambda row: (
            _chip_breakout_score(row, bars_by_symbol),
            _candidate_score(row, news_terms),
        ),
        reverse=True,
    )


def _rank_candidate_rows(rows: list[dict], news_terms: set[str], bars_by_symbol: dict[str, list]) -> list[dict]:
    chip_rows = _rank_chip_breakout_rows(rows, news_terms, bars_by_symbol)
    if chip_rows:
        return chip_rows
    revised_rows = _rank_revised_rows(rows, news_terms, bars_by_symbol)
    return revised_rows or _rank_legacy_rows(rows, news_terms)


def _rank_chip_radar_rows(rows: list[dict], news_terms: set[str], bars_by_symbol: dict[str, list]) -> list[dict]:
    filtered = [row for row in rows if _passes_chip_radar_strategy(row)]
    return sorted(
        filtered,
        key=lambda row: (
            _chip_radar_score(row),
            _platform_breakout_strength(_bars_for_row(row, bars_by_symbol)),
            _candidate_score(row, news_terms),
        ),
        reverse=True,
    )


def save_candidate_csv(path: Path, symbols: tuple[str, ...]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["rank", "symbol"])
        writer.writeheader()
        for rank, symbol in enumerate(symbols, start=1):
            writer.writerow({"rank": rank, "symbol": symbol})
    return path


# Hard filters for the short-swing strategy: mid/low price band with real liquidity.
MIN_UNIVERSE_PRICE = 10.0
MAX_UNIVERSE_PRICE = 50.0
MIN_AVG_DAILY_TURNOVER_TWD = 50_000_000.0


def _load_universe_rows(path: Path) -> list[dict]:
    flagged = load_regulatory_flag_symbols(path.parent / "tw_regulatory_flags.csv")
    excluded_regulatory = 0
    excluded_price_band = 0
    excluded_turnover = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            price = _float(row.get("price"))
            volume = _float(row.get("volume"))
            if price <= 0 or volume <= 0:
                continue
            symbol = str(row.get("symbol", "")).strip()
            if flagged.get(symbol):
                excluded_regulatory += 1
                continue
            if price < MIN_UNIVERSE_PRICE or price > MAX_UNIVERSE_PRICE:
                excluded_price_band += 1
                continue
            avg_volume = _float(row.get("avg_volume_20d")) or volume
            if price * avg_volume < MIN_AVG_DAILY_TURNOVER_TWD:
                excluded_turnover += 1
                continue
            rows.append(row)
    print(
        "universe_filter_excluded"
        f" regulatory={excluded_regulatory} price_band={excluded_price_band}"
        f" turnover={excluded_turnover} kept={len(rows)}",
        flush=True,
    )
    return rows


def _candidate_score(row: dict, news_terms: set[str]) -> float:
    price = _float(row.get("price"))
    volume = max(_float(row.get("volume")), _float(row.get("avg_volume_20d")))
    revenue_growth = _float(row.get("revenue_growth_yoy"))
    pe_ratio = _float(row.get("pe_ratio"))
    industry = str(row.get("industry", "")).lower()
    # Legacy heuristics stay only as tie-break support after the revised filters:
    # keep liquidity and basic quality, but avoid letting price buckets dominate.
    score = math.log10(max(volume, 1.0)) * 10
    score += _price_bucket_score(price) * 0.25
    score += max(min(revenue_growth, 80), -40) * 0.08
    score += 4 if 0 < pe_ratio <= 35 else 0
    score += 10 if any(term and term in industry for term in news_terms) else 0
    return score


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


def _bars_for_row(row: dict, bars_by_symbol: dict[str, list]) -> list:
    symbol = str(row.get("symbol", "")).strip().upper()
    platform_symbol = _platform_symbol(row).upper()
    return bars_by_symbol.get(symbol) or bars_by_symbol.get(platform_symbol) or []


def _margin_change_5d(row: dict) -> float | None:
    for key in (
        "margin_financing_change_5d",
        "margin_change_5d",
        "margin_5d_change",
        "five_day_margin_financing_change",
        "five_day_margin_change",
    ):
        value = str(row.get(key, "")).strip()
        if value:
            return _float(value)
    return None


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


def _platform_box_range(bars: list) -> tuple[float, float, float, int] | None:
    if len(bars) < 21:
        return None
    latest = bars[-1]
    best: tuple[float, float, float, int] | None = None
    for window_size in range(10, min(20, len(bars) - 1) + 1):
        setup = bars[-(window_size + 1) : -1]
        if len(setup) != window_size:
            continue
        highs = [bar.high for bar in setup if getattr(bar, "high", 0) > 0]
        lows = [bar.low for bar in setup if getattr(bar, "low", 0) > 0]
        closes = [bar.close for bar in setup if getattr(bar, "close", 0) > 0]
        if len(highs) != window_size or len(lows) != window_size or len(closes) != window_size:
            continue
        box_high = max(highs)
        box_low = min(lows)
        average_close = sum(closes) / len(closes)
        if average_close <= 0 or box_high <= box_low:
            continue
        compression = (box_high - box_low) / average_close
        if compression > 0.18:
            continue
        top_touch_count = sum(1 for bar in setup if bar.high >= box_high * 0.992)
        low_touch_count = sum(1 for bar in setup if bar.low <= box_low * 1.008)
        if top_touch_count < 2 or low_touch_count < 2:
            continue
        last_setup_close = setup[-1].close
        if last_setup_close >= box_high * 1.02 or last_setup_close <= box_low * 0.98:
            continue
        breakout_pct = latest.close / max(box_high, 0.01) - 1.0
        if breakout_pct <= 0:
            continue
        score = (0.18 - compression) * 1000.0 + breakout_pct * 1800.0 + window_size
        candidate = (box_high, box_low, compression, window_size)
        if best is None or score > ((0.18 - best[2]) * 1000.0 + (latest.close / max(best[0], 0.01) - 1.0) * 1800.0 + best[3]):
            best = candidate
    return best


def platform_neckline_price(bars: list) -> float | None:
    """Return the breakout platform's box-high (neckline) as a stop-loss reference."""
    box_range = _platform_box_range(bars)
    if box_range is None:
        return None
    return box_range[0]


def _platform_breakout_strength(bars: list) -> float:
    if len(bars) < 21:
        return 0.0
    latest = bars[-1]
    box_range = _platform_box_range(bars)
    if box_range is None:
        return 0.0
    box_high, box_low, compression, window_size = box_range
    if latest.close <= box_high:
        return 0.0
    breakout_pct = latest.close / max(box_high, 0.01) - 1.0
    if breakout_pct < 0.003:
        return 0.0
    breakout_body = (latest.close - max(latest.open, box_high)) / max(box_high, 0.01)
    if breakout_body < -0.002:
        return 0.0
    average_volume = sum(bar.volume for bar in bars[-(window_size + 1) : -1]) / float(window_size)
    volume_ratio = latest.volume / average_volume if average_volume else 1.0
    if volume_ratio < 1.2:
        return 0.0
    rebound_from_low = box_high / max(box_low, 0.01) - 1.0
    return (
        breakout_pct * 2600.0
        + max(0.0, 0.18 - compression) * 220.0
        + volume_ratio * 12.0
        + rebound_from_low * 80.0
    )


def _top10_main_force_strong(row: dict) -> bool:
    rank = _optional_float(row, "top10_main_force_buy_rank", "top10_main_force_rank")
    if rank is not None and rank > 0 and rank <= 10:
        return True
    strength = _top10_main_force_strength(row)
    if strength >= 60.0:
        return True
    net_buy = _optional_float(row, "top10_main_force_net_buy", "main_force_top10_net_buy")
    return net_buy is not None and net_buy > 0


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


def _price_bucket_score(price: float) -> float:
    if price < 30:
        return 10
    if price <= 100:
        return 8
    if price <= 200:
        return 4
    if price <= 500:
        return 1
    return -2


def _news_terms(news_path: Path | None) -> set[str]:
    if not news_path or not news_path.exists():
        return set()
    terms = set()
    for item in load_news(news_path):
        for industry in item.industries:
            text = industry.strip().lower()
            if text:
                terms.add(text)
    return terms


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


def _float(value) -> float:
    try:
        return float(str(value or "0").replace(",", "").strip())
    except ValueError:
        return 0.0


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
