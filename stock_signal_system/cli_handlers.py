from __future__ import annotations

import shutil
import time
import csv
from pathlib import Path

from quant_research_platform.config import QuantPlatformConfig
from quant_research_platform.data import fetch_openbb_ohlcv, save_ohlcv_csv
from quant_research_platform.twse_realtime import poll_realtime_quotes
from quant_research_platform.universe import select_candidate_symbols
from stock_signal_system.config import AppConfig
from stock_signal_system.data.rss_sources import fetch_rss_news, save_news_csv
from stock_signal_system.data.chip_snapshot import build_tw_chip_snapshot_csv
from stock_signal_system.data.tpex import (
    build_tpex_daily_price_csv,
    build_tpex_stock_csv,
    combine_csv_files,
    fetch_tpex_dataset,
)
from stock_signal_system.data.twse import (
    build_twse_daily_price_csv,
    build_twse_material_news_csv,
    build_twse_stock_csv,
    fetch_twse_dataset,
)
from stock_signal_system.data.yfinance_source import download_yfinance_history
from stock_signal_system.pages_publish import publish_report_to_pages
from stock_signal_system.pipeline import run_pipeline
from stock_signal_system.validation import has_errors, validate_config


def handle_run(args) -> None:
    config = AppConfig.from_file(args.config)
    result = run_pipeline(config)
    print(f"report_path={result.report_path}")
    print(f"industries={len(result.industry_signals)}")
    print(f"recommendations={len(result.recommendations)}")
    print(f"notification={result.notification_status}")


def handle_validate_config(args) -> None:
    config = AppConfig.from_file(args.config)
    messages = validate_config(config)
    for message in messages:
        print(message)
    if has_errors(messages):
        raise SystemExit(1)


def handle_refresh_data(args) -> None:
    config = AppConfig.from_file(args.config)
    if config.rss_sources_path:
        with _step_timer("rss_news_refresh"):
            news = fetch_rss_news(config.rss_sources_path, Path(args.cache_dir))
            output = save_news_csv(news, config.news_path)
            print(f"rss_news_rows={len(news)}", flush=True)
            print(f"rss_news_output={output}", flush=True)
    else:
        print("rss_news_skipped=no_rss_sources_path", flush=True)
    refreshed_paths = []
    if args.skip_twse:
        print("twse_skipped=skip_twse", flush=True)
    else:
        try:
            with _step_timer("twse_stock_snapshot_refresh"):
                stocks_output = build_twse_stock_csv(Path("data/twse_stocks.csv"), Path(args.cache_dir))
                refreshed_paths.append(stocks_output)
                print(f"twse_stocks_output={stocks_output}", flush=True)
            with _step_timer("twse_daily_price_refresh"):
                prices_output = build_twse_daily_price_csv(Path("data/twse_price_daily.csv"), Path(args.cache_dir))
                refreshed_paths.append(prices_output)
                print(f"twse_prices_output={prices_output}", flush=True)
            with _step_timer("twse_material_news_refresh"):
                news_output = build_twse_material_news_csv(Path("data/twse_material_news.csv"), Path(args.cache_dir))
                print(f"twse_news_output={news_output}", flush=True)
        except Exception as exc:
            print(f"warning: twse_refresh_failed={exc}", flush=True)
    if args.skip_tpex:
        print("tpex_skipped=skip_tpex", flush=True)
    else:
        try:
            with _step_timer("tpex_stock_snapshot_refresh"):
                tpex_stocks_output = build_tpex_stock_csv(Path("data/tpex_stocks.csv"), Path(args.cache_dir))
                refreshed_paths.append(tpex_stocks_output)
                print(f"tpex_stocks_output={tpex_stocks_output}", flush=True)
            with _step_timer("tpex_daily_price_refresh"):
                tpex_prices_output = build_tpex_daily_price_csv(Path("data/tpex_price_daily.csv"), Path(args.cache_dir))
                refreshed_paths.append(tpex_prices_output)
                print(f"tpex_prices_output={tpex_prices_output}", flush=True)
        except Exception as exc:
            print(f"warning: tpex_refresh_failed={exc}", flush=True)
    if refreshed_paths:
        with _step_timer("combine_tw_market_data"):
            stock_inputs = [Path("data/twse_stocks.csv"), Path("data/tpex_stocks.csv")]
            chip_snapshot = Path("data/tw_chip_snapshot.csv")
            try:
                with _step_timer("tw_chip_snapshot_refresh"):
                    broker_symbols, latest_volume_by_symbol = _chip_candidate_symbols_and_volumes(
                        Path("data/twse_stocks.csv"),
                        Path("data/tpex_stocks.csv"),
                    )
                    build_tw_chip_snapshot_csv(
                        chip_snapshot,
                        Path(args.cache_dir),
                        broker_symbols=broker_symbols,
                        latest_volume_by_symbol=latest_volume_by_symbol,
                    )
                    print(f"chip_snapshot_output={chip_snapshot}", flush=True)
            except Exception as exc:
                print(f"warning: chip_snapshot_refresh_failed={exc}", flush=True)
            if chip_snapshot.exists():
                stock_inputs.append(chip_snapshot)
                print(f"chip_snapshot_input={chip_snapshot}", flush=True)
            combined_stocks = combine_csv_files(
                stock_inputs,
                Path("data/tw_listed_otc_stocks.csv"),
            )
            combined_prices = combine_csv_files(
                [Path("data/twse_price_daily.csv"), Path("data/tpex_price_daily.csv")],
                Path("data/tw_listed_otc_price_daily.csv"),
            )
            print(f"combined_stocks_output={combined_stocks}", flush=True)
            print(f"combined_prices_output={combined_prices}", flush=True)
    elif Path("examples/stocks.csv").exists() and Path("examples/price_history.csv").exists():
        Path("data").mkdir(exist_ok=True)
        shutil.copyfile("examples/stocks.csv", "data/tw_listed_otc_stocks.csv")
        shutil.copyfile("examples/price_history.csv", "data/tw_listed_otc_price_daily.csv")
        print("warning: market_refresh_unavailable=using_example_fallback", flush=True)
    else:
        raise SystemExit("ERROR no TWSE/TPEx data could be refreshed and no fallback examples are available.")


