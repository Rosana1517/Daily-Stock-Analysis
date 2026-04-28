from __future__ import annotations

from collections import defaultdict

from stock_signal_system.models import IndustrySignal, NewsItem


POSITIVE_TERMS = (
    "growth",
    "demand",
    "investment",
    "spending",
    "approval",
    "expansion",
    "subsidy",
    "order",
    "surge",
    "record",
    "成長",
    "需求",
    "投資",
    "擴產",
    "補助",
    "訂單",
    "突破",
)
CAUTION_TERMS = (
    "cut",
    "layoff",
    "sanction",
    "probe",
    "fraud",
    "risk",
    "drop",
    "decline",
    "shortage",
    "調降",
    "裁員",
    "制裁",
    "調查",
    "風險",
    "下滑",
    "衰退",
)


def analyze_industries(news: list[NewsItem]) -> list[IndustrySignal]:
    scores: dict[str, float] = defaultdict(float)
    catalysts: dict[str, list[str]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    weights: dict[str, float] = defaultdict(float)

    for item in news:
        text = f"{item.title} {item.body}"
        sentiment = _term_score(text)
        weight = max(0.1, float(getattr(item, "source_weight", 1.0)))
        for industry in item.industries:
            counts[industry] += 1
            weights[industry] += weight
            scores[industry] += (45 + sentiment) * weight
            catalysts[industry].append(item.title)

    signals = [
        IndustrySignal(
            industry=industry,
            score=round(scores[industry] / max(0.1, weights[industry]), 1),
            catalysts=tuple(catalysts[industry][:3]),
            evidence_count=counts[industry],
        )
        for industry in scores
    ]
    return sorted(signals, key=lambda item: item.score, reverse=True)


def _term_score(text: str) -> float:
    text_lower = text.lower()
    positive = sum(1 for term in POSITIVE_TERMS if term.lower() in text_lower)
    caution = sum(1 for term in CAUTION_TERMS if term.lower() in text_lower)
    return min(35, positive * 7) - min(25, caution * 8)
