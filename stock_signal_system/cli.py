from __future__ import annotations

import argparse
import os
from pathlib import Path

from stock_signal_system.config import AppConfig
from stock_signal_system.data.finmind import FinMindClient
from stock_signal_system.data.rss_sources import fetch_rss_news, save_news_csv
from stock_signal_system.data.screener_sources import build_yfinance_ohlcv_csv, refresh_screener_data
from stock_signal_system.data.twse import build_twse_daily_price_csv, build_twse_material_news_csv, build_twse_stock_csv
from stock_signal_system.data.tpex import build_tpex_daily_price_csv, build_tpex_stock_csv, combine_csv_files
from stock_signal_system.data.yfinance_source import download_yfinance_history
from stock_signal_system.low_reversal_screener import (
    ScreenerConfig,
    run_low_reversal_screener,
    serve_low_reversal_screener,
)
from stock_signal_system.pages_publish import publish_report_to_pages
from stock_signal_system.pipeline import run_pipeline
from stock_signal_system.portfolio_pipeline import run_portfolio_pipeline
from stock_signal_system.validation import has_errors, validate_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily stock signal pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Generate the daily report.")
    run_parser.add_argument("--config", required=True, help="Path to JSON config.")

    screener_parser = subparsers.add_parser("run-screener", help="Generate the low-position reversal screener.")
    screener_parser.add_argument("--config", required=True, help="Path to screener JSON config.")

    serve_screener_parser = subparsers.add_parser("serve-screener", help="Serve the dynamic low-position reversal screener.")
    serve_screener_parser.add_argument("--config", required=True, help="Path to screener JSON config.")
    serve_screener_parser.add_argument("--host", default="0.0.0.0", help="Bind host.")
    serve_screener_parser.add_argument("--port", type=int, default=8765, help="Bind port.")

    portfolio_parser = subparsers.add_parser("run-portfolio", help="Generate the daily portfolio hold/sell report.")
    portfolio_parser.add_argument("--config", required=True, help="Path to JSON config.")
    portfolio_parser.add_argument("--portfolio", help="Path to portfolio CSV. Overrides config portfolio_path.")

    validate_parser = subparsers.add_parser("validate-config", help="Validate config files and required columns.")
    validate_parser.add_argument("--config", required=True, help="Path to JSON config.")

    refresh_parser = subparsers.add_parser("refresh-data", help="Refresh rolling daily data sources from config.")
    refresh_parser.add_argument("--config", required=True, help="Path to JSON config.")
    refresh_parser.add_argument("--cache-dir", default=".cache", help="Cache directory.")
    refresh_parser.add_argument("--skip-twse", action="store_true", help="Skip TWSE OpenAPI refresh.")
    refresh_parser.add_argument("--skip-tpex", action="store_true", help="Skip TPEx OpenAPI refresh.")

    refresh_screener_parser = subparsers.add_parser(
        "refresh-screener-data",
        help="Refresh monthly revenue, dividend yield, and ex-dividend CSVs for the screener.",
    )
    refresh_screener_parser.add_argument("--data-dir", default="data", help="Output data directory.")
    refresh_screener_parser.add_argument(
        "--include-non-common",
        action="store_true",
        help="Keep ETFs and non-common-stock symbols in the raw screener data files.",
    )

    refresh_screener_ohlcv_parser = subparsers.add_parser(
        "refresh-screener-ohlcv",
        help="Refresh full-market yfinance OHLCV history for the screener universe.",
    )
    refresh_screener_ohlcv_parser.add_argument("--universe", default="data/twse_common_stock_universe.csv")
    refresh_screener_ohlcv_parser.add_argument("--output", default="data/tw_yahoo_ohlcv.csv")
    refresh_screener_ohlcv_parser.add_argument("--period", default="1y")
    refresh_screener_ohlcv_parser.add_argument("--batch-size", type=int, default=50)
    refresh_screener_ohlcv_parser.add_argument("--sleep-seconds", type=float, default=0.5)

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

    quant_ohlcv_parser = subparsers.add_parser(
        "refresh-quant-ohlcv",
        help="Refresh OHLCV history for the quant hybrid interactive chart.",
    )
    quant_ohlcv_parser.add_argument("--config", required=True, help="Path to quant platform JSON config.")
    quant_ohlcv_parser.add_argument("--period", default="1y", help="Yahoo Finance period, e.g. 6mo, 1y, 2y.")
    quant_ohlcv_parser.add_argument("--output", help="Override output CSV path. Defaults to quant config ohlcv_path.")

    quant_realtime_parser = subparsers.add_parser(
        "refresh-quant-realtime",
        help="Refresh TWSE MIS realtime quotes for the quant hybrid pipeline.",
    )
    quant_realtime_parser.add_argument("--config", required=True, help="Path to quant platform JSON config.")
    quant_realtime_parser.add_argument("--cache", default="data/twse_common_stock_realtime_cache.csv")
    quant_realtime_parser.add_argument("--batch-size", type=int, default=75)

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
    elif args.command == "run-screener":
        config = ScreenerConfig.from_file(args.config)
        paths = run_low_reversal_screener(config)
        print(f"html_path={paths.html_path}")
        print(f"csv_path={paths.csv_path}")
        print(f"json_path={paths.json_path}")
    elif args.command == "serve-screener":
        config = ScreenerConfig.from_file(args.config)
        serve_low_reversal_screener(config, args.host, args.port)
    elif args.command == "run-portfolio":
        config = AppConfig.from_file(args.config)
        result = run_portfolio_pipeline(config, Path(args.portfolio) if args.portfolio else None)
        print(f"report_path={result.report_path}")
        print(f"html_report_path={result.html_report_path}")
        print(f"positions={len(result.assessments)}")
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
        refreshed_paths = []
        if args.skip_twse:
            print("twse_skipped=skip_twse")
        else:
            stocks_output = build_twse_stock_csv(Path("data/twse_stocks.csv"), Path(args.cache_dir))
            prices_output = build_twse_daily_price_csv(Path("data/twse_price_daily.csv"), Path(args.cache_dir))
            news_output = build_twse_material_news_csv(Path("data/twse_material_news.csv"), Path(args.cache_dir))
            refreshed_paths.extend([stocks_output, prices_output])
            print(f"twse_stocks_output={stocks_output}")
            print(f"twse_prices_output={prices_output}")
            print(f"twse_news_output={news_output}")
        if args.skip_tpex:
            print("tpex_skipped=skip_tpex")
        else:
            tpex_stocks_output = build_tpex_stock_csv(Path("data/tpex_stocks.csv"), Path(args.cache_dir))
            tpex_prices_output = build_tpex_daily_price_csv(Path("data/tpex_price_daily.csv"), Path(args.cache_dir))
            refreshed_paths.extend([tpex_stocks_output, tpex_prices_output])
            print(f"tpex_stocks_output={tpex_stocks_output}")
            print(f"tpex_prices_output={tpex_prices_output}")
        if refreshed_paths:
            combined_stocks = combine_csv_files(
                [Path("data/twse_stocks.csv"), Path("data/tpex_stocks.csv")],
                Path("data/tw_listed_otc_stocks.csv"),
            )
            combined_prices = combine_csv_files(
                [Path("data/twse_price_daily.csv"), Path("data/tpex_price_daily.csv")],
                Path("data/tw_listed_otc_price_daily.csv"),
            )
            print(f"combined_stocks_output={combined_stocks}")
            print(f"combined_prices_output={combined_prices}")
    elif args.command == "refresh-screener-data":
        paths = refresh_screener_data(Path(args.data_dir), common_stock_only=not args.include_non_common)
        print(f"monthly_revenue_path={paths.monthly_revenue_path}")
        print(f"dividend_yield_path={paths.dividend_yield_path}")
        print(f"ex_dividend_path={paths.ex_dividend_path}")
    elif args.command == "refresh-screener-ohlcv":
        output = build_yfinance_ohlcv_csv(
            Path(args.universe),
            Path(args.output),
            period=args.period,
            batch_size=args.batch_size,
            sleep_seconds=args.sleep_seconds,
        )
        print(f"ohlcv_path={output}")
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
    elif args.command == "refresh-quant-ohlcv":
        from quant_research_platform.config import QuantPlatformConfig
        from quant_research_platform.data import fetch_yahoo_ohlcv, save_ohlcv_csv
        from quant_research_platform.universe import save_candidate_csv, select_candidate_symbols

        quant_config = QuantPlatformConfig.from_file(args.config)
        output = Path(args.output) if args.output else quant_config.ohlcv_path
        if not output:
            raise SystemExit("ERROR quant config does not define ohlcv_path; pass --output.")
        selected_symbols = select_candidate_symbols(
            quant_config.universe_path,
            quant_config.symbols,
            quant_config.universe_candidate_limit,
            Path("data/news_rss.csv"),
        )
        save_candidate_csv(Path("data/quant_candidates.csv"), selected_symbols)
        bars_by_symbol = fetch_yahoo_ohlcv(selected_symbols, args.period)
        saved = save_ohlcv_csv(output, bars_by_symbol)
        rows = sum(len(bars) for bars in bars_by_symbol.values())
        print(f"quant_ohlcv_output={saved}")
        print(f"quant_ohlcv_symbols={len(bars_by_symbol)}")
        print(f"quant_ohlcv_rows={rows}")
        print("quant_candidates=" + ",".join(selected_symbols))
    elif args.command == "refresh-quant-realtime":
        from quant_research_platform.config import QuantPlatformConfig
        from quant_research_platform.twse_realtime import poll_realtime_quotes

        quant_config = QuantPlatformConfig.from_file(args.config)
        symbols = [_realtime_symbol(symbol) for symbol in quant_config.symbols]
        poll_realtime_quotes(
            symbols,
            cache_path=Path(args.cache),
            batch_size=args.batch_size,
            iterations=1,
        )
        print(f"quant_realtime_cache={args.cache}")
        print(f"quant_realtime_symbols={len(symbols)}")
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


def _realtime_symbol(symbol: str) -> str:
    text = symbol.strip()
    upper = text.upper()
    if upper.endswith(".TWO"):
        return f"otc:{text.split('.', 1)[0]}"
    if upper.endswith(".TW"):
        return text.split(".", 1)[0]
    return text


if __name__ == "__main__":
    main()
