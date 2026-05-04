from __future__ import annotations

from datetime import date
from pathlib import Path

from quant_research_platform.backtest import BacktestResult
from quant_research_platform.signals import ForecastSignal


def build_markdown_report(signals: list[ForecastSignal], result: BacktestResult, run_date: date) -> str:
    lines = [
        f"# Quant Research Platform Report - {run_date.isoformat()}",
        "",
        "## Signal Ranking",
        "",
        "| Rank | Symbol | Source | Current | Predicted | Expected Return | Confidence |",
        "|---:|---|---|---:|---:|---:|---:|",
    ]
    for rank, item in enumerate(sorted(signals, key=lambda x: x.expected_return, reverse=True), start=1):
        lines.append(
            "| "
            f"{rank} | {item.symbol} | {item.source} | {item.current_close:.2f} | "
            f"{item.predicted_close:.2f} | {item.expected_return:.2%} | {item.confidence:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Portfolio Simulation",
            "",
            "| Symbol | Weight | Expected Return | Confidence |",
            "|---|---:|---:|---:|",
        ]
    )
    for position in result.selected:
        lines.append(
            f"| {position.symbol} | {position.weight:.2%} | {position.expected_return:.2%} | {position.confidence:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Gross expected return: {result.gross_expected_return:.2%}",
            f"- Net expected return after cost: {result.net_expected_return:.2%}",
            f"- Estimated PnL: {result.estimated_pnl:,.2f}",
        ]
    )
    if result.benchmark_return is not None:
        lines.append(f"- Benchmark lookback return: {result.benchmark_return:.2%}")
    return "\n".join(lines) + "\n"


def save_report(output_dir: Path, run_date: date, content: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"quant_research_{run_date.isoformat()}.md"
    path.write_text(content, encoding="utf-8")
    return path
