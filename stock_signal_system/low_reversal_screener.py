from __future__ import annotations

import csv
import html
import json
import socket
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import parse_qs, urlparse

from stock_signal_system.ai_supply_chain import ai_profile_for


@dataclass(frozen=True)
class ScreenerConfig:
    universe_path: Path
    ohlcv_path: Path
    revenue_paths: tuple[Path, ...]
    dividend_yield_paths: tuple[Path, ...]
    ex_dividend_paths: tuple[Path, ...]
    realtime_cache_path: Optional[Path]
    report_dir: Path
    realtime_proxy_url: Optional[str] = None
    refresh_realtime: bool = False
    realtime_batch_size: int = 75
    realtime_stale_minutes: int = 30
    low_position_max: float = 0.50
    cross_lookback_days: int = 5
    min_revenue_growth_yoy: float = 10.0
    min_dividend_yield: float = 5.0
    ex_dividend_window_days: int = 150
    min_history_days: int = 30
    strict_all_conditions: bool = True

    @classmethod
    def from_file(cls, path: str | Path) -> "ScreenerConfig":
        config_path = Path(path)
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        base = config_path.parent.parent
        return cls(
            universe_path=_resolve(base, raw.get("universe_path", "data/twse_common_stock_universe.csv")),
            ohlcv_path=_resolve(base, raw.get("ohlcv_path", "data/tw_yahoo_ohlcv.csv")),
            revenue_paths=tuple(_resolve(base, item) for item in raw.get("revenue_paths", ["data/twse_stocks.csv"])),
            dividend_yield_paths=tuple(_resolve(base, item) for item in raw.get("dividend_yield_paths", [])),
            ex_dividend_paths=tuple(_resolve(base, item) for item in raw.get("ex_dividend_paths", [])),
            realtime_cache_path=_resolve_optional(base, raw.get("realtime_cache_path", "data/twse_common_stock_realtime_cache.csv")),
            report_dir=_resolve(base, raw.get("report_dir", "reports")),
            realtime_proxy_url=raw.get("realtime_proxy_url"),
            refresh_realtime=bool(raw.get("refresh_realtime", False)),
            realtime_batch_size=int(raw.get("realtime_batch_size", 75)),
            realtime_stale_minutes=int(raw.get("realtime_stale_minutes", 30)),
            low_position_max=float(raw.get("low_position_max", 0.50)),
            cross_lookback_days=int(raw.get("cross_lookback_days", 5)),
            min_revenue_growth_yoy=float(raw.get("min_revenue_growth_yoy", 10.0)),
            min_dividend_yield=float(raw.get("min_dividend_yield", 5.0)),
            ex_dividend_window_days=int(raw.get("ex_dividend_window_days", 150)),
            min_history_days=int(raw.get("min_history_days", 30)),
            strict_all_conditions=bool(raw.get("strict_all_conditions", True)),
        )


@dataclass(frozen=True)
class UniverseItem:
    symbol: str
    market: str
    name: str
    channel: str
    industry: str = ""


@dataclass(frozen=True)
class OhlcvBar:
    symbol: str
    market: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class FundamentalInfo:
    revenue_growth_yoy: Optional[float] = None
    dividend_yield: Optional[float] = None
    cash_dividend: Optional[float] = None
    ex_dividend_date: Optional[date] = None
    industry: str = ""


@dataclass(frozen=True)
class RealtimeState:
    symbol: str
    market: str
    name: str
    timestamp: datetime
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    price: Optional[float]
    previous_close: Optional[float]
    volume: Optional[float]
    change_pct: Optional[float]
    is_stale: bool


@dataclass(frozen=True)
class ScreenerPaths:
    html_path: Path
    csv_path: Path
    json_path: Path


def run_low_reversal_screener(
    config: ScreenerConfig,
    run_date: Optional[date] = None,
    now: Optional[datetime] = None,
) -> ScreenerPaths:
    payload = build_screener_payload(config, run_date, now)
    return save_screener_outputs(config.report_dir, date.fromisoformat(payload["report_date"]), _parse_datetime(payload["generated_at"]), config, payload["rows"])


def build_screener_payload(
    config: ScreenerConfig,
    run_date: Optional[date] = None,
    now: Optional[datetime] = None,
    refresh_realtime: Optional[bool] = None,
) -> dict:
    current_date = run_date or date.today()
    generated_at = now or datetime.now()

    universe = load_universe(config.universe_path)
    should_refresh = config.refresh_realtime if refresh_realtime is None else refresh_realtime
    if should_refresh and config.realtime_cache_path:
        _refresh_realtime_quotes(universe, config.realtime_cache_path, config.realtime_batch_size)

    bars_by_key = load_ohlcv(config.ohlcv_path)
    fundamentals = load_fundamentals(
        config.revenue_paths,
        config.dividend_yield_paths,
        config.ex_dividend_paths,
    )
    realtime = load_latest_realtime_states(
        config.realtime_cache_path,
        generated_at,
        stale_minutes=config.realtime_stale_minutes,
    )

    rows = build_screener_rows(universe, bars_by_key, fundamentals, realtime, config, current_date)
    return {
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "report_date": current_date.isoformat(),
        "thresholds": {
            "low_position_max": config.low_position_max,
            "cross_lookback_days": config.cross_lookback_days,
            "min_revenue_growth_yoy": config.min_revenue_growth_yoy,
            "min_dividend_yield": config.min_dividend_yield,
            "ex_dividend_window_days": config.ex_dividend_window_days,
        },
        "realtime_proxy_url": config.realtime_proxy_url,
        "rows": rows,
    }


def serve_low_reversal_screener(config: ScreenerConfig, host: str = "0.0.0.0", port: int = 8765) -> None:
    handler = _make_handler(config)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"serving=http://{host}:{port}")
    for url in _local_access_urls(port):
        print(f"access_url={url}")
    server.serve_forever()


