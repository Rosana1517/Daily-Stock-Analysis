from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from stock_signal_system.config import AppConfig
from stock_signal_system.data.csv_sources import load_news, load_portfolio, load_price_history, load_stocks
from stock_signal_system.industry import analyze_industries
from stock_signal_system.models import PortfolioAssessment
from stock_signal_system.portfolio import assess_portfolio
from stock_signal_system.portfolio_report import (
    build_portfolio_report,
    save_portfolio_report,
    save_portfolio_report_html,
)
from stock_signal_system.strategies.candlestick import analyze_candlesticks


@dataclass(frozen=True)
class PortfolioPipelineResult:
    report_path: str
    html_report_path: str
    assessments: list[PortfolioAssessment]


def run_portfolio_pipeline(
    config: AppConfig,
    portfolio_path: Path | None = None,
    report_date: date | None = None,
) -> PortfolioPipelineResult:
    current_date = report_date or date.today()
    path = portfolio_path or config.portfolio_path
    if path is None:
        raise ValueError("portfolio_path is required for portfolio analysis")

    positions = load_portfolio(path)
    stocks = load_stocks(config.stock_path)
    news = load_news(config.news_path)
    price_history = {}
    if config.price_history_path and config.price_history_path.exists():
        price_history = load_price_history(config.price_history_path)
    technicals = analyze_candlesticks(price_history) if price_history else {}
    industry_signals = analyze_industries(news)

    assessments = assess_portfolio(
        positions=positions,
        stocks=stocks,
        industry_signals=industry_signals,
        price_history=price_history,
        technicals=technicals,
    )
    report = build_portfolio_report(current_date, assessments)
    report_path = save_portfolio_report(config.report_dir, current_date, report)
    html_report_path = save_portfolio_report_html(config.report_dir, current_date, report)
    return PortfolioPipelineResult(str(report_path), str(html_report_path), assessments)
