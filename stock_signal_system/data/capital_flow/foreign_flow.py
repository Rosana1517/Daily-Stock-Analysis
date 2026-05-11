from __future__ import annotations

from .models import CapitalFlowRecord, FlowSignal, clamp_score, flow_intensity


def analyze_foreign_flow(record: CapitalFlowRecord) -> FlowSignal:
    if record.foreign_net_buy == 0:
        return FlowSignal("foreign investor accumulation", 50.0, missing=("foreign investor net buy",))
    intensity = flow_intensity(record.foreign_net_buy, record)
    score = clamp_score(50.0 + intensity * 34.0)
    return FlowSignal(
        "foreign investor accumulation",
        score,
        evidence=(f"net_buy={record.foreign_net_buy:.0f}", f"intensity={intensity:.2f}"),
    )
