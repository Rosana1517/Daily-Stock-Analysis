from __future__ import annotations

from typing import Optional

from stock_signal_system.models import CandlestickSignal, IndustrySignal, StockRecommendation, StockSnapshot


def score_stocks(
    stocks: list[StockSnapshot],
    industry_signals: list[IndustrySignal],
    min_score: float,
    candlestick_signals: Optional[dict[str, CandlestickSignal]] = None,
    trade_direction: str = "long_only",
) -> list[StockRecommendation]:
    industry_score = {item.industry: item.score for item in industry_signals}
    technicals = candlestick_signals or {}
    recommendations = []

    for stock in stocks:
        if stock.industry not in industry_score:
            continue
        signal = technicals.get(stock.symbol)
        score, reasons, risks = _score_one(stock, industry_score[stock.industry], signal)
        entry_plan = signal.entry if signal else "等待價格站回關鍵均線或支撐，且量能確認後再評估進場"
        stop_loss = signal.stop_loss if signal else "收盤跌破最近支撐或多方型態失效時停損"
        exit_plan = signal.exit if signal else "題材轉弱、量能退潮、跌破波段支撐或達到目標價時分批出場"

        if trade_direction == "long_only" and signal and signal.bias == "bearish":
            score = min(score, 59)
            risks.append("技術結構偏空，僅列追蹤名單；不做空、不追價，需等待 1H/日線轉強後才評估做多")
            entry_plan = "目前不進場；等待日線止跌、1H 轉為 HH/HL，且 5M 回測不破後才重新評估"
            stop_loss = "若仍在空方結構中，維持觀察不建立部位"
            exit_plan = "若已持有，跌破前低或三線反向轉黑時應分批降低曝險"

        if score >= min_score:
            recommendations.append(
                StockRecommendation(
                    stock=stock,
                    score=round(score, 1),
                    rating=_rating(score),
                    reasons=tuple(reasons),
                    risks=tuple(risks),
                    entry_plan=entry_plan,
                    stop_loss=stop_loss,
                    exit_plan=exit_plan,
                )
            )

    return sorted(recommendations, key=lambda item: item.score, reverse=True)


def _score_one(
    stock: StockSnapshot,
    industry_score: float,
    signal: Optional[CandlestickSignal],
) -> tuple[float, list[str], list[str]]:
    score = industry_score * 0.35
    reasons: list[str] = [
        f"產業訊號分數 {industry_score:.1f}",
        "個股分析已納入基本面、估值、技術與投資論點框架",
        "多因子檢查已納入動能、財務、流動性與風險旗標",
    ]
    risks: list[str] = []

    momentum = (stock.price / stock.price_20d_ago - 1) * 100 if stock.price_20d_ago else 0
    volume_ratio = stock.volume / stock.avg_volume_20d if stock.avg_volume_20d else 1

    if momentum >= 8:
        score += 18
        reasons.append(f"20日價格動能 {momentum:.1f}%")
    elif momentum < -5:
        score -= 10
        risks.append(f"20日價格動能偏弱 {momentum:.1f}%")

    if volume_ratio >= 1.15:
        score += 10
        reasons.append(f"量能高於20日均量 {volume_ratio:.2f} 倍")
    elif volume_ratio < 0.7:
        risks.append(f"量能低於20日均量 {volume_ratio:.2f} 倍，流動性與追價力道不足")

    if stock.revenue_growth_yoy >= 15:
        score += 15
        reasons.append(f"營收年增 {stock.revenue_growth_yoy:.1f}%")
    elif stock.revenue_growth_yoy < 0:
        score -= 12
        risks.append(f"營收年增轉弱 {stock.revenue_growth_yoy:.1f}%")

    if stock.operating_margin >= 12:
        score += 10
        reasons.append(f"營業利益率 {stock.operating_margin:.1f}%")
    elif stock.operating_margin < 5:
        risks.append(f"營業利益率偏低 {stock.operating_margin:.1f}%")

    if stock.free_cash_flow_margin >= 8:
        score += 8
        reasons.append(f"自由現金流率 {stock.free_cash_flow_margin:.1f}%")
    elif stock.free_cash_flow_margin < 0:
        score -= 10
        risks.append("自由現金流為負")

    if stock.debt_to_equity <= 0.6:
        score += 6
        reasons.append(f"負債權益比 {stock.debt_to_equity:.2f}，財務槓桿可控")
    elif stock.debt_to_equity > 1.2:
        score -= 8
        risks.append(f"負債權益比偏高 {stock.debt_to_equity:.2f}")

    if stock.pe_ratio > 35:
        score -= 8
        risks.append(f"本益比偏高 {stock.pe_ratio:.1f}")
    elif stock.pe_ratio <= 25:
        score += 5
        reasons.append(f"估值未明顯過熱，本益比 {stock.pe_ratio:.1f}")

    if signal:
        score += signal.score_adjustment
        reasons.append(f"技術策略調整 {signal.score_adjustment:+.1f} 分，方向 {signal.bias}")
        reasons.extend(signal.patterns[:4])
        if signal.risk_reward is not None:
            reasons.append(f"估算風險收益比 {signal.risk_reward:.1f}:1")
            if signal.risk_reward < 2:
                risks.append(f"風險收益比 {signal.risk_reward:.1f}:1，低於 2:1 交易門檻")
        elif signal.bias == "bullish":
            risks.append("多方訊號尚未形成完整風險收益比，僅列候選觀察")

    if stock.notes:
        reasons.append(stock.notes)

    if signal and signal.bias == "bullish":
        if signal.risk_reward is not None and signal.risk_reward < 1:
            score = min(score, 69)
        elif signal.risk_reward is not None and signal.risk_reward < 2:
            score = min(score, 74)
        elif signal.risk_reward is None:
            score = min(score, 69)

    return max(0, min(100, score)), reasons, risks


def _rating(score: float) -> str:
    if score >= 80:
        return "高優先關注"
    if score >= 70:
        return "值得關注"
    return "候選觀察"
