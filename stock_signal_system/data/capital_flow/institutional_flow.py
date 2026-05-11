from __future__ import annotations

from .models import CapitalFlowRecord, FlowSignal, clamp_score, flow_intensity


def analyze_institutional_flow(record: CapitalFlowRecord) -> FlowSignal:
    total = record.foreign_net_buy + record.investment_trust_net_buy + record.dealer_net_buy + record.etf_flow
    if total == 0:
        return FlowSignal("institutional conviction", 50.0, missing=("institutional net flow",))
    aligned_buyers = sum(
        1
        for value in (
            record.foreign_net_buy,
            record.investment_trust_net_buy,
            record.dealer_net_buy,
            record.etf_flow,
        )
        if value > 0
    )
    intensity = flow_intensity(total, record)
    score = clamp_score(45.0 + intensity * 28.0 + aligned_buyers * 4.5)
    return FlowSignal(
        "institutional conviction",
        score,
        evidence=(f"total_flow={total:.0f}", f"aligned_buyers={aligned_buyers}", f"intensity={intensity:.2f}"),
    )


def analyze_investment_trust_accumulation(record: CapitalFlowRecord) -> FlowSignal:
    if record.investment_trust_net_buy == 0:
        return FlowSignal("investment trust accumulation", 50.0, missing=("investment trust net buy",))
    intensity = flow_intensity(record.investment_trust_net_buy, record, scale=0.08)
    return FlowSignal(
        "investment trust accumulation",
        clamp_score(50.0 + intensity * 30.0),
        evidence=(f"net_buy={record.investment_trust_net_buy:.0f}", f"intensity={intensity:.2f}"),
    )
