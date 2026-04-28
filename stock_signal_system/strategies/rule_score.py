from __future__ import annotations

from typing import Optional

from stock_signal_system.models import CandlestickSignal, StockRecommendation, StockSnapshot
from stock_signal_system.models import IndustrySignal


def score_stocks(
    stocks: list[StockSnapshot],
    industry_signals: list[IndustrySignal],
    min_score: float,
    candlestick_signals: Optional[dict[str, CandlestickSignal]] = None,
    trade_direction: str = "long_only",
    previous_state: Optional[dict] = None,
) -> list[StockRecommendation]:
    industry_score = {item.industry: item.score for item in industry_signals}
    technicals = candlestick_signals or {}
    recommendations: list[StockRecommendation] = []

    for stock in stocks:
        matched_industries = _stock_signal_industries(stock)
        matched_scores = [industry_score[industry] for industry in matched_industries if industry in industry_score]
        if not matched_scores:
            continue
        signal = technicals.get(stock.symbol)
        score, reasons, risks = _score_one(stock, max(matched_scores), signal)
        if len(matched_industries) > 1:
            reasons.append(f"主題對應：{'、'.join(matched_industries)}")
        freshness_score, change_score, score_delta, rank_delta, status = _change_features(
            stock.symbol, score, previous_state
        )
        score += freshness_score + change_score
        if freshness_score:
            reasons.append(f"新鮮度加分 {freshness_score:+.1f}: 近期未在前次名單或屬新進候選")
        if change_score:
            reasons.append(f"變化率加分 {change_score:+.1f}: 分數或排名較前次改善")

        entry_plan = signal.entry if signal else "等待日線維持多方排列，1H 轉為 HH/HL，5M 出現放量突破後再分批進場。"
        stop_loss = signal.stop_loss if signal else "跌破近期支撐或進場價下方 5-7% 停損；若量縮失守 1H 結構，先降低部位。"
        exit_plan = signal.exit if signal else "3-20 天波段操作；若漲幅達預期、跌破 1H 上升結構或產業訊號轉弱，分批出場。"

        if trade_direction == "long_only" and signal and signal.bias == "bearish":
            score = min(score, 59)
            risks.append("長線只做多條件下，技術面仍偏弱，暫列觀察不追價。")
            entry_plan = "目前不進場；等待日線止跌、1H 轉為 HH/HL，且 5M 放量突破壓力後再評估。"
            stop_loss = "若續創波段低點或量增跌破支撐，移出高優先名單。"
            exit_plan = "若反彈無量或新聞題材退潮，降評為普通觀察。"

        score = max(0, min(100, score))
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
                    freshness_score=round(freshness_score, 1),
                    change_score=round(change_score, 1),
                    score_delta=round(score_delta, 1) if score_delta is not None else None,
                    rank_delta=rank_delta,
                    status=status,
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
        "股票所屬產業與今日新聞、政策或輿情主題相符",
        "以 3-20 天波段為主要觀察週期，偏向順勢做多",
    ]
    risks: list[str] = []

    momentum = (stock.price / stock.price_20d_ago - 1) * 100 if stock.price_20d_ago else 0
    volume_ratio = stock.volume / stock.avg_volume_20d if stock.avg_volume_20d else 1

    if momentum >= 8:
        score += 18
        reasons.append(f"20 日價格動能 {momentum:.1f}%")
    elif momentum >= 3:
        score += 8
        reasons.append(f"20 日價格溫和轉強 {momentum:.1f}%")
    elif momentum < -5:
        score -= 10
        risks.append(f"20 日價格動能偏弱 {momentum:.1f}%")

    if volume_ratio >= 1.15:
        score += 10
        reasons.append(f"成交量為 20 日均量 {volume_ratio:.2f} 倍")
    elif volume_ratio < 0.7:
        risks.append(f"成交量僅為 20 日均量 {volume_ratio:.2f} 倍，短線追價力道不足")

    if stock.revenue_growth_yoy >= 15:
        score += 15
        reasons.append(f"月營收年增 {stock.revenue_growth_yoy:.1f}%")
    elif stock.revenue_growth_yoy < 0:
        score -= 12
        risks.append(f"月營收年增為負 {stock.revenue_growth_yoy:.1f}%")

    if stock.operating_margin >= 12:
        score += 10
        reasons.append(f"營業利益率 {stock.operating_margin:.1f}%")
    elif 0 < stock.operating_margin < 5:
        risks.append(f"營業利益率偏低 {stock.operating_margin:.1f}%")

    if stock.free_cash_flow_margin >= 8:
        score += 8
        reasons.append(f"自由現金流率 {stock.free_cash_flow_margin:.1f}%")
    elif stock.free_cash_flow_margin < 0:
        score -= 10
        risks.append("自由現金流率為負")

    if 0 < stock.debt_to_equity <= 0.6:
        score += 6
        reasons.append(f"負債權益比 {stock.debt_to_equity:.2f}，財務彈性佳")
    elif stock.debt_to_equity > 1.2:
        score -= 8
        risks.append(f"負債權益比偏高 {stock.debt_to_equity:.2f}")

    if stock.pe_ratio > 35:
        score -= 8
        risks.append(f"本益比偏高 {stock.pe_ratio:.1f}")
    elif 0 < stock.pe_ratio <= 25:
        score += 5
        reasons.append(f"本益比 {stock.pe_ratio:.1f}，評價未明顯過熱")

    if signal:
        score += signal.score_adjustment
        reasons.append(f"蠟燭圖與多週期結構調整 {signal.score_adjustment:+.1f}，方向 {signal.bias}")
        reasons.extend(signal.patterns[:4])
        if signal.risk_reward is not None:
            reasons.append(f"預估風報比 {signal.risk_reward:.1f}:1")
            if signal.risk_reward < 2:
                risks.append(f"風報比 {signal.risk_reward:.1f}:1，低於 2:1 時不宜追價")
        elif signal.bias == "bullish":
            risks.append("技術面偏多但尚未能完整估算風報比，需用 1H/5M 確認進場點。")

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


