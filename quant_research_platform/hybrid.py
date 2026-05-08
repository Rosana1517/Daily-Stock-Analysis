from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from dataclasses import replace
from datetime import date
from pathlib import Path

from quant_research_platform.analysis_workflow import StockWorkflowAudit, build_workflow_audits
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
from quant_research_platform.fundamentals import load_fundamental_snapshots
from quant_research_platform.intraday import load_or_fetch_intraday_history
from quant_research_platform.liquidity import build_liquidity_snapshots
from quant_research_platform.qlib_adapter import (
    build_qlib_signal_backtest_config,
    run_inline_signal_diagnostics,
    run_qlib_engine_portfolio_backtest,
)
from quant_research_platform.signals import build_signals
from stock_signal_system.data.csv_sources import load_news


MAX_RECOMMENDATION_ROWS = 15


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
    recommendation_score: float
    price_bucket: str
    current_close: float
    predicted_close: float
    realtime_status: str
    action: str
    risk_note: str


@dataclass(frozen=True)
class UniverseCoverage:
    total_symbols: int
    screened_symbols: int
    deep_analysis_symbols: int
    source_path: str


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
    stock_snapshot_path: Path | None = None,
    price_1h_path: Path | None = None,
    price_5m_path: Path | None = None,
) -> tuple[Path, Path, Path, str]:
    selected_symbols, universe_coverage = _resolve_candidate_universe(config, stock_snapshot_path)
    config = replace(config, symbols=selected_symbols)
    report_top_n = _effective_report_top_n(config.top_n)
    bars_by_symbol = _load_bars(config)
    kronos_signals = build_signals(
        bars_by_symbol,
        lookback=config.lookback,
        prediction_length=config.prediction_length,
        kronos_repo_path=config.kronos_repo_path,
        kronos_tokenizer=config.kronos_tokenizer,
        kronos_model=config.kronos_model,
    )
    structure_history = load_or_fetch_intraday_history(price_1h_path, config.symbols, "1h", "5d")
    trigger_history = load_or_fetch_intraday_history(price_5m_path, config.symbols, "5m", "5d")
    technicals = build_technical_signals(bars_by_symbol, structure_history, trigger_history)
    industry_signals = load_or_fetch_industry_signals(news_path, rss_sources_path)
    news_items = load_news(news_path) if news_path and news_path.exists() else []
    realtime_states = load_latest_realtime_states(realtime_cache)
    fundamental_snapshots = load_fundamental_snapshots(stock_snapshot_path)
    liquidity_snapshots = build_liquidity_snapshots(bars_by_symbol, fundamental_snapshots)

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
        recommendation_score = _recommendation_score(hybrid_score, signal.current_close)
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
                recommendation_score=recommendation_score,
                price_bucket=_price_bucket(signal.current_close),
                current_close=signal.current_close,
                predicted_close=signal.predicted_close,
                realtime_status=realtime.status if realtime else "未接即時價",
                action=_action(hybrid_score, signal.expected_return, realtime.intraday_return if realtime else 0),
                risk_note=_risk_note(signal.expected_return, tech.bias if tech else "neutral", realtime.intraday_return if realtime else 0),
            )
        )
    rows = _rank_rows_with_price_bias(rows, report_top_n)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = config.output_dir / f"tw_hybrid_{report_date.isoformat()}.md"
    csv_path = config.output_dir / f"tw_hybrid_{report_date.isoformat()}.csv"
    qlib_path = config.output_dir / f"qlib_tw_hybrid_{report_date.isoformat()}.yaml"
    backtest = run_top_n_backtest(
        kronos_signals,
        bars_by_symbol,
        top_n=report_top_n,
        initial_cash=config.initial_cash,
        transaction_cost_bps=config.transaction_cost_bps,
        benchmark_symbol=config.benchmark_symbol,
    )
    _save_csv(csv_path, rows)
    build_qlib_signal_backtest_config(csv_path, "custom_tw", config.benchmark_symbol or "2330.TW", qlib_path, report_top_n, 1)
    qlib_metrics = run_inline_signal_diagnostics(rows, bars_by_symbol, report_top_n)
    qlib_engine = run_qlib_engine_portfolio_backtest(
        rows=rows,
        bars_by_symbol=bars_by_symbol,
        provider_dir=config.qlib_data_path or (config.output_dir / "qlib_data_custom_tw"),
        output_path=config.output_dir / f"qlib_engine_portfolio_{report_date.isoformat()}.csv",
        benchmark_symbol=config.benchmark_symbol,
        top_n=report_top_n,
        initial_cash=config.initial_cash,
        transaction_cost_bps=config.transaction_cost_bps,
    )
    workflow_audits = build_workflow_audits(
        rows=rows,
        bars_by_symbol=bars_by_symbol,
        technicals=technicals,
        realtime_states=realtime_states,
        industry_signals=industry_signals,
        news_items=news_items,
        qlib_path=qlib_path,
        data_source=config.data_source,
        openbb_provider=config.openbb_provider,
        fundamental_snapshots=fundamental_snapshots,
        liquidity_snapshots=liquidity_snapshots,
        qlib_metrics=qlib_metrics,
        qlib_engine=qlib_engine,
        structure_symbols=set(structure_history),
        trigger_symbols=set(trigger_history),
    )
    _save_report(
        report_path,
        rows,
        report_date,
        csv_path,
        qlib_path,
        backtest,
        industry_signals,
        news_items,
        workflow_audits,
        qlib_metrics,
        qlib_engine,
        bars_by_symbol,
        universe_coverage,
    )

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
    bars_by_symbol = load_csv_ohlcv(config.ohlcv_path, config.symbols)
    min_required = max(30, min(config.lookback, 120))
    missing = [symbol for symbol in config.symbols if len(bars_by_symbol.get(symbol.upper(), [])) < min_required]
    if missing:
        try:
            live_bars = fetch_openbb_ohlcv(missing, config.openbb_provider)
        except Exception:
            live_bars = {}
        for symbol, bars in live_bars.items():
            if len(bars) >= min_required:
                bars_by_symbol[symbol.upper()] = bars
    return bars_by_symbol


