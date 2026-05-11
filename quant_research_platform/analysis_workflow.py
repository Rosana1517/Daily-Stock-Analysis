from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class WorkflowStepDefinition:
    step: int
    task: str
    modules: tuple[str, ...]


@dataclass(frozen=True)
class WorkflowStepResult:
    step: int
    task: str
    modules: tuple[str, ...]
    status: str
    evidence: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class StockWorkflowAudit:
    symbol: str
    passed: int
    partial: int
    missing: int
    steps: tuple[WorkflowStepResult, ...]

    @property
    def total(self) -> int:
        return len(self.steps)


WORKFLOW_STEPS: tuple[WorkflowStepDefinition, ...] = (
    WorkflowStepDefinition(1, "RSS、新聞、政策、輿情蒐集", ("zai-cli", "web-access", "rss_sources.py")),
    WorkflowStepDefinition(2, "新聞清洗與排除雜訊", ("finance-sentiment", "rss_sources.py")),
    WorkflowStepDefinition(3, "產業訊號分類", ("finance-sentiment", "finance-investment-researcher", "industry.py")),
    WorkflowStepDefinition(4, "產業利基分析", ("finance-investment-researcher",)),
    WorkflowStepDefinition(5, "基本面分析", ("stock-analysis", "finance-financial-analyst", "funda-data")),
    WorkflowStepDefinition(6, "個股投資論點分析", ("stock-analysis", "finance-investment-researcher")),
    WorkflowStepDefinition(7, "流動性檢查", ("stock-liquidity", "rule_score.py")),
    WorkflowStepDefinition(8, "多因子訊號評分", ("stock-checker-analysis", "rule_score.py")),
    WorkflowStepDefinition(9, "產業與個股關聯檢查", ("stock-analysis", "stock-correlation")),
    WorkflowStepDefinition(10, "日線蠟燭圖策略", ("candlestick.py",)),
    WorkflowStepDefinition(11, "OpenBB/Qlib/Kronos分析", ("OpenBB", "Qlib", "Kronos")),
    WorkflowStepDefinition(12, "1H 趨勢結構", ("market_structure.py",)),
    WorkflowStepDefinition(13, "5M 進場確認", ("market_structure.py", "candlestick.py")),
    WorkflowStepDefinition(14, "只做多策略過濾", ("rule_score.py",)),
    WorkflowStepDefinition(15, "3-20 天波段條件判斷", ("stock-analysis", "策略模組")),
    WorkflowStepDefinition(16, "進場、停損、出場條件", ("candlestick.py", "rule_score.py")),
)

_STEP_BY_NUMBER = {definition.step: definition for definition in WORKFLOW_STEPS}


def build_workflow_audits(
    rows: Sequence[object],
    bars_by_symbol: Mapping[str, Sequence[object]],
    technicals: Mapping[str, object],
    realtime_states: Mapping[str, object],
    industry_signals: Sequence[object],
    news_items: Sequence[object],
    qlib_path: Path | None,
    data_source: str,
    openbb_provider: str | None = None,
    fundamental_snapshots: Mapping[str, object] | None = None,
    liquidity_snapshots: Mapping[str, object] | None = None,
    qlib_metrics: object | None = None,
    qlib_engine: object | None = None,
    structure_symbols: set[str] | None = None,
    trigger_symbols: set[str] | None = None,
) -> dict[str, StockWorkflowAudit]:
    industry_by_name = {str(getattr(item, "industry", "")): item for item in industry_signals}
    news_count = len(news_items)
    qlib_ready = bool(qlib_path)
    data_source = data_source.lower()
    audits: dict[str, StockWorkflowAudit] = {}

    for row in rows:
        symbol = str(getattr(row, "symbol", ""))
        industry = str(getattr(row, "industry", ""))
        bars = list(bars_by_symbol.get(symbol, ()))
        tech = technicals.get(symbol)
        realtime = realtime_states.get(symbol)
        signal = industry_by_name.get(industry)
        fundamentals = (fundamental_snapshots or {}).get(symbol)
        liquidity = (liquidity_snapshots or {}).get(symbol)
        steps = tuple(
            _stock_step_results(
                row=row,
                bars=bars,
                tech=tech,
                realtime=realtime,
                industry_signal=signal,
                news_count=news_count,
                qlib_ready=qlib_ready,
                data_source=data_source,
                openbb_provider=openbb_provider,
                fundamentals=fundamentals,
                liquidity=liquidity,
                qlib_metrics=qlib_metrics,
                qlib_engine=qlib_engine,
                has_structure_feed=symbol in (structure_symbols or set()),
                has_trigger_feed=symbol in (trigger_symbols or set()),
            )
        )
        audits[symbol] = StockWorkflowAudit(
            symbol=symbol,
            passed=sum(1 for item in steps if item.status == "pass"),
            partial=sum(1 for item in steps if item.status == "partial"),
            missing=sum(1 for item in steps if item.status == "missing"),
            steps=steps,
        )
    return audits


