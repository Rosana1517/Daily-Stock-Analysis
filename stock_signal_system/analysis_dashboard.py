from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from stock_signal_system.models import PriceBar, StockRecommendation


@dataclass(frozen=True)
class DashboardMetrics:
    ma5: float | None
    ma10: float | None
    ma20: float | None
    ma_alignment: str
    trend_score: float
    momentum_20d: float
    volume_ratio: float
    support_level: float | None
    resistance_level: float | None
    bias_ma5_pct: float | None
    drawdown_from_20d_high_pct: float | None
    volatility_20d_pct: float | None
    position_sizing: str
    confidence: str
    risk_level: str
    checklist: tuple[str, ...]


def build_dashboard_metrics(
    recommendations: list[StockRecommendation],
    daily_history: dict[str, list[PriceBar]] | None,
) -> dict[str, DashboardMetrics]:
    history = daily_history or {}
    return {item.stock.symbol: _build_one(item, history.get(item.stock.symbol, [])) for item in recommendations}


def _build_one(item: StockRecommendation, bars: list[PriceBar]) -> DashboardMetrics:
    stock = item.stock
    closes = [bar.close for bar in bars[-20:] if bar.close > 0]
    highs = [bar.high for bar in bars[-20:] if bar.high > 0]
    lows = [bar.low for bar in bars[-20:] if bar.low > 0]
    ranges = [((bar.high - bar.low) / bar.close) * 100 for bar in bars[-20:] if bar.close > 0]

    current_price = stock.price
    ma5 = _average(closes[-5:])
    ma10 = _average(closes[-10:])
    ma20 = _average(closes[-20:])
    support = min(lows) if lows else None
    resistance = max(highs) if highs else None
    momentum = ((current_price / stock.price_20d_ago) - 1) * 100 if stock.price_20d_ago else 0.0
    volume_ratio = stock.volume / stock.avg_volume_20d if stock.avg_volume_20d else 1.0
    bias_ma5 = ((current_price / ma5) - 1) * 100 if ma5 else None
    drawdown = ((current_price / resistance) - 1) * 100 if resistance else None
    volatility = mean(ranges) if ranges else None
    ma_alignment = _ma_alignment(current_price, ma5, ma10, ma20)
    trend_score = _trend_score(item.score, momentum, volume_ratio, ma_alignment)
    risk_level = _risk_level(item, volume_ratio, volatility, drawdown)

    return DashboardMetrics(
        ma5=ma5,
        ma10=ma10,
        ma20=ma20,
        ma_alignment=ma_alignment,
        trend_score=trend_score,
        momentum_20d=momentum,
        volume_ratio=volume_ratio,
        support_level=support,
        resistance_level=resistance,
        bias_ma5_pct=bias_ma5,
        drawdown_from_20d_high_pct=drawdown,
        volatility_20d_pct=volatility,
        position_sizing=_position_sizing(item.score, risk_level),
        confidence=_confidence(item.score, trend_score),
        risk_level=risk_level,
        checklist=_checklist(item, volume_ratio, ma_alignment),
    )


def _average(values: list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def _ma_alignment(current_price: float, ma5: float | None, ma10: float | None, ma20: float | None) -> str:
    if ma5 is None or ma10 is None or ma20 is None:
        return "資料不足"
    if current_price >= ma5 >= ma10 >= ma20:
        return "多頭排列"
    if current_price >= ma20 and ma5 >= ma20:
        return "偏多整理"
    if current_price < ma20:
        return "跌破月線"
    return "中性震盪"


def _trend_score(score: float, momentum: float, volume_ratio: float, ma_alignment: str) -> float:
    trend = score * 0.45
    if ma_alignment == "多頭排列":
        trend += 22
    elif ma_alignment == "偏多整理":
        trend += 14
    elif ma_alignment == "跌破月線":
        trend -= 12
    if momentum >= 8:
        trend += 12
    elif momentum >= 3:
        trend += 6
    elif momentum < -5:
        trend -= 8
    if volume_ratio >= 1.2:
        trend += 8
    elif volume_ratio < 0.7:
        trend -= 5
    return round(max(0, min(100, trend)), 1)


def _risk_level(
    item: StockRecommendation,
    volume_ratio: float,
    volatility: float | None,
    drawdown: float | None,
) -> str:
    risk_points = 0
    if item.risks:
        risk_points += min(2, len(item.risks))
    if volume_ratio < 0.7:
        risk_points += 1
    if volatility is not None and volatility >= 4:
        risk_points += 1
    if drawdown is not None and drawdown <= -8:
        risk_points += 1
    if item.stock.pe_ratio >= 35:
        risk_points += 1
    if risk_points >= 4:
        return "高"
    if risk_points >= 2:
        return "中"
    return "低"


def _position_sizing(score: float, risk_level: str) -> str:
    if risk_level == "高":
        return "試單 5% 以下，等待風險解除"
    if score >= 80:
        return "分批 15-25%，以突破確認後加碼"
    if score >= 70:
        return "分批 10-15%，拉回不破支撐再布局"
    return "觀察 5-10%，只在訊號轉強後試單"


def _confidence(score: float, trend_score: float) -> str:
    combined = (score + trend_score) / 2
    if combined >= 80:
        return "高"
    if combined >= 65:
        return "中"
    return "低"


def _checklist(item: StockRecommendation, volume_ratio: float, ma_alignment: str) -> tuple[str, ...]:
    checklist = [
        "日線題材與個股分數維持，避免只因單日消息追高。",
        "1H 結構維持 HH/HL，5M 出現突破或拉回承接再進場。",
        f"停損依既有規劃執行：{item.stop_loss}",
    ]
    if volume_ratio < 1:
        checklist.append("量能尚未放大，需等待量比回到 1 倍以上。")
    if ma_alignment in {"跌破月線", "資料不足"}:
        checklist.append("趨勢結構尚未完整，降低部位或延後進場。")
    return tuple(checklist)
