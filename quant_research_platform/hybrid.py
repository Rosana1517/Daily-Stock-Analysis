from __future__ import annotations

import html
import csv
import json
from dataclasses import dataclass
from dataclasses import replace
from datetime import date
from pathlib import Path

from quant_research_platform.agent_workflow import (
    AgentDecision,
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
from quant_research_platform.data import Bar, fetch_openbb_ohlcv, fetch_yahoo_ohlcv, load_csv_ohlcv, save_ohlcv_csv
from quant_research_platform.qlib_adapter import (
    build_qlib_signal_backtest_config,
    run_inline_signal_diagnostics,
    run_qlib_engine_portfolio_backtest,
)
from quant_research_platform.signals import build_signals
from quant_research_platform.market_regime_gate import MarketRegimeGate, evaluate_market_regime_gate
from quant_research_platform.universe import (
    build_candidate_selection_plan,
    platform_measured_move_target,
    platform_neckline_price,
)
from stock_signal_system.data.chip_snapshot import load_histock_broker_summaries, load_recent_twse_institutional_days
from stock_signal_system.data.csv_sources import load_intraday_history, load_news
from stock_signal_system.data.foreign_flow_trend import summarize_market_foreign_flow


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
    confidence_score: float
    hybrid_score: float
    current_close: float
    predicted_close: float
    realtime_status: str
    action: str
    risk_note: str
    stop_loss_price: float | None
    take_profit_price: float | None
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
    best_entry: bool = False


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
    regime_gate = evaluate_market_regime_gate(Path(".cache"))
    if regime_gate.available:
        print(
            f"market_regime_gate bullish={regime_gate.bullish} taiex_close={regime_gate.close:.1f}"
            f" ma20={regime_gate.ma20:.1f} distance_pct={regime_gate.distance_pct:.2f}",
            flush=True,
        )
    else:
        print("warning: market_regime_gate_unavailable=defaulting_bullish", flush=True)
    selection_plan = build_candidate_selection_plan(
        config.universe_path,
        config.symbols,
        config.universe_candidate_limit,
        news_path,
        config.ohlcv_path,
        regime_gate.bullish,
    )
    analysis_symbols = selection_plan.analysis_symbols or selection_plan.selected_symbols
    config = replace(config, symbols=analysis_symbols)
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
        chip_score = _chip_score(chip_snapshot)
        hybrid_score = (
            kronos_score * 0.35
            + news_score * 0.15
            + technical_score * 0.20
            + realtime_score * 0.10
            + signal.confidence * 100 * 0.10
            + chip_score * 0.10
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
            new_strategy_hit=symbol in revised_symbols,
            chip_radar_hit=symbol in chip_radar_symbols,
            signal_source=signal.source,
            kronos_return=signal.expected_return,
            kronos_score=kronos_score,
            news_score=news_score,
            technical_score=technical_score,
            realtime_score=realtime_score,
            confidence_score=signal.confidence * 100.0,
            hybrid_score=hybrid_score,
            current_close=signal.current_close,
            predicted_close=signal.predicted_close,
            realtime_status=realtime.status if realtime else "無即時資料",
            action=_action(hybrid_score, signal.expected_return, intraday_return),
            risk_note=_risk_note(signal.expected_return, tech.bias if tech else "neutral", intraday_return),
            stop_loss_price=platform_neckline_price(bars_by_symbol.get(symbol, [])),
            take_profit_price=platform_measured_move_target(bars_by_symbol.get(symbol, [])),
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
            best_entry=_is_best_entry(bars_by_symbol.get(symbol, [])),
        )
    report_symbols = []
    for symbol in (*analysis_symbols, *selection_plan.selected_symbols):
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
            not item.best_entry,
            not item.new_strategy_hit,
            not item.chip_radar_hit,
            not item.legacy_hit,
            -item.hybrid_score,
            rank_map.get(item.symbol, 9999),
        ),
    )
    chip_snapshot_by_symbol = _enrich_report_chip_snapshots(
        rows,
        chip_snapshot_by_symbol,
        bars_by_symbol,
        report_date,
        cache_dir=Path(".cache"),
        enrich_limit=24,
    )
    rows_by_symbol = _apply_chip_snapshot_enrichment(rows_by_symbol, chip_snapshot_by_symbol)
    rows = sorted(
        rows_by_symbol.values(),
        key=lambda item: (
            not item.best_entry,
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
    analyzed_rows = [row for row in rows if row.signal_source != "data-limited"]
    agent_workflow = run_five_agent_workflow(analyzed_rows)
    portfolio_decisions = portfolio_decision_map(agent_workflow)
    for row in rows:
        if row.symbol not in portfolio_decisions:
            portfolio_decisions[row.symbol] = _data_insufficient_decision(row)
    report_rows = _apply_sector_diversification(_portfolio_rows(rows, portfolio_decisions, "include"))

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
    recommendation_summary = _track_recommendations(rows, portfolio_decisions, report_date)
    _save_report(
        report_path,
        rows,
        report_date,
        csv_path,
        qlib_path,
        backtest,
        industry_signals,
        news_items,
        portfolio_decisions,
        bars_by_symbol,
        qlib_metrics,
        qlib_engine,
        config,
        chip_snapshot_by_symbol,
        recommendation_summary,
        regime_gate,
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
    bars_by_symbol = load_csv_ohlcv(config.ohlcv_path, config.symbols)
    required_bars = max(60, int(config.lookback or 0))
    missing_symbols = tuple(
        symbol
        for symbol in config.symbols
        if len(bars_by_symbol.get(symbol, [])) < required_bars
    )
    if not missing_symbols:
        return bars_by_symbol

    fetched = fetch_yahoo_ohlcv(missing_symbols, "1y")
    refreshed = False
    for symbol in missing_symbols:
        fallback_bars = fetched.get(symbol, [])
        if len(fallback_bars) >= required_bars:
            bars_by_symbol[symbol] = fallback_bars
            refreshed = True
    if refreshed:
        existing_all = load_csv_ohlcv(config.ohlcv_path) if config.ohlcv_path.exists() else {}
        existing_all.update(bars_by_symbol)
        save_ohlcv_csv(config.ohlcv_path, existing_all)
    return bars_by_symbol


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


def _enrich_report_chip_snapshots(
    rows: list[HybridRow],
    chip_snapshot_by_symbol: dict[str, dict],
    bars_by_symbol: dict[str, list[Bar]],
    report_date: date,
    *,
    cache_dir: Path,
    enrich_limit: int = 24,
) -> dict[str, dict]:
    missing_symbols: list[str] = []
    for row in rows[:enrich_limit]:
        snapshot = chip_snapshot_by_symbol.get(row.symbol, {})
        if _has_real_broker_snapshot(snapshot):
            continue
        if row.symbol not in missing_symbols:
            missing_symbols.append(row.symbol)
    if not missing_symbols:
        return chip_snapshot_by_symbol

    latest_volume_by_symbol: dict[str, int] = {}
    for row in rows[:enrich_limit]:
        if row.symbol not in missing_symbols:
            continue
        bars = bars_by_symbol.get(row.symbol, [])
        latest_volume_by_symbol[row.symbol] = int(bars[-1].volume) if bars else 0

    try:
        twse_days = load_recent_twse_institutional_days(cache_dir, as_of=report_date, lookback_sessions=3)
        if not twse_days:
            return chip_snapshot_by_symbol
        broker_summaries = load_histock_broker_summaries(
            cache_dir,
            twse_days,
            tuple(missing_symbols),
            latest_volume_by_symbol,
            broker_lookback_sessions=min(3, len(twse_days)),
        )
    except Exception:
        return chip_snapshot_by_symbol

    for symbol, summary in broker_summaries.items():
        full_symbol = f"{symbol}.TW"
        merged_snapshot = {
            **chip_snapshot_by_symbol.get(full_symbol, chip_snapshot_by_symbol.get(symbol, {})),
            "top10_main_force_buy_strength": f"{summary.top10_main_force_buy_strength:.1f}",
            "top10_main_force_net_buy": str(summary.top10_main_force_net_buy),
            "branch_main_force_buy_streak_days": str(summary.branch_main_force_buy_streak_days),
            "branch_main_force_leader": summary.branch_main_force_leader,
            "chip_data_date": summary.chip_data_date,
            "chip_data_source": summary.chip_data_source,
            "chip_data_source_status": summary.chip_data_source_status,
            "top10_main_force_brokers": summary.top10_main_force_brokers,
        }
        chip_snapshot_by_symbol[full_symbol] = merged_snapshot
        chip_snapshot_by_symbol[symbol] = merged_snapshot
    return chip_snapshot_by_symbol


def _has_real_broker_snapshot(snapshot: dict) -> bool:
    status = str(snapshot.get("chip_data_source_status", "")).strip().lower()
    return status.startswith("official+broker") and any(
        str(snapshot.get(key, "")).strip()
        for key in ("top10_main_force_net_buy", "branch_main_force_buy_streak_days", "branch_main_force_leader")
    )


def _apply_chip_snapshot_enrichment(
    rows_by_symbol: dict[str, HybridRow],
    chip_snapshot_by_symbol: dict[str, dict],
) -> dict[str, HybridRow]:
    enriched: dict[str, HybridRow] = {}
    for symbol, row in rows_by_symbol.items():
        snapshot = chip_snapshot_by_symbol.get(symbol)
        if not snapshot or not _has_real_broker_snapshot(snapshot):
            enriched[symbol] = row
            continue
        enriched[symbol] = replace(
            row,
            top10_main_force_buy_strength=_optional_float(snapshot, "top10_main_force_buy_strength", "top10_main_force_buy_strength_proxy"),
            top10_main_force_net_buy=_optional_float(snapshot, "top10_main_force_net_buy"),
            branch_main_force_buy_streak_days=_optional_float(snapshot, "branch_main_force_buy_streak_days"),
            branch_main_force_leader=str(snapshot.get("branch_main_force_leader", "")).strip(),
            chip_data_date=str(snapshot.get("chip_data_date", "")).strip(),
            chip_data_source=str(snapshot.get("chip_data_source", "")).strip(),
            chip_data_source_status=str(snapshot.get("chip_data_source_status", "")).strip(),
            top10_main_force_brokers=str(snapshot.get("top10_main_force_brokers", "")).strip(),
        )
    return enriched


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


def _chip_score(chip_snapshot: dict) -> float:
    """Blend top10 main-force buy strength with foreign/branch buy streaks
    into a 0-100 score so real capital flow moves hybrid_score, not just the
    screening bucket. Missing chip data stays neutral (50) rather than
    penalizing stocks that simply lack broker-level data."""
    strength = _optional_float(chip_snapshot, "top10_main_force_buy_strength", "top10_main_force_buy_strength_proxy")
    if strength is None:
        return 50.0
    foreign_streak = _optional_float(chip_snapshot, "foreign_buy_streak_days") or 0.0
    branch_streak = _optional_float(chip_snapshot, "branch_main_force_buy_streak_days") or 0.0
    streak_bonus = min(foreign_streak, 5.0) * 3.0 + min(branch_streak, 5.0) * 2.0
    return max(0.0, min(100.0, strength + streak_bonus))


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


RECOMMENDATION_LOG_PATH = Path("reports/recommendation_log.csv")
PRICE_SNAPSHOT_DIR = Path("reports/price_snapshots")


def _track_recommendations(
    rows: list[HybridRow],
    portfolio_decisions: dict,
    report_date: date,
):
    """Log today's top picks and close the loop on past ones (win-rate tracking)."""
    try:
        from stock_signal_system.recommendation_tracker import (
            append_recommendations,
            evaluate_pending,
            summarize,
        )
        from stock_signal_system.weight_diagnostics import SCORE_SNAPSHOT_PATH, append_score_snapshot

        candidates = [row for row in rows if row.signal_source != "data-limited" and row.current_close > 0]
        picks: list[dict[str, object]] = []
        picked_rows: list[HybridRow] = []
        seen: set[str] = set()
        for row in candidates:
            is_focus = portfolio_decision_bucket(portfolio_decisions.get(row.symbol)) == "include"
            if row.screening_bucket == "chip_confirmed" or is_focus:
                if row.symbol not in seen:
                    picks.append(_recommendation_payload(row))
                    picked_rows.append(row)
                    seen.add(row.symbol)
        for row in candidates[:5]:
            if row.symbol not in seen:
                picks.append(_recommendation_payload(row))
                picked_rows.append(row)
                seen.add(row.symbol)
        added = append_recommendations(RECOMMENDATION_LOG_PATH, report_date, picks)
        if added:
            for row in picked_rows:
                append_score_snapshot(
                    SCORE_SNAPSHOT_PATH,
                    report_date.isoformat(),
                    row.symbol,
                    {
                        "kronos_score": row.kronos_score,
                        "news_score": row.news_score,
                        "technical_score": row.technical_score,
                        "realtime_score": row.realtime_score,
                        "confidence_score": row.confidence_score,
                        "chip_score": _chip_score(
                            {
                                "top10_main_force_buy_strength": row.top10_main_force_buy_strength,
                                "foreign_buy_streak_days": row.foreign_buy_streak_days,
                                "branch_main_force_buy_streak_days": row.branch_main_force_buy_streak_days,
                            }
                        ),
                    },
                )
        evaluated = evaluate_pending(RECOMMENDATION_LOG_PATH, PRICE_SNAPSHOT_DIR, report_date)
        print(f"recommendation_log added={added} evaluated={evaluated}", flush=True)
        return summarize(RECOMMENDATION_LOG_PATH)
    except Exception as exc:
        print(f"warning: recommendation_tracking_failed={exc}", flush=True)
        return None


def _recommendation_payload(row: HybridRow) -> dict[str, object]:
    return {
        "symbol": row.symbol,
        "name": row.name,
        "bucket": row.screening_bucket,
        "entry_close": row.current_close,
        "stop_loss_price": row.stop_loss_price,
        "take_profit_price": row.take_profit_price,
    }


def _weight_diagnostics_section() -> list[str]:
    lines = ["", "## hybrid_score 權重診斷", ""]
    try:
        from stock_signal_system.weight_diagnostics import SCORE_SNAPSHOT_PATH, evaluate_weight_diagnostics

        result = evaluate_weight_diagnostics(RECOMMENDATION_LOG_PATH, SCORE_SNAPSHOT_PATH)
    except Exception as exc:
        lines.append(f"- 權重診斷暫時無法執行：{exc}")
        return lines
    lines.append(f"- {result.note}")
    if not result.sufficient:
        return lines
    lines.extend(
        [
            "",
            '<div class="table-wrap"><table>',
            "<thead><tr><th>分數分量</th><th>目前權重</th><th>與 5 日報酬相關係數</th></tr></thead>",
            "<tbody>",
        ]
    )
    for item in result.correlations:
        corr_text = f"{item.correlation:.3f}" if item.correlation is not None else "n/a"
        lines.append(f"<tr><td>{html.escape(item.component)}</td><td>{item.current_weight:.0%}</td><td>{corr_text}</td></tr>")
    lines.extend(["</tbody>", "</table></div>", '<p class="section-note">相關係數僅供參考，權重調整需人工確認後才會套用到生產設定。</p>'])
    return lines


def _recommendation_section(summary) -> list[str]:
    lines = ["", "## 推薦追蹤（勝率閉環）", ""]
    if summary is None:
        lines.append("- 推薦追蹤資料尚未建立。")
        return lines
    lines.append(f"- 已評估推薦數（動態出場，最長持有 5 個交易日）：{summary.evaluated_count}，待評估：{summary.pending_count}")
    if summary.win_rate is not None:
        lines.append(f"- 勝率（出場價 > 進場價）：{summary.win_rate:.1%}")
        lines.append(f"- 平均實現報酬：{summary.average_return_5d:.2%}")
        lines.append(f"- 平均持有期最大報酬：{summary.average_max_return_5d:.2%}")
        lines.append(
            f"- 出場分布：停損 {summary.stop_loss_exit_count} 檔、停利 {summary.take_profit_exit_count} 檔、"
            f"到期收盤 {summary.horizon_exit_count} 檔"
        )
    else:
        lines.append("- 尚無已完成評估的推薦（需累積至少 5 個交易日的價格快照）。")
    if summary.recent_evaluated:
        lines.extend(
            [
                "",
                '<div class="table-wrap"><table>',
                "<thead><tr><th>進場日</th><th>股票</th><th>來源池</th><th>進場價</th><th>出場日</th><th>出場原因</th><th>實現報酬</th><th>最大報酬</th><th>結果</th></tr></thead>",
                "<tbody>",
            ]
        )
        exit_labels = {"stop_loss": "停損出場", "take_profit": "停利出場", "horizon_close": "到期收盤", "unresolved": "資料缺漏"}
        for row in summary.recent_evaluated:
            result = "✅ 勝" if row.get("win") == "1" else "❌ 敗" if row.get("win") == "0" else "n/a"
            ret = row.get("return_5d", "")
            max_ret = row.get("max_return_5d", "")
            ret_text = f"{float(ret):.2%}" if ret else "n/a"
            max_text = f"{float(max_ret):.2%}" if max_ret else "n/a"
            exit_reason = exit_labels.get(row.get("exit_reason", ""), "n/a")
            lines.append(
                f"<tr><td>{html.escape(row.get('entry_date', ''))}</td><td>{html.escape(row.get('symbol', ''))} {html.escape(row.get('name', ''))}</td>"
                f"<td>{html.escape(row.get('bucket', ''))}</td><td>{html.escape(row.get('entry_close', ''))}</td>"
                f"<td>{html.escape(row.get('eval_date', ''))}</td><td>{exit_reason}</td>"
                f"<td>{ret_text}</td><td>{max_text}</td><td>{result}</td></tr>"
            )
        lines.extend(["</tbody>", "</table></div>"])
    return lines


def _foreign_flow_section(report_date: date, cache_dir: Path = Path(".cache")) -> list[str]:
    """外資動向 report block: last ~10 sessions of market-wide foreign net
    buy/sell aggregated from cached TWSE T86 data. Degrades to a placeholder
    line instead of failing the whole report when data is unavailable."""
    try:
        days = load_recent_twse_institutional_days(cache_dir, as_of=report_date, lookback_sessions=10)
        trend = summarize_market_foreign_flow(days)
    except Exception as exc:
        print(f"warning: foreign_flow_trend_failed={exc}", flush=True)
        trend = None
    lines = ["## 外資動向", ""]
    if trend is None:
        lines.extend(["- 外資資料暫缺，今日無法判讀外資動向。", ""])
        return lines
    streak_text = (
        f"連續買超 {trend.streak_days} 天"
        if trend.streak_days > 0
        else f"連續賣超 {abs(trend.streak_days)} 天" if trend.streak_days < 0 else "今日買賣超接近平衡"
    )
    lines.append(
        f"- 判讀：**{trend.bias}**（{streak_text}，近 {len(trend.daily_net_lots)} 個交易日累計 {trend.cumulative_net_lots:+,.0f} 張）"
    )
    lines.append("")
    lines.append('<div class="table-wrap"><table><thead><tr><th>日期</th><th>外資買賣超（張）</th></tr></thead><tbody>')
    for trade_date, net_lots in trend.daily_net_lots:
        color = "#dc2626" if net_lots > 0 else "#16a34a" if net_lots < 0 else "#475569"
        lines.append(
            f'<tr><td>{trade_date.isoformat()}</td><td style="color:{color};font-weight:700;">{net_lots:+,.0f}</td></tr>'
        )
    lines.append("</tbody></table></div>")
    lines.append('<p class="section-note">資料來源：TWSE T86 三大法人個股買賣超彙總（股數換算為張），僅含上市普通股。</p>')
    lines.append("")
    return lines


def _market_regime_line(regime_gate: MarketRegimeGate | None) -> str:
    if regime_gate is None or not regime_gate.available:
        return '<p class="section-note">大盤濾網：資料暫缺，本日突破類訊號未受篩選限制。</p>'
    if regime_gate.bullish:
        return (
            f'<p class="section-note">大盤濾網：加權指數 {regime_gate.close:,.0f} 站上 20 日均線'
            f'（{regime_gate.ma20:,.0f}，+{regime_gate.distance_pct:.1f}%），純技術突破訊號正常放行。</p>'
        )
    return (
        f'<p class="section-note">大盤濾網：加權指數 {regime_gate.close:,.0f} 跌破 20 日均線'
        f'（{regime_gate.ma20:,.0f}，{regime_gate.distance_pct:.1f}%），本日已停用「純技術突破」候選池'
        "（發動確認策略），避免逆勢追突破；有籌碼認養佐證的突破股不受影響。</p>"
    )


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
    chip_snapshot_by_symbol: dict[str, dict],
    recommendation_summary=None,
    regime_gate: MarketRegimeGate | None = None,
) -> None:
    portfolio_decisions = agent_workflow
    focus_rows = _portfolio_rows(rows, portfolio_decisions, "include")
    data_limited_rows = [row for row in rows if row.signal_source == "data-limited"]
    priority_rows = [row for row in rows if row.signal_source != "data-limited"] or rows
    priority_groups = _screening_priority_groups(priority_rows)
    focus_rows = _overall_focus_rows(priority_rows)

    priority_rows_html = []
    for group in priority_groups:
        priority_rows_html.append(
            "<tr>"
            f"<td>{group['priority']}</td>"
            f"<td>{html.escape(str(group['label']))}</td>"
            f"<td>{group['count']}</td>"
            f"<td>{html.escape(str(group['meaning']))}</td>"
            f"<td>{html.escape(str(group['action']))}</td>"
            f"<td>{html.escape(str(group['samples']))}</td>"
            "</tr>"
        )
    if not priority_rows_html:
        priority_rows_html.append(
            "<tr><td>-</td><td>尚無符合群組</td><td>0</td><td>目前沒有可分類的候選</td><td>等待下一次資料更新</td><td>n/a</td></tr>"
        )

    rss_cards_html = []
    if industry_signals:
        for signal in industry_signals[:8]:
            catalyst = signal.catalysts[0] if signal.catalysts else "暫無明確催化"
            rss_cards_html.append(
                f'<article class="rss-signal-card"><h3>{html.escape(signal.industry)}</h3><p class="rss-score">RSS {signal.score:.1f}</p><p>證據 {signal.evidence_count} 則</p><p>{html.escape(catalyst)}</p></article>'
            )
    else:
        rss_cards_html.append('<article class="rss-signal-card"><h3>RSS 訊號暫缺</h3><p class="rss-score">RSS 50.0</p><p>今日未取得有效產業訊號</p></article>')

    data_limited_html = []
    if data_limited_rows:
        for row in data_limited_rows[:12]:
            data_limited_html.append(
                f"<li>{html.escape(row.symbol)} {html.escape(row.name)}: 缺少完整 OHLCV / 技術資料，已保留在報表並標示為資料待補。</li>"
            )
    else:
        data_limited_html.append("<li>目前沒有資料待補股票。</li>")

    lines = [
        f"# Hybrid \u53f0\u80a1\u6bcf\u65e5\u5206\u6790\u5831\u544a - {report_date.isoformat()}",
        "",
        _market_regime_line(regime_gate),
        "",
        '<section class="report-card">',
        "<h2>選股優先順序表</h2>",
        '<div class="table-wrap"><table><thead><tr><th>優先級</th><th>組合</th><th>數量</th><th>風格判讀</th><th>建議動作</th><th>代表股票</th></tr></thead><tbody>',
        "".join(priority_rows_html),
        "</tbody></table></div>",
        '<p class="section-note">優先順序：<code>★最佳買點</code> &gt; <code>三者全中</code> &gt; <code>品質底池 + 主力動向</code> &gt; <code>品質底池 + 發動確認</code> &gt; <code>主力動向 + 發動確認</code> &gt; <code>單策略命中</code>。</p>',
        "</section>",
        '<div id="tech-section-marker"></div>',
        *_foreign_flow_section(report_date),
        "## \u0052\u0053\u0053 \u7522\u696d\u8a0a\u865f",
        "",
        '<div class="rss-signal-grid">',
        "".join(rss_cards_html),
        "</div>",
        "",
        "## \u8cc7\u6599\u5f85\u88dc\u6e05\u55ae",
        "",
        "<ul>",
        "".join(data_limited_html),
        "</ul>",
        "",
        "## \u6295\u7d44\u6a21\u64ec",
        "",
        f"- \u7c97\u4f30\u5831\u916c\u7387\uff1a{backtest.gross_expected_return:.2%}",
        f"- \u6263\u6210\u672c\u5f8c\u5831\u916c\u7387\uff1a{backtest.net_expected_return:.2%}",
        f"- \u9810\u4f30\u640d\u76ca\uff1a{backtest.estimated_pnl:,.2f}",
        "",
        "## \u53ef\u91cd\u7b97\u9a57\u8b49\u6307\u6a19",
        "",
        f"- \u9a57\u8b49\u6a23\u672c\u6578\uff1a{getattr(getattr(backtest, 'validation', None), 'sample_count', 0)}",
        f"- \u52dd\u7387\uff1a{_format_rate(getattr(getattr(backtest, 'validation', None), 'win_rate', None))}",
        f"- False positive rate\uff1a{_format_rate(getattr(getattr(backtest, 'validation', None), 'false_positive_rate', None))}",
        f"- \u5e73\u5747\u5be6\u73fe\u5831\u916c\uff1a{_format_rate(getattr(getattr(backtest, 'validation', None), 'average_realized_return', None))}",
    ]
    if backtest.benchmark_return is not None:
        lines.append(f"- \u57fa\u6e96\u5831\u916c\uff1a{backtest.benchmark_return:.2%}")
    lines.extend([
        "",
        "## \u65b0\u805e\u5feb\u8a0a",
        "",
    ])
    for item in news_items[:6]:
        industries = ", ".join(item.industries) if item.industries else "\u7d9c\u5408"
        lines.append(f"- [{industries}] {item.title}?{item.source}, {item.date.isoformat()}?")
    if not news_items:
        lines.append("- \u4eca\u65e5\u6c92\u6709\u53ef\u4f75\u5165\u5831\u544a\u7684 RSS \u65b0\u805e\u3002")
    lines.extend(_recommendation_section(recommendation_summary))
    lines.extend(_weight_diagnostics_section())
    lines.extend(_candidate_analysis_block(rows, portfolio_decisions, chip_snapshot_by_symbol))
    lines.extend(["", "```technical-chart-data", json.dumps(_technical_chart_payload(rows, bars_by_symbol, portfolio_decisions, focus_rows), ensure_ascii=False, separators=(",", ":")), "```"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _data_insufficient_decision(row: HybridRow) -> AgentDecision:
    return AgentDecision(
        agent="Portfolio_Manager_Agent",
        symbol=row.symbol,
        score=0.0,
        stance="exclude_data_insufficient",
        evidence=("data_insufficient=true", f"signal_source={row.signal_source}"),
        veto=False,
    )

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


MAX_PICKS_PER_INDUSTRY = 2


def _apply_sector_diversification(rows: list[HybridRow], max_per_industry: int = MAX_PICKS_PER_INDUSTRY) -> list[HybridRow]:
    """Cap how many picks from the same industry can appear in the final
    recommendation set (CSV export + LINE notification), so a single hot
    sector rotation can't fill every slot with correlated risk. Rows arrive
    pre-sorted by priority/score; ties within an industry are broken by that
    existing order, so the strongest picks per sector survive the cap."""
    if max_per_industry <= 0:
        return rows
    counts: dict[str, int] = {}
    kept: list[HybridRow] = []
    dropped = 0
    for row in rows:
        industry = row.industry or "未分類"
        count = counts.get(industry, 0)
        if count >= max_per_industry:
            dropped += 1
            continue
        counts[industry] = count + 1
        kept.append(row)
    if dropped:
        print(f"sector_diversification_capped dropped={dropped} max_per_industry={max_per_industry}", flush=True)
    return kept


def _screening_priority_groups(rows: list[HybridRow]) -> list[dict[str, object]]:
    buckets = (
        (
            1,
            "三者全中",
            "績優且安全的主清單",
            "主清單優先",
            lambda row: row.legacy_hit and row.new_strategy_hit and row.chip_radar_hit,
        ),
        (
            2,
            "品質底池 + 主力動向",
            "穩健型上漲潛力",
            "次主清單 / 持續觀察",
            lambda row: row.legacy_hit and row.chip_radar_hit,
        ),
        (
            3,
            "品質底池 + 發動確認",
            "技術確認型",
            "可觀察 / 等籌碼補強",
            lambda row: row.legacy_hit and row.new_strategy_hit,
        ),
        (
            4,
            "主力動向 + 發動確認",
            "進攻型發動股",
            "關注發動延續",
            lambda row: row.new_strategy_hit and row.chip_radar_hit,
        ),
        (
            5,
            "單品質底池",
            "只有品質底",
            "觀察名單",
            lambda row: row.legacy_hit and not row.new_strategy_hit and not row.chip_radar_hit,
        ),
        (
            5,
            "單發動確認",
            "只有發動確認",
            "只留觀察",
            lambda row: row.new_strategy_hit and not row.legacy_hit and not row.chip_radar_hit,
        ),
        (
            5,
            "單主力動向",
            "只有主力支持",
            "等待發動確認",
            lambda row: row.chip_radar_hit and not row.legacy_hit and not row.new_strategy_hit,
        ),
    )
    groups: list[dict[str, object]] = []
    for priority, label, meaning, action, predicate in buckets:
        members = [row for row in rows if predicate(row)]
        members.sort(
            key=lambda row: (
                row.hybrid_score,
                row.technical_score,
                row.top10_main_force_buy_strength or 0.0,
                row.top10_main_force_net_buy or 0.0,
            ),
            reverse=True,
        )
        groups.append(
            {
                "priority": priority,
                "label": label,
                "count": len(members),
                "meaning": meaning,
                "action": action,
                "samples": _priority_samples(members),
            }
        )
    return groups


def _priority_samples(rows: list[HybridRow], limit: int = 4) -> str:
    samples = [f"{row.symbol} {row.name}" for row in rows[:limit]]
    if not samples:
        return "n/a"
    if len(rows) > limit:
        samples.append("等")
    return "、".join(samples)


def _candidate_analysis_block(
    rows: list[HybridRow],
    portfolio_decisions: dict[str, AgentDecision],
    chip_snapshot_by_symbol: dict[str, dict[str, object]],
) -> list[str]:
    lines = [
        '<details class="candidate-panel">',
        '<summary>候選股票分析</summary>',
        '<div class="table-wrap"><table>',
        '<thead><tr><th>股票</th><th>名稱</th><th>產業</th><th>Hybrid</th><th>品質底池</th><th>發動確認</th><th>主力動向</th><th>停損參考(頸線)</th><th>停利參考(量測目標)</th><th>前十大主力強度</th><th>前十大主力淨買超</th><th>外資連買</th><th>主分點連買</th><th>主分點</th><th>籌碼日期</th><th>籌碼狀態</th><th>組合決策</th><th>風險註記</th></tr></thead>',
        '<tbody>',
    ]
    for row in rows:
        decision = portfolio_decisions.get(row.symbol)
        snapshot = chip_snapshot_by_symbol.get(row.symbol, {})
        top10_main_force_buy_strength = _optional_float(snapshot, "top10_main_force_buy_strength", "top10_main_force_buy_strength_proxy")
        top10_main_force_net_buy = _optional_float(snapshot, "top10_main_force_net_buy")
        foreign_buy_streak_days = _optional_float(snapshot, "foreign_buy_streak_days")
        branch_main_force_buy_streak_days = _optional_float(snapshot, "branch_main_force_buy_streak_days")
        branch_main_force_leader = str(snapshot.get("branch_main_force_leader", "")).strip() or row.branch_main_force_leader
        chip_data_date = str(snapshot.get("chip_data_date", "")).strip() or row.chip_data_date
        chip_data_source_status = str(snapshot.get("chip_data_source_status", "")).strip() or row.chip_data_source_status
        legacy_label = "\u662f" if row.legacy_hit else "\u5426"
        new_label = "\u662f" if row.new_strategy_hit else "\u5426"
        chip_label = "\u662f" if row.chip_radar_hit else "\u5426"
        lines.append(
            f"<tr><td>{html.escape(row.symbol)}</td><td>{html.escape(row.name)}</td><td>{html.escape(row.industry)}</td><td>{row.hybrid_score:.1f}</td><td>{legacy_label}</td><td>{new_label}</td><td>{chip_label}</td><td>{_stop_loss_cell(row)}</td><td>{_take_profit_cell(row)}</td><td>{_chip_value(top10_main_force_buy_strength)}</td><td>{_chip_value(top10_main_force_net_buy, digits=0)}</td><td>{_chip_value(foreign_buy_streak_days, digits=0)}</td><td>{_chip_value(branch_main_force_buy_streak_days, digits=0)}</td><td>{html.escape(branch_main_force_leader or 'n/a')}</td><td>{html.escape(chip_data_date or 'n/a')}</td><td>{html.escape(chip_data_source_status or 'n/a')}</td><td>{html.escape(portfolio_decision_label(decision))}</td><td>{html.escape(row.risk_note)}</td></tr>"
        )
    lines.extend(['</tbody>', '</table></div>', '</details>'])
    return lines


def _overall_focus_rows(rows: list[HybridRow], limit: int = 20) -> list[HybridRow]:
    ranked = sorted(
        rows,
        key=lambda row: (
            _overall_focus_priority(row),
            -(row.hybrid_score or 0.0),
            -(row.technical_score or 0.0),
            -float(row.top10_main_force_buy_strength or 0.0),
            -float(row.top10_main_force_net_buy or 0.0),
        ),
    )
    return ranked[:limit]


def _overall_focus_priority(row: HybridRow) -> int:
    if row.best_entry:
        return 0
    if row.legacy_hit and row.new_strategy_hit and row.chip_radar_hit:
        return 1
    if row.legacy_hit and row.chip_radar_hit and not row.new_strategy_hit:
        return 2
    if row.legacy_hit and row.new_strategy_hit and not row.chip_radar_hit:
        return 3
    if row.new_strategy_hit and row.chip_radar_hit and not row.legacy_hit:
        return 4
    if row.new_strategy_hit and not row.legacy_hit and not row.chip_radar_hit:
        return 5
    if row.chip_radar_hit and not row.legacy_hit and not row.new_strategy_hit:
        return 6
    if row.legacy_hit and not row.new_strategy_hit and not row.chip_radar_hit:
        return 7
    return 8


def _overall_focus_label(row: HybridRow) -> str:
    if row.best_entry:
        return '★最佳買點'
    if row.legacy_hit and row.new_strategy_hit and row.chip_radar_hit:
        return '三者全中'
    if row.legacy_hit and row.chip_radar_hit and not row.new_strategy_hit:
        return '品質底池 + 主力動向'
    if row.legacy_hit and row.new_strategy_hit and not row.chip_radar_hit:
        return '品質底池 + 發動確認'
    if row.new_strategy_hit and row.chip_radar_hit and not row.legacy_hit:
        return '主力動向 + 發動確認'
    if row.new_strategy_hit and not row.legacy_hit and not row.chip_radar_hit:
        return '單獨命中發動確認'
    if row.chip_radar_hit and not row.legacy_hit and not row.new_strategy_hit:
        return '單獨命中主力動向'
    if row.legacy_hit and not row.new_strategy_hit and not row.chip_radar_hit:
        return '單獨命中品質底池'
    return '未命中'


def _overall_focus_reason(row: HybridRow) -> str:
    if row.best_entry:
        return '收盤站上 60MA 且 MACD 剛形成黃金交叉'
    if row.legacy_hit and row.new_strategy_hit and row.chip_radar_hit:
        return '品質、籌碼、發動點三者都成立'
    if row.legacy_hit and row.chip_radar_hit and not row.new_strategy_hit:
        return '有基本品質，也有主力照顧，但發動未必完整'
    if row.legacy_hit and row.new_strategy_hit and not row.chip_radar_hit:
        return '有品質，也有技術發動，但籌碼支持不一定強'
    if row.new_strategy_hit and row.chip_radar_hit and not row.legacy_hit:
        return '有籌碼與發動，但品質底未必最完整'
    if row.new_strategy_hit and not row.legacy_hit and not row.chip_radar_hit:
        return '只有發動條件，不一定有籌碼與品質底'
    if row.chip_radar_hit and not row.legacy_hit and not row.new_strategy_hit:
        return '有主力照顧，但尚未確認發動'
    if row.legacy_hit and not row.new_strategy_hit and not row.chip_radar_hit:
        return '只有品質底，但尚未看到籌碼或發動'
    return '暫不列入綜合關注'


def _overall_focus_action(row: HybridRow) -> str:
    if row.best_entry:
        return '最佳買點，第一優先'
    if row.legacy_hit and row.new_strategy_hit and row.chip_radar_hit:
        return '主清單，優先看'
    if row.legacy_hit and row.chip_radar_hit and not row.new_strategy_hit:
        return '次主清單，持續觀察'
    if row.legacy_hit and row.new_strategy_hit and not row.chip_radar_hit:
        return '可看，但風險高於第 2 類'
    if row.new_strategy_hit and row.chip_radar_hit and not row.legacy_hit:
        return '當機會股，不當第一順位'
    if row.new_strategy_hit and not row.legacy_hit and not row.chip_radar_hit:
        return '只留觀察，不列主清單'
    if row.chip_radar_hit and not row.legacy_hit and not row.new_strategy_hit:
        return '先觀察，等發動確認'
    if row.legacy_hit and not row.new_strategy_hit and not row.chip_radar_hit:
        return '放觀察名單'
    return '暫不納入'


def _overall_focus_scroll_item(rank: int, row: HybridRow) -> str:
    top10_strength = row.top10_main_force_buy_strength or 0.0
    net_buy = row.top10_main_force_net_buy or 0.0
    label = _overall_focus_label(row)
    reason = _overall_focus_reason(row)
    action = _overall_focus_action(row)
    return (
        '<div style="display:flex; gap:10px; align-items:flex-start; padding:10px 8px; border-bottom:1px solid #e6edf5;">'
        f'<div style="min-width:34px; height:34px; border-radius:999px; background:#0f766e; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:13px;">{rank}</div>'
        '<div style="flex:1; min-width:0;">'
        f'<div style="font-weight:800; color:#0f172a; margin-bottom:4px;">{html.escape(row.symbol)} {html.escape(row.name)} <span style="color:#0f766e;">{html.escape(label)}</span></div>'
        f'<div style="color:#475569; font-size:12px; line-height:1.45;">{html.escape(reason)} · {html.escape(action)}</div>'
        f'<div style="color:#64748b; font-size:11px; margin-top:4px;">Hybrid {row.hybrid_score:.1f} / 技術 {row.technical_score:.1f} / 前十大主力強度 {_chip_value(top10_strength)} / 前十大主力淨買超 {_chip_value(net_buy, digits=0)}</div>'
        '</div>'
        '</div>'
    )
def _research_observation(row: HybridRow, label: str) -> str:
    risk_low, risk_high = _risk_range(row)
    return (
        f"- {row.symbol} {row.name}: {label}?\u73fe\u50f9 {row.current_close:.2f}?"
        f"Kronos \u9810\u4f30 {row.predicted_close:.2f}?Hybrid {row.hybrid_score:.1f}?"
        f"\u98a8\u96aa\u5340\u9593 {risk_low:.2f} ~ {risk_high:.2f}?"
        f"\u5931\u6548\u689d\u4ef6 {_invalidation_condition(row, risk_low)}?"
        f"\u98a8\u96aa\u8a3b\u8a18 {row.risk_note}"
    )


def _risk_range(row: HybridRow) -> tuple[float, float]:
    downside = row.current_close * 0.955
    upside = max(row.predicted_close, row.current_close * 1.06)
    return downside, upside


def _invalidation_condition(row: HybridRow, risk_low: float) -> str:
    checks = (
        (row.kronos_return <= 0, "Kronos \u9810\u4f30\u8f49\u5f31"),
        (row.technical_score < 50, "\u6280\u8853\u5206\u6578\u4f4e\u65bc 50"),
        (row.realtime_score < 50, "\u5373\u6642\u5206\u6578\u4f4e\u65bc 50"),
    )
    return next((message for matched, message in checks if matched), f"\u8dcc\u7834\u98a8\u96aa\u4e0b\u7de3 {risk_low:.2f}")


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


def _stop_loss_cell(row: HybridRow) -> str:
    if row.stop_loss_price is None or row.stop_loss_price <= 0:
        return "n/a"
    pct = ""
    if row.current_close and row.current_close > 0:
        distance = (row.current_close - row.stop_loss_price) / row.current_close * 100
        pct = f" (-{distance:.1f}%)" if distance >= 0 else " (已破頸線)"
    return f"{row.stop_loss_price:.2f}{pct}"


def _take_profit_cell(row: HybridRow) -> str:
    if row.take_profit_price is None or row.take_profit_price <= 0:
        return "n/a"
    pct = ""
    if row.current_close and row.current_close > 0:
        distance = (row.take_profit_price - row.current_close) / row.current_close * 100
        pct = f" (+{distance:.1f}%)" if distance >= 0 else " (已達目標)"
    return f"{row.take_profit_price:.2f}{pct}"


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
        confidence_score=0.0,
        hybrid_score=0.0,
        current_close=price,
        predicted_close=price,
        realtime_status="無即時資料",
        action="待補資料",
        risk_note="缺少完整 OHLCV / 技術資料",
        stop_loss_price=None,
        take_profit_price=None,
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


def _technical_chart_payload(
    rows: list[HybridRow],
    bars_by_symbol: dict[str, list[Bar]],
    decisions: dict,
    focus_rows: list[HybridRow] | None = None,
) -> dict:
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
        "focusStocks": [
            _technical_chart_focus_stock(row, rank)
            for rank, row in enumerate(focus_rows or [], start=1)
        ],
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
    risk_low, risk_high = _risk_range(row)
    return {
        "symbol": row.symbol,
        "name": row.name,
        "industry": row.industry,
        "screeningBucket": row.screening_bucket,
        "screeningLabel": "籌碼突破主清單" if row.screening_bucket == "chip_confirmed" else "籌碼觀察清單" if row.screening_bucket == "chip_watch" else "品質底池觀察清單",
        "screeningFlags": {
            "legacyMotherPoolHit": row.legacy_hit,
            "legacy": row.legacy_hit,
            "newStrategy": row.new_strategy_hit,
            "chipRadar": row.chip_radar_hit,
            "bestEntry": row.best_entry,
        },
        "signalSource": row.signal_source,
        "hybridScore": round(row.hybrid_score, 2),
        "technicalScore": round(row.technical_score, 2),
        "decision": portfolio_decision_label(decision),
        "bucket": portfolio_decision_bucket(decision),
        "riskNote": row.risk_note,
        "riskLevel": _chart_risk_level(row),
        "marketBias": _chart_market_bias(row),
        "currentClose": round(row.current_close, 4),
        "predictedClose": round(row.predicted_close, 4),
        "priceRange": {"low": round(risk_low, 4), "high": round(risk_high, 4)},
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


def _technical_chart_focus_stock(row: HybridRow, rank: int) -> dict:
    return {
        "rank": rank,
        "symbol": row.symbol,
        "name": row.name,
        "industry": row.industry,
        "label": _overall_focus_label(row),
        "reason": _overall_focus_reason(row),
        "action": _overall_focus_action(row),
        "hybridScore": round(row.hybrid_score, 2),
        "technicalScore": round(row.technical_score, 2),
        "chipRadarHit": row.chip_radar_hit,
        "newStrategyHit": row.new_strategy_hit,
        "legacyHit": row.legacy_hit,
        "bestEntry": row.best_entry,
        "top10MainForceBuyStrength": row.top10_main_force_buy_strength,
        "top10MainForceNetBuy": row.top10_main_force_net_buy,
    }


def _support_resistance(bars: list[Bar]) -> tuple[float | None, float | None]:
    if not bars:
        return None, None
    window = bars[-60:] if len(bars) >= 60 else bars
    return round(min(bar.low for bar in window), 4), round(max(bar.high for bar in window), 4)


def _chart_market_bias(row: HybridRow) -> str:
    for item in row.technical_evidence:
        text = str(item)
        if not text.startswith("structure_bias="):
            continue
        value = text.split("=", 1)[1].strip().lower()
        return {
            "bullish": "偏多",
            "bearish": "偏空",
            "neutral": "中性",
            "data_limited": "資料不足",
        }.get(value, value or "資料不足")
    return "資料不足"


def _chart_risk_level(row: HybridRow) -> str:
    note = str(row.risk_note or "")
    if row.technical_score < 45 or "偏空" in note or "轉弱" in note:
        return "高"
    if row.technical_score < 60 or "留意" in note or "震盪" in note:
        return "中"
    return "低"


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


BEST_ENTRY_FRESH_CROSS_SESSIONS = 2


def _is_best_entry(bars: list[Bar]) -> bool:
    """★最佳買點: close at/above the 60-day MA AND the MACD(12,26,9) DIF line
    crossed above its signal line within the last BEST_ENTRY_FRESH_CROSS_SESSIONS
    sessions (a fresh golden cross, not one that fired long ago). Label-only:
    it never filters candidates, only boosts their display priority."""
    closes = [bar.close for bar in bars]
    if len(closes) < 61:
        return False
    ma60 = sum(closes[-60:]) / 60.0
    if closes[-1] < ma60:
        return False
    fast_ema = _ema(closes, 12)
    slow_ema = _ema(closes, 26)
    dif = [fast_value - slow_value for fast_value, slow_value in zip(fast_ema, slow_ema)]
    signal_line = _ema(dif, 9)
    hist = [dif_value - signal_value for dif_value, signal_value in zip(dif, signal_line)]
    for offset in range(1, BEST_ENTRY_FRESH_CROSS_SESSIONS + 1):
        index = len(hist) - offset
        if index >= 1 and hist[index] > 0 and hist[index - 1] <= 0:
            return True
    return False


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