def _resolve_candidate_symbols(config: QuantPlatformConfig, stock_snapshot_path: Path | None = None) -> tuple[str, ...]:
    return _resolve_candidate_universe(config, stock_snapshot_path)[0]


def _resolve_candidate_universe(
    config: QuantPlatformConfig,
    stock_snapshot_path: Path | None = None,
) -> tuple[tuple[str, ...], UniverseCoverage]:
    universe_path = config.universe_path or stock_snapshot_path
    if not universe_path or not universe_path.exists():
        return config.symbols, UniverseCoverage(
            total_symbols=len(config.symbols),
            screened_symbols=len(config.symbols),
            deep_analysis_symbols=len(config.symbols),
            source_path=str(universe_path or "config.symbols"),
        )
    total_symbols = _count_universe_symbols(universe_path)
    universe = _load_universe_candidates(universe_path)
    if not universe:
        return config.symbols, UniverseCoverage(
            total_symbols=total_symbols,
            screened_symbols=0,
            deep_analysis_symbols=len(config.symbols),
            source_path=str(universe_path),
        )
    base_symbols = {symbol.upper() for symbol in config.symbols}
    ranked = sorted(universe, key=lambda item: item["score"], reverse=True)
    selected: list[str] = []

    # Keep a few familiar anchors, then fill from the whole API universe by price/liquidity.
    for symbol in config.symbols:
        symbol = symbol.upper()
        if symbol in {item["symbol"] for item in universe} and symbol not in selected:
            selected.append(symbol)
        if len(selected) >= min(12, config.universe_candidate_limit):
            break
    for item in ranked:
        symbol = item["symbol"]
        if symbol not in selected:
            selected.append(symbol)
        if len(selected) >= max(len(base_symbols), config.universe_candidate_limit):
            break
    selected_symbols = tuple(selected)
    return selected_symbols, UniverseCoverage(
        total_symbols=total_symbols,
        screened_symbols=len(universe),
        deep_analysis_symbols=len(selected_symbols),
        source_path=str(universe_path),
    )


