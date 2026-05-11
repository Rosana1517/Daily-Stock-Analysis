from __future__ import annotations

from collections.abc import Iterable

from .models import MissedCandidate, ReviewFinding


def analyze_missed_runners(candidates: Iterable[MissedCandidate], threshold: float = 0.08) -> tuple[ReviewFinding, ...]:
    findings: list[ReviewFinding] = []
    for candidate in candidates:
        if candidate.missed_return < threshold:
            continue
        severity = "high" if candidate.ranking_probability >= 65 else "medium"
        findings.append(
            ReviewFinding(
                "missed_runner",
                severity,
                "Missed runner: high-ranked candidate moved without being traded.",
                (
                    f"symbol={candidate.symbol}",
                    f"setup={candidate.setup}",
                    f"missed_return={candidate.missed_return:.2%}",
                    f"reason_not_taken={candidate.reason_not_taken or 'unknown'}",
                ),
            )
        )
    return tuple(sorted(findings, key=lambda item: item.evidence[2], reverse=True))
