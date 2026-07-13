from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


# Below this many evaluated recommendations, correlation estimates are too
# noisy to act on (a handful of trades can flip the sign of a correlation).
MIN_SAMPLE_SIZE = 30

SCORE_SNAPSHOT_PATH = Path("reports/score_snapshots.csv")

SCORE_COMPONENTS = (
    "kronos_score",
    "news_score",
    "technical_score",
    "realtime_score",
    "confidence_score",
    "chip_score",
)

# Mirrors the production weights in quant_research_platform/hybrid.py::run_tw_hybrid.
CURRENT_WEIGHTS: dict[str, float] = {
    "kronos_score": 0.35,
    "news_score": 0.15,
    "technical_score": 0.20,
    "realtime_score": 0.10,
    "confidence_score": 0.10,
    "chip_score": 0.10,
}


@dataclass(frozen=True)
class ComponentCorrelation:
    component: str
    correlation: float | None
    current_weight: float


@dataclass(frozen=True)
class WeightDiagnosticsResult:
    sample_size: int
    sufficient: bool
    min_sample_size: int
    correlations: tuple[ComponentCorrelation, ...]
    note: str


def evaluate_weight_diagnostics(
    recommendation_log_path: Path,
    score_snapshot_path: Path,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> WeightDiagnosticsResult:
    """Check whether enough evaluated recommendations exist to say anything
    statistically meaningful about the hybrid_score component weights, and if
    so, report each component's correlation with realized 5-day return.

    This is diagnostic only: it never mutates the production weights in
    hybrid.py. Treat a component with negative or near-zero correlation as a
    candidate for a human to consider down-weighting, not an automatic change.
    """
    trades = _load_evaluated_trades(recommendation_log_path)
    sample_size = len(trades)
    if sample_size < min_sample_size:
        return WeightDiagnosticsResult(
            sample_size=sample_size,
            sufficient=False,
            min_sample_size=min_sample_size,
            correlations=(),
            note=(
                f"樣本數不足（{sample_size}/{min_sample_size}），權重相關性分析暫緩。"
                "累積更多推薦追蹤資料後再評估。"
            ),
        )

    scores_by_key = _load_score_snapshots(score_snapshot_path)
    returns = []
    component_series: dict[str, list[float]] = {name: [] for name in SCORE_COMPONENTS}
    for trade in trades:
        key = (trade["entry_date"], trade["symbol"])
        scores = scores_by_key.get(key)
        if scores is None:
            continue
        returns.append(trade["return_5d"])
        for name in SCORE_COMPONENTS:
            component_series[name].append(scores.get(name, 50.0))

    if len(returns) < min_sample_size:
        return WeightDiagnosticsResult(
            sample_size=len(returns),
            sufficient=False,
            min_sample_size=min_sample_size,
            correlations=(),
            note=(
                f"已評估推薦數足夠，但可對應到分數快照的樣本仍不足"
                f"（{len(returns)}/{min_sample_size}）。需同步啟用分數快照記錄。"
            ),
        )

    correlations = tuple(
        ComponentCorrelation(
            component=name,
            correlation=_pearson_correlation(component_series[name], returns),
            current_weight=CURRENT_WEIGHTS.get(name, 0.0),
        )
        for name in SCORE_COMPONENTS
    )
    return WeightDiagnosticsResult(
        sample_size=len(returns),
        sufficient=True,
        min_sample_size=min_sample_size,
        correlations=correlations,
        note=f"樣本數 {len(returns)} 筆，以下為各分數分量與 5 日實現報酬的相關係數（僅供參考，不會自動套用）。",
    )


def append_score_snapshot(path: Path, entry_date: str, symbol: str, scores: dict[str, float]) -> None:
    """Record the hybrid_score components for a pick at recommendation time,
    so weight diagnostics can later correlate them against realized returns."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["entry_date", "symbol", *SCORE_COMPONENTS]
    is_new = not path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        writer.writerow({"entry_date": entry_date, "symbol": symbol, **scores})


def _load_evaluated_trades(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    trades = []
    with log_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("win") not in {"0", "1"}:
                continue
            return_5d = _to_float(row.get("return_5d"))
            if return_5d is None:
                continue
            trades.append({"entry_date": row.get("entry_date", ""), "symbol": row.get("symbol", ""), "return_5d": return_5d})
    return trades


def _load_score_snapshots(path: Path) -> dict[tuple[str, str], dict[str, float]]:
    if not path.exists():
        return {}
    result: dict[tuple[str, str], dict[str, float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("entry_date", ""), row.get("symbol", ""))
            result[key] = {name: _to_float(row.get(name)) or 50.0 for name in SCORE_COMPONENTS}
    return result


def _pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = (var_x * var_y) ** 0.5
    if denom == 0:
        return None
    return cov / denom


def _to_float(value) -> float | None:
    text = str(value if value is not None else "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
