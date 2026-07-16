"""CLI handlers for refreshing/verifying raw market data (RSS news, TWSE,
TPEx, chip snapshot) — the 'refresh-data', 'fetch-*', and 'verify-*'
subcommands."""

from __future__ import annotations

import csv
import shutil
from datetime import date
from pathlib import Path

from stock_signal_system.cli_step_timer import _step_timer
from stock_signal_system.config import AppConfig
from stock_signal_system.data.chip_snapshot import build_tw_chip_snapshot_csv, load_recent_twse_institutional_days
from stock_signal_system.data.rss_sources import fetch_rss_news, save_news_csv
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
    try:
        with _step_timer("tw_regulatory_flags_refresh"):
            from stock_signal_system.data.regulatory_flags import build_tw_regulatory_flags_csv

            flags_output = build_tw_regulatory_flags_csv(Path("data/tw_regulatory_flags.csv"), Path(args.cache_dir))
            print(f"regulatory_flags_output={flags_output}", flush=True)
    except Exception as exc:
        print(f"warning: regulatory_flags_refresh_failed={exc}", flush=True)
    if refreshed_paths:
        with _step_timer("combine_tw_market_data"):
            stock_inputs = [p for p in [Path("data/twse_stocks.csv"), Path("data/tpex_stocks.csv")] if p.exists()]
            chip_snapshot = Path("data/tw_chip_snapshot.csv")
            chip_snapshot_ready = False
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
                    _validate_chip_snapshot_schema(chip_snapshot)
                    chip_snapshot_ready = True
                    print(f"chip_snapshot_output={chip_snapshot}", flush=True)
            except Exception as exc:
                print(f"warning: chip_snapshot_refresh_failed={exc}", flush=True)
            if chip_snapshot_ready:
                stock_inputs.append(chip_snapshot)
                print(f"chip_snapshot_input={chip_snapshot}", flush=True)
            else:
                print("warning: chip_snapshot_unavailable=proceeding_without_chip_data", flush=True)
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
            _archive_daily_snapshots(chip_snapshot if chip_snapshot_ready else None, combined_prices)
    elif Path("examples/stocks.csv").exists() and Path("examples/price_history.csv").exists():
        Path("data").mkdir(exist_ok=True)
        shutil.copyfile("examples/stocks.csv", "data/tw_listed_otc_stocks.csv")
        shutil.copyfile("examples/price_history.csv", "data/tw_listed_otc_price_daily.csv")
        print("warning: market_refresh_unavailable=using_example_fallback", flush=True)
    else:
        raise SystemExit("ERROR no TWSE/TPEx data could be refreshed and no fallback examples are available.")


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


def _taipei_today() -> date:
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Taipei")).date()
    except Exception:
        return date.today()


def _archive_daily_snapshots(chip_snapshot: Path | None, combined_prices: Path | None) -> None:
    """Persist daily chip/price snapshots under reports/ so the publish step
    commits them, building history for win-rate tracking and backtests."""
    today = _taipei_today().isoformat()
    targets = []
    if chip_snapshot and chip_snapshot.exists():
        targets.append((chip_snapshot, Path("reports/chip_snapshots") / f"tw_chip_snapshot_{today}.csv"))
    if combined_prices and combined_prices.exists():
        targets.append((combined_prices, Path("reports/price_snapshots") / f"tw_price_daily_{today}.csv"))
    for source, target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            print(f"snapshot_archived={target}", flush=True)
        except OSError as exc:
            print(f"warning: snapshot_archive_failed={target} error={exc}", flush=True)


def _chip_candidate_symbols_and_volumes(*stock_paths: Path, limit: int = 30) -> tuple[tuple[str, ...], dict[str, int]]:
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


def _validate_chip_snapshot_schema(path: Path) -> None:
    required = {
        "symbol",
        "top10_main_force_buy_strength",
        "top10_main_force_net_buy",
        "branch_main_force_buy_streak_days",
        "foreign_buy_streak_days",
        "chip_data_source",
        "chip_data_source_status",
    }
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        fieldnames = set((csv.DictReader(handle).fieldnames or []))
    missing = sorted(required - fieldnames)
    if missing:
        raise ValueError(f"chip snapshot schema missing fields: {', '.join(missing)}")


def _ensure_quant_chip_snapshot_current(config: AppConfig, cache_dir: Path) -> None:
    if not config.quant_config_path:
        return
    chip_snapshot = Path("data/tw_chip_snapshot.csv")
    twse_stock_path = Path("data/twse_stocks.csv")
    tpex_stock_path = Path("data/tpex_stocks.csv")
    if not twse_stock_path.exists() or not tpex_stock_path.exists():
        return
    latest_official_date = _latest_available_twse_chip_date(cache_dir)
    if latest_official_date is None:
        return
    snapshot_date = _latest_chip_snapshot_date(chip_snapshot)
    if snapshot_date is not None and snapshot_date >= latest_official_date:
        return
    broker_symbols, latest_volume_by_symbol = _chip_candidate_symbols_and_volumes(twse_stock_path, tpex_stock_path)
    build_tw_chip_snapshot_csv(
        chip_snapshot,
        cache_dir,
        as_of=latest_official_date,
        broker_symbols=broker_symbols,
        latest_volume_by_symbol=latest_volume_by_symbol,
    )
    _validate_chip_snapshot_schema(chip_snapshot)
    combine_csv_files(
        [twse_stock_path, tpex_stock_path, chip_snapshot],
        Path("data/tw_listed_otc_stocks.csv"),
    )
    print(
        f"chip_snapshot_autorefresh=updated snapshot_date={latest_official_date.isoformat()} output={chip_snapshot}",
        flush=True,
    )


def _latest_available_twse_chip_date(cache_dir: Path) -> date | None:
    days = load_recent_twse_institutional_days(cache_dir, as_of=date.today(), lookback_sessions=1, max_calendar_days=7)
    return days[0].trade_date if days else None


def _latest_chip_snapshot_date(path: Path) -> date | None:
    if not path.exists():
        return None
    latest: date | None = None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw = str(row.get("chip_data_date", "")).strip()
            if not raw:
                continue
            try:
                parsed = date.fromisoformat(raw)
            except ValueError:
                continue
            if latest is None or parsed > latest:
                latest = parsed
    return latest
