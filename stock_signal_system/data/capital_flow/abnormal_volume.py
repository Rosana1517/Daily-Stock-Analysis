from __future__ import annotations

from .models import CapitalFlowRecord, FlowSignal, clamp_score


def analyze_abnormal_volume(record: CapitalFlowRecord) -> FlowSignal:
    realtime_volume = record.realtime_volume or record.volume
    if record.avg_volume_20d <= 0:
        return FlowSignal("abnormal turnover", 50.0, missing=("avg_volume_20d",))
    expansion = realtime_volume / record.avg_volume_20d
    score = clamp_score(42.0 + expansion * 24.0)
    if record.previous_volume > 0 and realtime_volume > record.previous_volume * 1.6:
        score = clamp_score(score + 8.0)
    return FlowSignal(
        "abnormal turnover",
        score,
        evidence=(f"volume_expansion={expansion:.2f}x", f"turnover_value={record.turnover_value:.0f}"),
    )