def build_screener_rows(
    universe: list[UniverseItem],
    bars_by_key: dict[tuple[str, str], list[OhlcvBar]],
    fundamentals: dict[tuple[str, str], FundamentalInfo],
    realtime: dict[tuple[str, str], RealtimeState],
    config: ScreenerConfig,
    run_date: date,
) -> list[dict]:
    rows: list[dict] = []
    ex_end = run_date + timedelta(days=config.ex_dividend_window_days)
    for item in universe:
        key = (item.symbol, item.market)
        bars = bars_by_key.get(key, [])
        if len(bars) < config.min_history_days:
            continue
        fund = fundamentals.get(key) or fundamentals.get((item.symbol, "")) or FundamentalInfo()
        quote = realtime.get(key)
        indicators = _technical_snapshot(bars, config)
        ex_date = fund.ex_dividend_date

        revenue_pass = fund.revenue_growth_yoy is not None and fund.revenue_growth_yoy >= config.min_revenue_growth_yoy
        dividend_pass = (
            fund.dividend_yield is not None
            and fund.dividend_yield >= config.min_dividend_yield
            and ex_date is not None
            and run_date <= ex_date <= ex_end
        )
        reversal_pass = indicators["low_position_pass"] and (
            indicators["macd_cross_recent"] or indicators["kd_cross_recent"]
        )
        pass_all = reversal_pass and revenue_pass and dividend_pass
        if config.strict_all_conditions and not pass_all:
            include_default = False
        else:
            include_default = pass_all

        volume_ratio = _volume_ratio(bars, quote.volume if quote else None)
        score = _score_row(indicators, fund, quote, volume_ratio, config, run_date)
        industry = fund.industry or item.industry or "未分類"
        ai_profile = ai_profile_for(item.symbol)
        stock_type = "AI類股" if ai_profile else industry
        rows.append(
            {
                "symbol": item.symbol,
                "market": item.market,
                "name": quote.name if quote and quote.name else item.name,
                "industry": industry,
                "stock_type": stock_type,
                "ai_category": ai_profile.category if ai_profile else "",
                "ai_score": ai_profile.score if ai_profile else 0,
                "ai_tier": ai_profile.tier if ai_profile else "",
                "ai_reason": ai_profile.reason if ai_profile else "",
                "ai_market_mainline": ai_profile.market_mainline if ai_profile else False,
                "score": round(score, 1),
                "pass_all": pass_all,
                "include_default": include_default,
                "low_reversal_pass": reversal_pass,
                "revenue_pass": revenue_pass,
                "dividend_pass": dividend_pass,
                "latest_close": round(bars[-1].close, 2),
                "price_position_52w": _round_optional(indicators["position_52w"], 4),
                "position_label": _position_label(indicators["position_52w"]),
                "macd_cross_recent": indicators["macd_cross_recent"],
                "macd_cross_date": _date_iso(indicators["macd_cross_date"]),
                "kd_cross_recent": indicators["kd_cross_recent"],
                "kd_cross_date": _date_iso(indicators["kd_cross_date"]),
                "revenue_growth_yoy": _round_optional(fund.revenue_growth_yoy, 2),
                "dividend_yield": _round_optional(fund.dividend_yield, 2),
                "cash_dividend": _round_optional(fund.cash_dividend, 3),
                "ex_dividend_date": _date_iso(ex_date),
                "realtime_price": _round_optional(quote.price if quote else None, 2),
                "realtime_change_pct": _round_optional((quote.change_pct * 100) if quote and quote.change_pct is not None else None, 2),
                "realtime_open": _round_optional(quote.open if quote else None, 2),
                "realtime_high": _round_optional(quote.high if quote else None, 2),
                "realtime_low": _round_optional(quote.low if quote else None, 2),
                "realtime_volume": _round_optional(quote.volume if quote else None, 0),
                "volume_ratio": _round_optional(volume_ratio, 2),
                "realtime_timestamp": quote.timestamp.strftime("%Y-%m-%d %H:%M:%S") if quote else "",
                "realtime_status": _realtime_status(quote),
                "notes": _row_notes(indicators, fund, quote, config, run_date, ex_end),
            }
        )
    return sorted(rows, key=lambda row: (row["pass_all"], row["score"]), reverse=True)


def load_universe(path: Path) -> list[UniverseItem]:
    items: list[UniverseItem] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = _clean_symbol(_first(row, "symbol", "code", "Code", "SecuritiesCompanyCode"))
            market = _normalize_market(_first(row, "market", "Market", "ex"))
            name = _first(row, "name", "Name", "CompanyName")
            channel = _first(row, "channel", "raw_channel")
            industry = _first(row, "industry", "Industry", "產業別")
            if not _is_common_stock(symbol):
                continue
            items.append(UniverseItem(symbol, market or "tse", name, channel, industry))
    return sorted(_dedupe_universe(items), key=lambda item: (item.market, item.symbol))


