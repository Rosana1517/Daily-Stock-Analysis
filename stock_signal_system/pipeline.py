from __future__ import annotations

import json
import re
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
    report_url = public_report_url(config.report_public_base_url, html_report_path)
    _save_tw_hybrid_audit(config.report_dir, current_date, report_path, html_report_path, report, config)
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


def _save_tw_hybrid_audit(
    report_dir,
    report_date: date,
    markdown_path,
    html_path,
    report: str,
    config: AppConfig,
) -> None:
    """Write the minimum Taiwan daily-review audit contract beside the report."""
    data_gaps = []
    if not config.price_1h_path:
        data_gaps.append("price_1h_path 未設定，市場結構改用日線資料")
    if not config.price_5m_path:
        data_gaps.append("price_5m_path 未設定，流動性掃描改用日線資料")
    if not config.quant_realtime_cache_path or not config.quant_realtime_cache_path.exists():
        data_gaps.append("即時行情快取不存在或未設定")
    audit = {
        "report_date": report_date.isoformat(),
        "timezone": "Asia/Taipei",
        "branch": "market_day" if report_date.weekday() < 5 else "closed_market_weekend",
        "session": "09:00-13:30 Asia/Taipei",
        "market_scope": config.market_scope,
        "artifacts": {
            "markdown": str(markdown_path),
            "html": str(html_path),
        },
        "sources": [
            {"name": "TWSE", "url": "https://www.twse.com.tw/"},
            {"name": "TPEx", "url": "https://www.tpex.org.tw/"},
            {"name": "TPEx Industry Value Chain", "url": "https://ic.tpex.org.tw/"},
            {"name": "RSS sources", "path": str(config.rss_sources_path) if config.rss_sources_path else None},
        ],
        "data_gaps": data_gaps,
        "qa": {
            "markdown_exists": markdown_path.exists(),
            "html_exists": html_path.exists(),
            "html_shell": _html_contains_document_shell(html_path),
            "self_contained_html": _html_is_self_contained(html_path),
            "mobile_css_present": _html_has_mobile_css(html_path),
            "has_industry_chain_section": "## 產業鏈同步訊號" in report,
            "has_data_gap_section": "## 資料待補清單" in report,
            "no_investment_advice_claim": "保證獲利" not in report and "必買" not in report,
        },
    }
    audit_path = report_dir / f"tw_hybrid_{report_date.isoformat()}.audit.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_html_for_qa(html_path) -> str:
    try:
        return html_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _html_contains_document_shell(html_path) -> bool:
    content = _read_html_for_qa(html_path).lower()
    return "<html" in content and "</html>" in content


def _html_is_self_contained(html_path) -> bool:
    content = _read_html_for_qa(html_path)
    return not bool(re.search(r"<(?:link|script|img)[^>]+(?:href|src)=https?://", content, re.I))


def _html_has_mobile_css(html_path) -> bool:
    return bool(re.search(r"@media[^{}]*max-width", _read_html_for_qa(html_path), re.I))


def _first_report_sections(report: str, max_lines: int = 26) -> str:
    lines = [line for line in report.splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])
