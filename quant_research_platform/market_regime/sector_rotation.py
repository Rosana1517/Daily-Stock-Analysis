from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .models import SignalScore, clamp_score


AI_KEYWORDS = ("AI", "人工智慧", "半導體", "伺服器", "散熱", "光通訊", "IC", "ASIC", "電子零組件")
DEFENSIVE_KEYWORDS = ("金融", "電信", "食品", "水泥", "公用", "醫療", "生技")


def evaluate_sector_rotation(
    stock_rows: Sequence[Mapping[str, Any]],
    sector_news_scores: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    weighted_return: dict[str, float] = defaultdict(float)
    weights: dict[str, float] = defaultdict(float)
    for row in stock_rows:
        sector = str(row.get("industry") or row.get("sector") or "未分類").strip() or "未分類"
        current = _float(row.get("price") or row.get("close"))
        previous = _float(row.get("price_20d_ago") or row.get("previous_close") or row.get("prev_close"))
        volume = max(_float(row.get("volume")), 1.0)
        if current <= 0 or previous <= 0:
            continue
        change = current / previous - 1.0
        grouped[sector].append(change)
        weighted_return[sector] += change * volume
        weights[sector] += volume

    if not grouped:
        empty = SignalScore("sector relative strength", 50.0, missing=("industry", "price_20d_ago"))
        return {"sector_relative_strength": empty, "metrics": {"top_sector": "unknown", "sector_scores": {}}}

    sector_scores: dict[str, float] = {}
    for sector, changes in grouped.items():
        base_return = weighted_return[sector] / weights[sector] if weights[sector] else sum(changes) / len(changes)
        news_boost = ((sector_news_scores or {}).get(sector, 50.0) - 50.0) / 450.0
        sector_scores[sector] = base_return + news_boost

    top_sector = max(sector_scores, key=sector_scores.get)
    top_value = sector_scores[top_sector]
    average_value = sum(sector_scores.values()) / len(sector_scores)
    dispersion = top_value - average_value
    score = clamp_score(50.0 + top_value * 240.0 + dispersion * 180.0)
    ai_score = _theme_score(sector_scores, AI_KEYWORDS)
    defensive_score = _theme_score(sector_scores, DEFENSIVE_KEYWORDS)
    return {
        "sector_relative_strength": SignalScore(
            "sector relative strength",
            score,
            evidence=(f"top_sector={top_sector}", f"relative_return={top_value:.2%}", f"dispersion={dispersion:.2%}"),
        ),
        "ai_sector_strength": SignalScore("AI sector strength", ai_score, evidence=(f"top_sector={top_sector}",)),
        "defensive_sector_strength": SignalScore("defensive sector strength", defensive_score, evidence=(f"top_sector={top_sector}",)),
        "metrics": {
            "top_sector": top_sector,
            "top_sector_score": top_value,
            "sector_scores": sector_scores,
            "ai_theme_score": ai_score,
            "defensive_theme_score": defensive_score,
        },
    }


def _theme_score(sector_scores: Mapping[str, float], keywords: Sequence[str]) -> float:
    themed = [value for sector, value in sector_scores.items() if any(keyword.lower() in sector.lower() for keyword in keywords)]
    if not themed:
        return 45.0
    return clamp_score(50.0 + max(themed) * 260.0)


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
