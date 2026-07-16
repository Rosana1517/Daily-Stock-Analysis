"""CLI handlers for the quant research platform's candidate OHLCV/realtime
refresh and chip-breakout backtest subcommands."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from quant_research_platform.config import QuantPlatformConfig
from quant_research_platform.data import fetch_openbb_ohlcv, fetch_yahoo_ohlcv, load_csv_ohlcv, save_ohlcv_csv
from quant_research_platform.twse_realtime import poll_realtime_quotes
from quant_research_platform.universe import build_candidate_selection_plan
from stock_signal_system.cli_step_timer import _step_timer


def handle_backtest_chip_breakout(args) -> None:
    from stock_signal_system.chip_backtest import run_chip_breakout_backtest, save_backtest_report

    result = run_chip_breakout_backtest(
        Path(args.chip_dir),
        Path(args.price_dir),
        horizon=args.horizon,
    )
    print(f"backtest_signal_dates_scanned={result.signal_dates_scanned}", flush=True)
    print(f"backtest_trades={result.trade_count}", flush=True)
    if result.trade_count:
        print(f"backtest_win_rate={result.win_rate:.1%}", flush=True)
        print(f"backtest_avg_return_5d={result.average_return_5d:.2%}", flush=True)
        print(f"backtest_avg_max_return_5d={result.average_max_return_5d:.2%}", flush=True)
        output = save_backtest_report(result, Path(args.output))
        print(f"backtest_output={output}", flush=True)
    else:
        print(
            "backtest_no_trades=insufficient_history_or_no_signals"
            " (needs >=21 daily price snapshots plus 5 forward sessions)",
            flush=True,
        )


def handle_refresh_quant_ohlcv(args) -> None:
    config = QuantPlatformConfig.from_file(args.config)
    if not config.ohlcv_path:
        raise SystemExit("ERROR quant config missing ohlcv_path.")
    selection_plan = build_candidate_selection_plan(
        config.universe_path,
        config.symbols,
        config.universe_candidate_limit,
        ohlcv_path=config.ohlcv_path,
    )
    symbols = selection_plan.analysis_symbols or selection_plan.selected_symbols
    if not symbols:
        raise SystemExit("ERROR no quant candidate symbols available for OHLCV refresh.")
    with _step_timer("quant_candidate_ohlcv_refresh"):
        existing_all = load_csv_ohlcv(config.ohlcv_path) if config.ohlcv_path.exists() else {}
        existing_selected = {symbol: existing_all.get(symbol, []) for symbol in symbols}
        bars_by_symbol = fetch_openbb_ohlcv(symbols, config.openbb_provider, args.period)
        required_bars = max(60, int(config.lookback or 0))
        missing_symbols = tuple(
            symbol
            for symbol in symbols
            if len(bars_by_symbol.get(symbol, [])) < required_bars
        )
        if missing_symbols:
            retry_bars = fetch_yahoo_ohlcv(missing_symbols, args.period)
            for symbol in missing_symbols:
                retried = retry_bars.get(symbol, [])
                if len(retried) > len(bars_by_symbol.get(symbol, [])):
                    bars_by_symbol[symbol] = retried
        unresolved_symbols: list[str] = []
        tolerated_short_history: list[str] = []
        for symbol in symbols:
            current_bars = bars_by_symbol.get(symbol, [])
            if len(current_bars) >= required_bars:
                continue
            fallback_bars = existing_selected.get(symbol, [])
            if len(fallback_bars) >= required_bars:
                bars_by_symbol[symbol] = fallback_bars
            elif _should_tolerate_short_history(symbol, current_bars, required_bars, current_date=date.today()):
                tolerated_short_history.append(symbol)
            else:
                unresolved_symbols.append(symbol)
        merged_bars = dict(existing_all)
        merged_bars.update(bars_by_symbol)
        output = save_ohlcv_csv(config.ohlcv_path, merged_bars)
        rows = sum(len(rows) for rows in bars_by_symbol.values())
        print(f"quant_ohlcv_output={output}", flush=True)
        print(f"quant_candidate_symbols={len(symbols)}", flush=True)
        print(f"quant_ohlcv_rows={rows}", flush=True)
        print(f"quant_legacy_pool_symbols={len(selection_plan.legacy_pool_symbols)}", flush=True)
        print(f"quant_chip_radar_symbols={len(selection_plan.chip_radar_symbols)}", flush=True)
        print(f"quant_chip_breakout_symbols={len(selection_plan.chip_breakout_symbols)}", flush=True)
        if tolerated_short_history:
            detail = ", ".join(
                f"{symbol}({len(bars_by_symbol.get(symbol, []))} bars)"
                for symbol in tolerated_short_history
            )
            print(
                f"warning: quant_short_history_tolerated={detail}; latest available data kept for recent listing candidates",
                flush=True,
            )
        if unresolved_symbols:
            missing = ", ".join(unresolved_symbols)
            raise SystemExit(
                f"ERROR incomplete quant OHLCV coverage; missing >= {required_bars} bars for: {missing}"
            )


def handle_refresh_quant_realtime(args) -> None:
    config = QuantPlatformConfig.from_file(args.config)
    plan = build_candidate_selection_plan(
        config.universe_path,
        config.symbols,
        config.universe_candidate_limit,
        ohlcv_path=config.ohlcv_path,
    )
    symbols = plan.analysis_symbols or plan.selected_symbols
    if not symbols:
        raise SystemExit("ERROR no quant candidate symbols available for realtime refresh.")
    channels = [_symbol_to_realtime_channel(symbol) for symbol in symbols]
    with _step_timer("quant_candidate_realtime_refresh"):
        poll_realtime_quotes(
            channels,
            cache_path=Path(args.cache),
            interval_seconds=0.0,
            batch_size=args.batch_size,
            iterations=1,
            random_sleep_min=0.0,
            random_sleep_max=0.0,
        )
        print(f"quant_realtime_cache={Path(args.cache)}", flush=True)
        print(f"quant_realtime_symbols={len(symbols)}", flush=True)


def _symbol_to_realtime_channel(symbol: str) -> str:
    text = symbol.strip().upper()
    if ":" in text:
        return text.lower()
    if text.endswith(".TWO"):
        return f"otc:{text[:-4]}"
    if text.endswith(".TW"):
        return f"tse:{text[:-3]}"
    return f"tse:{text}"


def _should_tolerate_short_history(symbol: str, bars: list, required_bars: int, current_date: date) -> bool:
    if len(bars) >= required_bars or len(bars) < 20:
        return False
    latest = getattr(bars[-1], "timestamp", None)
    latest_date = latest.date() if latest else None
    if latest_date is None:
        return False
    return (current_date - latest_date).days <= 3
