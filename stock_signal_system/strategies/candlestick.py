from __future__ import annotations

from statistics import mean
from typing import Optional

from stock_signal_system.models import CandlestickSignal, PriceBar
from stock_signal_system.strategies.market_structure import (
    inverse_fvg_signal,
    liquidity_sweep_signal,
    market_structure_bias,
    previous_session_targets,
)


def analyze_candlesticks(
    history: dict[str, list[PriceBar]],
    structure_history: Optional[dict[str, list[PriceBar]]] = None,
    trigger_history: Optional[dict[str, list[PriceBar]]] = None,
) -> dict[str, CandlestickSignal]:
    signals = {}
    for symbol, bars in history.items():
        if len(bars) >= 5:
            signals[symbol] = _analyze_symbol(
                symbol,
                bars,
                (structure_history or {}).get(symbol),
                (trigger_history or {}).get(symbol),
            )
    return signals


def _analyze_symbol(
    symbol: str,
    bars: list[PriceBar],
    structure_bars: Optional[list[PriceBar]] = None,
    trigger_bars: Optional[list[PriceBar]] = None,
) -> CandlestickSignal:
    recent = bars[-1]
    previous = bars[-2]
    structure_source = structure_bars if structure_bars and len(structure_bars) >= 5 else bars
    trigger_source = trigger_bars if trigger_bars and len(trigger_bars) >= 5 else bars

    patterns: list[str] = []
    risks: list[str] = []
    adjustment = 0.0

    uptrend = _trend(bars[-6:]) > 0.03
    downtrend = _trend(bars[-6:]) < -0.03
    support = min(bar.low for bar in bars[-10:-1])
    resistance = max(bar.high for bar in bars[-10:-1])
    near_support = recent.low <= support * 1.03
    near_resistance = recent.high >= resistance * 0.97

    structure = market_structure_bias(structure_source)
    sweep = liquidity_sweep_signal(trigger_source)
    ifvg = inverse_fvg_signal(trigger_source)

    if structure == "bullish":
        patterns.append("1H/Daily 市場結構為 HH/HL，只優先尋找多方機會")
        adjustment += 8
    elif structure == "bearish":
        patterns.append("1H/Daily 市場結構為 LH/LL，只優先尋找空方或減碼機會")
        adjustment -= 8

    if _hammer(recent) and (downtrend or near_support):
        patterns.append("錘子線出現在跌勢或支撐區")
        adjustment += 12
    if _shooting_star(recent) and (uptrend or near_resistance):
        patterns.append("流星線出現在漲勢或壓力區")
        adjustment -= 12
        risks.append("高位拒絕高價，需等隔日收盤確認")
    if _doji(recent) and (uptrend or downtrend):
        patterns.append("十字星顯示原趨勢猶豫")
        adjustment += -5 if uptrend else 5
    if _high_wave(recent):
        patterns.append("高浪線/紡錘線，動能衰減")
        adjustment -= 4

    engulfing = _engulfing(previous, recent)
    if engulfing == "bullish" and (downtrend or near_support):
        patterns.append("多頭吞噬發生在趨勢末端或支撐區")
        adjustment += 16
    elif engulfing == "bearish" and (uptrend or near_resistance):
        patterns.append("空頭吞噬發生在高位或壓力區")
        adjustment -= 16
        risks.append("空頭吞噬，短線應避免追高")

    two_bar = _two_bar_reversal(previous, recent)
    if two_bar == "piercing" and (downtrend or near_support):
        patterns.append("刺穿形態，收盤切入前黑 K 實體一半以上")
        adjustment += 12
    elif two_bar == "dark_cloud" and (uptrend or near_resistance):
        patterns.append("烏雲蓋頂，收盤切入前白 K 實體一半以上")
        adjustment -= 12
        risks.append("烏雲蓋頂，賣壓已切入前日實體")

    star = _star_pattern(bars[-3:])
    if star == "morning" and (downtrend or near_support):
        patterns.append("啟明星，底部反轉確認")
        adjustment += 18
    elif star == "evening" and (uptrend or near_resistance):
        patterns.append("黃昏星，頂部反轉確認")
        adjustment -= 18
        risks.append("黃昏星，優先保護獲利")

    if _bullish_gap(previous, recent):
        patterns.append("上升窗口，缺口下緣可視為支撐")
        adjustment += 7
    elif _bearish_gap(previous, recent):
        patterns.append("下降窗口，缺口上緣可視為壓力")
        adjustment -= 7
        risks.append("下降窗口未回補前偏弱")

    record_highs = _record_highs(bars[-10:])
    record_lows = _record_lows(bars[-10:])
    if record_highs >= 8:
        patterns.append(f"迭創新高 {record_highs} 根，市場可能過度延伸")
        adjustment -= 10
        risks.append("連續新高後應分批獲利或提高停利")
    if record_lows >= 8:
        patterns.append(f"迭創新低 {record_lows} 根，空方可能過度延伸")
        adjustment += 8

    t_break = _three_line_break(bars)
    if t_break == "bullish":
        patterns.append("三線反向突破轉白，突破前三根高點")
        adjustment += 10
    elif t_break == "bearish":
        patterns.append("三線反向突破轉黑，跌破前三根低點")
        adjustment -= 10
        risks.append("三線反向突破轉弱")

    disparity = _disparity(bars, 10)
    if disparity is not None:
        if disparity > 10:
            patterns.append(f"差異指數 {disparity:.1f}%，偏離均線過高")
            adjustment -= 8
            risks.append("價格相對均線過度伸展")
        elif disparity < -10:
            patterns.append(f"差異指數 {disparity:.1f}%，偏離均線過低")
            adjustment += 6

    if _spring(bars):
        patterns.append("彈簧線，跌破支撐後收回")
        adjustment += 14
    if _upthrust(bars):
        patterns.append("上插線，突破壓力後收回")
        adjustment -= 14
        risks.append("上插線顯示假突破")

    if sweep == "bullish_sweep":
        patterns.append("5M 掃下方流動性後收回，符合多方掃盤條件")
        adjustment += 10
    elif sweep == "bearish_sweep":
        patterns.append("5M 掃上方流動性後收回，符合空方掃盤條件")
        adjustment -= 10
        risks.append("上方流動性被掃後收回，追高風險升高")

    if ifvg == "bullish_ifvg":
        patterns.append("5M 出現多方反轉型公平價值缺口 IFVG")
        adjustment += 12
    elif ifvg == "bearish_ifvg":
        patterns.append("5M 出現空方反轉型公平價值缺口 IFVG")
        adjustment -= 12
        risks.append("空方 IFVG 出現，等待反彈受阻或減碼")

    trigger_bias = _bias_hint(sweep, ifvg)
    if structure == "bullish" and trigger_bias == "bearish":
        risks.append("1H 偏多但 5M 出現空方觸發，等待方向重新一致")
        adjustment -= 8
    elif structure == "bearish" and trigger_bias == "bullish":
        risks.append("1H 偏空但 5M 出現多方觸發，僅視為反彈")
        adjustment -= 8

    if not patterns:
        patterns.append("未出現明確蠟燭圖觸發，維持基本面與產業訊號權重")

    bias = "bullish" if adjustment > 5 else "bearish" if adjustment < -5 else "neutral"
    stop = _stop_loss(bars, trigger_source, bias)
    fallback_target = _target_price(bars, bias)
    target, opposite_level = previous_session_targets(bars, bias)
    if bias == "bullish" and target <= recent.close:
        target = fallback_target
    elif bias == "bearish" and target >= recent.close:
        target = fallback_target
    rr = _risk_reward(recent.close, stop, target, bias)
    entry = _entry_plan(bias, recent, support, resistance, ifvg)
    exit_plan = _exit_plan(bias, target, opposite_level)

    if bias == "bullish":
        if rr is None:
            adjustment -= 18
            risks.append("尚無有效上方目標，風險收益比不足")
        elif rr < 1:
            adjustment -= 18
            risks.append(f"風險收益比 {rr:.1f}:1，遠低於 2:1 門檻")
        elif rr < 2:
            adjustment -= 10
            risks.append(f"風險收益比 {rr:.1f}:1，低於 2:1 門檻")

    return CandlestickSignal(
        symbol=symbol,
        bias=bias,
        score_adjustment=max(-25, min(25, adjustment)),
        patterns=tuple(patterns + risks),
        entry=entry,
        stop_loss=f"收盤跌破 {stop:.2f} 時停損" if bias != "bearish" else f"收盤突破 {stop:.2f} 時停損",
        exit=exit_plan,
        risk_reward=rr,
        structure_bias=structure,
    )


