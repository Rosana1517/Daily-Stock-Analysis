from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from dataclasses import replace
from datetime import date
from pathlib import Path

from quant_research_platform.agent_workflow import (
    agent_workflow_markdown,
    portfolio_decision_bucket,
    portfolio_decision_label,
    portfolio_decision_map,
    run_five_agent_workflow,
)
from quant_research_platform.backtest import run_top_n_backtest
from quant_research_platform.config import QuantPlatformConfig
from quant_research_platform.daily_stock_bridge import (
    RealtimeState,
    build_technical_signals,
    industry_news_score,
    load_latest_realtime_states,
    load_or_fetch_industry_signals,
    load_stock_profiles,
    notification_summary,
    send_hybrid_notification,
    stock_industry,
    stock_name,
)
from quant_research_platform.data import Bar, fetch_openbb_ohlcv, load_csv_ohlcv
from quant_research_platform.qlib_adapter import build_qlib_signal_backtest_config
from quant_research_platform.signals import build_signals
from quant_research_platform.universe import select_candidate_symbols
from stock_signal_system.data.csv_sources import load_news


@dataclass(frozen=True)
class HybridRow:
    symbol: str
    name: str
    industry: str
    kronos_return: float
    kronos_score: float
    news_score: float
    technical_score: float
    realtime_score: float
    hybrid_score: float
    current_close: float
    predicted_close: float
    realtime_status: str
    action: str
    risk_note: str
    technical_evidence: tuple[str, ...]


def run_tw_hybrid(
    config: QuantPlatformConfig,
    report_date: date,
    realtime_cache: Path | None = None,
    news_path: Path | None = None,
    rss_sources_path: Path | None = None,
    notify: bool = False,
    webhook_env: str | None = None,
    line_channel_access_token_env: str | None = None,
    line_to_env: str | None = None,
    line_broadcast: bool = False,
) -> tuple[Path, Path, Path, str]:
    selected_symbols = select_candidate_symbols(
        config.universe_path,
        config.symbols,
        config.universe_candidate_limit,
        news_path,
        config.ohlcv_path,
    )
    config = replace(config, symbols=selected_symbols)
    load_stock_profiles(config.universe_path)
    bars_by_symbol = _load_bars(config)
    kronos_signals = build_signals(
        bars_by_symbol,
        lookback=config.lookback,
        prediction_length=config.prediction_length,
        kronos_repo_path=config.kronos_repo_path,
        kronos_tokenizer=config.kronos_tokenizer,
        kronos_model=config.kronos_model,
    )
    technicals = build_technical_signals(bars_by_symbol)
    industry_signals = load_or_fetch_industry_signals(news_path, rss_sources_path)
    news_items = load_news(news_path) if news_path and news_path.exists() else []
    realtime_states = load_latest_realtime_states(realtime_cache)

    rows = []
    for signal in kronos_signals:
        symbol = signal.symbol
        industry = stock_industry(symbol)
        tech = technicals.get(symbol)
        realtime = realtime_states.get(symbol)
        intraday_return = realtime.intraday_return if realtime else 0.0
        kronos_score = _kronos_score(signal.expected_return)
        news_score = industry_news_score(industry, industry_signals)
        technical_score = 50 + (tech.score_adjustment if tech else 0)
        realtime_score = _realtime_score(intraday_return)
        hybrid_score = (
            kronos_score * 0.40
            + news_score * 0.20
            + technical_score * 0.20
            + realtime_score * 0.10
            + signal.confidence * 100 * 0.10
        )
        rows.append(
            HybridRow(
                symbol=symbol,
                name=stock_name(symbol),
                industry=industry,
                kronos_return=signal.expected_return,
                kronos_score=kronos_score,
                news_score=news_score,
                technical_score=technical_score,
                realtime_score=realtime_score,
                hybrid_score=hybrid_score,
                current_close=signal.current_close,
                predicted_close=signal.predicted_close,
                realtime_status=realtime.status if realtime else "無即時資料",
                action=_action(hybrid_score, signal.expected_return, intraday_return),
                risk_note=_risk_note(signal.expected_return, tech.bias if tech else "neutral", intraday_return),
                technical_evidence=_technical_evidence(symbol, tech, bars_by_symbol.get(symbol, [])),
            )
        )
    rows = sorted(rows, key=lambda item: item.hybrid_score, reverse=True)
    agent_workflow = run_five_agent_workflow(rows)
    portfolio_decisions = portfolio_decision_map(agent_workflow)
    report_rows = _portfolio_rows(rows, portfolio_decisions, "include")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = config.output_dir / f"tw_hybrid_{report_date.isoformat()}.md"
    csv_path = config.output_dir / f"tw_hybrid_{report_date.isoformat()}.csv"
    qlib_path = config.output_dir / f"qlib_tw_hybrid_{report_date.isoformat()}.yaml"
    backtest = run_top_n_backtest(
        kronos_signals,
        bars_by_symbol,
        top_n=config.top_n,
        initial_cash=config.initial_cash,
        transaction_cost_bps=config.transaction_cost_bps,
        benchmark_symbol=config.benchmark_symbol,
    )
    _save_csv(csv_path, report_rows)
    _save_report(
        report_path,
        rows,
        report_date,
        csv_path,
        qlib_path,
        backtest,
        industry_signals,
        news_items,
        agent_workflow,
        bars_by_symbol,
    )
    build_qlib_signal_backtest_config(csv_path, "custom_tw", config.benchmark_symbol or "2330.TW", qlib_path, config.top_n, 1)

    status = "disabled"
    if notify:
        status = send_hybrid_notification(
            notification_summary(report_rows, report_path),
            webhook_env,
            line_channel_access_token_env,
            line_to_env,
            line_broadcast,
        )
    return report_path, csv_path, qlib_path, status


