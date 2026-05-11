from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .models import CapitalFlowRecord, FlowSignal, clamp_score


def sector_heat_scores(records: Iterable[CapitalFlowRecord]) -> dict[str, float]:
    flow_by_sector: dict[str, float] = defaultdict(float)
    turnover_by_sector: dict[str, float] = defaultdict(float)
    count_by_sector: dict[str, int] = defaultdict(int)
    for record in records:
        flow = (
            record.foreign_net_buy
            + record.investment_trust_net_buy
            + record.dealer_net_buy
            + record.etf_flow
            + max(0.0, record.margin_financing_change)
        )
        flow_by_sector[record.industry] += flow
        turnover_by_sector[record.industry] += max(record.turnover_value, 1.0)
        count_by_sector[record.industry] += 1

    scores: dict[str, float] = {}
    for sector, flow in flow_by_sector.items():
        concentration = flow / max(turnover_by_sector[sector] * 0.10, 10_000_000.0)
        breadth = min(count_by_sector[sector], 8) * 1.5
        scores[sector] = clamp_score(50.0 + concentration * 22.0 + breadth)
    return scores


def analyze_sector_heat(record: CapitalFlowRecord, sector_scores: dict[str, float]) -> FlowSignal:
    score = sector_scores.get(record.industry)
    if score is None:
        return FlowSignal("sector capital concentration", 50.0, missing=("sector heat score",))
    return FlowSignal("sector capital concentration", score, evidence=(f"industry={record.industry}",))
