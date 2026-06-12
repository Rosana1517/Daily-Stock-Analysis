from __future__ import annotations

import argparse

from stock_signal_system.cli_handlers import (
    handle_fetch_news,
    handle_fetch_tpex,
    handle_fetch_twse,
    handle_fetch_yfinance,
    handle_publish_pages,
    handle_refresh_data,
    handle_refresh_quant_ohlcv,
    handle_refresh_quant_realtime,
    handle_run,
    handle_validate_config,
    handle_verify_tpex,
    handle_verify_twse,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily stock signal pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Generate the daily report.")
    run_parser.add_argument("--config", required=True, help="Path to JSON config.")

    validate_parser = subparsers.add_parser("validate-config", help="Validate config files and required columns.")
    validate_parser.add_argument("--config", required=True, help="Path to JSON config.")

    refresh_parser = subparsers.add_parser("refresh-data", help="Refresh rolling daily data sources from config.")
    refresh_parser.add_argument("--config", required=True, help="Path to JSON config.")
    refresh_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")
    refresh_parser.add_argument("--skip-twse", action="store_true", help="Skip TWSE OpenAPI refresh.")
    refresh_parser.add_argument("--skip-tpex", action="store_true", help="Skip TPEx OpenAPI refresh.")

    quant_ohlcv_parser = subparsers.add_parser(
        "refresh-quant-ohlcv",
        help="Select quant candidates and refresh TW/OTC OHLCV history.",
    )
    quant_ohlcv_parser.add_argument("--config", required=True, help="Path to quant platform JSON config.")
    quant_ohlcv_parser.add_argument("--period", default="1y", help="OHLCV history period.")

    quant_realtime_parser = subparsers.add_parser(
        "refresh-quant-realtime",
        help="Refresh realtime quotes for quant candidate symbols.",
    )
    quant_realtime_parser.add_argument("--config", required=True, help="Path to quant platform JSON config.")
    quant_realtime_parser.add_argument("--cache", required=True, help="Realtime cache CSV path.")
    quant_realtime_parser.add_argument("--batch-size", type=int, default=75, help="Symbols per realtime request batch.")

    rss_parser = subparsers.add_parser("fetch-news", help="Fetch RSS news into a CSV file.")
    rss_parser.add_argument("--sources", required=True, help="Path to RSS sources JSON.")
    rss_parser.add_argument("--output", required=True, help="Output CSV path.")
    rss_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")

    yf_parser = subparsers.add_parser("fetch-yfinance", help="Fetch yfinance daily history into cache CSV.")
    yf_parser.add_argument("--symbols", nargs="+", required=True, help="Symbols, e.g. AAPL MSFT 2330.TW.")
    yf_parser.add_argument("--period", default="3mo", help="yfinance period.")
    yf_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")

    twse_parser = subparsers.add_parser("fetch-twse", help="Fetch selected TWSE OpenAPI datasets into system CSV files.")
    twse_parser.add_argument("--stocks-output", default="data/twse_stocks.csv", help="Output stock snapshot CSV.")
    twse_parser.add_argument("--prices-output", default="data/twse_price_daily.csv", help="Output daily OHLC CSV.")
    twse_parser.add_argument("--news-output", default="data/twse_material_news.csv", help="Output material news CSV.")
    twse_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")

    tpex_parser = subparsers.add_parser("fetch-tpex", help="Fetch TPEx OpenAPI datasets into system CSV files.")
    tpex_parser.add_argument("--stocks-output", default="data/tpex_stocks.csv", help="Output OTC stock snapshot CSV.")
    tpex_parser.add_argument("--prices-output", default="data/tpex_price_daily.csv", help="Output OTC daily OHLC CSV.")
    tpex_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")

    tpex_verify_parser = subparsers.add_parser("verify-tpex", help="Verify TPEx quotes and peratio endpoints.")
    tpex_verify_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")

    twse_verify_parser = subparsers.add_parser("verify-twse", help="Verify core TWSE OpenAPI endpoints.")
    twse_verify_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")

    pages_parser = subparsers.add_parser("publish-pages", help="Publish a generated HTML report to GitHub Pages repo.")
    pages_parser.add_argument("--report-html", required=True, help="Path to generated report HTML.")
    pages_parser.add_argument("--repo-dir", default="../Daily-Stock-Analysis", help="Local GitHub Pages repo directory.")
    pages_parser.add_argument(
        "--repo-url",
        default="https://github.com/Rosana1517/Daily-Stock-Analysis.git",
        help="GitHub Pages repo URL.",
    )
    pages_parser.add_argument(
        "--public-base-url",
        default="https://rosana1517.github.io/Daily-Stock-Analysis/reports",
        help="Public reports base URL.",
    )

    args = parser.parse_args()
    if args.command == "run":
        handle_run(args)
    elif args.command == "validate-config":
        handle_validate_config(args)
    elif args.command == "refresh-data":
        handle_refresh_data(args)
    elif args.command == "refresh-quant-ohlcv":
        handle_refresh_quant_ohlcv(args)
    elif args.command == "refresh-quant-realtime":
        handle_refresh_quant_realtime(args)
    elif args.command == "fetch-news":
        handle_fetch_news(args)
    elif args.command == "fetch-yfinance":
        handle_fetch_yfinance(args)
    elif args.command == "fetch-twse":
        handle_fetch_twse(args)
    elif args.command == "fetch-tpex":
        handle_fetch_tpex(args)
    elif args.command == "verify-tpex":
        handle_verify_tpex(args)
    elif args.command == "verify-twse":
        handle_verify_twse(args)
    elif args.command == "publish-pages":
        handle_publish_pages(args)


if __name__ == "__main__":
    main()
