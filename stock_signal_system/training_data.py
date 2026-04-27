from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median
from typing import Mapping

from stock_signal_system.models import PriceBar


@dataclass(frozen=True)
class TrainingDataPolicy:
    black_swan_abs_market_return: float = 0.07
    broad_rally_positive_ratio: float = 0.80
    broad_rally_median_return: float = 0.03
    min_cross_section_count: int = 5
    purge_before_days: int = 1
    purge_after_days: int = 3
    exclude_tags: tuple[str, ...] = (
        "black_swan",
        "broad_rally",
        "limit_up_down",
        "halt",
        "extraordinary_event",
        "data_error",
    )


@dataclass(frozen=True)
class TrainingSample:
    symbol: str
    sample_date: date
    features: Mapping[str, float]
    label: float
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DroppedTrainingSample:
    sample: TrainingSample
    reasons: tuple[str, ...]


def daily_return_matrix(history: Mapping[str, list[PriceBar]]) -> dict[date, dict[str, float]]:
    by_date: dict[date, dict[str, float]] = {}
    for symbol, bars in history.items():
        ordered = sorted(bars, key=lambda bar: bar.date)
        for previous, current in zip(ordered, ordered[1:]):
            if previous.close <= 0:
                continue
            by_date.setdefault(current.date, {})[symbol] = current.close / previous.close - 1
    return by_date


def detect_dirty_training_dates(
    history: Mapping[str, list[PriceBar]],
    market_symbol: str | None = None,
    policy: TrainingDataPolicy | None = None,
) -> dict[date, tuple[str, ...]]:
    policy = policy or TrainingDataPolicy()
    returns_by_date = daily_return_matrix(history)
    dirty: dict[date, tuple[str, ...]] = {}

    for trading_date, returns in returns_by_date.items():
        reasons: list[str] = []
        market_return = returns.get(market_symbol) if market_symbol else None
        values = list(returns.values())

        if market_return is not None and abs(market_return) >= policy.black_swan_abs_market_return:
            reasons.append("black_swan_market_move")
        elif len(values) >= policy.min_cross_section_count and abs(median(values)) >= policy.black_swan_abs_market_return:
            reasons.append("black_swan_cross_section_move")

        if len(values) >= policy.min_cross_section_count:
            positive_ratio = sum(1 for value in values if value > 0) / len(values)
            if positive_ratio >= policy.broad_rally_positive_ratio and median(values) >= policy.broad_rally_median_return:
                reasons.append("broad_rally_market")

        if reasons:
            dirty[trading_date] = tuple(reasons)

    return dirty


def purge_date_window(
    dirty_dates: Mapping[date, tuple[str, ...]],
    policy: TrainingDataPolicy | None = None,
) -> dict[date, tuple[str, ...]]:
    policy = policy or TrainingDataPolicy()
    purged: dict[date, set[str]] = {}
    for dirty_date, reasons in dirty_dates.items():
        for offset in range(-policy.purge_before_days, policy.purge_after_days + 1):
            target_date = dirty_date + timedelta(days=offset)
            purged.setdefault(target_date, set()).update(reasons)
            if offset != 0:
                purged[target_date].add("purged_event_window")
    return {item_date: tuple(sorted(reasons)) for item_date, reasons in sorted(purged.items())}


def filter_training_samples(
    samples: list[TrainingSample],
    dirty_dates: Mapping[date, tuple[str, ...]],
    policy: TrainingDataPolicy | None = None,
) -> tuple[list[TrainingSample], list[DroppedTrainingSample]]:
    policy = policy or TrainingDataPolicy()
    purged_dates = purge_date_window(dirty_dates, policy)
    clean: list[TrainingSample] = []
    dropped: list[DroppedTrainingSample] = []

    for sample in samples:
        reasons: list[str] = []
        tag_hits = sorted(set(sample.tags).intersection(policy.exclude_tags))
        if tag_hits:
            reasons.extend(f"tag:{tag}" for tag in tag_hits)
        if sample.sample_date in purged_dates:
            reasons.extend(purged_dates[sample.sample_date])

        if reasons:
            dropped.append(DroppedTrainingSample(sample=sample, reasons=tuple(sorted(set(reasons)))))
        else:
            clean.append(sample)

    return clean, dropped