def _stock_step_results(
    row: object,
    bars: Sequence[object],
    tech: object | None,
    realtime: object | None,
    industry_signal: object | None,
    news_count: int,
    qlib_ready: bool,
    data_source: str,
    openbb_provider: str | None,
    fundamentals: object | None,
    liquidity: object | None,
    qlib_metrics: object | None,
    qlib_engine: object | None,
    has_structure_feed: bool,
    has_trigger_feed: bool,
) -> Iterable[WorkflowStepResult]:
    industry = str(getattr(row, "industry", ""))
    hybrid_score = _float_attr(row, "hybrid_score")
    news_score = _float_attr(row, "news_score")
    kronos_return = _float_attr(row, "kronos_return")
    current_close = _float_attr(row, "current_close")
    predicted_close = _float_attr(row, "predicted_close")
    action = str(getattr(row, "action", "") or "")
    risk_note = str(getattr(row, "risk_note", "") or "")
    has_prices = bool(bars) and current_close > 0 and predicted_close > 0
    volume_available = any(_float_attr(bar, "volume") > 0 for bar in bars[-30:])
    has_fundamentals = fundamentals is not None
    has_liquidity = liquidity is not None
    has_technical = tech is not None
    has_structure = bool(getattr(tech, "structure_bias", "")) if tech else False
    has_entry = bool(getattr(tech, "entry", "")) if tech else False
    has_stop = bool(getattr(tech, "stop_loss", "")) if tech else False
    has_exit = bool(getattr(tech, "exit", "")) if tech else False
    patterns = tuple(str(item) for item in getattr(tech, "patterns", ()) or ()) if tech else ()
    has_industry_link = bool(industry and (industry_signal or news_score != 50))
    has_qlib = _has_qlib_engine(qlib_engine) or _has_qlib_metrics(qlib_metrics)

    yield _result(1, "pass" if news_count else "missing", (f"RSS/news rows: {news_count}",) if news_count else (), () if news_count else ("RSS/news feed missing",))
    yield _result(2, "pass" if news_count else "missing", ("RSS cleaned and rule sentiment scored",) if news_count else (), () if news_count else ("No news rows to clean",))
    yield _result(3, "pass" if has_industry_link else "partial", (f"industry={industry}", f"news_score={news_score:.1f}"), () if has_industry_link else ("No direct RSS industry signal",))
    yield _result(4, "pass" if industry_signal or news_score != 50 else "partial", _industry_evidence(industry_signal) or ((f"industry_score={news_score:.1f}",) if news_score != 50 else ()), () if industry_signal or news_score != 50 else ("Industry thesis only from fallback grouping",))
    yield _result(5, "pass" if has_fundamentals else "partial" if has_prices else "missing", tuple(item for item in (f"current={current_close:.2f}" if has_prices else "", f"predicted={predicted_close:.2f}" if has_prices else "", _fundamental_evidence(fundamentals) if has_fundamentals else "") if item), () if has_fundamentals else ("Fundamental snapshot unavailable",))
    yield _result(6, "pass" if action or risk_note else "missing", tuple(item for item in (action, risk_note) if item), () if action or risk_note else ("Investment thesis/action missing",))
    yield _result(7, "pass" if has_liquidity else "partial" if volume_available else "missing", tuple(item for item in ("OHLCV volume available" if volume_available else "", _liquidity_evidence(liquidity) if has_liquidity else "") if item), () if has_liquidity else ("Liquidity spread/depth estimate unavailable",))
    yield _result(8, "pass" if hybrid_score > 0 else "missing", (f"Hybrid={hybrid_score:.1f}", f"Kronos={_float_attr(row, 'kronos_score'):.1f}", f"News={news_score:.1f}", f"Technical={_float_attr(row, 'technical_score'):.1f}") if hybrid_score > 0 else (), () if hybrid_score > 0 else ("Hybrid score missing",))
    yield _result(9, "pass" if has_industry_link else "partial" if industry else "missing", (f"stock mapped to industry={industry}",) if industry else (), () if has_industry_link else ("Direct industry/news correlation weak",))
    yield _result(10, "pass" if has_technical else "missing", tuple(patterns[:3]) or ((f"bias={getattr(tech, 'bias', '')}",) if tech else ()), () if has_technical else ("Candlestick analysis missing",))
    yield _result(11, "pass" if data_source in {"openbb", "csv"} and has_qlib and kronos_return else "partial" if qlib_ready or has_qlib or kronos_return else "missing", tuple(item for item in (f"Kronos expected_return={kronos_return:.2%}", "Qlib handoff config generated" if qlib_ready else "", _qlib_evidence(qlib_metrics), _qlib_engine_evidence(qlib_engine), f"data_source={data_source}") if item), () if has_qlib else ("Qlib diagnostics/engine metrics unavailable",))
    yield _result(12, "pass" if has_structure else "partial" if bars else "missing", (f"structure_bias={getattr(tech, 'structure_bias', '')}",) if has_structure else (), () if has_structure else ("1H feed unavailable; daily structure fallback used",))
    yield _result(13, "pass" if has_entry or patterns else "partial" if bars else "missing", tuple(patterns[:2]) if patterns else ((getattr(tech, "entry", ""),) if has_entry else ()), () if has_entry or patterns else ("5M trigger feed unavailable; daily trigger fallback used",))
    yield _result(14, "pass" if action else "missing", (f"long_only_action={action}",) if action else (), () if action else ("Long-only action missing",))
    yield _result(15, "pass" if has_prices else "missing", (f"3-20d expected_return={(predicted_close / current_close - 1):.2%}",) if has_prices and current_close else (), () if has_prices else ("3-20 day swing condition missing prices",))
    yield _result(16, "pass" if has_prices else "missing", tuple(item for item in (getattr(tech, "entry", ""), getattr(tech, "stop_loss", ""), getattr(tech, "exit", "")) if item) or ((f"fallback close={current_close:.2f}",) if has_prices else ()), () if has_prices else ("Entry/stop/exit conditions missing",))