def _change_features(symbol: str, raw_score: float, previous_state: Optional[dict]) -> tuple[float, float, Optional[float], Optional[int], str]:
    if not previous_state:
        return 2.0, 0.0, None, None, "新進候選"
    previous = previous_state.get("recommendations", {})
    if symbol not in previous:
        return 6.0, 0.0, None, None, "新進候選"

    prior = previous[symbol]
    prior_score = float(prior.get("score", 0))
    prior_rank = int(prior.get("rank", 999))
    score_delta = raw_score - prior_score
    rank_delta = prior_rank
    change_score = 0.0
    if score_delta >= 8:
        change_score += 5
    elif score_delta >= 3:
        change_score += 2
    elif score_delta <= -8:
        change_score -= 4
    elif score_delta <= -3:
        change_score -= 2

    if prior_rank > 5:
        change_score += 2

    return 0.0, max(-5.0, min(7.0, change_score)), score_delta, rank_delta, "續抱/續觀察"


def _rating(score: float) -> str:
    if score >= 80:
        return "高優先觀察"
    if score >= 70:
        return "值得關注"
    return "續抱/續觀察"


def _stock_signal_industries(stock: StockSnapshot) -> tuple[str, ...]:
    themes = {stock.industry}
    text = f"{stock.symbol} {stock.name} {stock.industry}"
    if stock.symbol in {"2382", "3231", "6669", "2356", "2317", "2308"} or any(
        term in text for term in ("伺服器", "電腦及週邊", "網通")
    ):
        themes.add("AI伺服器")
    if stock.symbol in {"2330", "2454", "2303", "2379", "3034", "3443"} or "半導體" in text:
        themes.add("半導體")
    if stock.symbol in {"3017", "3324", "3653", "2421"} or any(term in text for term in ("散熱", "電機機械")):
        themes.add("散熱")
    if stock.symbol in {"1513", "1504", "1605", "1609", "1611"} or any(term in text for term in ("電力", "電機", "電器電纜")):
        themes.add("電力設備")
    if stock.symbol in {"2308", "1513", "1504", "6443"} or any(term in text for term in ("儲能", "電池", "電源")):
        themes.add("儲能")
    if stock.symbol in {"2317", "2324", "4938", "2354"}:
        themes.add("消費電子")
    return tuple(sorted(themes))
