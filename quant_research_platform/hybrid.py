from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from quant_research_platform.backtest import run_top_n_backtest
from quant_research_platform.config import QuantPlatformConfig
from quant_research_platform.daily_stock_bridge import (
    build_technical_signals,
    industry_news_score,
    load_latest_realtime_states,
    load_or_fetch_industry_signals,
    notification_summary,
    send_hybrid_notification,
    stock_industry,
    stock_name,
)
from quant_research_platform.data import fetch_openbb_ohlcv, load_csv_ohlcv
from quant_research_platform.qlib_adapter import build_qlib_signal_backtest_config
from quant_research_platform.signals import build_signals
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
        kronos_score = _kronos_score(signal.expected_return)
        news_score = industry_news_score(industry, industry_signals)
        technical_score = 50 + (tech.score_adjustment if tech else 0)
        realtime_score = _realtime_score(realtime.intraday_return if realtime else 0)
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
                realtime_status=realtime.status if realtime else "未接即時價",
                action=_action(hybrid_score, signal.expected_return, realtime.intraday_return if realtime else 0),
                risk_note=_risk_note(signal.expected_return, tech.bias if tech else "neutral", realtime.intraday_return if realtime else 0),
            )
        )
    rows = sorted(rows, key=lambda item: item.hybrid_score, reverse=True)

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
    _save_csv(csv_path, rows)
    _save_report(report_path, rows, report_date, csv_path, qlib_path, backtest, industry_signals, news_items)
    build_qlib_signal_backtest_config(csv_path, "custom_tw", config.benchmark_symbol or "2330.TW", qlib_path, config.top_n, 1)

    status = "disabled"
    if notify:
        status = send_hybrid_notification(
            notification_summary(rows, report_path),
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


def _action(score: float, expected_return: float, intraday_return: float) -> str:
    if score >= 70 and expected_return > 0 and intraday_return >= -0.01:
        return "可列入買進觀察"
    if score >= 62 and expected_return > 0:
        return "等待盤中確認"
    if expected_return < -0.03 or score < 50:
        return "暫避或減碼"
    return "觀察"


def _risk_note(expected_return: float, tech_bias: str, intraday_return: float) -> str:
    risks = []
    if expected_return < 0:
        risks.append("Kronos 預測偏空")
    if tech_bias == "bearish":
        risks.append("技術策略偏空")
    if intraday_return < -0.01:
        risks.append("即時價轉弱")
    return "；".join(risks) if risks else "控制單檔部位與停損"


def _save_csv(path: Path, rows: list[HybridRow]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(HybridRow.__dataclass_fields__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def _save_report(
    path: Path,
    rows: list[HybridRow],
    report_date: date,
    csv_path: Path,
    qlib_path: Path,
    backtest,
    industry_signals: list,
    news_items: list,
) -> None:
    lines = [
        f"# Hybrid Quant Daily Stock Report - {report_date.isoformat()}",
        "",
        "## Workflow Coverage",
        "",
        "- Kronos: forecast return and confidence for each symbol; falls back to momentum only if local model loading is unavailable.",
        "- OpenBB: supported as the market data gateway when `data_source` is `openbb`; CSV cache remains available for scheduled offline runs.",
        "- Qlib: emits a signal CSV and a Qlib TopK-Dropout backtest scaffold for deeper IC, Rank IC, turnover, and drawdown evaluation.",
        "- Daily Stock Analysis: RSS/news industry score, candlestick structure score, report rendering, and LINE/webhook delivery are reused.",
        "",
        "## Top Ranking",
        "",
        "| Rank | Symbol | Name | Industry | Hybrid | Kronos | News | Tech | Realtime | Action |",
        "|---:|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for rank, row in enumerate(rows, start=1):
        lines.append(
            f"| {rank} | {row.symbol} | {row.name} | {row.industry} | {row.hybrid_score:.1f} | "
            f"{row.kronos_return:.2%} | {row.news_score:.1f} | {row.technical_score:.1f} | "
            f"{row.realtime_status} | {row.action} |"
        )
    lines.extend(
        [
            "",
            "## RSS Industry Signals",
            "",
            "| Industry | RSS Score | Evidence | Key Catalyst |",
            "|---|---:|---:|---|",
        ]
    )
    for signal in industry_signals[:8]:
        catalyst = signal.catalysts[0] if signal.catalysts else "No fresh catalyst"
        lines.append(f"| {signal.industry} | {signal.score:.1f} | {signal.evidence_count} | {catalyst} |")
    if not industry_signals:
        lines.append("| Market Watch | 50.0 | 0 | RSS temporarily unavailable; using neutral news score. |")

    lines.extend(["", "## Industry Groups", "", "| Industry | Symbols | Average Hybrid | Bias |", "|---|---|---:|---|"])
    for industry, group in _group_rows_by_industry(rows).items():
        symbols = ", ".join(f"{row.symbol} {row.name}" for row in group[:4])
        average = sum(row.hybrid_score for row in group) / len(group)
        lines.append(f"| {industry} | {symbols} | {average:.1f} | {_industry_bias(average)} |")

    lines.extend(["", "## Investment Notes", ""])
    for row in rows[:5]:
        entry, stop, target, take_profit = _strategy_points(row)
        lines.append(
            f"- {row.symbol} {row.name}: current {row.current_close:.2f}, "
            f"predicted {row.predicted_close:.2f}, hybrid {row.hybrid_score:.1f}. "
            f"{row.action}. Entry {entry:.2f}, add {target:.2f}, stop {stop:.2f}, take-profit {take_profit:.2f}. "
            f"Risk: {row.risk_note}."
        )
    lines.extend(
        [
            "",
            "## Portfolio Simulation",
            "",
            f"- Gross expected return: {backtest.gross_expected_return:.2%}",
            f"- Net expected return after cost: {backtest.net_expected_return:.2%}",
            f"- Estimated PnL: {backtest.estimated_pnl:,.2f}",
        ]
    )
    if backtest.benchmark_return is not None:
        lines.append(f"- Benchmark lookback return: {backtest.benchmark_return:.2%}")
    lines.extend(
        [
            "",
            "## News Feed",
            "",
        ]
    )
    for item in news_items[:6]:
        industries = ", ".join(item.industries) if item.industries else "Market"
        lines.append(f"- [{industries}] {item.title} ({item.source}, {item.date.isoformat()})")
    if not news_items:
        lines.append("- RSS feed unavailable in this run; report used cached market data and neutral RSS scoring.")
    lines.extend(
        [
            "",
            "## Generated Artifacts",
            "",
            f"- Hybrid signal CSV: `{csv_path}`",
            f"- Qlib handoff config: `{qlib_path}`",
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
        return "積極觀察"
    if score >= 62:
        return "等待確認"
    if score < 50:
        return "降低曝險"
    return "中性觀察"


def _strategy_points(row: HybridRow) -> tuple[float, float, float, float]:
    entry = row.current_close * 0.995
    add = row.current_close * 1.015
    stop = row.current_close * 0.955
    take_profit = max(row.predicted_close, row.current_close * 1.06)
    return entry, stop, add, take_profit
