from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from stock_signal_system.config import AppConfig
from stock_signal_system.data.csv_sources import load_intraday_history, load_news, load_price_history, load_stocks
from stock_signal_system.industry import analyze_industries
from stock_signal_system.models import ChangeSummary, IndustrySignal, StockRecommendation, StockSnapshot
from stock_signal_system.notify import send_notification
from stock_signal_system.report import build_report, public_report_url, save_report, save_report_html
from stock_signal_system.strategies.candlestick import analyze_candlesticks
from stock_signal_system.strategies.rule_score import score_stocks


DEFAULT_OBSERVATION_INDUSTRIES = ("半導體", "AI伺服器", "電力設備", "儲能", "散熱", "電子零組件")


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
    previous_state = _load_previous_state(config.report_dir)

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

    limit = max(config.min_recommendations, min(config.top_n, config.max_watchlist))
    recommendations = score_stocks(
        stocks,
        industry_signals,
        config.min_score,
        technicals,
        trade_direction=config.trade_direction,
        previous_state=previous_state,
    )
    if len(recommendations) < min(config.min_recommendations, limit):
        recommendations = _fill_recommendations(
            recommendations,
            stocks,
            industry_signals,
            technicals,
            config.trade_direction,
            limit,
            previous_state,
        )
    recommendations = _apply_final_rank_changes(recommendations, previous_state)[:limit]
    change_summary = _build_change_summary(recommendations, industry_signals, previous_state)

    report = build_report(
        current_date,
        industry_signals,
        recommendations,
        change_summary,
        stock_universe_count=len(stocks),
    )
    report_path = save_report(config.report_dir, current_date, report)
    html_report_path = save_report_html(config.report_dir, current_date, report)
    report_url = public_report_url(config.report_public_base_url, html_report_path)
    _save_state(config.report_dir, current_date, industry_signals, recommendations)

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
    stock_industries = list(DEFAULT_OBSERVATION_INDUSTRIES)
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
                catalysts=("今日有效新聞證據不足，依固定台股追蹤領域列為備選觀察。",),
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
    previous_state: dict | None,
) -> list[StockRecommendation]:
    existing_symbols = {item.stock.symbol for item in current}
    expanded = score_stocks(
        stocks,
        industry_signals,
        0,
        technicals,
        trade_direction=trade_direction,
        previous_state=previous_state,
    )
    combined = list(current)
    for item in expanded:
        if len(combined) >= limit:
            break
        if item.stock.symbol in existing_symbols:
            continue
        combined.append(item)
        existing_symbols.add(item.stock.symbol)
    return sorted(combined, key=lambda item: item.score, reverse=True)


def _apply_final_rank_changes(
    recommendations: list[StockRecommendation],
    previous_state: dict | None,
) -> list[StockRecommendation]:
    ranked = sorted(recommendations, key=lambda item: item.score, reverse=True)
    if not previous_state:
        return ranked
    previous = previous_state.get("recommendations", {})
    updated = []
    for rank, item in enumerate(ranked, start=1):
        prior = previous.get(item.stock.symbol)
        if prior:
            rank_delta = int(prior.get("rank", rank)) - rank
            status = item.status
        else:
            rank_delta = None
            status = "新進候選"
        updated.append(
            StockRecommendation(
                stock=item.stock,
                score=item.score,
                rating=item.rating,
                reasons=item.reasons,
                risks=item.risks,
                entry_plan=item.entry_plan,
                stop_loss=item.stop_loss,
                exit_plan=item.exit_plan,
                freshness_score=item.freshness_score,
                change_score=item.change_score,
                score_delta=item.score_delta,
                rank_delta=rank_delta,
                status=status,
            )
        )
    return updated


def _build_change_summary(
    recommendations: list[StockRecommendation],
    industry_signals: list[IndustrySignal],
    previous_state: dict | None,
) -> ChangeSummary:
    current_symbols = {item.stock.symbol: item for item in recommendations}
    current_industries = {item.industry for item in industry_signals}
    if not previous_state:
        return ChangeSummary(
            new_symbols=tuple(current_symbols.keys()),
            industry_new=tuple(sorted(current_industries)),
        )
    previous_symbols = set(previous_state.get("recommendations", {}).keys())
    previous_industries = set(previous_state.get("industries", {}).keys())
    improved = [
        symbol
        for symbol, item in current_symbols.items()
        if item.score_delta is not None and item.score_delta >= 3
    ]
    weakened = [
        symbol
        for symbol, item in current_symbols.items()
        if item.score_delta is not None and item.score_delta <= -3
    ]
    return ChangeSummary(
        new_symbols=tuple(symbol for symbol in current_symbols if symbol not in previous_symbols),
        removed_symbols=tuple(symbol for symbol in previous_symbols if symbol not in current_symbols),
        improved_symbols=tuple(improved),
        weakened_symbols=tuple(weakened),
        industry_new=tuple(sorted(current_industries - previous_industries)),
        industry_removed=tuple(sorted(previous_industries - current_industries)),
    )


def _load_previous_state(report_dir: Path) -> dict | None:
    path = report_dir / "latest_state.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_state(
    report_dir: Path,
    report_date: date,
    industry_signals: list[IndustrySignal],
    recommendations: list[StockRecommendation],
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": report_date.isoformat(),
        "industries": {item.industry: {"score": item.score, "rank": rank} for rank, item in enumerate(industry_signals, start=1)},
        "recommendations": {
            item.stock.symbol: {
                "name": item.stock.name,
                "industry": item.stock.industry,
                "score": item.score,
                "rank": rank,
                "rating": item.rating,
            }
            for rank, item in enumerate(recommendations, start=1)
        },
    }
    (report_dir / "latest_state.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
        return _notification_link_only(report_path, report_url)
    return _notification_summary(recommendations, report_path, notification_min_score)


def _notification_link_only(report_path: str, report_url: str | None) -> str:
    if report_url:
        return f"\u5b8c\u6574\u5831\u544a\u9023\u7d50\uff1a{report_url}"
    return f"\u5b8c\u6574\u5831\u544a\u5df2\u7522\u51fa\uff1a{report_path}"

def _notification_summary(
    recommendations: list[StockRecommendation],
    report_path: str,
    notification_min_score: float,
) -> str:
    high_priority = [item for item in recommendations if item.score >= notification_min_score]
    if not high_priority:
        picks = "、".join(f"{item.stock.symbol} {item.stock.name}({item.score:.1f})" for item in recommendations[:5])
        return f"今日沒有達高優先門檻的標的；前 5 名觀察：{picks}。報告：{report_path}"
    picks = "、".join(
        f"{item.stock.symbol} {item.stock.name}({item.score:.1f})" for item in high_priority[:5]
    )
    return f"今日高優先觀察：{picks}。報告：{report_path}"
