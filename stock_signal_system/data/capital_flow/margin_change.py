from __future__ import annotations

from .models import CapitalFlowRecord, FlowSignal, clamp_score


def analyze_margin_change(record: CapitalFlowRecord) -> FlowSignal:
    if record.margin_financing_change == 0:
        return FlowSignal("margin financing change", 50.0, missing=("margin financing change",))
    if record.free_float_shares > 0:
        ratio = record.margin_financing_change / record.free_float_shares
        score = clamp_score(50.0 + ratio * 4200.0)
        evidence = (f"margin_change={record.margin_financing_change:.0f}", f"free_float_ratio={ratio:.3%}")
    else:
        turnover_units = max(record.volume, 1.0)
        ratio = record.margin_financing_change / turnover_units
        score = clamp_score(50.0 + ratio * 28.0)
        evidence = (f"margin_change={record.margin_financing_change:.0f}", f"volume_ratio={ratio:.2f}")
    return FlowSignal("margin financing change", score, evidence=evidence)
