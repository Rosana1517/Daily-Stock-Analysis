from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Optional

from stock_signal_system.config import AppConfig
from stock_signal_system.data.csv_sources import load_intraday_history, load_news, load_price_history, load_stocks
from stock_signal_system.industry import analyze_industries
from stock_signal_system.models import IndustrySignal, StockRecommendation
from stock_signal_system.notify import send_notification
from stock_signal_system.pipeline_helpers import (
    _ensure_min_industry_signals,
    _fill_recommendations,
    _notification_body,
    _quant_notification_body,
)
from stock_signal_system.report import build_report, public_report_url, save_report, save_report_html
from stock_signal_system.strategies.candlestick import analyze_candlesticks
from stock_signal_system.strategies.rule_score import score_stocks


DEFAULT_OBSERVATION_INDUSTRIES = ("AI伺服器", "半導體", "電力設備", "儲能", "散熱", "消費電子")


@dataclass(frozen=True)
class PipelineResult:
    report_path: str
    industry_signals: list[IndustrySignal]
    recommendations: list[StockRecommendation]
    notification_status: str


def run_pipeline(config: AppConfig, report_date: Optional[date] = None) -> PipelineResult:
    current_date = report_date or date.today()
    if config.quant_config_path:
        return _run_quant_hybrid_pipeline(config, current_date)

    news = load_news(config.news_path)
    stocks = load_stocks(config.stock_path)

    daily_history = {}
    structure_history = {}
    trigger_history = {}
    if config.price_history_path and config.price_history_path.exists():
        daily_history = load_price_history(config.price_history_path)
    if config.price_1h_path and config.price_1h_path.exists():
        structure_history = load_intraday_history(config.price_1h_path)
    if config.price_5m_path and config.price_5m_path.exists():
        trigger_history = load_intraday_history(config.price_5m_path)

    technicals = analyze_candlesticks(daily_history, structure_history, trigger_history) if daily_history else {}
    industry_signals = analyze_industries(news)
    if config.watch_industries:
        watched = set(config.watch_industries)
        industry_signals = [item for item in industry_signals if item.industry in watched]
    required_industry_count = max(config.min_industry_signals, config.min_recommendations)
    industry_signals = _ensure_min_industry_signals(
        industry_signals,
        stocks,
        required_industry_count,
        DEFAULT_OBSERVATION_INDUSTRIES,
    )

    limit = min(config.top_n, config.max_watchlist)
    recommendations = score_stocks(
        stocks,
        industry_signals,
        config.min_score,
        technicals,
        trade_direction=config.trade_direction,
    )
    if len(recommendations) < min(config.min_recommendations, limit):
        recommendations = _fill_recommendations(
            recommendations,
            stocks,
            industry_signals,
            technicals,
            config.trade_direction,
            limit,
        )
    recommendations = recommendations[:limit]

    report = build_report(current_date, industry_signals, recommendations)
    report_path = save_report(config.report_dir, current_date, report)
    html_report_path = save_report_html(config.report_dir, current_date, report)
    report_url = public_report_url(config.report_public_base_url, html_report_path)

    notification_body = _notification_body(
        recommendations,
        str(report_path),
        config.notification_min_score,
        config.notification_mode,
        report,
        report_url,
    )
    notification_status = send_notification(
        title=f"瘥?貉閫撖??- {current_date.isoformat()}",
        body=notification_body,
        webhook_env=config.notification_webhook_env,
        line_channel_access_token_env=config.line_channel_access_token_env,
        line_to_env=config.line_to_env,
        line_broadcast=config.line_broadcast,
    )
    return PipelineResult(str(report_path), industry_signals, recommendations, notification_status)


def _run_quant_hybrid_pipeline(config: AppConfig, current_date: date) -> PipelineResult:
    from quant_research_platform.config import QuantPlatformConfig
    from quant_research_platform.hybrid import run_tw_hybrid

    quant_config = QuantPlatformConfig.from_file(config.quant_config_path)
    quant_config = replace(quant_config, output_dir=config.report_dir)
    report_path, _csv_path, _qlib_path, _hybrid_status = run_tw_hybrid(
        quant_config,
        current_date,
        realtime_cache=config.quant_realtime_cache_path,
        news_path=config.news_path,
        rss_sources_path=config.rss_sources_path,
        notify=False,
        stock_snapshot_path=config.stock_path,
        price_1h_path=config.price_1h_path,
        price_5m_path=config.price_5m_path,
    )
    report = report_path.read_text(encoding="utf-8")
    html_report_path = save_report_html(config.report_dir, current_date, report)
    public_report_url(config.report_public_base_url, html_report_path)
    return PipelineResult(str(report_path), [], [], "disabled")
    report_url = public_report_url(config.report_public_base_url, html_report_path)
    notification_body = _quant_notification_body(report, str(report_path), config.notification_mode, report_url)
    notification_status = send_notification(
        title=current_date.isoformat() if config.notification_mode == "report_link" and report_url else f"Hybrid Quant 瘥?∠巨?勗? - {current_date.isoformat()}",
        body=notification_body,
        webhook_env=config.notification_webhook_env,
        line_channel_access_token_env=config.line_channel_access_token_env,
        line_to_env=config.line_to_env,
        line_broadcast=config.line_broadcast,
    )
    return PipelineResult(str(report_path), [], [], notification_status)


def _first_report_sections(report: str, max_lines: int = 26) -> str:
    lines = [line for line in report.splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])
