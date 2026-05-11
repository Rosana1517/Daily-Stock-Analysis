from __future__ import annotations

from collections.abc import Mapping

from .models import SignalScore, clamp_score


def evaluate_sentiment(sector_news_scores: Mapping[str, float] | None = None) -> dict[str, object]:
    if not sector_news_scores:
        return {
            "news_sentiment": SignalScore("news and policy sentiment", 50.0, missing=("sector news scores",)),
            "metrics": {"average_sentiment": 50.0, "positive_sector_count": 0},
        }
    scores = [float(value) for value in sector_news_scores.values()]
    average = sum(scores) / len(scores)
    positive = sum(1 for value in scores if value >= 60.0)
    return {
        "news_sentiment": SignalScore(
            "news and policy sentiment",
            clamp_score(average),
            evidence=(f"average={average:.1f}", f"positive_sectors={positive}"),
        ),
        "metrics": {"average_sentiment": average, "positive_sector_count": positive},
    }