def _load_bars(config: QuantPlatformConfig):
    if config.data_source == "openbb":
        return fetch_openbb_ohlcv(config.symbols, config.openbb_provider)
    if not config.ohlcv_path:
        return {}
    return load_csv_ohlcv(config.ohlcv_path, config.symbols)


def _kronos_score(expected_return: float) -> float:
    return max(0.0, min(100.0, 50 + expected_return * 600))


def _realtime_score(intraday_return: float) -> float:
    return max(0.0, min(100.0, 50 + intraday_return * 700))


def _realtime_state_from_quote(quote) -> RealtimeState:
    suffix = "TWO" if str(quote.market).lower() == "otc" else "TW"
    price = float(quote.price or 0)
    previous = float(quote.previous_close or 0)
    intraday_return = price / previous - 1 if previous else 0.0
    return RealtimeState(
        symbol=f"{quote.symbol}.{suffix}",
        price=price,
        previous_close=previous,
        intraday_return=intraday_return,
        status=_quote_intraday_status(intraday_return),
        timestamp=quote.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _quote_intraday_status(value: float) -> str:
    if value >= 0.015:
        return "盤中偏多"
    if value >= 0.003:
        return "盤中偏強"
    if value <= -0.015:
        return "盤中偏弱"
    if value <= -0.003:
        return "盤中走弱"
    return "盤中持平"


def _action(score: float, expected_return: float, intraday_return: float) -> str:
    if score >= 70 and expected_return > 0 and intraday_return >= -0.01:
        return "研究重點"
    if score >= 62 and expected_return > 0:
        return "等待確認"
    if expected_return < -0.03 or score < 50:
        return "排除"
    return "觀察"


def _risk_note(expected_return: float, tech_bias: str, intraday_return: float) -> str:
    risks = []
    if expected_return < 0:
        risks.append("Kronos 預期報酬為負")
    if tech_bias == "bearish":
        risks.append("技術結構偏空")
    if intraday_return < -0.01:
        risks.append("盤中走弱")
    return "；".join(risks) if risks else "風險穩定"


def _save_csv(path: Path, rows: list[HybridRow]) -> None:
    fieldnames = [name for name in HybridRow.__dataclass_fields__.keys() if name != "technical_evidence"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = {name: getattr(row, name) for name in fieldnames}
            writer.writerow(payload)


def _save_report(
    path: Path,
    rows: list[HybridRow],
    report_date: date,
    csv_path: Path,
    qlib_path: Path,
    backtest,
    industry_signals: list,
    news_items: list,
    agent_workflow,
    bars_by_symbol: dict[str, list[Bar]],
) -> None:
    portfolio_decisions = portfolio_decision_map(agent_workflow)
    focus_rows = _portfolio_rows(rows, portfolio_decisions, "include")
    watch_rows = _portfolio_rows(rows, portfolio_decisions, "watch")
    excluded_rows = _portfolio_rows(rows, portfolio_decisions, "exclude")

    lines = [
        f"# Hybrid 量化每日選股報告 - {report_date.isoformat()}",
        "",
        "## 工作流程覆蓋",
        "",
        "- Kronos：預測各股票的預期報酬與信心度；若本機模型不可用，報告會標記為模型回退風險。",
        "- Qlib：輸出訊號 CSV 與 TopK-Dropout 交接設定，後續可做更完整的 IC、Rank IC 與回撤檢查。",
        "- 五代理：Portfolio_Manager_Agent 的決策會控制每日研究名單；Devil_Advocate_Agent 否決標的不會進入重點 CSV。",
        "",
        "## 每日研究名單",
        "",
        "| 排名 | 股票 | 名稱 | 產業 | Hybrid | Kronos | 新聞 | 技術 | 即時盤 | 組合決策 |",
        "|---:|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    if focus_rows:
        for rank, row in enumerate(focus_rows, start=1):
            decision = portfolio_decisions.get(row.symbol)
            lines.append(
                f"| {rank} | {row.symbol} | {row.name} | {row.industry} | {row.hybrid_score:.1f} | "
                f"{row.kronos_return:.2%} | {row.news_score:.1f} | {row.technical_score:.1f} | "
                f"{row.realtime_status} | {portfolio_decision_label(decision)} |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - | - | 本次無符合條件標的 |")

    lines.extend(["", "## 候選全覽", "", "| 股票 | 名稱 | 產業 | Hybrid | 組合決策 | 風險註記 |", "|---|---|---|---:|---|---|"])
    for row in rows:
        decision = portfolio_decisions.get(row.symbol)
        lines.append(
            f"| {row.symbol} | {row.name} | {row.industry} | {row.hybrid_score:.1f} | "
            f"{portfolio_decision_label(decision)} | {row.risk_note} |"
        )

    lines.extend(["", *agent_workflow_markdown(agent_workflow)])
    lines.extend(
        [
            "",
            "## 互動技術分析策略",
            "",
            "| 策略 | 圖上位置 | 採用角色 | 用途邊界 |",
            "|---|---|---|---|",
            "| 黃金交叉 / 死亡交叉 | 主 K 線區，MA5/MA20/MA60 可調 | Technical、Quant、Devil | 研究條件與假突破檢查，不直接產生推薦 |",
            "| 週期均線與支撐壓力 | 主 K 線區，預設近 60 根高低點 | Technical、Portfolio | 決定觀察條件是否清楚；Portfolio 只彙整 |",
            "| MACD | 副圖動能區，12/26/9 可調 | Technical、Quant | 量化交叉與柱狀體翻轉，需樣本驗證 |",
            "| RSI | 副圖相對強弱區，14 日與 20/80 可調 | Technical、Devil | 標示過熱或低檔鈍化風險，避免單一指標決策 |",
            "| 布林通道 | 主 K 線區，20 日/2 倍標準差可調 | Technical、Devil | 檢查突破、回落與波動擴張 |",
            "| K 線型態與量價 | 主 K 線標記與成交量副圖 | Technical、Devil | 只在趨勢與量能確認後作為證據 |",
            "| 三線突破 | 主 K 線訊號標記 | Quant、Devil | 作為可重算突破因子，低量或未站穩需降權 |",
            "| 近 10 日漲停排除 3 連漲 | 策略摘要與標記區 | Quant、Devil | 找短線強勢但排除過熱連續鎖漲停 |",
            "| 月均線 MACD 金叉向上 | 策略摘要 | Technical、Quant | 以月線級別確認中期動能，樣本不足時只列觀察 |",
            "| 日均線股價在 20 均線附近且放量陽線 | 日 K 線與成交量副圖 | Technical、Devil | 僅檢查日線收盤價是否靠近日 MA20，且當日為放量陽線；低量或非陽線不成立 |",
        ]
    )
    lines.extend(["", "## RSS 產業訊號", "", "| 產業 | RSS 分數 | 證據數 | 主要催化 |", "|---|---:|---:|---|"])
    for signal in industry_signals[:8]:
        catalyst = signal.catalysts[0] if signal.catalysts else "無新的催化訊號"
        lines.append(f"| {signal.industry} | {signal.score:.1f} | {signal.evidence_count} | {catalyst} |")
    if not industry_signals:
        lines.append("| 市場觀察 | 50.0 | 0 | RSS 暫時不可用，使用中性新聞分數。 |")

    lines.extend(["", "## 產業分組", "", "| 產業 | 股票 | 平均 Hybrid | 偏向 |", "|---|---|---:|---|"])
    for industry, group in _group_rows_by_industry(rows).items():
        symbols = ", ".join(f"{row.symbol} {row.name}" for row in group[:4])
        average = sum(row.hybrid_score for row in group) / len(group)
        lines.append(f"| {industry} | {symbols} | {average:.1f} | {_industry_bias(average)} |")

    lines.extend(["", "## 研究觀察", ""])
    if focus_rows:
        lines.extend(_research_observation(row, "研究重點") for row in focus_rows[:5])
    else:
        lines.append("- 本次沒有 Portfolio_Manager_Agent 核准進入每日研究名單的標的。")

    lines.extend(["", "## 觀察名單", ""])
    if watch_rows:
        lines.extend(_research_observation(row, "觀察") for row in watch_rows[:5])
    else:
        lines.append("- 本次沒有 watch_only 標的。")

    if excluded_rows:
        lines.extend(["", "## 排除原因", ""])
        for row in excluded_rows[:8]:
            decision = portfolio_decisions.get(row.symbol)
            lines.append(f"- {row.symbol} {row.name}: {portfolio_decision_label(decision)}；原因：{row.risk_note}。")

    lines.extend(
        [
            "",
            "## 投組模擬",
            "",
            f"- 毛預期報酬：{backtest.gross_expected_return:.2%}",
            f"- 扣除成本後預期報酬：{backtest.net_expected_return:.2%}",
            f"- 預估損益：{backtest.estimated_pnl:,.2f}",
            "",
            "## 可重算驗證指標",
            "",
            "- 說明：此區是以現有樣本做保守、可重算的觀察驗證，尚不等同完整樣本外回測。",
            f"- 樣本數：{getattr(getattr(backtest, 'validation', None), 'sample_count', 0)}",
            f"- 勝率：{_format_rate(getattr(getattr(backtest, 'validation', None), 'win_rate', None))}",
            f"- False positive rate：{_format_rate(getattr(getattr(backtest, 'validation', None), 'false_positive_rate', None))}",
            f"- 平均觀察報酬：{_format_rate(getattr(getattr(backtest, 'validation', None), 'average_realized_return', None))}",
        ]
    )
    if backtest.benchmark_return is not None:
        lines.append(f"- 基準回看報酬：{backtest.benchmark_return:.2%}")

    lines.extend(["", "## 新聞快訊", ""])
    for item in news_items[:6]:
        industries = ", ".join(item.industries) if item.industries else "市場"
        lines.append(f"- [{industries}] {item.title}（{item.source}, {item.date.isoformat()}）")
    if not news_items:
        lines.append("- 本次 RSS 不可用；報告使用快取市場資料與中性 RSS 分數。")
    lines.extend(["", "## 產出檔案", "", f"- Hybrid 研究名單 CSV：`{csv_path}`", f"- Qlib 交接設定：`{qlib_path}`"])
    lines.extend(
        [
            "",
            "```technical-chart-data",
            json.dumps(_technical_chart_payload(rows, bars_by_symbol, portfolio_decisions), ensure_ascii=False, separators=(",", ":")),
            "```",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _group_rows_by_industry(rows: list[HybridRow]) -> dict[str, list[HybridRow]]:
    groups: dict[str, list[HybridRow]] = {}
    for row in rows:
        groups.setdefault(row.industry, []).append(row)
    return {
        industry: sorted(group, key=lambda item: item.hybrid_score, reverse=True)
        for industry, group in sorted(
            groups.items(),
            key=lambda item: sum(row.hybrid_score for row in item[1]) / len(item[1]),
            reverse=True,
        )
    }


def _industry_bias(score: float) -> str:
    if score >= 70:
        return "強勢觀察"
    if score >= 62:
        return "偏多觀察"
    if score < 50:
        return "偏弱"
    return "中性觀察"


def _portfolio_rows(rows: list[HybridRow], decisions: dict, bucket: str) -> list[HybridRow]:
    return [row for row in rows if portfolio_decision_bucket(decisions.get(row.symbol)) == bucket]


def _research_observation(row: HybridRow, label: str) -> str:
    risk_low, risk_high = _risk_range(row)
    return (
        f"- {row.symbol} {row.name}: {label}；目前價格 {row.current_close:.2f}，"
        f"Kronos 觀察價 {row.predicted_close:.2f}，Hybrid {row.hybrid_score:.1f}。"
        f"風險區間 {risk_low:.2f} 至 {risk_high:.2f}；"
        f"失效條件：{_invalidation_condition(row, risk_low)}；"
        f"風險註記：{row.risk_note}。"
    )


def _risk_range(row: HybridRow) -> tuple[float, float]:
    downside = row.current_close * 0.955
    upside = max(row.predicted_close, row.current_close * 1.06)
    return downside, upside


def _invalidation_condition(row: HybridRow, risk_low: float) -> str:
    checks = (
        (row.kronos_return <= 0, "Kronos 預期報酬轉負"),
        (row.technical_score < 50, "技術分數低於 50"),
        (row.realtime_score < 50, "即時盤分數低於 50"),
    )
    return next((message for matched, message in checks if matched), f"跌破風險區間下緣 {risk_low:.2f}")


def _technical_evidence(symbol: str, tech, bars: list[Bar]) -> tuple[str, ...]:
    if not bars:
        return ("ohlcv=data_limited", "multi_timeframe=data_limited", "volume_price=data_limited")
    latest = bars[-1]
    volume_ratio = _volume_ratio(bars)
    patterns = tuple(getattr(tech, "patterns", ())[:2]) if tech else ()
    support = min(bar.low for bar in bars[-10:]) if len(bars) >= 2 else latest.low
    resistance = max(bar.high for bar in bars[-10:]) if len(bars) >= 2 else latest.high
    evidence = [
        f"close={latest.close:.2f}",
        f"support={support:.2f}",
        f"resistance={resistance:.2f}",
        f"volume_ratio={volume_ratio:.2f}" if volume_ratio is not None else "volume_ratio=data_limited",
        f"structure_bias={getattr(tech, 'structure_bias', 'data_limited') if tech else 'data_limited'}",
    ]
    evidence.extend(patterns or ("pattern=data_limited",))
    return tuple(evidence)


def _volume_ratio(bars: list[Bar]) -> float | None:
    if len(bars) < 2:
        return None
    window = bars[-20:]
    average = sum(bar.volume for bar in window) / len(window)
    return bars[-1].volume / average if average else None


def _format_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def _technical_chart_payload(rows: list[HybridRow], bars_by_symbol: dict[str, list[Bar]], decisions: dict) -> dict:
    return {
        "defaults": {
            "maShort": 5,
            "maMid": 20,
            "maLong": 60,
            "rsiPeriod": 14,
            "rsiLow": 20,
            "rsiHigh": 80,
            "macdFast": 12,
            "macdSlow": 26,
            "macdSignal": 9,
            "bollingerPeriod": 20,
            "bollingerSigma": 2,
        },
        "agentPolicy": [
            "Market_Intelligence_Agent 只提供市場背景與風險標籤，不推薦股票。",
            "Technical_Analyst_Agent 只使用 K 線、均線、量價與技術結構。",
            "Quant_Research_Agent 只保留可重算的因子與 false positive 檢查。",
            "Devil_Advocate_Agent 對低量突破、過熱背離、資料不足保留 veto。",
            "Portfolio_Manager_Agent 只彙整其他 agents，不自行分析股票。",
        ],
        "stocks": [_technical_chart_stock(row, bars_by_symbol.get(row.symbol, []), decisions.get(row.symbol)) for row in rows],
    }


def _technical_chart_stock(row: HybridRow, bars: list[Bar], decision) -> dict:
    recent_bars = bars[-160:]
    support, resistance = _support_resistance(recent_bars)
    return {
        "symbol": row.symbol,
        "name": row.name,
        "industry": row.industry,
        "hybridScore": round(row.hybrid_score, 2),
        "technicalScore": round(row.technical_score, 2),
        "decision": portfolio_decision_label(decision),
        "bucket": portfolio_decision_bucket(decision),
        "riskNote": row.risk_note,
        "support": support,
        "resistance": resistance,
        "evidence": list(row.technical_evidence),
        "strategySummary": _technical_strategy_summary(row, recent_bars),
        "bars": [
            {
                "date": bar.timestamp.date().isoformat(),
                "open": round(bar.open, 4),
                "high": round(bar.high, 4),
                "low": round(bar.low, 4),
                "close": round(bar.close, 4),
                "volume": round(bar.volume, 2),
            }
            for bar in recent_bars
        ],
    }


def _support_resistance(bars: list[Bar]) -> tuple[float | None, float | None]:
    if not bars:
        return None, None
    window = bars[-60:] if len(bars) >= 60 else bars
    return round(min(bar.low for bar in window), 4), round(max(bar.high for bar in window), 4)


def _technical_strategy_summary(row: HybridRow, bars: list[Bar]) -> list[dict[str, str]]:
    if len(bars) < 2:
        return [{"strategy": "資料完整性", "status": "資料不足", "agent": "Devil_Advocate_Agent", "use": "排除每日重點"}]
    latest = bars[-1]
    volume_ratio = _volume_ratio(bars)
    support, resistance = _support_resistance(bars)
    return [
        {
            "strategy": "黃金交叉 / 死亡交叉",
            "status": _cross_status([bar.close for bar in bars], 5, 20),
            "agent": "Technical_Analyst_Agent",
            "use": "主圖標記均線交叉，交給 Quant 驗證觸發後表現。",
        },
        {
            "strategy": "MA20 風險線",
            "status": _ma_position_status([bar.close for bar in bars], 20),
            "agent": "Technical_Analyst_Agent",
            "use": "對應操作重點文件的 20 週線紀律；日線先作近似觀察。",
        },
        {
            "strategy": "RSI",
            "status": _rsi_status([bar.close for bar in bars], 14, 20, 80),
            "agent": "Devil_Advocate_Agent",
            "use": "檢查過熱、低檔鈍化與單一指標風險。",
        },
        {
            "strategy": "布林通道",
            "status": _bollinger_status([bar.close for bar in bars], 20, 2),
            "agent": "Technical_Analyst_Agent",
            "use": "檢查波動擴張、突破後回落與風險區間。",
        },
        {
            "strategy": "量價確認",
            "status": "量能放大" if volume_ratio is not None and volume_ratio >= 1.5 else "量能未明顯放大",
            "agent": "Devil_Advocate_Agent",
            "use": "低量突破不得列為強訊號。",
        },
        {
            "strategy": "三線突破",
            "status": _three_line_status(bars),
            "agent": "Quant_Research_Agent",
            "use": "作為可重算突破因子與 false positive 檢查。",
        },
        {
            "strategy": "近 10 日漲停排除 3 連漲",
            "status": _recent_limit_up_status(bars),
            "agent": "Devil_Advocate_Agent",
            "use": "保留短線強勢觀察，但排除連續鎖漲停造成的過熱風險。",
        },
        {
            "strategy": "月均線 MACD 金叉向上",
            "status": _monthly_ma_macd_status(bars),
            "agent": "Technical_Analyst_Agent",
            "use": "以月線級別確認中期動能；資料不足時不得升級為主訊號。",
        },
        {
            "strategy": "日均線股價在 20 均線附近且放量陽線",
            "status": _ma20_volume_bull_status(bars),
            "agent": "Technical_Analyst_Agent",
            "use": "檢查日線收盤價靠近日 MA20 時，當日是否為放量陽線。",
        },
        {
            "strategy": "支撐壓力",
            "status": f"支撐 {support:.2f} / 壓力 {resistance:.2f}" if support is not None and resistance is not None else "資料不足",
            "agent": "Portfolio_Manager_Agent",
            "use": f"只彙整為{row.symbol}的研究觀察，不自行延伸判斷。",
        },
        {
            "strategy": "當日 K 線",
            "status": _candle_status(latest),
            "agent": "Technical_Analyst_Agent",
            "use": "K 線型態必須搭配趨勢與量能，不可孤立解讀。",
        },
    ]


def _rolling_average(values: list[float], window: int) -> float | None:
    return sum(values[-window:]) / window if len(values) >= window and window > 0 else None


def _cross_status(values: list[float], short_window: int, long_window: int) -> str:
    if len(values) <= long_window:
        return "資料不足"
    prev_short = sum(values[-short_window - 1 : -1]) / short_window
    prev_long = sum(values[-long_window - 1 : -1]) / long_window
    current_short = _rolling_average(values, short_window)
    current_long = _rolling_average(values, long_window)
    if current_short is None or current_long is None:
        return "資料不足"
    if prev_short <= prev_long and current_short > current_long:
        return "黃金交叉成立"
    if prev_short >= prev_long and current_short < current_long:
        return "死亡交叉成立"
    return "未出現新交叉"


def _ma_position_status(values: list[float], window: int) -> str:
    average = _rolling_average(values, window)
    if average is None:
        return "資料不足"
    return "收盤站上均線" if values[-1] >= average else "收盤低於均線"


def _rsi_status(values: list[float], period: int, low: float, high: float) -> str:
    if len(values) <= period:
        return "資料不足"
    deltas = [values[index] - values[index - 1] for index in range(len(values) - period, len(values))]
    gains = sum(delta for delta in deltas if delta > 0) / period
    losses = abs(sum(delta for delta in deltas if delta < 0) / period)
    rsi = 100.0 if losses == 0 else 100 - (100 / (1 + gains / losses))
    if rsi <= low:
        return f"RSI {rsi:.1f}，低檔觀察"
    if rsi >= high:
        return f"RSI {rsi:.1f}，過熱風險"
    return f"RSI {rsi:.1f}，中性"


def _bollinger_status(values: list[float], window: int, sigma: float) -> str:
    average = _rolling_average(values, window)
    if average is None:
        return "資料不足"
    variance = sum((value - average) ** 2 for value in values[-window:]) / window
    width = variance ** 0.5 * sigma
    close = values[-1]
    if close > average + width:
        return "突破上緣，檢查回落風險"
    if close < average - width:
        return "跌破下緣，檢查波動風險"
    return "位於通道內"


def _three_line_status(bars: list[Bar]) -> str:
    if len(bars) < 4:
        return "資料不足"
    previous = bars[-4:-1]
    close = bars[-1].close
    if close > max(bar.high for bar in previous):
        return "向上三線突破"
    if close < min(bar.low for bar in previous):
        return "向下三線突破"
    return "未突破前三根區間"


def _recent_limit_up_status(bars: list[Bar]) -> str:
    if len(bars) < 11:
        return "資料不足"
    returns = [(bars[index].close / bars[index - 1].close - 1) for index in range(1, len(bars))]
    recent = returns[-10:]
    limit_flags = [value >= 0.095 for value in recent]
    has_limit = any(limit_flags)
    three_consecutive = any(all(limit_flags[start : start + 3]) for start in range(0, max(len(limit_flags) - 2, 0)))
    if has_limit and not three_consecutive:
        count = sum(1 for flagged in limit_flags if flagged)
        return f"近 10 日有 {count} 次漲停，未達 3 連漲"
    if three_consecutive:
        return "近 10 日出現 3 連漲停，過熱排除"
    return "近 10 日未見漲停"


def _monthly_ma_macd_status(bars: list[Bar]) -> str:
    monthly = _monthly_closes(bars)
    if len(monthly) < 8:
        return "月線資料不足"
    closes = [item[1] for item in monthly]
    ma3 = _rolling_average(closes, 3)
    ma6 = _rolling_average(closes, 6)
    macd_line, signal_line = _macd_latest(closes, 3, 6, 3)
    if ma3 is None or ma6 is None or macd_line is None or signal_line is None:
        return "月線資料不足"
    if ma3 > ma6 and macd_line > signal_line and macd_line > 0:
        return "月均線多頭且 MACD 金叉向上"
    if ma3 > ma6 and macd_line > signal_line:
        return "月均線偏多，MACD 金叉待確認"
    return "月線動能未同步轉強"


def _ma20_volume_bull_status(bars: list[Bar]) -> str:
    if len(bars) < 20:
        return "資料不足"
    latest = bars[-1]
    ma20 = _rolling_average([bar.close for bar in bars], 20)
    volume_ratio = _volume_ratio(bars)
    if ma20 is None or volume_ratio is None:
        return "資料不足"
    near_ma20 = abs(latest.close - ma20) / ma20 <= 0.02
    bullish = latest.close > latest.open
    high_volume = volume_ratio >= 1.5
    if near_ma20 and bullish and high_volume:
        return f"日線收盤靠近日 MA20 且放量陽線，量比 {volume_ratio:.2f}"
    missing = []
    if not near_ma20:
        missing.append("日線收盤未貼近日 MA20")
    if not bullish:
        missing.append("日 K 非陽線")
    if not high_volume:
        missing.append(f"量比 {volume_ratio:.2f} 未放大")
    return "，".join(missing)


def _monthly_closes(bars: list[Bar]) -> list[tuple[str, float]]:
    monthly: dict[str, float] = {}
    for bar in bars:
        key = bar.timestamp.strftime("%Y-%m")
        monthly[key] = bar.close
    return list(monthly.items())


def _macd_latest(values: list[float], fast: int, slow: int, signal: int) -> tuple[float | None, float | None]:
    if len(values) < slow + signal:
        return None, None
    fast_ema = _ema(values, fast)
    slow_ema = _ema(values, slow)
    macd = [fast_value - slow_value for fast_value, slow_value in zip(fast_ema, slow_ema)]
    signal_line = _ema(macd, signal)
    return macd[-1], signal_line[-1]


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (span + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * multiplier + result[-1] * (1 - multiplier))
    return result


def _candle_status(bar: Bar) -> str:
    body = abs(bar.close - bar.open)
    spread = max(bar.high - bar.low, 0.0001)
    upper = bar.high - max(bar.open, bar.close)
    lower = min(bar.open, bar.close) - bar.low
    if body / spread <= 0.12:
        return "十字線，等待確認"
    if lower >= body * 2 and upper <= body:
        return "錘子線特徵"
    if upper >= body * 2 and lower <= body:
        return "長上影，檢查出貨風險"
    return "一般 K 線"
