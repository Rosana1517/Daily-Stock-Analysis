from __future__ import annotations

import argparse
import os
from pathlib import Path

from stock_signal_system.config import AppConfig
from stock_signal_system.data.finmind import FinMindClient
from stock_signal_system.data.rss_sources import fetch_rss_news, save_news_csv
from stock_signal_system.data.twse import build_twse_daily_price_csv, build_twse_material_news_csv, build_twse_stock_csv
from stock_signal_system.data.yfinance_source import download_yfinance_history
from stock_signal_system.pages_publish import publish_report_to_pages
from stock_signal_system.pipeline import run_pipeline
from stock_signal_system.validation import has_errors, validate_config


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

    rss_parser = subparsers.add_parser("fetch-news", help="Fetch RSS news into a CSV file.")
    rss_parser.add_argument("--sources", required=True, help="Path to RSS sources JSON.")
    rss_parser.add_argument("--output", required=True, help="Output CSV path.")
    rss_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")

    finmind_parser = subparsers.add_parser("fetch-finmind", help="Fetch Taiwan stock price rows from FinMind.")
    finmind_parser.add_argument("--stock-id", required=True, help="Taiwan stock id, e.g. 2330.")
    finmind_parser.add_argument("--start-date", required=True, help="YYYY-MM-DD.")
    finmind_parser.add_argument("--end-date", required=True, help="YYYY-MM-DD.")
    finmind_parser.add_argument("--token-env", default="FINMIND_TOKEN", help="Environment variable with FinMind token.")
    finmind_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")

    yf_parser = subparsers.add_parser("fetch-yfinance", help="Fetch yfinance daily history into cache CSV.")
    yf_parser.add_argument("--symbols", nargs="+", required=True, help="Symbols, e.g. AAPL MSFT 2330.TW.")
    yf_parser.add_argument("--period", default="3mo", help="yfinance period.")
    yf_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")

    twse_parser = subparsers.add_parser("fetch-twse", help="Fetch selected TWSE OpenAPI datasets into system CSV files.")
    twse_parser.add_argument("--stocks-output", default="data/twse_stocks.csv", help="Output stock snapshot CSV.")
    twse_parser.add_argument("--prices-output", default="data/twse_price_daily.csv", help="Output daily OHLC CSV.")
    twse_parser.add_argument("--news-output", default="data/twse_material_news.csv", help="Output material news CSV.")
    twse_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")

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
        config = AppConfig.from_file(args.config)
        result = run_pipeline(config)
        print(f"report_path={result.report_path}")
        print(f"industries={len(result.industry_signals)}")
        print(f"recommendations={len(result.recommendations)}")
        print(f"notification={result.notification_status}")
    elif args.command == "validate-config":
        config = AppConfig.from_file(args.config)
        messages = validate_config(config)
        for message in messages:
            print(message)
        if has_errors(messages):
            raise SystemExit(1)
    elif args.command == "refresh-data":
        config = AppConfig.from_file(args.config)
        if config.rss_sources_path:
            news = fetch_rss_news(config.rss_sources_path, Path(args.cache_dir))
            output = save_news_csv(news, config.news_path)
            print(f"rss_news_rows={len(news)}")
            print(f"rss_news_output={output}")
        else:
            print("rss_news_skipped=no_rss_sources_path")
        if args.skip_twse:
            print("twse_skipped=skip_twse")
        else:
            stocks_output = build_twse_stock_csv(Path("data/twse_stocks.csv"), Path(args.cache_dir))
            prices_output = build_twse_daily_price_csv(Path("data/twse_price_daily.csv"), Path(args.cache_dir))
            news_output = build_twse_material_news_csv(Path("data/twse_material_news.csv"), Path(args.cache_dir))
            print(f"twse_stocks_output={stocks_output}")
            print(f"twse_prices_output={prices_output}")
            print(f"twse_news_output={news_output}")
    elif args.command == "fetch-news":
        news = fetch_rss_news(Path(args.sources), Path(args.cache_dir))
        output = save_news_csv(news, Path(args.output))
        print(f"news_rows={len(news)}")
        print(f"output={output}")
    elif args.command == "fetch-finmind":
        client = FinMindClient(Path(args.cache_dir), token=os.getenv(args.token_env))
        rows = client.taiwan_stock_price(args.stock_id, args.start_date, args.end_date)
        print(f"rows={len(rows)}")
        if rows:
            print(rows[-1])
    elif args.command == "fetch-yfinance":
        output = download_yfinance_history(args.symbols, args.period, Path(args.cache_dir))
        print(f"output={output}")
    elif args.command == "fetch-twse":
        stocks_output = build_twse_stock_csv(Path(args.stocks_output), Path(args.cache_dir))
        prices_output = build_twse_daily_price_csv(Path(args.prices_output), Path(args.cache_dir))
        news_output = build_twse_material_news_csv(Path(args.news_output), Path(args.cache_dir))
        print(f"stocks_output={stocks_output}")
        print(f"prices_output={prices_output}")
        print(f"news_output={news_output}")
    elif args.command == "publish-pages":
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


if __name__ == "__main__":
    main()