def _bias_hint(sweep: Optional[str], ifvg: Optional[str]) -> str:
    if sweep == "bullish_sweep" or ifvg == "bullish_ifvg":
        return "bullish"
    if sweep == "bearish_sweep" or ifvg == "bearish_ifvg":
        return "bearish"
    return "neutral"


def _body(bar: PriceBar) -> float:
    return abs(bar.close - bar.open)


def _range(bar: PriceBar) -> float:
    return max(0.01, bar.high - bar.low)


def _upper_shadow(bar: PriceBar) -> float:
    return bar.high - max(bar.open, bar.close)


def _lower_shadow(bar: PriceBar) -> float:
    return min(bar.open, bar.close) - bar.low


def _is_white(bar: PriceBar) -> bool:
    return bar.close > bar.open


def _is_black(bar: PriceBar) -> bool:
    return bar.close < bar.open


def _hammer(bar: PriceBar) -> bool:
    return _lower_shadow(bar) >= _body(bar) * 3 and _upper_shadow(bar) <= _range(bar) * 0.25


def _shooting_star(bar: PriceBar) -> bool:
    return _upper_shadow(bar) >= _body(bar) * 3 and _lower_shadow(bar) <= _range(bar) * 0.25


def _doji(bar: PriceBar) -> bool:
    return _body(bar) <= _range(bar) * 0.08