def _result(
    step: int,
    status: str,
    evidence: Sequence[str] = (),
    missing: Sequence[str] = (),
) -> WorkflowStepResult:
    definition = _STEP_BY_NUMBER[step]
    return WorkflowStepResult(
        step=definition.step,
        task=definition.task,
        modules=definition.modules,
        status=status,
        evidence=tuple(item for item in evidence if item),
        missing=tuple(item for item in missing if item),
    )


def _industry_evidence(industry_signal: object | None) -> tuple[str, ...]:
    if industry_signal is None:
        return ()
    catalysts = tuple(str(item) for item in getattr(industry_signal, "catalysts", ()) or ())
    evidence = [
        f"industry_score={_float_attr(industry_signal, 'score'):.1f}",
        f"evidence_count={int(_float_attr(industry_signal, 'evidence_count'))}",
    ]
    evidence.extend(catalysts[:2])
    return tuple(evidence)


def _float_attr(value: object, attr: str) -> float:
    try:
        raw = getattr(value, attr, 0)
        if raw in (None, ""):
            return 0.0
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _fundamental_evidence(snapshot: object) -> str:
    return (
        f"營收年增率={_float_attr(snapshot, 'revenue_growth_yoy'):.1f}%, "
        f"毛利率={_float_attr(snapshot, 'gross_margin'):.1f}%, "
        f"營業利益率={_float_attr(snapshot, 'operating_margin'):.1f}%, "
        f"自由現金流率={_float_attr(snapshot, 'free_cash_flow_margin'):.1f}%, "
        f"負債權益比={_float_attr(snapshot, 'debt_to_equity'):.2f}, "
        f"本益比={_float_attr(snapshot, 'pe_ratio'):.1f}"
    )


def _liquidity_evidence(snapshot: object) -> str:
    turnover = getattr(snapshot, "turnover_ratio", None)
    spread = getattr(snapshot, "estimated_spread_bps", None)
    impact = getattr(snapshot, "impact_bps_1pct_adv", None)
    return (
        f"avg_volume={_float_attr(snapshot, 'avg_volume'):.0f}, "
        f"spread_bps={_optional_float(spread)}, "
        f"impact_bps={_optional_float(impact)}, "
        f"turnover={_optional_float(turnover)}"
    )


def _qlib_evidence(metrics: object | None) -> str:
    if not metrics:
        return ""
    return (
        f"即時診斷/IC={_optional_float(getattr(metrics, 'ic', None))}, "
        f"RankIC={_optional_float(getattr(metrics, 'rank_ic', None))}, "
        f"TopK={_optional_float(getattr(metrics, 'topk_return', None))}, "
        f"樣本={int(_float_attr(metrics, 'observations'))}"
    )


def _has_qlib_metrics(metrics: object | None) -> bool:
    return bool(metrics) and _float_attr(metrics, "observations") >= 2


def _qlib_engine_evidence(metrics: object | None) -> str:
    if not metrics:
        return ""
    if not bool(getattr(metrics, "executed", False)):
        error = str(getattr(metrics, "error", "") or "")
        return f"Qlib engine 未執行={error[:80]}" if error else "Qlib engine 未執行"
    return (
        f"Qlib engine 投組={_optional_float(getattr(metrics, 'portfolio_return', None))}, "
        f"基準={_optional_float(getattr(metrics, 'benchmark_return', None))}, "
        f"最大回撤={_optional_float(getattr(metrics, 'max_drawdown', None))}, "
        f"週轉率={_optional_float(getattr(metrics, 'average_turnover', None))}, "
        f"樣本={int(_float_attr(metrics, 'observations'))}"
    )


def _has_qlib_engine(metrics: object | None) -> bool:
    return bool(metrics) and bool(getattr(metrics, "executed", False)) and _float_attr(metrics, "observations") >= 2


def _optional_float(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "n/a"
