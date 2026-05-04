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
    volume_available = any(_float_attr(bar, "volume") > 0 for bar in bars[-30:])
    has_prices = bool(bars) and current_close > 0 and predicted_close > 0
    has_fundamentals = fundamentals is not None
    has_liquidity = liquidity is not None
    has_technical = tech is not None
    has_structure = bool(getattr(tech, "structure_bias", "")) if tech else False
    has_entry = bool(getattr(tech, "entry", "")) if tech else False
    has_stop = bool(getattr(tech, "stop_loss", "")) if tech else False
    has_exit = bool(getattr(tech, "exit", "")) if tech else False
    patterns = tuple(str(item) for item in getattr(tech, "patterns", ()) or ()) if tech else ()

    yield _result(
        1,
        "pass" if news_count else "missing",
        (f"RSS/新聞筆數：{news_count}",) if news_count else (),
        () if news_count else ("RSS/新聞快取為空或抓取失敗",),
    )
    yield _result(
        2,
        "partial" if news_count else "missing",
        ("rss_sources.py 已產生結構化新聞資料",) if news_count else (),
        ("尚未接入獨立 finance-sentiment API 分數",)
        if news_count
        else ("沒有新聞資料可清洗",),
    )
    yield _result(
        3,
        "pass" if industry_signal or news_score != 50 else "partial",
        (f"產業：{industry}", f"新聞分數={news_score:.1f}"),
        () if industry_signal else ("RSS 產業催化題材未直接對應此股票產業",),
    )
    yield _result(
        4,
        "pass" if industry_signal else "partial",
        _industry_evidence(industry_signal),
        () if industry_signal else ("產業利基暫由股票分類推估，尚未有直接新聞佐證",),
    )
    yield _result(
        5,
        "pass" if has_fundamentals else "partial" if has_prices else "missing",
        tuple(
            item
            for item in (
                f"現價={current_close:.2f}" if has_prices else "",
                f"預估價={predicted_close:.2f}" if has_prices else "",
                _fundamental_evidence(fundamentals) if has_fundamentals else "",
            )
            if item
        ),
        () if has_fundamentals else ("完整財報衍生欄位不足",) if has_prices else ("缺少 OHLCV/價格資料",),
    )
    yield _result(
        6,
        "partial" if action or risk_note else "missing",
        tuple(item for item in (action, risk_note) if item),
        ("尚未保存完整多方/基本/空方投資論點",),
    )
    yield _result(
        7,
        "pass" if has_liquidity else "partial" if volume_available else "missing",
        tuple(
            item
            for item in (
                "近期 OHLCV 成交量可用" if volume_available else "",
                _liquidity_evidence(liquidity) if has_liquidity else "",
            )
            if item
        ),
        () if has_liquidity else ("尚未產生價差、週轉率與衝擊成本估計",),
    )
    yield _result(
        8,
        "pass" if hybrid_score > 0 else "missing",
        (
            f"Hybrid分數={hybrid_score:.1f}",
            f"Kronos分數={_float_attr(row, 'kronos_score'):.1f}",
            f"新聞分數={news_score:.1f}",
            f"技術分數={_float_attr(row, 'technical_score'):.1f}",
        )
        if hybrid_score > 0
        else (),
        () if hybrid_score > 0 else ("Hybrid 分數未產生",),
    )
    yield _result(
        9,
        "partial" if industry else "missing",
        (f"股票已對應產業：{industry}",) if industry else (),
        ("尚未產生個股兩兩相關係數矩陣",),
    )
    yield _result(
        10,
        "pass" if has_technical else "missing",
        tuple(patterns[:3]) or ((f"bias={getattr(tech, 'bias', '')}",) if tech else ()),
        () if has_technical else ("candlestick.py 未回傳技術訊號",),
    )
    yield _result(
        11,
        "pass"
        if data_source == "openbb" and _has_qlib_engine(qlib_engine)
        else "partial"
        if qlib_ready or _has_qlib_metrics(qlib_metrics) or kronos_return
        else "missing",
        tuple(
            item
            for item in (
                f"Kronos 預估報酬={kronos_return:.2%}",
                "已輸出 Qlib handoff config" if qlib_ready else "",
                _qlib_evidence(qlib_metrics),
                _qlib_engine_evidence(qlib_engine),
                f"OpenBB 即時資料入口已啟用，provider={openbb_provider or 'default'}" if data_source == "openbb" else "",
            )
            if item
        ),
        tuple(
            item
            for item in (
                "" if data_source == "openbb" else "本次未使用 OpenBB 即時資料入口",
                "" if _has_qlib_engine(qlib_engine) else "Qlib engine 投組回測未執行",
            )
            if item
        ),
    )
    yield _result(
        12,
        "pass" if has_structure_feed and has_structure else "partial" if has_structure else "missing",
        (f"趨勢結構={getattr(tech, 'structure_bias', '')}",) if has_structure else (),
        () if has_structure_feed else ("僅有日線資料，尚未接入真實 1H OHLCV",),
    )
    yield _result(
        13,
        "pass" if has_trigger_feed and (has_entry or patterns) else "partial" if has_entry or patterns else "missing",
        tuple(patterns[:2]) if patterns else (getattr(tech, "entry", ""),) if has_entry else (),
        () if has_trigger_feed else ("僅有日線確認，尚未接入真實 5M 進場資料",),
    )
    yield _result(
        14,
        "pass" if action else "missing",
        (f"操作建議={action}",) if action else (),
        () if action else ("只做多策略過濾未產生決策",),
    )
    yield _result(
        15,
        "partial" if has_prices else "missing",
        (f"預估報酬={(predicted_close / current_close - 1):.2%}",) if has_prices and current_close else (),
        ("3-20 天波段條件由 Kronos 預測週期與日線型態近似判斷",),
    )
    yield _result(
        16,
        "pass" if has_entry and has_stop and has_exit else "partial" if has_prices else "missing",
        tuple(item for item in (getattr(tech, "entry", ""), getattr(tech, "stop_loss", ""), getattr(tech, "exit", "")) if item)
        or ((f"fallback close={current_close:.2f}",) if has_prices else ()),
        () if has_entry and has_stop and has_exit else ("進場/停損/出場欄位尚未完整",),
    )


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
