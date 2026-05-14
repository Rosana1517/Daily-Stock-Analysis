from __future__ import annotations

import html
from datetime import date
from pathlib import Path

from stock_signal_system.models import PortfolioAssessment
from stock_signal_system.report import markdown_to_html


def build_portfolio_report(report_date: date, assessments: list[PortfolioAssessment]) -> str:
    total_value = sum(item.market_value for item in assessments)
    high_risk = [item for item in assessments if item.action in {"減碼觀察", "賣出/停損", "賣出或等待重新轉強"}]
    lines = [
        f"# 每日持倉健檢 - {report_date.isoformat()}",
        "",
        "## 總覽",
        "",
        f"- 持倉檔數：{len(assessments)}",
        f"- 估計市值：{total_value:,.0f}",
        f"- 需要處理/提高警戒：{len(high_risk)}",
        "- 判讀來源：持倉成本、產業訊號、公司基本面、K 線/均線與停損停利價位。",
        "- 這是交易輔助，不是保證漲跌；隔日偏向代表風險方向與勝率傾斜。",
        "",
        "## 持倉決策",
        "",
    ]

    if not assessments:
        lines.append("- 尚未建立持倉資料。")
        return "\n".join(lines)

    for item in assessments:
        position = item.position
        lines.extend(
            [
                f"### {position.symbol} {position.name} - {item.action} ({item.score:.1f})",
                "",
                f"- 隔日偏向：{item.next_day_bias}",
                f"- 帳面損益：{item.unrealized_return_pct:.2f}%",
                f"- 市值：{item.market_value:,.0f}",
                "",
                "**續抱理由**",
                "",
                *[f"- {reason}" for reason in item.reasons],
                "",
                "**反轉/賣出風險**",
                "",
                *([f"- {risk}" for risk in item.risks] or ["- 暫無重大風險，但仍需依停損與趨勢變化控管。"]),
                "",
                "**觀察價位**",
                "",
                *[f"- {level}" for level in item.watch_levels],
                "",
            ]
        )
    return "\n".join(lines)


def save_portfolio_report(report_dir: Path, report_date: date, content: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"portfolio_signals_{report_date.isoformat()}.md"
    path.write_text(content, encoding="utf-8")
    return path


def save_portfolio_report_html(report_dir: Path, report_date: date, content: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"portfolio_signals_{report_date.isoformat()}.html"
    title = f"每日持倉健檢 - {html.escape(report_date.isoformat())}"
    path.write_text(markdown_to_html(content, title=title), encoding="utf-8")
    return path
