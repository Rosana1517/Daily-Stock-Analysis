from __future__ import annotations

from pathlib import Path

from .models import TradeReviewReport


def build_review_markdown(report: TradeReviewReport) -> str:
    title_date = report.report_date.isoformat() if report.report_date else "latest"
    lines = [
        f"# Trade Review - {title_date}",
        "",
        "## Summary",
        f"- Reviewed trades: {report.metadata.get('trade_count', len(report.reviewed_trades))}",
        f"- Missed runners: {len(report.missed_runners)}",
        f"- Alpha decay alerts: {len(report.alpha_decay_alerts)}",
        "",
        "## Setup Performance",
        "| Setup | Trades | Win Rate | Avg Return | Payoff | Alert |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for stat in report.setup_stats:
        lines.append(
            f"| {stat.setup} | {stat.trades} | {stat.win_rate:.1%} | {stat.average_return:.2%} | {stat.payoff_ratio:.2f} | {stat.alert} |"
        )
    lines.extend(["", "## Findings"])
    for reviewed in report.reviewed_trades:
        for finding in reviewed.findings:
            lines.append(f"- {reviewed.trade.symbol}: [{finding.severity}] {finding.message} ({'; '.join(finding.evidence)})")
    for finding in report.missed_runners + report.alpha_decay_alerts + report.market_behavior_shifts:
        lines.append(f"- [{finding.severity}] {finding.message} ({'; '.join(finding.evidence)})")
    if lines[-1] == "## Findings":
        lines.append("- No review findings.")
    return "\n".join(lines)


def save_review_markdown(path: Path, report: TradeReviewReport) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_review_markdown(report), encoding="utf-8")
    return path
