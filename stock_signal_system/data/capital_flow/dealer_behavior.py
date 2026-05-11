from __future__ import annotations

from .models import CapitalFlowRecord, FlowSignal, clamp_score, flow_intensity


def analyze_dealer_behavior(record: CapitalFlowRecord) -> FlowSignal:
    if record.dealer_net_buy == 0:
        return FlowSignal("dealer positioning", 50.0, missing=("dealer net buy",))
    intensity = flow_intensity(record.dealer_net_buy, record, scale=0.07)
    score = clamp_score(50.0 + intensity * 24.0)
    evidence = (f"net_buy={record.dealer_net_buy:.0f}", f"intensity={intensity:.2f}")
    if record.dealer_net_buy > 0 and record.volume_ratio > 1.4:
        score = clamp_score(score + 6.0)
        evidence += ("dealer_with_volume_expansion",)
    return FlowSignal("dealer positioning", score, evidence=evidence)