def _high_wave(bar: PriceBar) -> bool:
    return (
        _body(bar) <= _range(bar) * 0.25
        and _upper_shadow(bar) >= _range(bar) * 0.3
        and _lower_shadow(bar) >= _range(bar) * 0.3
    )


def _engulfing(prev: PriceBar, cur: PriceBar) -> Optional[str]:
    prev_low, prev_high = sorted((prev.open, prev.close))
    cur_low, cur_high = sorted((cur.open, cur.close))
    if _is_black(prev) and _is_white(cur) and cur_low <= prev_low and cur_high >= prev_high:
        return "bullish"
    if _is_white(prev) and _is_black(cur) and cur_low <= prev_low and cur_high >= prev_high:
        return "bearish"
    return None


def _two_bar_reversal(prev: PriceBar, cur: PriceBar) -> Optional[str]:
    midpoint = (prev.open + prev.close) / 2
    if _is_black(prev) and _is_white(cur) and cur.open < prev.low and cur.close > midpoint:
        return "piercing"
    if _is_white(prev) and _is_black(cur) and cur.open > prev.high and cur.close < midpoint:
        return "dark_cloud"
    return None


def _star_pattern(bars: list[PriceBar]) -> Optional[str]:
    first, middle, last = bars
    if _is_black(first) and _body(middle) <= _body(first) * 0.45 and _is_white(last) and last.close > (first.open + first.close) / 2:
        return "morning"
    if _is_white(first) and _body(middle) <= _body(first) * 0.45 and _is_black(last) and last.close < (first.open + first.close) / 2:
        return "evening"
    return None


def _bullish_gap(prev: PriceBar, cur: PriceBar) -> bool:
    return cur.low > prev.high


def _bearish_gap(prev: PriceBar, cur: PriceBar) -> bool:
    return cur.high < prev.low


