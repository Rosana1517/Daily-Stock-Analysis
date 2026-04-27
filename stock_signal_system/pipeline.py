from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from stock_signal_system.config import AppConfig
from stock_signal_system.data.csv_sources import load_intraday_history, load_news, load_price_history, load_stocks
from stock_signal_system.industry import analyze_industries
from stock_signal_system.models import IndustrySignal, StockRecommendation, StockSnapshot
from stock_signal_system.notify import send_notification
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
    industry_signals = _ensure_min_industry_signals(industry_signals, stocks, required_industry_count)

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
        title=f"每日選股觀察報告 - {current_date.isoformat()}",
        body=notification_body,
        webhook_env=config.notification_webhook_env,
        line_channel_access_token_env=config.line_channel_access_token_env,
        line_to_env=config.line_to_env,
        line_broadcast=config.line_broadcast,
    )
    return PipelineResult(str(report_path), industry_signals, recommendations, notification_status)


def _ensure_min_industry_signals(
    industry_signals: list[IndustrySignal],
    stocks: list[StockSnapshot],
    min_count: int,
) -> list[IndustrySignal]:
    if len(industry_signals) >= min_count:
        return industry_signals
    existing = {item.industry for item in industry_signals}
    stock_industries = [industry for industry in DEFAULT_OBSERVATION_INDUSTRIES if any(s.industry == industry for s in stocks)]
    supplemented = list(industry_signals)
    for industry in stock_industries:
        if len(supplemented) >= min_count:
            break
        if industry in existing:
            continue
        supplemented.append(
            IndustrySignal(
                industry=industry,
                score=42.0,
                catalysts=("今日有效新聞證據不足，依固定台股追蹤領域列為備選觀察",),
                evidence_count=0,
            )
        )
        existing.add(industry)
    return supplemented


def _fill_recommendations(
    current: list[StockRecommendation],
    stocks: list[StockSnapshot],
    industry_signals: list[IndustrySignal],
    technicals: dict,
    trade_direction: str,
    limit: int,
) -> list[StockRecommendation]:
    existing_symbols = {item.stock.symbol for item in current}
    expanded = score_stocks(stocks, industry_signals, 0, technicals, trade_direction=trade_direction)
    combined = list(current)
    for item in expanded:
        if len(combined) >= limit:
            break
        if item.stock.symbol in existing_symbols:
            continue
        combined.append(item)
        existing_symbols.add(item.stock.symbol)
    return sorted(combined, key=lambda item: item.score, reverse=True)


def _notification_body(
    recommendations: list[StockRecommendation],
    report_path: str,
    notification_min_score: float,
    notification_mode: str,
    report: str,
    report_url: str | None = None,
) -> str:
    if notification_mode == "full_report":
        return report
    if notification_mode == "report_link":
        return _notification_link_summary(recommendations, report_path, notification_min_score, report_url)
    return _notification_summary(recommendations, report_path, notification_min_score)


def _notification_link_summary(
    recommendations: list[StockRecommendation],
    report_path: str,
    notification_min_score: float,
    report_url: str | None,
) -> str:
    summary = _notification_summary(recommendations, report_path, notification_min_score)
    if report_url:
        return f"{summary}\n\n完整可閱讀報告：\n{report_url}"
    return f"{summary}\n\n尚未設定公開報告網址，已產生本機報告：{report_path}"


def _notification_summary(
    recommendations: list[StockRecommendation],
    report_path: str,
    notification_min_score: float,
) -> str:
    high_priority = [item for item in recommendations if item.score >= notification_min_score]
    if not high_priority:
        picks = "、".join(f"{item.stock.symbol} {item.stock.name}({item.score:.1f})" for item in recommendations[:5])
        return f"今日沒有高優先標的。候選觀察：{picks}。完整報告：{report_path}"
    picks = "、".join(
        f"{item.stock.symbol} {item.stock.name}({item.score:.1f})" for item in high_priority[:5]
    )
    return f"高優先標的：{picks}。完整報告：{report_path}"
