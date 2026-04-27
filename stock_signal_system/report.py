from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

from stock_signal_system.models import IndustrySignal, StockRecommendation
from stock_signal_system.translation import zh_text


def build_report(
    report_date: date,
    industry_signals: list[IndustrySignal],
    recommendations: list[StockRecommendation],
) -> str:
    lines = [
        f"# 每日選股觀察報告 - {report_date.isoformat()}",
        "",
        "## 資料更新摘要",
        "",
        f"- 分析日期：{report_date.isoformat()}",
        "- 每日流程：先更新 RSS/新聞與市場資料，再依產業訊號、基本面、流動性、技術結構與風險收益比篩選。",
        "- 策略限制：台股上市/上櫃、只做多、波段 3-20 天、每日最多 5 檔觀察名單。",
        "- 模型與回測資料：排除黑天鵝、普漲行情、漲跌停、暫停交易與明顯資料錯誤，避免過擬合。",
        "",
        "## 今日產業訊號",
        "",
    ]

    if not industry_signals:
        lines.append("- 今日未偵測到足夠明確且可對應台股供應鏈的產業訊號。")
    for signal in industry_signals:
        catalysts = "；".join(zh_text(item) for item in signal.catalysts)
        lines.append(
            f"- {zh_text(signal.industry)}: 訊號分數 {signal.score:.1f}，證據 {signal.evidence_count} 則。催化因素：{catalysts}"
        )

    lines.extend(["", "## 篩選結果", ""])
    if recommendations:
        actionable = sum(1 for item in recommendations if item.score >= 60)
        watch_only = len(recommendations) - actionable
        lines.append(f"- 今日輸出觀察名單：{len(recommendations)} 檔，其中 {actionable} 檔達基本分數門檻，{watch_only} 檔為等待技術轉強的備選追蹤。")
        lines.append("- 排序依據：產業催化、20日動能、量能、營收成長、營業利益率、自由現金流、負債、本益比、日線蠟燭圖、1H/5M 結構與風險收益比。")
    else:
        lines.append("- 今日沒有符合分數、風險收益比與只做多條件的候選標的。")

    lines.extend(["", "## 值得關注股票", ""])

    if not recommendations:
        lines.append("今日暫不新增觀察標的。")
    else:
        for item in recommendations:
            stock = item.stock
            risk_lines = (
                [f"- {zh_text(risk)}" for risk in item.risks]
                if item.risks
                else ["- 尚未偵測到重大單一風險，但仍需留意大盤、產業與財報事件。"]
            )
            lines.extend(
                [
                    f"### {stock.symbol} {stock.name} - {zh_text(item.rating)} ({item.score:.1f})",
                    "",
                    "**為何值得關注**",
                    "",
                    *[f"- {zh_text(reason)}" for reason in item.reasons],
                    "",
                    "**進場條件**",
                    "",
                    f"- {zh_text(item.entry_plan)}",
                    "",
                    "**停損條件**",
                    "",
                    f"- {zh_text(item.stop_loss)}",
                    "",
                    "**出場條件**",
                    "",
                    f"- {zh_text(item.exit_plan)}",
                    "",
                    "**主要風險**",
                    "",
                    *risk_lines,
                    "",
                ]
            )

    return "\n".join(lines)


def save_report(report_dir: Path, report_date: date, content: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"stock_signals_{report_date.isoformat()}.md"
    path.write_text(content, encoding="utf-8")
    return path


def save_report_html(report_dir: Path, report_date: date, content: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"stock_signals_{report_date.isoformat()}.html"
    title = f"每日選股觀察報告 - {report_date.isoformat()}"
    path.write_text(markdown_to_html(content, title=title), encoding="utf-8")
    return path


def markdown_to_html(markdown: str, title: str) -> str:
    body_lines = []
    in_list = False
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            continue
        if line.startswith("# "):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "):
            if not in_list:
                body_lines.append("<ul>")
                in_list = True
            body_lines.append(f"<li>{_inline_markdown(line[2:])}</li>")
        else:
            if in_list:
                body_lines.append("</ul>")
                in_list = False
            body_lines.append(f"<p>{_inline_markdown(line)}</p>")
    if in_list:
        body_lines.append("</ul>")

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; background: #f6f7f9; color: #202124; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif; line-height: 1.7; }}
    main {{ max-width: 880px; margin: 0 auto; padding: 28px 18px 56px; background: #fff; min-height: 100vh; }}
    h1 {{ font-size: 28px; margin: 0 0 20px; }}
    h2 {{ font-size: 21px; margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #e5e7eb; }}
    h3 {{ font-size: 18px; margin: 22px 0 8px; }}
    p {{ margin: 8px 0; }}
    ul {{ padding-left: 22px; margin: 8px 0 16px; }}
    li {{ margin: 5px 0; }}
    strong {{ font-weight: 700; }}
    @media (max-width: 560px) {{ main {{ padding: 20px 14px 44px; }} h1 {{ font-size: 23px; }} h2 {{ font-size: 19px; }} }}
  </style>
</head>
<body>
  <main>
    {"".join(body_lines)}
  </main>
</body>
</html>
"""


def public_report_url(base_url: str | None, report_path: Path) -> str | None:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/{report_path.name}"


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