def handle_refresh_quant_ohlcv(args) -> None:
    config = QuantPlatformConfig.from_file(args.config)
    if not config.ohlcv_path:
        raise SystemExit("ERROR quant config missing ohlcv_path.")
    symbols = select_candidate_symbols(
        config.universe_path,
        config.symbols,
        config.universe_candidate_limit,
        ohlcv_path=config.ohlcv_path,
    )
    if not symbols:
        raise SystemExit("ERROR no quant candidate symbols available for OHLCV refresh.")
    with _step_timer("quant_candidate_ohlcv_refresh"):
        bars_by_symbol = fetch_openbb_ohlcv(symbols, config.openbb_provider, args.period)
        output = save_ohlcv_csv(config.ohlcv_path, bars_by_symbol)
        rows = sum(len(rows) for rows in bars_by_symbol.values())
        print(f"quant_ohlcv_output={output}", flush=True)
        print(f"quant_candidate_symbols={len(symbols)}", flush=True)
        print(f"quant_ohlcv_rows={rows}", flush=True)


def handle_refresh_quant_realtime(args) -> None:
    config = QuantPlatformConfig.from_file(args.config)
    symbols = select_candidate_symbols(
        config.universe_path,
        config.symbols,
        config.universe_candidate_limit,
        ohlcv_path=config.ohlcv_path,
    )
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


def handle_fetch_news(args) -> None:
    news = fetch_rss_news(Path(args.sources), Path(args.cache_dir))
    output = save_news_csv(news, Path(args.output))
    print(f"news_rows={len(news)}")
    print(f"output={output}")


def handle_fetch_yfinance(args) -> None:
    output = download_yfinance_history(args.symbols, args.period, Path(args.cache_dir))
    print(f"output={output}")


def handle_fetch_twse(args) -> None:
    stocks_output = build_twse_stock_csv(Path(args.stocks_output), Path(args.cache_dir))
    prices_output = build_twse_daily_price_csv(Path(args.prices_output), Path(args.cache_dir))
    news_output = build_twse_material_news_csv(Path(args.news_output), Path(args.cache_dir))
    print(f"stocks_output={stocks_output}")
    print(f"prices_output={prices_output}")
    print(f"news_output={news_output}")


