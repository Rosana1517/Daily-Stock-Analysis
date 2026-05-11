from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping, Sequence

from .abnormal_volume import analyze_abnormal_volume
from .dealer_behavior import analyze_dealer_behavior
from .foreign_flow import analyze_foreign_flow
from .institutional_flow import analyze_institutional_flow, analyze_investment_trust_accumulation
from .margin_change import analyze_margin_change
from .models import CapitalFlowRecord, CapitalFlowReport, CapitalFlowResult, FlowSignal, clamp_score
from .sector_heat import analyze_sector_heat, sector_heat_scores
from .short_covering import analyze_short_covering


def analyze_capital_flow(
    rows: Iterable[CapitalFlowRecord | Mapping[str, object]],
    report_date: date | None = None,
    top_n: int = 10,
) -> CapitalFlowReport:
    records = tuple(_coerce_record(row) for row in rows)
    sector_scores = sector_heat_scores(records)
    results = tuple(_score_record(record, sector_scores) for record in records)
    ranked = sorted(results, key=lambda item: item.capital_flow_score, reverse=True)
    return CapitalFlowReport(
        report_date=report_date,
        results=tuple(ranked),
        top_accumulation_candidates=tuple(
            item for item in ranked if item.accumulation_score >= 68.0 and item.institutional_conviction_score >= 58.0
        )[:top_n],
        hidden_accumulation_candidates=tuple(
            item
            for item in ranked
            if item.accumulation_score >= 62.0 and item.speculative_activity_score <= 62.0 and item.record.volume_ratio <= 1.35
        )[:top_n],
        early_momentum_candidates=tuple(
            item for item in ranked if item.capital_flow_score >= 64.0 and 1.15 <= item.record.volume_ratio <= 2.2
        )[:top_n],
        speculative_overheating_warnings=tuple(
            item for item in ranked if item.speculative_activity_score >= 77.5 and item.institutional_conviction_score < 62.0
        )[:top_n],
        sector_scores=sector_scores,
    )


def _score_record(record: CapitalFlowRecord, sector_scores: dict[str, float]) -> CapitalFlowResult:
    signals = {
        "foreign_flow": analyze_foreign_flow(record),
        "investment_trust": analyze_investment_trust_accumulation(record),
        "institutional_flow": analyze_institutional_flow(record),
        "dealer_behavior": analyze_dealer_behavior(record),
        "margin_change": analyze_margin_change(record),
        "short_covering": analyze_short_covering(record),
        "abnormal_volume": analyze_abnormal_volume(record),
        "sector_heat": analyze_sector_heat(record, sector_scores),
    }
    institutional = _avg(
        signals["foreign_flow"].score,
        signals["investment_trust"].score,
        signals["institutional_flow"].score,
        signals["dealer_behavior"].score,
    )
    accumulation = _avg(
        institutional * 1.20,
        signals["sector_heat"].score,
        signals["abnormal_volume"].score,
        _low_noise_margin_score(signals["margin_change"]),
    )
    speculative = _avg(
        signals["margin_change"].score * 1.10,
        signals["short_covering"].score,
        signals["abnormal_volume"].score,
        _volume_overheat_score(record),
    )
    sector_rotation = signals["sector_heat"].score
    capital_flow = _avg(
        accumulation * 1.15,
        institutional,
        sector_rotation,
        signals["abnormal_volume"].score,
        max(35.0, 100.0 - max(0.0, speculative - 72.0) * 0.65),
    )
    labels, warnings = _classify(record, accumulation, speculative, institutional, capital_flow)
    return CapitalFlowResult(
        record=record,
        capital_flow_score=round(capital_flow, 1),
        accumulation_score=round(accumulation, 1),
        speculative_activity_score=round(speculative, 1),
        institutional_conviction_score=round(institutional, 1),
        sector_rotation_score=round(sector_rotation, 1),
        signals=signals,
        labels=labels,
        warnings=warnings,
    )


def _classify(
    record: CapitalFlowRecord,
    accumulation: float,
    speculative: float,
    institutional: float,
    capital_flow: float,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    labels: list[str] = []
    warnings: list[str] = []
    if accumulation >= 68.0 and institutional >= 58.0:
        labels.append("top accumulation")
    if accumulation >= 62.0 and speculative <= 62.0 and record.volume_ratio <= 1.35:
        labels.append("hidden accumulation")
    if capital_flow >= 64.0 and 1.15 <= record.volume_ratio <= 2.2:
        labels.append("early momentum")
    if speculative >= 77.5 and institutional < 62.0:
        warnings.append("speculative overheating")
    if record.volume_ratio >= 3.0 and institutional < 55.0:
        warnings.append("abnormal turnover without institutional confirmation")
    return tuple(labels), tuple(warnings)


def _coerce_record(row: CapitalFlowRecord | Mapping[str, object]) -> CapitalFlowRecord:
    if isinstance(row, CapitalFlowRecord):
        return row
    return CapitalFlowRecord.from_mapping(row)


def _avg(*values: float) -> float:
    return clamp_score(sum(values) / len(values))


def _low_noise_margin_score(signal: FlowSignal) -> float:
    return signal.score if signal.score <= 72.0 else 72.0


def _volume_overheat_score(record: CapitalFlowRecord) -> float:
    if record.volume_ratio >= 4.0:
        return 90.0
    if record.volume_ratio >= 2.5:
        return 78.0
    if record.volume_ratio >= 1.6:
        return 64.0
    return 48.0


def top_symbols(results: Sequence[CapitalFlowResult]) -> tuple[str, ...]:
    return tuple(item.record.symbol for item in results)
