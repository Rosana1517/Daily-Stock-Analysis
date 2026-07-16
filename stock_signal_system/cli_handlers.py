"""CLI subcommand handlers. Split by concern:
- this module: the daily pipeline run/validate/publish handlers
- cli_handlers_market_data: RSS/TWSE/TPEx/chip-snapshot refresh + verify handlers
- cli_handlers_quant: quant-platform OHLCV/realtime refresh + backtest handlers

All handle_* names are re-exported here so `stock_signal_system.cli` keeps a
single import source.
"""

from __future__ import annotations

from pathlib import Path

from stock_signal_system.cli_handlers_market_data import (  # noqa: F401 (re-exported for tests)
    _ensure_quant_chip_snapshot_current,
    _validate_chip_snapshot_schema,
    handle_fetch_news,
    handle_fetch_tpex,
    handle_fetch_twse,
    handle_fetch_yfinance,
    handle_refresh_data,
    handle_verify_tpex,
    handle_verify_twse,
)
from stock_signal_system.cli_handlers_quant import (  # noqa: F401 (re-exported for tests)
    _should_tolerate_short_history,
    _symbol_to_realtime_channel,
    handle_backtest_chip_breakout,
    handle_refresh_quant_ohlcv,
    handle_refresh_quant_realtime,
)
from stock_signal_system.config import AppConfig
from stock_signal_system.pages_publish import publish_report_to_pages
from stock_signal_system.pipeline import run_pipeline
from stock_signal_system.validation import has_errors, validate_config

__all__ = [
    "handle_run",
    "handle_validate_config",
    "handle_publish_pages",
    "handle_refresh_data",
    "handle_fetch_news",
    "handle_fetch_yfinance",
    "handle_fetch_twse",
    "handle_fetch_tpex",
    "handle_verify_tpex",
    "handle_verify_twse",
    "handle_backtest_chip_breakout",
    "handle_refresh_quant_ohlcv",
    "handle_refresh_quant_realtime",
]


def handle_run(args) -> None:
    config = AppConfig.from_file(args.config)
    _ensure_quant_chip_snapshot_current(config, Path(".cache"))
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