def load_ohlcv(path: Path) -> dict[tuple[str, str], list[OhlcvBar]]:
    grouped: dict[tuple[str, str], list[OhlcvBar]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol, market = _split_symbol_market(_first(row, "symbol", "code", "Code"))
            market = market or "tse"
            if not _is_common_stock(symbol):
                continue
            bar = OhlcvBar(
                symbol=symbol,
                market=market,
                trade_date=_parse_date(_first(row, "date", "Date", "datetime", "timestamp")),
                open=_float(_first(row, "open", "Open", "OpeningPrice")),
                high=_float(_first(row, "high", "High", "HighestPrice")),
                low=_float(_first(row, "low", "Low", "LowestPrice")),
                close=_float(_first(row, "close", "Close", "ClosingPrice")),
                volume=_float(_first(row, "volume", "Volume", "TradeVolume")),
            )
            grouped.setdefault((symbol, market), []).append(bar)
    return {key: sorted(value, key=lambda bar: bar.trade_date) for key, value in grouped.items()}


def load_fundamentals(
    revenue_paths: Iterable[Path],
    dividend_yield_paths: Iterable[Path],
    ex_dividend_paths: Iterable[Path],
) -> dict[tuple[str, str], FundamentalInfo]:
    data: dict[tuple[str, str], FundamentalInfo] = {}
    for path in revenue_paths:
        if path.exists():
            for key, values in _load_revenue(path).items():
                data[key] = _merge_fundamental(
                    data.get(key),
                    revenue_growth_yoy=values.get("revenue_growth_yoy"),
                    industry=str(values.get("industry") or ""),
                )
    for path in dividend_yield_paths:
        if path.exists():
            for key, values in _load_dividend_yields(path).items():
                data[key] = _merge_fundamental(
                    data.get(key),
                    dividend_yield=values.get("dividend_yield"),
                    cash_dividend=values.get("cash_dividend"),
                )
    for path in ex_dividend_paths:
        if path.exists():
            for key, values in _load_ex_dividends(path).items():
                data[key] = _merge_fundamental(
                    data.get(key),
                    ex_dividend_date=values.get("ex_dividend_date"),
                    cash_dividend=values.get("cash_dividend"),
                )
    return data


def load_latest_realtime_states(
    path: Optional[Path],
    now: datetime,
    stale_minutes: int = 30,
) -> dict[tuple[str, str], RealtimeState]:
    if not path or not path.exists():
        return {}
    latest: dict[tuple[str, str], dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = _clean_symbol(_first(row, "symbol", "code", "Code"))
            market = _normalize_market(_first(row, "market", "Market", "ex")) or _market_from_channel(_first(row, "raw_channel"))
            if not symbol or not market:
                continue
            key = (symbol, market)
            current_dt = _parse_datetime(_first(row, "datetime", "timestamp"))
            if key not in latest or current_dt >= _parse_datetime(_first(latest[key], "datetime", "timestamp")):
                latest[key] = row

    states = {}
    for (symbol, market), row in latest.items():
        timestamp = _parse_datetime(_first(row, "datetime", "timestamp"))
        price = _optional_float(_first(row, "close", "price", "z"))
        previous = _optional_float(_first(row, "previous_close", "y"))
        change_pct = price / previous - 1 if price is not None and previous not in (None, 0) else None
        states[(symbol, market)] = RealtimeState(
            symbol=symbol,
            market=market,
            name=_first(row, "name", "Name", "n"),
            timestamp=timestamp,
            open=_optional_float(_first(row, "open", "o")),
            high=_optional_float(_first(row, "high", "h")),
            low=_optional_float(_first(row, "low", "l")),
            price=price,
            previous_close=previous,
            volume=_optional_float(_first(row, "volume", "v")),
            change_pct=change_pct,
            is_stale=(now - timestamp) > timedelta(minutes=stale_minutes),
        )
    return states


def save_screener_outputs(
    report_dir: Path,
    report_date: date,
    generated_at: datetime,
    config: ScreenerConfig,
    rows: list[dict],
) -> ScreenerPaths:
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = f"low_reversal_screener_{report_date.isoformat()}"
    html_path = report_dir / f"{stem}.html"
    csv_path = report_dir / f"{stem}.csv"
    json_path = report_dir / f"{stem}.json"
    payload = _payload_from_rows(report_date, generated_at, config, rows)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _save_csv(csv_path, rows)
    html_path.write_text(_render_html(payload), encoding="utf-8")
    return ScreenerPaths(html_path=html_path, csv_path=csv_path, json_path=json_path)


def _technical_snapshot(bars: list[OhlcvBar], config: ScreenerConfig) -> dict:
    window = bars[-252:] if len(bars) >= 252 else bars
    high_52w = max(bar.high for bar in window)
    low_52w = min(bar.low for bar in window)
    latest = bars[-1].close
    position = (latest - low_52w) / (high_52w - low_52w) if high_52w > low_52w else 1.0
    macd_cross_date = _last_recent_cross_date(_macd_crosses(bars), bars[-1].trade_date, config.cross_lookback_days)
    kd_cross_date = _last_recent_cross_date(_kd_crosses(bars), bars[-1].trade_date, config.cross_lookback_days)
    return {
        "position_52w": position,
        "low_position_pass": position <= config.low_position_max,
        "macd_cross_recent": macd_cross_date is not None,
        "macd_cross_date": macd_cross_date,
        "kd_cross_recent": kd_cross_date is not None,
        "kd_cross_date": kd_cross_date,
    }


def _macd_crosses(bars: list[OhlcvBar]) -> list[date]:
    closes = [bar.close for bar in bars]
    if len(closes) < 35:
        return []
    macd = [fast - slow for fast, slow in zip(_ema(closes, 12), _ema(closes, 26))]
    signal = _ema(macd, 9)
    crosses = []
    for index in range(1, len(bars)):
        if macd[index - 1] <= signal[index - 1] and macd[index] > signal[index]:
            crosses.append(bars[index].trade_date)
    return crosses


def _kd_crosses(bars: list[OhlcvBar], period: int = 9) -> list[date]:
    if len(bars) < period + 2:
        return []
    k_values: list[float] = []
    d_values: list[float] = []
    k = 50.0
    d = 50.0
    for index, bar in enumerate(bars):
        start = max(0, index - period + 1)
        window = bars[start : index + 1]
        lowest = min(item.low for item in window)
        highest = max(item.high for item in window)
        rsv = 50.0 if highest == lowest else (bar.close - lowest) / (highest - lowest) * 100
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
        k_values.append(k)
        d_values.append(d)
    crosses = []
    for index in range(1, len(bars)):
        if k_values[index - 1] <= d_values[index - 1] and k_values[index] > d_values[index]:
            crosses.append(bars[index].trade_date)
    return crosses


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    output = [values[0]]
    for value in values[1:]:
        output.append(value * alpha + output[-1] * (1 - alpha))
    return output


def _last_recent_cross_date(crosses: list[date], latest_date: date, lookback_days: int) -> Optional[date]:
    if not crosses:
        return None
    cutoff = latest_date - timedelta(days=lookback_days * 2 + 4)
    recent = [item for item in crosses if item >= cutoff]
    return recent[-1] if recent else None


def _load_revenue(path: Path) -> dict[tuple[str, str], dict[str, object]]:
    output: dict[tuple[str, str], dict[str, object]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol, market = _split_symbol_market(_first_any(row, ("symbol", "code", "Code", "公司代號", "證券代號")))
            value = _optional_float(
                _first_any(row, ("revenue_growth_yoy", "monthly_revenue_yoy", "營業收入-去年同月增減(%)", "去年同月增減(%)"))
            )
            industry = _first_any(row, ("industry", "Industry", "產業別"))
            if symbol and value is not None:
                output[(symbol, market)] = {"revenue_growth_yoy": value, "industry": industry}
    return output


def _load_dividend_yields(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    output: dict[tuple[str, str], dict[str, float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol, market = _split_symbol_market(_first_any(row, ("symbol", "code", "Code", "SecuritiesCompanyCode", "證券代號")))
            dividend_yield = _optional_float(
                _first_any(row, ("dividend_yield", "DividendYield", "殖利率(%)", "殖利率", "Yield"))
            )
            cash_dividend = _optional_float(
                _first_any(row, ("cash_dividend", "CashDividend", "現金股利", "股利年度現金股利", "Dividend"))
            )
            if symbol and (dividend_yield is not None or cash_dividend is not None):
                output[(symbol, market)] = {"dividend_yield": dividend_yield, "cash_dividend": cash_dividend}
    return output


def _load_ex_dividends(path: Path) -> dict[tuple[str, str], dict[str, object]]:
    output: dict[tuple[str, str], dict[str, object]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol, market = _split_symbol_market(_first_any(row, ("symbol", "code", "Code", "股票代號", "證券代號")))
            ex_date = _optional_date(
                _first_any(row, ("ex_dividend_date", "ExDividendDate", "除息日", "除權息日期", "停止過戶起始日"))
            )
            cash_dividend = _optional_float(
                _first_any(row, ("cash_dividend", "CashDividend", "現金股利", "現金股利配發元", "Dividend"))
            )
            if symbol and ex_date is not None:
                output[(symbol, market)] = {"ex_dividend_date": ex_date, "cash_dividend": cash_dividend}
    return output


def _merge_fundamental(
    current: Optional[FundamentalInfo],
    revenue_growth_yoy: Optional[float] = None,
    dividend_yield: Optional[float] = None,
    cash_dividend: Optional[float] = None,
    ex_dividend_date: Optional[date] = None,
    industry: str = "",
) -> FundamentalInfo:
    base = current or FundamentalInfo()
    return FundamentalInfo(
        revenue_growth_yoy=base.revenue_growth_yoy if revenue_growth_yoy is None else revenue_growth_yoy,
        dividend_yield=base.dividend_yield if dividend_yield is None else dividend_yield,
        cash_dividend=base.cash_dividend if cash_dividend is None else cash_dividend,
        ex_dividend_date=base.ex_dividend_date if ex_dividend_date is None else ex_dividend_date,
        industry=base.industry if not industry else industry,
    )


def _refresh_realtime_quotes(universe: list[UniverseItem], cache_path: Path, batch_size: int) -> None:
    from quant_research_platform.twse_realtime import append_quote_cache, fetch_realtime_quotes, normalize_channel

    channels = [item.channel or normalize_channel(f"{item.market}:{item.symbol}") for item in universe]
    for batch in _chunks(channels, batch_size):
        quotes = fetch_realtime_quotes(batch)
        append_quote_cache(cache_path, quotes)


def _score_row(
    indicators: dict,
    fund: FundamentalInfo,
    quote: Optional[RealtimeState],
    volume_ratio: Optional[float],
    config: ScreenerConfig,
    run_date: date,
) -> float:
    score = 0.0
    position = indicators["position_52w"]
    score += max(0, (config.low_position_max - position) / max(config.low_position_max, 0.01)) * 20
    if indicators["macd_cross_recent"]:
        score += 15
    if indicators["kd_cross_recent"]:
        score += 15
    if fund.revenue_growth_yoy is not None:
        score += min(25, max(0, fund.revenue_growth_yoy - config.min_revenue_growth_yoy) * 0.8 + 10)
    if fund.dividend_yield is not None:
        score += min(20, max(0, fund.dividend_yield - config.min_dividend_yield) * 2 + 10)
    if fund.ex_dividend_date:
        days = (fund.ex_dividend_date - run_date).days
        if 0 <= days <= config.ex_dividend_window_days:
            score += max(0, 10 - days / max(config.ex_dividend_window_days, 1) * 5)
    if quote and quote.change_pct is not None and quote.change_pct > 0:
        score += min(5, quote.change_pct * 100)
    if volume_ratio and volume_ratio >= 1.2:
        score += min(5, (volume_ratio - 1) * 3)
    return min(score, 100.0)


def _volume_ratio(bars: list[OhlcvBar], realtime_volume: Optional[float]) -> Optional[float]:
    if realtime_volume is None:
        return None
    history = [bar.volume for bar in bars[-20:] if bar.volume > 0]
    if not history:
        return None
    return realtime_volume / (sum(history) / len(history))


def _save_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = list(rows[0].keys()) if rows else [
        "symbol",
        "market",
        "name",
        "score",
        "pass_all",
        "low_reversal_pass",
        "revenue_pass",
        "dividend_pass",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _payload_from_rows(report_date: date, generated_at: datetime, config: ScreenerConfig, rows: list[dict]) -> dict:
    return {
        "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "report_date": report_date.isoformat(),
        "thresholds": {
            "low_position_max": config.low_position_max,
            "cross_lookback_days": config.cross_lookback_days,
            "min_revenue_growth_yoy": config.min_revenue_growth_yoy,
            "min_dividend_yield": config.min_dividend_yield,
            "ex_dividend_window_days": config.ex_dividend_window_days,
        },
        "realtime_proxy_url": config.realtime_proxy_url,
        "rows": rows,
    }


def _make_handler(config: ScreenerConfig):
    class ScreenerHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._send_text(_render_html(None, api_mode=True), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/screener":
                params = parse_qs(parsed.query)
                refresh = params.get("refresh", ["0"])[0] in {"1", "true", "yes"}
                payload = build_screener_payload(config, refresh_realtime=refresh)
                self._send_text(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")
                return
            if parsed.path == "/api/export":
                payload = build_screener_payload(config)
                paths = save_screener_outputs(
                    config.report_dir,
                    date.fromisoformat(payload["report_date"]),
                    _parse_datetime(payload["generated_at"]),
                    config,
                    payload["rows"],
                )
                self._send_text(
                    json.dumps(
                        {
                            "html_path": str(paths.html_path),
                            "csv_path": str(paths.csv_path),
                            "json_path": str(paths.json_path),
                        },
                        ensure_ascii=False,
                    ),
                    "application/json; charset=utf-8",
                )
                return
            self.send_error(404)

        def log_message(self, format: str, *args) -> None:
            return

        def _send_text(self, body: str, content_type: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

    return ScreenerHandler


def _render_html(payload: Optional[dict], api_mode: bool = False) -> str:
    data_json = "null" if payload is None else json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    generated = payload["generated_at"] if payload else "API 即時載入"
    report_date = payload["report_date"] if payload else "動態"
    realtime_proxy_url = (payload or {}).get("realtime_proxy_url") or ""
    thresholds = payload["thresholds"] if payload else {
        "min_revenue_growth_yoy": 10,
        "min_dividend_yield": 5,
        "low_position_max": 0.5,
        "cross_lookback_days": 5,
        "ex_dividend_window_days": 150,
    }
    title = f"台股低位階翻多互動選股網 - {report_date}"
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #f4f1e8;
      --ink: #18201f;
      --muted: #66706b;
      --line: #d5d0c2;
      --panel: #fffdf6;
      --green: #0f8a5f;
      --red: #b94738;
      --blue: #1f5f8f;
      --amber: #b7791f;
      --shadow: 0 16px 38px rgba(24, 32, 31, .10);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: "Noto Sans TC", "Microsoft JhengHei", "Segoe UI", sans-serif; }}
    header {{ padding: 26px 22px 18px; border-bottom: 1px solid var(--line); background: #efe8d8; }}
    .wrap {{ max-width: 1380px; margin: 0 auto; }}
    h1 {{ margin: 0; font-size: 30px; font-weight: 800; }}
    .subtitle {{ margin: 8px 0 0; color: var(--muted); font-size: 14px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 12px; padding: 18px 22px; }}
    .metric {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; box-shadow: var(--shadow); }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; }}
    .metric strong {{ display: block; font-size: 25px; margin-top: 4px; }}
    .controls {{ display: grid; grid-template-columns: 1.4fr .85fr .95fr .9fr .8fr .8fr; gap: 10px; padding: 0 22px 18px; }}
    input, select, button {{ min-height: 38px; border: 1px solid var(--line); border-radius: 7px; background: #fffdf8; color: var(--ink); padding: 8px 10px; font: inherit; }}
    button {{ cursor: pointer; font-weight: 700; }}
    button.active {{ background: var(--ink); color: #fffdf8; border-color: var(--ink); }}
    .type-cell small {{ display: block; margin-top: 4px; color: var(--muted); }}
    .switches {{ display: flex; flex-wrap: wrap; gap: 8px; padding: 0 22px 18px; }}
    .switches label {{ display: inline-flex; gap: 7px; align-items: center; border: 1px solid var(--line); border-radius: 7px; padding: 8px 10px; background: #fffdf8; }}
    main {{ padding: 0 22px 34px; }}
    .table-shell {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); box-shadow: var(--shadow); }}
    table {{ width: 100%; min-width: 1660px; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid #e9e3d5; text-align: left; white-space: nowrap; }}
    th {{ position: sticky; top: 0; background: #f6efdf; z-index: 2; font-size: 12px; color: #3d4843; cursor: pointer; }}
    tr:hover td {{ background: #fbf3e5; }}
    .name strong {{ display: block; font-size: 14px; }}
    .name small {{ color: var(--muted); }}
    .pill {{ display: inline-flex; align-items: center; min-height: 22px; border-radius: 999px; padding: 2px 8px; font-size: 12px; font-weight: 700; background: #ece7dc; color: #38443f; }}
    .pass {{ background: #e0f2e9; color: var(--green); }}
    .fail {{ background: #f8e2de; color: var(--red); }}
    .warn {{ background: #f7ebcf; color: var(--amber); }}
    .num-pos {{ color: var(--green); font-weight: 800; }}
    .num-neg {{ color: var(--red); font-weight: 800; }}
    .notes {{ max-width: 300px; white-space: normal; color: var(--muted); line-height: 1.45; }}
    .empty {{ padding: 28px; color: var(--muted); text-align: center; }}
    .static-note {{ align-self: center; color: var(--muted); font-size: 13px; }}
    .refresh-note {{ align-self: center; color: var(--green); font-size: 13px; font-weight: 700; }}
    @media (max-width: 880px) {{
      .summary {{ grid-template-columns: repeat(2, 1fr); padding: 14px; }}
      .controls {{ grid-template-columns: 1fr 1fr; padding: 0 14px 14px; }}
      main {{ padding: 0 14px 28px; }}
      h1 {{ font-size: 24px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="wrap">
      <h1>台股低位階翻多互動選股網</h1>
      <p class="subtitle">資料日 <span v-text="reportDate">{html.escape(report_date)}</span>，產出時間 <span v-text="generatedAt">{html.escape(generated)}</span>。預設顯示候選池；可切換只看三條件全符合：低位階翻多、營收成長、殖利率與除息。</p>
    </div>
  </header>
  <div id="app" v-cloak>
  <section class="wrap summary">
    <div class="metric"><span>三條件全符合</span><strong>{{{{ passCount }}}}</strong></div>
    <div class="metric"><span>低位階翻多</span><strong>{{{{ reversalCount }}}}</strong></div>
    <div class="metric"><span>營收 YoY 門檻</span><strong>{thresholds['min_revenue_growth_yoy']:.0f}%</strong></div>
    <div class="metric"><span>殖利率門檻</span><strong>{thresholds['min_dividend_yield']:.0f}%</strong></div>
  </section>
  <section class="wrap controls">
    <input v-model="filters.search" type="search" placeholder="搜尋代號、名稱、產業">
    <select v-model="filters.market"><option value="all">上市 + 上櫃</option><option value="tse">上市</option><option value="otc">上櫃</option></select>
    <select v-model="filters.stockType">
      <option value="all">全部股票類型</option>
      <option v-for="type in typeOptions" :key="type.name" :value="type.name">{{{{ type.name }}}} ({{{{ type.count }}}})</option>
    </select>
    <select v-model="filters.cross"><option value="all">全部技術狀態</option><option value="either">MACD 或 KD</option><option value="both">MACD + KD</option><option value="macd">只看 MACD</option><option value="kd">只看 KD</option></select>
    <input v-model="filters.minYield" type="number" min="0" step="0.5" placeholder="殖利率門檻">
    <input v-model="filters.minRevenue" type="number" step="1" placeholder="營收 YoY 門檻">
  </section>
  <section class="wrap switches">
    <label><input v-model="filters.strict" type="checkbox"> 只看三條件全符合 <small v-if="passCount === 0">目前 0 檔</small></label>
    <label><input v-model="filters.upOnly" type="checkbox"> 只看即時上漲</label>
    <label><input v-model="filters.volumeOnly" type="checkbox"> 只看盤中放量</label>
    <button :class="{{active: sortKey === 'score'}}" type="button" @click="setSort('score')">依分數</button>
    <button :class="{{active: sortKey === 'realtime_change_pct'}}" type="button" @click="setSort('realtime_change_pct')">依即時漲跌</button>
    <button :class="{{active: sortKey === 'dividend_yield'}}" type="button" @click="setSort('dividend_yield')">依殖利率</button>
    <button v-if="apiMode" type="button" @click="loadData(false)">重新載入</button>
    <button v-if="apiMode || realtimeProxyUrl" type="button" @click="loadData(true)">刷新即時</button>
    <button v-if="apiMode" type="button" @click="exportFiles">匯出檔案</button>
    <button v-if="!apiMode && !realtimeProxyUrl" type="button" disabled>靜態快照</button>
    <span v-if="!apiMode && !realtimeProxyUrl" class="static-note">外部 Pages 版不含即時 API；行情以產出時快照為準。</span>
    <span v-if="!apiMode && realtimeProxyUrl" class="static-note">外部 Pages 版會透過 Cloudflare Worker 刷新即時行情。</span>
    <span v-if="realtimeRefreshMessage" class="refresh-note">{{{{ realtimeRefreshMessage }}}}</span>
  </section>
  <main class="wrap">
    <div class="table-shell">
      <table>
        <thead><tr>
          <th @click="setSort('score')">分數</th><th>股票</th><th>類型</th><th>AI分類</th><th @click="setSort('ai_score')">AI_SCORE</th><th>Tier</th><th>主線</th><th>市場</th><th>條件</th><th @click="setSort('price_position_52w')">52週位階</th>
          <th>MACD</th><th>KD</th><th @click="setSort('revenue_growth_yoy')">營收YoY</th><th @click="setSort('dividend_yield')">殖利率</th><th>除息日</th>
          <th @click="setSort('realtime_price')">即時價</th><th @click="setSort('realtime_change_pct')">漲跌幅</th><th>開高低</th><th @click="setSort('volume_ratio')">量比</th><th>行情時間</th><th>備註</th>
        </tr></thead>
        <tbody>
          <tr v-for="row in filteredRows" :key="row.market + row.symbol">
            <td><strong>{{{{ number(row.score, 1) }}}}</strong></td>
            <td class="name"><strong>{{{{ row.symbol }}}} {{{{ row.name }}}}</strong><small>日線收盤 {{{{ number(row.latest_close, 2) }}}}</small></td>
            <td class="type-cell"><span class="pill">{{{{ row.stock_type || row.industry || '未分類' }}}}</span><small v-if="row.stock_type !== row.industry">{{{{ row.industry }}}}</small></td>
            <td class="notes">{{{{ row.ai_category || '--' }}}}</td>
            <td>{{{{ row.ai_score ? number(row.ai_score, 0) : '--' }}}}</td>
            <td>{{{{ row.ai_tier || '--' }}}}</td>
            <td><span :class="['pill', row.ai_market_mainline ? 'pass' : 'fail']">{{{{ row.ai_market_mainline ? 'TRUE' : 'FALSE' }}}}</span></td>
            <td>{{{{ row.market === 'tse' ? '上市' : '上櫃' }}}}</td>
            <td><span :class="['pill', row.low_reversal_pass ? 'pass' : 'fail']">翻多</span> <span :class="['pill', row.revenue_pass ? 'pass' : 'fail']">營收</span> <span :class="['pill', row.dividend_pass ? 'pass' : 'fail']">配息</span></td>
            <td>{{{{ number((row.price_position_52w || 0) * 100, 1) }}}}% <span class="pill">{{{{ row.position_label }}}}</span></td>
            <td><span :class="['pill', row.macd_cross_recent ? 'pass' : 'fail']">{{{{ row.macd_cross_recent ? '交叉' : '未交叉' }}}}</span><br><small>{{{{ row.macd_cross_date || '--' }}}}</small></td>
            <td><span :class="['pill', row.kd_cross_recent ? 'pass' : 'fail']">{{{{ row.kd_cross_recent ? '交叉' : '未交叉' }}}}</span><br><small>{{{{ row.kd_cross_date || '--' }}}}</small></td>
            <td v-html="pct(row.revenue_growth_yoy)"></td>
            <td v-html="pct(row.dividend_yield)"></td>
            <td>{{{{ row.ex_dividend_date || '--' }}}}</td>
            <td>{{{{ number(row.realtime_price, 2) }}}}</td>
            <td v-html="pct(row.realtime_change_pct)"></td>
            <td>{{{{ number(row.realtime_open, 2) }}}} / {{{{ number(row.realtime_high, 2) }}}} / {{{{ number(row.realtime_low, 2) }}}}</td>
            <td>{{{{ number(row.volume_ratio, 2) }}}}</td>
            <td><span :class="['pill', realtimeClass(row.realtime_status)]">{{{{ realtimeLabel(row.realtime_status) }}}}</span><br><small>{{{{ row.realtime_timestamp || '--' }}}}</small></td>
            <td class="notes">{{{{ row.ai_reason ? row.ai_reason + '；' + row.notes : row.notes }}}}</td>
          </tr>
        </tbody>
      </table>
      <div class="empty" v-if="loading">資料載入中...</div>
      <div class="empty" v-else-if="filteredRows.length === 0">
        目前條件下沒有符合股票。若勾選「只看三條件全符合」，代表低位階翻多、營收成長、殖利率>=門檻且未來除息日四項交集目前為 0。
      </div>
    </div>
  </main>
  </div>
  <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
  <script>
    window.SCREENER_API_MODE = {str(api_mode).lower()};
    window.SCREENER_PAYLOAD = {data_json};
    window.REALTIME_PROXY_URL = {json.dumps(realtime_proxy_url)};
    const {{ createApp }} = Vue;
    createApp({{
      data() {{
        return {{
          rows: [],
          apiMode: window.SCREENER_API_MODE,
          realtimeProxyUrl: window.REALTIME_PROXY_URL || '',
          realtimeRefreshMessage: '',
          generatedAt: '{html.escape(generated)}',
          reportDate: '{html.escape(report_date)}',
          loading: false,
          sortKey: 'score',
          sortDesc: true,
          filters: {{
            search: '',
            market: 'all',
            stockType: 'all',
            cross: 'all',
            minYield: '',
            minRevenue: '',
            strict: false,
            upOnly: false,
            volumeOnly: false
          }}
        }};
      }},
      computed: {{
        passCount() {{ return this.rows.filter(row => row.pass_all).length; }},
        reversalCount() {{ return this.rows.filter(row => row.low_reversal_pass).length; }},
        typeOptions() {{
          const counts = new Map();
          for (const row of this.rows) {{
            const type = row.stock_type || row.industry || '未分類';
            counts.set(type, (counts.get(type) || 0) + 1);
          }}
          return [...counts.entries()]
            .map(([name, count]) => ({{ name, count }}))
            .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh-Hant'));
        }},
        filteredRows() {{
          const query = this.filters.search.trim().toLowerCase();
          const items = this.rows.filter(row => {{
            if (this.filters.strict && !row.pass_all) return false;
            if (this.filters.market !== 'all' && row.market !== this.filters.market) return false;
            if (this.filters.stockType !== 'all' && (row.stock_type || row.industry || '未分類') !== this.filters.stockType) return false;
            if (query && !(row.symbol + row.name + (row.industry || '')).toLowerCase().includes(query)) return false;
            if (!this.passesCross(row)) return false;
            if (this.filters.minYield !== '' && (row.dividend_yield ?? -999) < Number(this.filters.minYield)) return false;
            if (this.filters.minRevenue !== '' && (row.revenue_growth_yoy ?? -999) < Number(this.filters.minRevenue)) return false;
            if (this.filters.upOnly && !((row.realtime_change_pct ?? 0) > 0)) return false;
            if (this.filters.volumeOnly && !((row.volume_ratio ?? 0) >= 1.2)) return false;
            return true;
          }});
          return items.sort((a, b) => {{
            const av = a[this.sortKey] ?? -999999;
            const bv = b[this.sortKey] ?? -999999;
            return this.sortDesc ? bv - av : av - bv;
          }});
        }}
      }},
      mounted() {{
        if (window.SCREENER_PAYLOAD) this.applyPayload(window.SCREENER_PAYLOAD);
        if (window.SCREENER_API_MODE) this.loadData(false);
      }},
      methods: {{
        async loadData(refresh) {{
          if (!window.SCREENER_API_MODE) {{
            if (refresh && this.realtimeProxyUrl) await this.refreshRealtimeViaProxy();
            return;
          }}
          this.loading = true;
          const res = await fetch('/api/screener' + (refresh ? '?refresh=1' : ''), {{ cache: 'no-store' }});
          this.applyPayload(await res.json());
          this.loading = false;
        }},
        async refreshRealtimeViaProxy() {{
          this.loading = true;
          try {{
            const targets = this.filteredRows.length ? this.filteredRows : this.rows;
            const targetKeys = new Set(targets.map(row => row.market + ':' + row.symbol));
            const res = await fetch(this.realtimeProxyUrl.replace(/\\/$/, '') + '/quotes', {{
              method: 'POST',
              cache: 'no-store',
              headers: {{ 'content-type': 'application/json' }},
              body: JSON.stringify({{
                symbols: targets.map(row => ({{ symbol: row.symbol, market: row.market }})),
                batchSize: 80
              }})
            }});
            if (!res.ok) throw new Error('proxy status ' + res.status);
            const payload = await res.json();
            const quotes = new Map((payload.quotes || []).map(q => [q.market + ':' + q.symbol, q]));
            let updated = 0;
            let missing = 0;
            this.rows = this.rows.map(row => {{
              const key = row.market + ':' + row.symbol;
              if (!targetKeys.has(key)) return row;
              const quote = quotes.get(key);
              if (!quote) {{
                missing += 1;
                return {{
                  ...row,
                  realtime_price: null,
                  realtime_change_pct: null,
                  realtime_open: null,
                  realtime_high: null,
                  realtime_low: null,
                  realtime_volume: null,
                  realtime_timestamp: '',
                  realtime_status: 'missing',
                  notes: this.appendRealtimeNote(row.notes, '本次刷新未回報即時行情')
                }};
              }}
              updated += 1;
              return {{
                ...row,
                realtime_price: quote.price,
                realtime_change_pct: quote.change_pct == null ? null : quote.change_pct * 100,
                realtime_open: quote.open,
                realtime_high: quote.high,
                realtime_low: quote.low,
                realtime_volume: quote.volume,
                realtime_timestamp: quote.timestamp || '',
                realtime_status: 'fresh',
                volume_ratio: row.volume_ratio,
                notes: this.cleanRealtimeNotes(row.notes)
              }};
            }});
            this.generatedAt = payload.generated_at || this.generatedAt;
            this.realtimeRefreshMessage = `已刷新 ${{updated}} 檔即時行情${{missing ? `，${{missing}} 檔未回報` : ''}}`;
          }} catch (error) {{
            this.realtimeRefreshMessage = '即時刷新失敗：' + error.message;
            alert('即時刷新失敗：' + error.message);
          }} finally {{
            this.loading = false;
          }}
        }},
        async exportFiles() {{
          if (!window.SCREENER_API_MODE) return;
          const res = await fetch('/api/export', {{ cache: 'no-store' }});
          const data = await res.json();
          alert('已匯出\\nHTML: ' + data.html_path + '\\nCSV: ' + data.csv_path + '\\nJSON: ' + data.json_path);
        }},
        applyPayload(payload) {{
          this.rows = payload.rows || [];
          this.generatedAt = payload.generated_at;
          this.reportDate = payload.report_date;
        }},
        setSort(key) {{
          this.sortDesc = this.sortKey === key ? !this.sortDesc : true;
          this.sortKey = key;
        }},
        passesCross(row) {{
          if (this.filters.cross === 'all') return true;
          if (this.filters.cross === 'both') return row.macd_cross_recent && row.kd_cross_recent;
          if (this.filters.cross === 'macd') return row.macd_cross_recent;
          if (this.filters.cross === 'kd') return row.kd_cross_recent;
          return row.macd_cross_recent || row.kd_cross_recent;
        }},
        cleanRealtimeNotes(notes) {{
          const parts = String(notes || '')
            .split('；')
            .map(part => part.trim())
            .filter(part => part && part !== '即時行情已過期' && part !== '缺即時行情');
          return parts.length ? parts.join('；') : '即時行情已更新，留意成交量與盤中波動。';
        }},
        appendRealtimeNote(notes, note) {{
          const base = this.cleanRealtimeNotes(notes);
          return base.includes(note) ? base : `${{base}}；${{note}}`;
        }},
        number(value, digits = 2) {{
          return value === null || value === undefined || value === '' ? '--' : Number(value).toFixed(digits);
        }},
        pct(value) {{
          if (value === null || value === undefined || value === '') return '--';
          const cls = value >= 0 ? 'num-pos' : 'num-neg';
          return `<span class="${{cls}}">${{Number(value).toFixed(2)}}%</span>`;
        }},
        realtimeClass(status) {{ return status === 'fresh' ? 'pass' : status === 'stale' ? 'warn' : 'fail'; }},
        realtimeLabel(status) {{ return status === 'fresh' ? '即時' : status === 'stale' ? '舊報價' : '缺報價'; }}
      }}
    }}).mount('#app');
  </script>
</body>
</html>
"""


def _row_notes(
    indicators: dict,
    fund: FundamentalInfo,
    quote: Optional[RealtimeState],
    config: ScreenerConfig,
    run_date: date,
    ex_end: date,
) -> str:
    notes = []
    if not indicators["low_position_pass"]:
        notes.append("52週位階高於低檔門檻")
    if not (indicators["macd_cross_recent"] or indicators["kd_cross_recent"]):
        notes.append("近期未出現 MACD/KD 黃金交叉")
    if fund.revenue_growth_yoy is None:
        notes.append("缺月營收年增資料")
    elif fund.revenue_growth_yoy < config.min_revenue_growth_yoy:
        notes.append("營收年增低於門檻")
    if fund.dividend_yield is None:
        notes.append("缺殖利率資料")
    elif fund.dividend_yield < config.min_dividend_yield:
        notes.append("殖利率低於門檻")
    if fund.ex_dividend_date is None:
        notes.append("缺未來除息日")
    elif not (run_date <= fund.ex_dividend_date <= ex_end):
        notes.append("除息日不在觀察窗")
    if quote is None:
        notes.append("缺即時行情")
    elif quote.is_stale:
        notes.append("即時行情已過期")
    return "；".join(notes) if notes else "三條件符合，留意成交量與除息前後波動。"


def _local_access_urls(port: int) -> list[str]:
    urls = ["http://127.0.0.1:%d" % port]
    seen = {"127.0.0.1"}
    try:
        hostname = socket.gethostname()
        for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM):
            address = sockaddr[0]
            if ":" in address or address.startswith("127.") or address in seen:
                continue
            seen.add(address)
            urls.append(f"http://{address}:{port}")
    except OSError:
        pass
    return urls


def _realtime_status(quote: Optional[RealtimeState]) -> str:
    if quote is None:
        return "missing"
    return "stale" if quote.is_stale else "fresh"


def _position_label(value: Optional[float]) -> str:
    if value is None:
        return "--"
    if value <= 0.25:
        return "低檔"
    if value <= 0.50:
        return "低半部"
    if value <= 0.75:
        return "中高"
    return "高位"


def _dedupe_universe(items: list[UniverseItem]) -> list[UniverseItem]:
    seen = {}
    for item in items:
        seen[(item.symbol, item.market)] = item
    return list(seen.values())


def _split_symbol_market(value: str) -> tuple[str, str]:
    text = str(value or "").strip().upper()
    if "." in text:
        symbol, suffix = text.split(".", 1)
        return _clean_symbol(symbol), _normalize_market(suffix)
    return _clean_symbol(text), ""


def _clean_symbol(value: str) -> str:
    return str(value or "").strip().upper().split(".", 1)[0]


def _normalize_market(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"tse", "tw", "listed", "上市"}:
        return "tse"
    if text in {"otc", "two", "tpex", "上櫃"}:
        return "otc"
    return text


def _market_from_channel(value: str) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("otc_") or text.startswith("otc:"):
        return "otc"
    if text.startswith("tse_") or text.startswith("tse:"):
        return "tse"
    return ""


def _is_common_stock(symbol: str) -> bool:
    return symbol.isdigit() and len(symbol) == 4 and not symbol.startswith("0")


def _first(row: dict, *names: str) -> str:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return str(row[name]).strip()
    return ""


def _first_any(row: dict, names: tuple[str, ...]) -> str:
    direct = _first(row, *names)
    if direct:
        return direct
    lowered = {str(key).lower(): key for key in row}
    for name in names:
        key = lowered.get(name.lower())
        if key and row.get(key) not in (None, ""):
            return str(row[key]).strip()
    return ""


def _float(value: str) -> float:
    number = _optional_float(value)
    return number if number is not None else 0.0


def _optional_float(value: str) -> Optional[float]:
    text = str(value or "").replace(",", "").replace("%", "").strip()
    if not text or text in {"-", "--", "N/A", "NaN"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_date(value: str) -> date:
    parsed = _optional_date(value)
    if parsed is None:
        raise ValueError(f"Invalid date: {value}")
    return parsed


def _optional_date(value: str) -> Optional[date]:
    text = str(value or "").strip()
    if not text or text in {"-", "--", "N/A"}:
        return None
    text = text.replace("/", "-").replace(".", "-")
    if len(text) >= 10 and text[4] == "-":
        return date.fromisoformat(text[:10])
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    if len(text) == 7 and text.isdigit():
        return date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:7]))
    if "-" in text:
        parts = text.split("-")
        if len(parts) == 3 and len(parts[0]) <= 3:
            return date(int(parts[0]) + 1911, int(parts[1]), int(parts[2]))
    return None


def _parse_datetime(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.min


def _date_iso(value: Optional[date]) -> str:
    return value.isoformat() if value else ""


def _round_optional(value: Optional[float], digits: int) -> Optional[float]:
    return None if value is None else round(value, digits)


def _chunks(items: list[str], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _resolve_optional(base: Path, value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    return _resolve(base, value)
