from __future__ import annotations

from statistics import mean

from stock_signal_system.models import (
    CandlestickSignal,
    IndustrySignal,
    PortfolioAssessment,
    PortfolioPosition,
    PriceBar,
    StockSnapshot,
)


def assess_portfolio(
    positions: list[PortfolioPosition],
    stocks: list[StockSnapshot],
    industry_signals: list[IndustrySignal],
    price_history: dict[str, list[PriceBar]] | None = None,
    technicals: dict[str, CandlestickSignal] | None = None,
) -> list[PortfolioAssessment]:
    stock_by_symbol = {stock.symbol: stock for stock in stocks}
    industry_score = {signal.industry: signal.score for signal in industry_signals}
    price_history = price_history or {}
    technicals = technicals or {}

    assessments = [
        _assess_one(
            position,
            stock_by_symbol.get(position.symbol),
            industry_score,
            price_history.get(position.symbol, []),
            technicals.get(position.symbol),
        )
        for position in positions
    ]
    return sorted(assessments, key=lambda item: item.score)


def _assess_one(
    position: PortfolioPosition,
    stock: StockSnapshot | None,
    industry_score: dict[str, float],
    bars: list[PriceBar],
    technical: CandlestickSignal | None,
) -> PortfolioAssessment:
    current_price = _current_price(position, stock, bars)
    market_value = current_price * position.quantity
    unrealized_return = _return_pct(current_price, position.average_cost)
    score = 50.0
    reasons: list[str] = []
    risks: list[str] = []
    watch_levels: list[str] = []

    industry = position.industry or (stock.industry if stock else "")
    signal_score = industry_score.get(industry)
    if signal_score is not None:
        adjustment = (signal_score - 50) * 0.25
        score += adjustment
        reasons.append(f"產業前景分數 {signal_score:.1f}，對持倉分數影響 {adjustment:+.1f}")
    elif industry:
        risks.append(f"{industry} 今日缺少明確產業催化訊號")

    if stock:
        _score_fundamentals(stock, reasons, risks)
        score += _fundamental_adjustment(stock)
    else:
        risks.append("股票基本面資料庫尚未包含此持倉")

    momentum = _momentum(bars)
    if momentum is not None:
        if momentum >= 6:
            score += 10
            reasons.append(f"近 20 日價格動能 {momentum:.1f}%，趨勢仍偏多")
        elif momentum <= -6:
            score -= 12
            risks.append(f"近 20 日價格動能 {momentum:.1f}%，需要提防趨勢轉弱")
        else:
            reasons.append(f"近 20 日價格動能 {momentum:.1f}%，暫屬盤整")

    ma20 = _moving_average(bars, 20)
    if ma20:
        if current_price >= ma20:
            score += 5
            reasons.append(f"收盤價仍在 20 日均線 {ma20:.2f} 上方")
        else:
            score -= 8
            risks.append(f"收盤價跌破 20 日均線 {ma20:.2f}")
            watch_levels.append(f"重新站回 20 日均線 {ma20:.2f} 才算修復")

    if technical:
        score += technical.score_adjustment * 0.6
        reasons.append(f"技術型態偏向 {technical.bias}，分數調整 {technical.score_adjustment:+.1f}")
        if technical.bias == "bearish":
            risks.append("技術訊號轉弱，隔日續跌或反彈失敗風險升高")
        watch_levels.append(technical.stop_loss)
        watch_levels.append(technical.exit)

    if position.stop_loss:
        if current_price <= position.stop_loss:
            score -= 30
            risks.append(f"已觸及設定停損 {position.stop_loss:.2f}")
        else:
            distance = (current_price / position.stop_loss - 1) * 100
            watch_levels.append(f"停損 {position.stop_loss:.2f}，距離約 {distance:.1f}%")

    if position.target_price:
        distance = (position.target_price / current_price - 1) * 100 if current_price else 0
        watch_levels.append(f"目標價 {position.target_price:.2f}，距離約 {distance:.1f}%")
        if distance <= 3 and unrealized_return > 0:
            score -= 4
            reasons.append("接近目標價，適合開始規劃分批停利")

    if unrealized_return <= -10:
        score -= 10
        risks.append(f"帳面損益 {unrealized_return:.1f}%，若基本面或趨勢未修復應降低部位")
    elif unrealized_return >= 15:
        score += 4
        reasons.append(f"帳面損益 {unrealized_return:.1f}%，可用移動停利保護獲利")

    if position.thesis:
        reasons.append(f"原始持股理由：{position.thesis}")

    score = max(0, min(100, score))
    action = _action(score, risks)
    next_day_bias = _next_day_bias(score, technical, momentum)
    if not watch_levels:
        watch_levels.append("尚無明確價位，先以 20 日均線與前低作風控")

    return PortfolioAssessment(
        position=position,
        score=round(score, 1),
        action=action,
        next_day_bias=next_day_bias,
        unrealized_return_pct=round(unrealized_return, 2),
        market_value=round(market_value, 2),
        reasons=tuple(reasons),
        risks=tuple(risks),
        watch_levels=tuple(watch_levels),
    )


