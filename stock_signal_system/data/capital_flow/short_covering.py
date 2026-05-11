from __future__ import annotations

from .models import CapitalFlowRecord, FlowSignal, clamp_score


def analyze_short_covering(record: CapitalFlowRecord) -> FlowSignal:
    if record.short_interest_change == 0:
        return FlowSignal("short covering", 50.0, missing=("short interest change",))
    covering = -record.short_interest_change
    ratio = covering / max(record.volume, 1.0)
    score = clamp_score(50.0 + ratio * 38.0)
    return FlowSignal(
        "short covering",
        score,
        evidence=(f"short_interest_change={record.short_interest_change:.0f}", f"covering_volume_ratio={ratio:.2f}"),
    )
