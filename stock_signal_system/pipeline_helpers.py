from __future__ import annotations

from stock_signal_system.models import IndustrySignal, StockRecommendation, StockSnapshot
from stock_signal_system.strategies.rule_score import score_stocks


def _quant_notification_body(report: str, report_path: str, notification_mode: str, report_url: str | None) -> str:
    if notification_mode == "report_link" and report_url:
        return report_url
    if notification_mode == "report_link":
        return report_path
    return report


def _ensure_min_industry_signals(
    industry_signals: list[IndustrySignal],
    stocks: list[StockSnapshot],
    min_count: int,
    default_observation_industries: tuple[str, ...],
) -> list[IndustrySignal]:
    if len(industry_signals) >= min_count:
        return industry_signals
    existing = {item.industry for item in industry_signals}
    stock_industries = [industry for industry in default_observation_industries if any(s.industry == industry for s in stocks)]
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
                catalysts=("觀察到新的產業催化，建議持續追蹤市場變化",),
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
        return report_url or report_path
    return _notification_summary(recommendations, report_path, notification_min_score)


def _notification_link_summary(
    recommendations: list[StockRecommendation],
    report_path: str,
    notification_min_score: float,
    report_url: str | None,
) -> str:
    if report_url:
        return f"{_notification_pick_summary(recommendations, notification_min_score)}\n\n連結：{report_url}"
    summary = _notification_summary(recommendations, report_path, notification_min_score)
    return f"{summary}\n\n報告路徑：{report_path}"


def _notification_pick_summary(
    recommendations: list[StockRecommendation],
    notification_min_score: float,
) -> str:
    high_priority = [item for item in recommendations if item.score >= notification_min_score]
    if not high_priority:
        picks = ", ".join(f"{item.stock.symbol} {item.stock.name}({item.score:.1f})" for item in recommendations[:5])
        return f"尚未達高優先門檻，先觀察：{picks}"
    picks = ", ".join(f"{item.stock.symbol} {item.stock.name}({item.score:.1f})" for item in high_priority[:5])
    return f"高優先標的：{picks}"


def _notification_summary(
    recommendations: list[StockRecommendation],
    report_path: str,
    notification_min_score: float,
) -> str:
    high_priority = [item for item in recommendations if item.score >= notification_min_score]
    if not high_priority:
        picks = ", ".join(f"{item.stock.symbol} {item.stock.name}({item.score:.1f})" for item in recommendations[:5])
        return f"尚未達高優先門檻，先觀察：{picks}\n報告：{report_path}"
    picks = ", ".join(f"{item.stock.symbol} {item.stock.name}({item.score:.1f})" for item in high_priority[:5])
    return f"高優先標的：{picks}\n報告：{report_path}"
