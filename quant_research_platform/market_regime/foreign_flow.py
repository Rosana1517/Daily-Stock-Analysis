from __future__ import annotations

from collections.abc import Mapping

from .models import SignalScore, clamp_score


def evaluate_foreign_flow(
    foreign_flow: Mapping[str, float] | None = None,
    investment_trust_flow: Mapping[str, float] | None = None,
    dealer_flow: Mapping[str, float] | None = None,
    margin_financing: Mapping[str, float] | None = None,
    short_covering: Mapping[str, float] | None = None,
) -> dict[str, object]:
    foreign_score = _flow_signal("foreign investor flow", foreign_flow)
    trust_score = _flow_signal("investment trust accumulation", investment_trust_flow)
    dealer_score = _flow_signal("dealer behavior", dealer_flow)
    margin_score = _flow_signal("margin financing", margin_financing, positive_is_good=False)
    covering_score = _flow_signal("short covering", short_covering)
    return {
        "foreign_investor_flow": foreign_score,
        "investment_trust_accumulation": trust_score,
        "dealer_behavior": dealer_score,
        "margin_financing": margin_score,
        "short_covering": covering_score,
        "metrics": {
            "foreign_flow": _sum_flow(foreign_flow),
            "investment_trust_flow": _sum_flow(investment_trust_flow),
            "dealer_flow": _sum_flow(dealer_flow),
            "margin_financing": _sum_flow(margin_financing),
            "short_covering": _sum_flow(short_covering),
        },
    }


def _flow_signal(name: str, values: Mapping[str, float] | None, positive_is_good: bool = True) -> SignalScore:
    if not values:
        return SignalScore(name, 50.0, missing=(f"{name} dataset",))
    total = _sum_flow(values)
    direction = 1.0 if positive_is_good else -1.0
    return SignalScore(name, clamp_score(50.0 + direction * total / 80_000_000.0), evidence=(f"net_flow={total:.0f}",))


def _sum_flow(values: Mapping[str, float] | None) -> float:
    if not values:
        return 0.0
    return sum(float(value) for value in values.values())