def _count_universe_symbols(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return sum(1 for row in csv.DictReader(handle) if str(row.get("symbol", "")).strip())
    except OSError:
        return 0


def _load_universe_candidates(path: Path) -> list[dict[str, float | str]]:
    candidates: list[dict[str, float | str]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = str(row.get("symbol", "")).strip().upper()
                price = _safe_float(row.get("price"))
                volume = _safe_float(row.get("volume"))
                avg_volume = _safe_float(row.get("avg_volume_20d"))
                if not symbol or price <= 0 or max(volume, avg_volume) <= 0:
                    continue
                candidates.append(
                    {
                        "symbol": symbol,
                        "price": price,
                        "score": _universe_candidate_score(price, max(volume, avg_volume)),
                    }
                )
    except OSError:
        return []
    return candidates


def _universe_candidate_score(price: float, volume: float) -> float:
    liquidity = math.log10(max(volume, 1.0))
    if price < 30:
        bucket = 12.0
    elif price <= 100:
        bucket = 10.0
    elif price <= 200:
        bucket = 4.0
    else:
        bucket = 0.0
    return bucket + liquidity


def _safe_float(value) -> float:
    try:
        return float(str(value or "0").replace(",", "").strip())
    except ValueError:
        return 0.0


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
    workflow_audits: dict[str, StockWorkflowAudit],
    qlib_metrics,
    qlib_engine,
    bars_by_symbol: dict[str, list],
    universe_coverage: UniverseCoverage,
) -> None:
    lines = [
        f"# Hybrid Quant 每日股票分析報告 - {report_date.isoformat()}",
        "",
        "## Market Universe Coverage",
        "",
        "| Metric | Count | Description |",
        "|---|---:|---|",
        f"| 全市場掃描數 | {universe_coverage.total_symbols} | 來自 `{_md_cell(universe_coverage.source_path)}` 的 TWSE/TPEx 股票池 |",
        f"| 初篩通過數 | {universe_coverage.screened_symbols} | 已完成價格、成交量與流動性輕量初篩，可進入候選排序 |",
        f"| 深度分析數 | {universe_coverage.deep_analysis_symbols} | 送入 Hybrid / OpenBB / Qlib / Kronos / K線策略的股票數 |",
        "",
        "## Workflow Coverage",
        "",
        "- Kronos：產生每檔股票的預估報酬與信心分數；若本機模型未載入，會以動能模型作為保守備援。",
        "- OpenBB/CSV：作為每日行情資料入口；雲端排程先刷新 TWSE/TPEx 資料，再提供給本報告使用。",
        "- Qlib：由每日 OHLCV 建立本地資料庫，並執行 TopK-Dropout 投組回測，納入週轉率、成本、基準與最大回撤。",
        "- Daily Stock Analysis：沿用 RSS 新聞產業分數、蠟燭圖策略、報告產生與 LINE/webhook 推播流程。",
        "",
        "## Top Ranking",
        "",
        "| Rank | Symbol | Name | Industry | Current | Price Band | Recommend | Hybrid | Kronos | News | Tech | Realtime | Action |",
        "|---:|---|---|---|---:|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for rank, row in enumerate(rows, start=1):
        lines.append(
            f"| {rank} | {row.symbol} | {row.name} | {row.industry} | {row.current_close:.2f} | "
            f"{row.price_bucket} | {row.recommendation_score:.1f} | {row.hybrid_score:.1f} | "
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
        catalyst = signal.catalysts[0] if signal.catalysts else "暫無新的明確催化題材"
        lines.append(f"| {signal.industry} | {signal.score:.1f} | {signal.evidence_count} | {catalyst} |")
    if not industry_signals:
        lines.append("| 市場觀察 | 50.0 | 0 | RSS 暫時無法取得，新聞分數採中性值。 |")

    lines.extend(["", "## Industry Groups", "", "| Industry | Symbols | Average Hybrid | Bias |", "|---|---|---:|---|"])
    for industry, group in _group_rows_by_industry(rows).items():
        symbols = ", ".join(f"{row.symbol} {row.name}" for row in group[:4])
        average = sum(row.hybrid_score for row in group) / len(group)
        lines.append(f"| {industry} | {symbols} | {average:.1f} | {_industry_bias(average)} |")

    lines.extend(["", "## Investment Notes", ""])
    for row in rows[:5]:
        entry, stop, target, take_profit = _strategy_points(row)
        lines.append(
            f"- {row.symbol} {row.name}：現價 {row.current_close:.2f}，"
            f"預估價 {row.predicted_close:.2f}，Hybrid 分數 {row.hybrid_score:.1f}。"
            f"{row.action}。進場 {entry:.2f}，加碼 {target:.2f}，停損 {stop:.2f}，停利 {take_profit:.2f}。"
            f"風險：{row.risk_note}。"
        )
    lines.extend(
        [
            "",
            "## Portfolio Simulation",
            "",
            f"- 投組預估毛報酬：{backtest.gross_expected_return:.2%}",
            f"- 扣除交易成本後預估報酬：{backtest.net_expected_return:.2%}",
            f"- 預估損益：{backtest.estimated_pnl:,.2f}",
            f"- Qlib 即時 IC：{_optional_pct(qlib_metrics.ic)}",
            f"- Qlib 即時 Rank IC：{_optional_pct(qlib_metrics.rank_ic)}",
            f"- Qlib TopK 報酬：{_optional_pct(qlib_metrics.topk_return)}",
            f"- Qlib 樣本數：{qlib_metrics.observations}",
            f"- Qlib engine 是否執行：{'是' if getattr(qlib_engine, 'executed', False) else '否'}",
            f"- Qlib engine 回測期間：{getattr(qlib_engine, 'start_time', None) or '無'} 至 {getattr(qlib_engine, 'end_time', None) or '無'}",
            f"- Qlib engine 投組報酬：{_optional_pct(getattr(qlib_engine, 'portfolio_return', None))}",
            f"- Qlib engine 年化報酬：{_optional_pct(getattr(qlib_engine, 'annualized_return', None))}",
            f"- Qlib engine 基準報酬：{_optional_pct(getattr(qlib_engine, 'benchmark_return', None))}",
            f"- Qlib engine 超額報酬：{_optional_pct(getattr(qlib_engine, 'excess_return', None))}",
            f"- Qlib engine 最大回撤：{_optional_pct(getattr(qlib_engine, 'max_drawdown', None))}",
            f"- Qlib engine 資訊比率：{_optional_number(getattr(qlib_engine, 'information_ratio', None))}",
            f"- Qlib engine 平均週轉率：{_optional_pct(getattr(qlib_engine, 'average_turnover', None))}",
        ]
    )
    if getattr(qlib_engine, "report_path", None):
        lines.append(f"- Qlib engine 明細 CSV：`{qlib_engine.report_path}`")
    if getattr(qlib_engine, "error", None):
        lines.append(f"- Qlib engine 錯誤：{qlib_engine.error}")
    if backtest.benchmark_return is not None:
        lines.append(f"- 基準期間報酬：{backtest.benchmark_return:.2%}")
    lines.extend(
        [
            "",
            "## News Feed",
            "",
        ]
    )
    for item in news_items[:6]:
        industries = ", ".join(item.industries) if item.industries else "市場"
        lines.append(f"- [{industries}] {item.title} ({item.source}, {item.date.isoformat()})")
    if not news_items:
        lines.append("- 本次未取得 RSS 新聞，報告改用快取行情與中性新聞分數。")

    lines.extend(
        [
            "",
            "## OHLCV Chart Data",
            "",
            "| Symbol | Date | Open | High | Low | Close | Volume |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        for bar in bars_by_symbol.get(row.symbol, [])[-90:]:
            lines.append(
                f"| {_md_cell(row.symbol)} | {bar.timestamp.date().isoformat()} | "
                f"{bar.open:.4f} | {bar.high:.4f} | {bar.low:.4f} | {bar.close:.4f} | {bar.volume:.0f} |"
            )

    lines.extend(
        [
            "",
            "## Workflow Coverage Matrix",
            "",
            "| Symbol | Step | Task | Status | Evidence | Missing | Modules |",
            "|---|---:|---|---|---|---|---|",
        ]
    )
    for row in rows:
        audit = workflow_audits.get(row.symbol)
        if not audit:
            continue
        for step in audit.steps:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(row.symbol),
                        str(step.step),
                        _md_cell(step.task),
                        step.status,
                        _md_cell("; ".join(step.evidence) or "-"),
                        _md_cell("; ".join(step.missing) or "-"),
                        _md_cell(", ".join(step.modules)),
                    ]
                )
                + " |"
            )
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
        industry: sorted(group, key=lambda item: item.recommendation_score, reverse=True)
        for industry, group in sorted(
            groups.items(),
            key=lambda item: sum(row.recommendation_score for row in item[1]) / len(item[1]),
            reverse=True,
        )
    }


def _rank_rows_with_price_bias(rows: list[HybridRow], top_n: int) -> list[HybridRow]:
    ranked = sorted(
        rows,
        key=lambda item: (item.recommendation_score, item.hybrid_score, item.kronos_return),
        reverse=True,
    )
    if top_n <= 0:
        return ranked[:MAX_RECOMMENDATION_ROWS]
    high_cap = max(1, top_n // 3)
    selected: list[HybridRow] = []
    deferred_high: list[HybridRow] = []
    for row in ranked:
        if len(selected) >= top_n:
            break
        if _is_high_price(row.current_close) and sum(_is_high_price(item.current_close) for item in selected) >= high_cap:
            deferred_high.append(row)
            continue
        selected.append(row)
    for row in ranked:
        if len(selected) >= top_n:
            break
        if row not in selected:
            selected.append(row)
    return selected[:top_n]


def _effective_report_top_n(top_n: int) -> int:
    if top_n <= 0:
        return MAX_RECOMMENDATION_ROWS
    return min(top_n, MAX_RECOMMENDATION_ROWS)


def _recommendation_score(hybrid_score: float, current_close: float) -> float:
    return max(0.0, min(100.0, hybrid_score + _price_bucket_bonus(current_close)))


def _price_bucket_bonus(current_close: float) -> float:
    if current_close <= 0:
        return 0.0
    if current_close < 30:
        return 9.0
    if current_close <= 100:
        return 6.0
    if current_close <= 200:
        return 1.5
    if current_close <= 500:
        return -2.0
    return -5.0


def _price_bucket(current_close: float) -> str:
    if current_close <= 0:
        return "價格不足"
    if current_close < 30:
        return "低價股"
    if current_close <= 100:
        return "中價股"
    return "高價股"


def _is_high_price(current_close: float) -> bool:
    return current_close > 100


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


def _md_cell(value: str) -> str:
    return str(value).replace("|", "/").replace("\n", " ").strip()


def _optional_pct(value) -> str:
    return "n/a" if value is None else f"{float(value):.2%}"


def _optional_number(value) -> str:
    return "n/a" if value is None else f"{float(value):.4f}"