def handle_fetch_tpex(args) -> None:
    stocks_output = build_tpex_stock_csv(Path(args.stocks_output), Path(args.cache_dir))
    prices_output = build_tpex_daily_price_csv(Path(args.prices_output), Path(args.cache_dir))
    print(f"stocks_output={stocks_output}")
    print(f"prices_output={prices_output}")


def handle_verify_tpex(args) -> None:
    with _step_timer("tpex_quotes_endpoint_verify"):
        quotes = fetch_tpex_dataset("quotes", Path(args.cache_dir))
        print(f"tpex_quotes_rows={len(quotes)}", flush=True)
    with _step_timer("tpex_peratio_endpoint_verify"):
        peratio = fetch_tpex_dataset("peratio", Path(args.cache_dir))
        pe_rows = sum(1 for row in peratio if str(row.get("PriceEarningRatio", "")).strip())
        print(f"tpex_peratio_rows={len(peratio)}", flush=True)
        print(f"tpex_peratio_nonempty_pe_rows={pe_rows}", flush=True)


def handle_verify_twse(args) -> None:
    with _step_timer("twse_daily_all_endpoint_verify"):
        daily = fetch_twse_dataset("daily_all", Path(args.cache_dir))
        print(f"twse_daily_all_rows={len(daily)}", flush=True)
    with _step_timer("twse_valuation_endpoint_verify"):
        valuation = fetch_twse_dataset("valuation", Path(args.cache_dir))
        pe_rows = sum(1 for row in valuation if str(row.get("PEratio", "")).strip())
        print(f"twse_valuation_rows={len(valuation)}", flush=True)
        print(f"twse_valuation_nonempty_pe_rows={pe_rows}", flush=True)


def handle_publish_pages(args) -> None:
    result = publish_report_to_pages(
        Path(args.report_html),
        Path(args.repo_dir),
        public_base_url=args.public_base_url,
        repo_url=args.repo_url,
    )
    print(f"repo_dir={result.repo_dir}")
    print(f"report_name={result.report_name}")
    print(f"committed={result.committed}")
    print(f"pushed={result.pushed}")
    if result.url:
        print(f"url={result.url}")


def _symbol_to_realtime_channel(symbol: str) -> str:
    text = symbol.strip().upper()
    if ":" in text:
        return text.lower()
    if text.endswith(".TWO"):
        return f"otc:{text[:-4]}"
    if text.endswith(".TW"):
        return f"tse:{text[:-3]}"
    return f"tse:{text}"


def _chip_candidate_symbols_and_volumes(*stock_paths: Path, limit: int = 120) -> tuple[tuple[str, ...], dict[str, int]]:
    rows = []
    latest_volume_by_symbol: dict[str, int] = {}
    for path in stock_paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = str(row.get("symbol", "")).strip()
                market = str(row.get("market", "")).strip().lower()
                if not symbol or market not in {"tse", "twse"}:
                    continue
                volume = int(_safe_float(row.get("volume")))
                latest_volume_by_symbol[symbol] = volume
                rows.append((symbol, volume))
    rows.sort(key=lambda item: item[1], reverse=True)
    symbols = tuple(symbol for symbol, volume in rows[:limit] if volume > 0)
    return symbols, latest_volume_by_symbol


def _safe_float(value) -> float:
    try:
        return float(str(value or "0").replace(",", "").strip())
    except ValueError:
        return 0.0


class _step_timer:
    def __init__(self, name: str) -> None:
        self.name = name
        self.started_at = 0.0

    def __enter__(self):
        self.started_at = time.monotonic()
        print(f"step_start={self.name}", flush=True)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        elapsed = time.monotonic() - self.started_at
        if exc_type:
            print(f"step_failed={self.name} elapsed_seconds={elapsed:.1f} error={exc}", flush=True)
            return False
        print(f"step_done={self.name} elapsed_seconds={elapsed:.1f}", flush=True)
        return False
