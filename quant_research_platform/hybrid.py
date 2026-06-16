from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from dataclasses import replace
from datetime import date
from pathlib import Path

from quant_research_platform.agent_workflow import (
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
from quant_research_platform.qlib_adapter import (
    build_qlib_signal_backtest_config,
    run_inline_signal_diagnostics,
    run_qlib_engine_portfolio_backtest,
)
from quant_research_platform.signals import build_signals
from quant_research_platform.universe import build_candidate_selection_plan
from stock_signal_system.data.csv_sources import load_intraday_history, load_news


@dataclass(frozen=True)
class HybridRow:
    symbol: str
    name: str
    industry: str
    screening_bucket: str
    legacy_hit: bool
    new_strategy_hit: bool
    chip_radar_hit: bool
    signal_source: str
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
    top10_main_force_buy_strength: float | None
    top10_main_force_net_buy: float | None
    foreign_buy_streak_days: float | None
    branch_main_force_buy_streak_days: float | None
    branch_main_force_leader: str
    chip_data_date: str
    chip_data_source: str
    chip_data_source_status: str
    top10_main_force_brokers: str
    technical_evidence: tuple[str, ...]


def run_tw_hybrid(
    config: QuantPlatformConfig,
    report_date: date,
    realtime_cache: Path | None = None,
    news_path: Path | None = None,
    rss_sources_path: Path | None = None,
    stock_snapshot_path: Path | None = None,
    price_1h_path: Path | None = None,
    price_5m_path: Path | None = None,
    notify: bool = False,
    webhook_env: str | None = None,
    line_channel_access_token_env: str | None = None,
    line_to_env: str | None = None,
    line_broadcast: bool = False,
) -> tuple[Path, Path, Path, str]:
    selection_plan = build_candidate_selection_plan(
        config.universe_path,
        config.symbols,
        config.universe_candidate_limit,
        news_path,
        config.ohlcv_path,
    )
    selected_symbols = selection_plan.selected_symbols
    config = replace(config, symbols=selected_symbols)
    load_stock_profiles(config.universe_path, stock_snapshot_path)
    bars_by_symbol = _load_bars(config)
    structure_history = load_intraday_history(price_1h_path) if price_1h_path and price_1h_path.exists() else {}
    trigger_history = load_intraday_history(price_5m_path) if price_5m_path and price_5m_path.exists() else {}
    kronos_signals = build_signals(
        bars_by_symbol,
        lookback=config.lookback,
        prediction_length=config.prediction_length,
        kronos_repo_path=config.kronos_repo_path,
        kronos_tokenizer=config.kronos_tokenizer,
        kronos_model=config.kronos_model,
    )
    technicals = build_technical_signals(
        bars_by_symbol,
        structure_history if structure_history else None,
        trigger_history if trigger_history else None,
    )
    industry_signals = load_or_fetch_industry_signals(news_path, rss_sources_path)
    news_items = load_news(news_path) if news_path and news_path.exists() else []
    realtime_states = load_latest_realtime_states(realtime_cache)
    chip_snapshot_by_symbol = _load_chip_snapshot_lookup(config.universe_path, stock_snapshot_path)

    rows = []
    rows_by_symbol: dict[str, HybridRow] = {}
    chip_radar_symbols = set(selection_plan.chip_radar_symbols)
    chip_breakout_symbols = set(selection_plan.chip_breakout_symbols)
    legacy_pool_symbols = set(selection_plan.legacy_pool_symbols)
    revised_symbols = set(selection_plan.revised_symbols)
    for signal in kronos_signals:
        symbol = signal.symbol
        industry = stock_industry(symbol)
        tech = technicals.get(symbol)
        realtime = realtime_states.get(symbol)
        chip_snapshot = chip_snapshot_by_symbol.get(symbol, {})
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
        rows_by_symbol[symbol] = HybridRow(
            symbol=symbol,
            name=stock_name(symbol),
            industry=industry,
            screening_bucket=(
                "chip_confirmed"
                if symbol in chip_breakout_symbols
                else "chip_watch" if symbol in revised_symbols or symbol in chip_radar_symbols else "legacy_watch"
            ),
            legacy_hit=symbol in legacy_pool_symbols,
            new_strategy_hit=symbol in chip_breakout_symbols or symbol in revised_symbols,
            chip_radar_hit=symbol in chip_radar_symbols,
            signal_source=signal.source,
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
            top10_main_force_buy_strength=_optional_float(chip_snapshot, "top10_main_force_buy_strength", "top10_main_force_buy_strength_proxy"),
            top10_main_force_net_buy=_optional_float(chip_snapshot, "top10_main_force_net_buy"),
            foreign_buy_streak_days=_optional_float(chip_snapshot, "foreign_buy_streak_days"),
            branch_main_force_buy_streak_days=_optional_float(chip_snapshot, "branch_main_force_buy_streak_days"),
            branch_main_force_leader=str(chip_snapshot.get("branch_main_force_leader", "")).strip(),
            chip_data_date=str(chip_snapshot.get("chip_data_date", "")).strip(),
            chip_data_source=str(chip_snapshot.get("chip_data_source", "")).strip(),
            chip_data_source_status=str(chip_snapshot.get("chip_data_source_status", "")).strip(),
            top10_main_force_brokers=str(chip_snapshot.get("top10_main_force_brokers", "")).strip(),
            technical_evidence=_technical_evidence(symbol, tech, bars_by_symbol.get(symbol, [])),
        )
    report_symbols = []
    for symbol in (*selection_plan.legacy_pool_symbols, *selection_plan.chip_radar_symbols, *selection_plan.selected_symbols):
        if symbol not in report_symbols:
            report_symbols.append(symbol)
    for symbol in report_symbols:
        if symbol in rows_by_symbol:
            continue
        rows_by_symbol[symbol] = _placeholder_row(
            symbol,
            chip_snapshot_by_symbol.get(symbol, {}),
            symbol in legacy_pool_symbols,
            symbol in revised_symbols or symbol in chip_breakout_symbols,
            symbol in chip_radar_symbols,
        )
    rank_map = {symbol: index for index, symbol in enumerate(report_symbols)}
    rows = sorted(
        rows_by_symbol.values(),
        key=lambda item: (
            not item.new_strategy_hit,
            not item.chip_radar_hit,
            not item.legacy_hit,
            -item.hybrid_score,
            rank_map.get(item.symbol, 9999),
        ),
    )
    qlib_metrics = run_inline_signal_diagnostics(kronos_signals, bars_by_symbol, config.top_n)
    qlib_engine = run_qlib_engine_portfolio_backtest(
        kronos_signals,
        bars_by_symbol,
        config.output_dir / f"qlib_provider_{report_date.isoformat()}",
        config.output_dir / f"qlib_engine_{report_date.isoformat()}.csv",
        config.benchmark_symbol,
        config.top_n,
        config.initial_cash,
        config.transaction_cost_bps,
    )
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
        qlib_metrics,
        qlib_engine,
        config,
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


def _load_chip_snapshot_lookup(*paths: Path | None) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for path in paths:
        if not path or not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    symbol = str(row.get("symbol", "")).strip().upper()
                    if not symbol:
                        continue
                    lookup[symbol] = row
                    if "." not in symbol:
                        lookup[f"{symbol}.TW"] = row
                        lookup[f"{symbol}.TWO"] = row
        except OSError:
            continue
    return lookup


def _optional_float(row: dict, *keys: str) -> float | None:
    for key in keys:
        value = str(row.get(key, "")).replace(",", "").strip()
        if not value:
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return None


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
    qlib_metrics,
    qlib_engine,
    config: QuantPlatformConfig,
) -> None:
    portfolio_decisions = portfolio_decision_map(agent_workflow)
    focus_rows = _portfolio_rows(rows, portfolio_decisions, "include")
    watch_rows = _portfolio_rows(rows, portfolio_decisions, "watch")
    excluded_rows = _portfolio_rows(rows, portfolio_decisions, "exclude")
    chip_rows = [row for row in rows if row.screening_bucket == "chip_confirmed"]
    revised_rows = [row for row in rows if row.screening_bucket in {"chip_confirmed", "chip_watch"}]
    chip_watch_rows = [row for row in rows if row.screening_bucket == "chip_watch"]
    legacy_watch_rows = [row for row in rows if row.screening_bucket == "legacy_watch"]

    lines = [
        f"# Hybrid 量化每日選股報告 - {report_date.isoformat()}",
        "",
        "## 每日研究名單",
        "",
        "| 排名 | 股票 | 名稱 | 產業 | Hybrid | 前十大主力強度 | 前十大主力淨買超 | 外資連買 | 主分點連買 | 主分點 | 籌碼日期 | 籌碼狀態 | 組合決策 |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    lines[2:2] = [
        "## \u7c4c\u78bc\u512a\u5148\u96d9\u968e\u6bb5\u8f38\u51fa",
        "",
        *_screening_triple_column_block(chip_rows, chip_watch_rows, legacy_watch_rows, portfolio_decisions),
        "",
    ]
    if focus_rows:
        for rank, row in enumerate(focus_rows, start=1):
            decision = portfolio_decisions.get(row.symbol)
            lines.append(
                f"| {rank} | {row.symbol} | {row.name} | {row.industry} | {row.hybrid_score:.1f} | "
                f"{_chip_value(row.top10_main_force_buy_strength)} | {_chip_value(row.top10_main_force_net_buy, digits=0)} | "
                f"{_chip_value(row.foreign_buy_streak_days, digits=0)} | {_chip_value(row.branch_main_force_buy_streak_days, digits=0)} | "
                f"{row.branch_main_force_leader or 'n/a'} | {row.chip_data_date or 'n/a'} | {row.chip_data_source_status or 'n/a'} | "
                f"{portfolio_decision_label(decision)} |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - | - | 本次無符合條件標的 |")

    lines.extend(["", "## 候選全覽", "", "| 股票 | 名稱 | 產業 | Hybrid | 前十大主力強度 | 外資連買 | 主分點連買 | 主分點 | 籌碼日期 | 籌碼狀態 | 組合決策 | 風險註記 |", "|---|---|---|---:|---:|---:|---:|---|---|---|---|---|"])
    for row in rows:
        decision = portfolio_decisions.get(row.symbol)
        lines.append(
            f"| {row.symbol} | {row.name} | {row.industry} | {row.hybrid_score:.1f} | "
            f"{_chip_value(row.top10_main_force_buy_strength)} | {_chip_value(row.foreign_buy_streak_days, digits=0)} | "
            f"{_chip_value(row.branch_main_force_buy_streak_days, digits=0)} | {row.branch_main_force_leader or 'n/a'} | "
            f"{row.chip_data_date or 'n/a'} | {row.chip_data_source_status or 'n/a'} | "
            f"{portfolio_decision_label(decision)} | {row.risk_note} |"
        )

    lines.extend(
        [
            "",
            "## 選股條件摘要",
            "",
            f"- K值 < 40",
            f"- 近 5 日融資增加前 100 大",
            f"- 收盤價 20 日均線上升",
        ]
    )
    lines.extend(["", "## \u7c4c\u78bc\u512a\u5148\u6d41\u7a0b\u6458\u8981", ""])
    lines.append("- \u7b2c\u4e00\u5c64\uff1a\u4ee5\u7c4c\u78bc\u5feb\u7167\u7576\u524d\u7f6e\u96f7\u9054\uff0c\u5148\u6490\u51fa\u4e3b\u529b\u8207\u6cd5\u4eba\u6301\u7e8c\u505a\u591a\u7684\u5019\u9078\u6c60\u3002")
    lines.append("- \u7b2c\u4e8c\u5c64\uff1a\u4ee5\u65e2\u6709\u50f9\u91cf\u6d41\u7a0b\u7576\u78ba\u8a8d\u5668\uff0c\u8981\u6c42 MA20 \u4e0a\u5347\u3001\u7a81\u7834\u5e73\u53f0\u8207\u878d\u8cc7\u689d\u4ef6\u901a\u904e\u3002")
    lines.append("- \u7b2c\u4e09\u5c64\uff1a\u4f9d\u78ba\u8a8d\u5f37\u5ea6\u5206\u7d1a\u8f38\u51fa\u70ba\u300c\u7c4c\u78bc\u7a81\u7834\u4e3b\u6e05\u55ae\u300d\u300c\u7c4c\u78bc\u89c0\u5bdf\u6e05\u55ae\u300d\u8207\u300c\u820a\u7248\u89c0\u5bdf\u6e05\u55ae\u300d\u3002")
    lines.append(f"- \u7c4c\u78bc\u7a81\u7834\u4e3b\u6e05\u55ae\uff1a{len(chip_rows)} \u6a94")
    lines.append(f"- \u7c4c\u78bc\u89c0\u5bdf\u6e05\u55ae\uff1a{len(chip_watch_rows)} \u6a94")
    lines.append(f"- \u820a\u7248\u89c0\u5bdf\u6e05\u55ae\uff1a{len(legacy_watch_rows)} \u6a94")
    lines.extend(["", "## \u7c4c\u78bc\u89c0\u5bdf\u6e05\u55ae", ""])
    if chip_watch_rows:
        for row in chip_watch_rows[:8]:
            lines.append(f"- {row.symbol} {row.name}: \u7c4c\u78bc\u96f7\u9054\u5df2\u89f8\u767c\uff0c\u4f46\u5c1a\u672a\u901a\u904e\u5b8c\u6574\u6280\u8853\u8207\u878d\u8cc7\u78ba\u8a8d\u3002")
    else:
        lines.append("- \u672c\u6b21\u7121\u9700\u7368\u7acb\u8ffd\u8e64\u7684\u7c4c\u78bc\u89c0\u5bdf\u6a19\u7684\u3002")
    lines.extend(["", "## \u820a\u7248\u89c0\u5bdf\u6e05\u55ae", ""])
    if legacy_watch_rows:
        for row in legacy_watch_rows[:8]:
            lines.append(f"- {row.symbol} {row.name}: \u901a\u904e\u65e2\u6709\u6d41\u7a0b\u689d\u4ef6\uff0c\u4f46\u7576\u65e5\u7c4c\u78bc\u96f7\u9054\u672a\u9054\u512a\u5148\u7b49\u7d1a\u3002")
    else:
        lines.append("- \u672c\u6b21\u7121\u50c5\u7531\u820a\u7248\u6d41\u7a0b\u652f\u6490\u7684\u89c0\u5bdf\u6a19\u7684\u3002")
    lines.extend(
        [
            "",
            "## 互動技術分析策略",
            "",
            "| 策略 | 圖上位置 | 採用角色 | 用途邊界 |",
            "|---|---|---|---|",
            "| 均線、趨勢與支撐壓力 | 主 K 線區，MA5/MA20/MA60 與近 60 根高低點 | Technical、Quant、Portfolio | 先確認方向、站位與關鍵價位，再決定是否列入研究重點 |",
            "| 動能與波動 | MACD、RSI、布林通道 | Technical、Quant、Devil | 觀察動能延續、過熱回落與波動擴張，不單靠單一指標下結論 |",
            "| 型態、量價與突破確認 | K 線標記、成交量、副圖突破訊號 | Technical、Quant、Devil | 只把有量能配合的型態與突破列為證據，低量或未站穩一律降權 |",
            "| 近 10 日漲停排除 3 連漲 | 策略摘要與標記區 | Quant、Devil | 找短線強勢但排除過熱連續鎖漲停 |",
            "| 月均線 MACD 金叉向上 | 策略摘要 | Technical、Quant | 以月線級別確認中期動能，樣本不足時只列觀察 |",
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


def _chip_value(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _placeholder_row(
    symbol: str,
    chip_snapshot: dict,
    legacy_hit: bool,
    new_strategy_hit: bool,
    chip_radar_hit: bool,
) -> HybridRow:
    price = _optional_float(chip_snapshot, "price") or 0.0
    bucket = "chip_confirmed" if new_strategy_hit and chip_radar_hit else "chip_watch" if chip_radar_hit or new_strategy_hit else "legacy_watch"
    return HybridRow(
        symbol=symbol,
        name=stock_name(symbol),
        industry=stock_industry(symbol),
        screening_bucket=bucket,
        legacy_hit=legacy_hit,
        new_strategy_hit=new_strategy_hit,
        chip_radar_hit=chip_radar_hit,
        signal_source="data-limited",
        kronos_return=0.0,
        kronos_score=0.0,
        news_score=50.0,
        technical_score=0.0,
        realtime_score=0.0,
        hybrid_score=0.0,
        current_close=price,
        predicted_close=price,
        realtime_status="無即時資料",
        action="待補資料",
        risk_note="缺少完整 OHLCV / 技術資料",
        top10_main_force_buy_strength=_optional_float(chip_snapshot, "top10_main_force_buy_strength", "top10_main_force_buy_strength_proxy"),
        top10_main_force_net_buy=_optional_float(chip_snapshot, "top10_main_force_net_buy"),
        foreign_buy_streak_days=_optional_float(chip_snapshot, "foreign_buy_streak_days"),
        branch_main_force_buy_streak_days=_optional_float(chip_snapshot, "branch_main_force_buy_streak_days"),
        branch_main_force_leader=str(chip_snapshot.get("branch_main_force_leader", "")).strip(),
        chip_data_date=str(chip_snapshot.get("chip_data_date", "")).strip(),
        chip_data_source=str(chip_snapshot.get("chip_data_source", "")).strip(),
        chip_data_source_status=str(chip_snapshot.get("chip_data_source_status", "")).strip(),
        top10_main_force_brokers=str(chip_snapshot.get("top10_main_force_brokers", "")).strip(),
        technical_evidence=("ohlcv=data_limited", "screening=pool_only"),
    )


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


def _screening_triple_column_block(rows_main: list[HybridRow], rows_chip_watch: list[HybridRow], rows_legacy: list[HybridRow], decisions: dict) -> list[str]:
    main_empty = "\u672c\u6b21\u7121\u7b26\u5408\u300c\u7c4c\u78bc\u512a\u5148 + \u6280\u8853\u78ba\u8a8d\u300d\u7684\u6a19\u7684"
    chip_watch_empty = "\u7c4c\u78bc\u96f7\u9054\u5df2\u89f8\u767c\uff0c\u4f46\u5c1a\u672a\u901a\u904e\u7b2c\u4e8c\u5c64\u78ba\u8a8d"
    legacy_empty = "\u672c\u6b21\u7121\u820a\u7248\u6d41\u7a0b\u7368\u7acb\u4fdd\u7559\u7684\u6a19\u7684"
    return [
        "<table>",
        "<tr>",
        f'<td valign="top" width="33%"><strong>\u7c4c\u78bc\u7a81\u7834\u4e3b\u6e05\u55ae</strong><br>{_screening_column_html(rows_main, decisions, main_empty)}</td>',
        f'<td valign="top" width="33%"><strong>\u7c4c\u78bc\u89c0\u5bdf\u6e05\u55ae</strong><br>{_screening_column_html(rows_chip_watch, decisions, chip_watch_empty)}</td>',
        f'<td valign="top" width="34%"><strong>\u820a\u7248\u89c0\u5bdf\u6e05\u55ae</strong><br>{_screening_column_html(rows_legacy, decisions, legacy_empty)}</td>',
        "</tr>",
        "</table>",
    ]

def _screening_column_html(rows: list[HybridRow], decisions: dict, empty_text: str) -> str:
    if not rows:
        return empty_text
    items = []
    for rank, row in enumerate(rows[:8], start=1):
        decision = portfolio_decision_label(decisions.get(row.symbol))
        bucket_label = " | \u7c4c\u78bc\u7a81\u7834" if row.screening_bucket == "chip_confirmed" else " | \u7c4c\u78bc\u89c0\u5bdf" if row.screening_bucket == "chip_watch" else ""
        items.append(f"{rank}. {row.symbol} {row.name} | {row.industry} | Hybrid {row.hybrid_score:.1f} | {decision}{bucket_label}")
    return "<br>".join(items)


def _technical_chart_stock(row: HybridRow, bars: list[Bar], decision) -> dict:
    recent_bars = bars[-160:]
    support, resistance = _support_resistance(recent_bars)
    return {
        "symbol": row.symbol,
        "name": row.name,
        "industry": row.industry,
        "screeningBucket": row.screening_bucket,
        "screeningLabel": "\u7c4c\u78bc\u7a81\u7834\u4e3b\u6e05\u55ae" if row.screening_bucket == "chip_confirmed" else "\u7c4c\u78bc\u89c0\u5bdf\u6e05\u55ae" if row.screening_bucket == "chip_watch" else "\u820a\u7248\u89c0\u5bdf\u6e05\u55ae",
        "screeningFlags": {
            "legacy": row.legacy_hit,
            "newStrategy": row.new_strategy_hit,
            "chipRadar": row.chip_radar_hit,
        },
        "signalSource": row.signal_source,
        "hybridScore": round(row.hybrid_score, 2),
        "technicalScore": round(row.technical_score, 2),
        "decision": portfolio_decision_label(decision),
        "bucket": portfolio_decision_bucket(decision),
        "riskNote": row.risk_note,
        "chipSnapshot": {
            "top10MainForceBuyStrength": row.top10_main_force_buy_strength,
            "top10MainForceNetBuy": row.top10_main_force_net_buy,
            "foreignBuyStreakDays": row.foreign_buy_streak_days,
            "branchMainForceBuyStreakDays": row.branch_main_force_buy_streak_days,
            "branchMainForceLeader": row.branch_main_force_leader,
            "chipDataDate": row.chip_data_date,
            "chipDataSource": row.chip_data_source,
            "chipDataSourceStatus": row.chip_data_source_status,
            "top10MainForceBrokers": row.top10_main_force_brokers,
        },
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
    volume_ratio = _volume_ratio(bars)
    support, resistance = _support_resistance(bars)
    closes = [bar.close for bar in bars]
    support_status = f"支撐 {support:.2f} / 壓力 {resistance:.2f}" if support is not None and resistance is not None else "資料不足"
    volume_status = "量能放大" if volume_ratio is not None and volume_ratio >= 1.5 else "量能未明顯放大"
    return [
        {
            "strategy": "均線、趨勢與支撐壓力",
            "status": "；".join((_cross_status(closes, 5, 20), _ma_position_status(closes, 20), support_status)),
            "agent": "Technical_Analyst_Agent",
            "use": "先確認方向、站位與關鍵價位，再決定是否列入研究重點。",
        },
        {
            "strategy": "動能與波動",
            "status": "；".join((_rsi_status(closes, 14, 20, 80), _bollinger_status(closes, 20, 2))),
            "agent": "Devil_Advocate_Agent",
            "use": "用來辨識過熱、鈍化與波動擴張，避免追高或過早抄底。",
        },
        {
            "strategy": "型態、量價與突破確認",
            "status": "；".join((volume_status, _three_line_status(bars), _ma20_volume_bull_status(bars))),
            "agent": "Quant_Research_Agent",
            "use": "只有在量價配合時才提高可信度，否則一律視為待確認訊號。",
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
            "use": f"用較長週期確認 {row.symbol} 的中期動能是否仍偏多。",
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
