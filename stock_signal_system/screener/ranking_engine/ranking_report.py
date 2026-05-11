from __future__ import annotations

import csv
from pathlib import Path

from .ranking_model import RankingResult


def ranking_rows(ranked: list[RankingResult]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, item in enumerate(ranked, start=1):
        rows.append(
            {
                "rank": str(index),
                "symbol": item.stock.symbol,
                "name": item.stock.name,
                "industry": item.stock.industry,
                "composite_score": f"{item.composite_score:.1f}",
                "probability": f"{item.probability:.1f}",
                "confidence": f"{item.confidence:.1f}",
                "setup": item.setup.value,
                "holding_period": item.expected_holding_period,
                "expected_volatility": item.expected_volatility,
                "risk_reward": f"{item.risk_reward:.2f}",
            }
        )
    return rows


def build_ranking_markdown(ranked: list[RankingResult]) -> str:
    lines = [
        "# Probability Ranking",
        "",
        "| Rank | Symbol | Name | Industry | Probability | Composite | Setup | Holding | R/R |",
        "| --- | --- | --- | --- | ---: | ---: | --- | --- | ---: |",
    ]
    for row in ranking_rows(ranked):
        lines.append(
            "| {rank} | {symbol} | {name} | {industry} | {probability} | {composite_score} | {setup} | {holding_period} | {risk_reward} |".format(
                **row
            )
        )
    return "\n".join(lines)


def save_ranking_csv(path: Path, ranked: list[RankingResult]) -> Path:
    rows = ranking_rows(ranked)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["rank"])
        writer.writeheader()
        writer.writerows(rows)
    return path