def _record_highs(bars: list[PriceBar]) -> int:
    count = 0
    prior_high = bars[0].high
    for bar in bars[1:]:
        if bar.high > prior_high:
            count += 1
            prior_high = bar.high
    return count


def _record_lows(bars: list[PriceBar]) -> int:
    count = 0
    prior_low = bars[0].low
    for bar in bars[1:]:
        if bar.low < prior_low:
            count += 1
            prior_low = bar.low
    return count


def _three_line_break(bars: list[PriceBar]) -> Optional[str]:
    if len(bars) < 4:
        return None
    prior = bars[-4:-1]
    cur = bars[-1]
    if cur.close > max(bar.high for bar in prior):
        return "bullish"
    if cur.close < min(bar.low for bar in prior):
        return "bearish"
    return None


def _disparity(bars: list[PriceBar], period: int) -> Optional[float]:
    if len(bars) < period:
        return None
    ma = mean(bar.close for bar in bars[-period:])
    return (bars[-1].close / ma - 1) * 100 if ma else None


def _spring(bars: list[PriceBar]) -> bool:
    if len(bars) < 10:
        return False
    support = min(bar.low for bar in bars[-10:-1])
    cur = bars[-1]
    return cur.low < support and cur.close > support and _lower_shadow(cur) > _body(cur) * 2


def _upthrust(bars: list[PriceBar]) -> bool:
    if len(bars) < 10:
        return False
    resistance = max(bar.high for bar in bars[-10:-1])
    cur = bars[-1]
    return cur.high > resistance and cur.close < resistance and _upper_shadow(cur) > _body(cur) * 2


def _trend(bars: list[PriceBar]) -> float:
    return bars[-1].close / bars[0].close - 1 if bars[0].close else 0


def _stop_loss(daily_bars: list[PriceBar], trigger_bars: list[PriceBar], bias: str) -> float:
    source = trigger_bars[-6:] if len(trigger_bars) >= 6 else daily_bars[-3:]
    if bias == "bearish":
        return max(bar.high for bar in source)
    return min(bar.low for bar in source)


def _target_price(bars: list[PriceBar], bias: str) -> float:
    if bias == "bearish":
        return min(bar.low for bar in bars[-10:])
    return max(bar.high for bar in bars[-10:])


def _risk_reward(entry: float, stop: float, target: float, bias: str) -> Optional[float]:
    risk = entry - stop if bias != "bearish" else stop - entry
    reward = target - entry if bias != "bearish" else entry - target
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


def _entry_plan(bias: str, bar: PriceBar, support: float, resistance: float, ifvg: Optional[str]) -> str:
    if bias == "bullish":
        if ifvg == "bullish_ifvg":
            return f"1H 偏多時，等 5M 回測多方 IFVG 不破再分批進場；收盤需站穩 {bar.close:.2f}"
        return f"只在收盤站穩 {bar.close:.2f} 或回測支撐 {support:.2f} 不破時分批進場"
    if bias == "bearish":
        if ifvg == "bearish_ifvg":
            return f"1H 偏空時，等 5M 回測空方 IFVG 受阻再減碼或放空；收盤跌破 {bar.low:.2f} 才確認"
        return f"避免追高；若收盤跌破 {bar.low:.2f} 或反彈至壓力 {resistance:.2f} 受阻，優先減碼"
    return "等待收盤確認；未突破支撐或壓力前不主動加碼"


def _exit_plan(bias: str, target: float, opposite_level: float) -> str:
    if bias == "bullish":
        return f"目標先看前一交易日高點或前高 {target:.2f}；跌回 {opposite_level:.2f} 下方或三線反向轉黑，分批出場"
    if bias == "bearish":
        return f"目標先看前一交易日低點或前低 {target:.2f}；若反向站回 {opposite_level:.2f} 或出現多頭吞噬，停止追空"
    return "若後續出現明確多頭形態再提高評等；若跌破支撐則移出觀察清單"