def _current_price(position: PortfolioPosition, stock: StockSnapshot | None, bars: list[PriceBar]) -> float:
    if position.current_price:
        return position.current_price
    if bars:
        return bars[-1].close
    if stock:
        return stock.price
    return 0.0


def _return_pct(price: float, cost: float) -> float:
    return (price / cost - 1) * 100 if price and cost else 0.0


def _momentum(bars: list[PriceBar]) -> float | None:
    if len(bars) < 2:
        return None
    lookback = bars[-20] if len(bars) >= 20 else bars[0]
    return _return_pct(bars[-1].close, lookback.close)


def _moving_average(bars: list[PriceBar], period: int) -> float | None:
    if not bars:
        return None
    source = bars[-period:]
    return mean(bar.close for bar in source)


def _fundamental_adjustment(stock: StockSnapshot) -> float:
    score = 0.0
    if stock.revenue_growth_yoy >= 15:
        score += 8
    elif stock.revenue_growth_yoy < 0:
        score -= 10
    if stock.operating_margin >= 12:
        score += 6
    elif stock.operating_margin < 5:
        score -= 5
    if stock.free_cash_flow_margin >= 8:
        score += 4
    elif stock.free_cash_flow_margin < 0:
        score -= 6
    if stock.debt_to_equity > 1.2:
        score -= 6
    if stock.pe_ratio > 35:
        score -= 5
    return score


def _score_fundamentals(stock: StockSnapshot, reasons: list[str], risks: list[str]) -> None:
    if stock.revenue_growth_yoy >= 15:
        reasons.append(f"營收年增 {stock.revenue_growth_yoy:.1f}%，公司成長仍有支撐")
    elif stock.revenue_growth_yoy < 0:
        risks.append(f"營收年增 {stock.revenue_growth_yoy:.1f}%，基本面轉弱")
    if stock.operating_margin >= 12:
        reasons.append(f"營業利益率 {stock.operating_margin:.1f}%，獲利品質尚可")
    elif stock.operating_margin < 5:
        risks.append(f"營業利益率 {stock.operating_margin:.1f}%，獲利緩衝偏薄")
    if stock.free_cash_flow_margin < 0:
        risks.append("自由現金流率為負，需追蹤現金轉換能力")
    if stock.pe_ratio > 35:
        risks.append(f"本益比 {stock.pe_ratio:.1f} 偏高，評價壓縮風險較大")


def _action(score: float, risks: list[str]) -> str:
    joined = " ".join(risks)
    if "已觸及設定停損" in joined:
        return "賣出/停損"
    if score >= 72:
        return "續抱"
    if score >= 58:
        return "續抱但提高警戒"
    if score >= 45:
        return "減碼觀察"
    return "賣出或等待重新轉強"


def _next_day_bias(score: float, technical: CandlestickSignal | None, momentum: float | None) -> str:
    if technical and technical.bias == "bullish" and score >= 58:
        return "偏漲"
    if technical and technical.bias == "bearish":
        return "偏跌"
    if momentum is not None:
        if momentum >= 6 and score >= 58:
            return "偏漲"
        if momentum <= -6 or score < 50:
            return "偏跌"
    return "震盪"

