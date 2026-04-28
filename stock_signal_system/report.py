from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

from stock_signal_system.models import ChangeSummary, IndustrySignal, StockRecommendation
from stock_signal_system.translation import zh_text


def build_report(
    report_date: date,
    industry_signals: list[IndustrySignal],
    recommendations: list[StockRecommendation],
    change_summary: ChangeSummary | None = None,
    stock_universe_count: int | None = None,
) -> str:
    change_summary = change_summary or ChangeSummary()
    high_priority = [item for item in recommendations if item.score >= 70][:5]
    ranked_watchlist = recommendations[:5]
    new_candidates = [item for item in recommendations if item.status == "新進候選"][:3]
    continuing = [item for item in recommendations if item.status != "新進候選"][:5]
    universe_text = f"{stock_universe_count} 檔" if stock_universe_count is not None else "每日刷新"

    lines = [
        f"# 每日選股觀察報告 - {report_date.isoformat()}",
        "",
        "## 資料更新摘要",
        "",
        f"- 資料日期：{report_date.isoformat()}",
        f"- 股票池：本次由 TWSE/TPEx OpenAPI 重新產生上市與上櫃普通股快照，共 {universe_text}；未使用範例股票池。",
        "- 策略：只做多、3-20 天波段；以新聞/政策/輿情產業訊號、基本面、量價、蠟燭圖與 1H/5M 結構共同篩選。",
        "- 排名：加入新鮮度與變化率，避免同一批股票只因舊分數長期霸榜。",
        "",
        "## 今日變化",
        "",
        f"- 新進候選：{_names(change_summary.new_symbols) or '無明顯新進標的'}",
        f"- 移出前次名單：{_names(change_summary.removed_symbols) or '無'}",
        f"- 分數改善：{_names(change_summary.improved_symbols) or '無明顯改善'}",
        f"- 分數轉弱：{_names(change_summary.weakened_symbols) or '無明顯轉弱'}",
        f"- 新增產業訊號：{_names(change_summary.industry_new) or '無'}",
        "",
        "## 今日產業訊號",
        "",
    ]

    if not industry_signals:
        lines.append("- 今日未取得足夠有效產業訊號，暫不擴大追價。")
    for signal in industry_signals:
        catalysts = "；".join(zh_text(item) for item in signal.catalysts)
        lines.append(
            f"- {zh_text(signal.industry)}：訊號分數 {signal.score:.1f}，證據 {signal.evidence_count} 則。催化因素：{catalysts}"
        )

    actionable = sum(1 for item in recommendations if item.score >= 60)
    watch_only = len(recommendations) - actionable
    lines.extend(
        [
            "",
            "## 篩選結果",
            "",
            f"- 今日候選股：{len(recommendations)} 檔；可行動觀察 {actionable} 檔，續觀察 {watch_only} 檔。",
            f"- 高優先觀察：{len(high_priority)} 檔；新進候選：{len(new_candidates[:3])} 檔；續抱/續觀察：{len(continuing[:5])} 檔。",
            "- 若高優先觀察不足 3 檔，代表今日沒有足夠標的同時達到產業、量價與風險門檻，系統會保守列出前 5 名觀察清單而不強行給買進結論。",
        ]
    )

    lines.extend(["", "## 高優先觀察 3-5 檔", ""])
    _append_summary_list(lines, high_priority)

    lines.extend(["", "## 前 5 名觀察清單", ""])
    _append_summary_list(lines, ranked_watchlist)

    lines.extend(["", "## 新進候選 1-3 檔", ""])
    _append_summary_list(lines, new_candidates[:3])

    lines.extend(["", "## 續抱/續觀察", ""])
    _append_summary_list(lines, continuing[:5])

    lines.extend(["", "## 個股分析", ""])
    if not recommendations:
        lines.append("今日沒有股票同時符合產業訊號、量價、基本面與只做多策略門檻。")
    else:
        for item in recommendations:
            stock = item.stock
            risk_lines = [f"- {zh_text(risk)}" for risk in item.risks] if item.risks else ["- 仍需留意大盤、匯率與產業新聞變化。"]
            lines.extend(
                [
                    f"### {stock.symbol} {stock.name} - {zh_text(item.rating)} ({item.score:.1f})",
                    "",
                    f"- 產業：{zh_text(stock.industry)}",
                    f"- 今日狀態：{item.status}",
                    f"- 分數變化：{_score_delta(item.score_delta)}；排名參考：{_rank_delta(item.rank_delta)}",
                    f"- 新鮮度/變化率：{item.freshness_score:+.1f} / {item.change_score:+.1f}",
                    "",
                    "**值得關注原因**",
                    "",
                    *[f"- {zh_text(reason)}" for reason in item.reasons[:8]],
                    "",
                    "**進場計畫**",
                    "",
                    f"- {zh_text(item.entry_plan)}",
                    "",
                    "**停損計畫**",
                    "",
                    f"- {zh_text(item.stop_loss)}",
                    "",
                    "**出場計畫**",
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
    main {{ max-width: 920px; margin: 0 auto; padding: 28px 18px 56px; background: #fff; min-height: 100vh; }}
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


def _append_summary_list(lines: list[str], items: list[StockRecommendation]) -> None:
    if not items:
        lines.append("- 無符合條件標的。")
        return
    for item in items:
        stock = item.stock
        lines.append(
            f"- {stock.symbol} {stock.name}：{item.score:.1f} 分，{item.status}，"
            f"分數變化 {_score_delta(item.score_delta)}，理由：{zh_text(item.reasons[0]) if item.reasons else '無'}"
        )


def _score_delta(value: float | None) -> str:
    if value is None:
        return "新進"
    return f"{value:+.1f}"


def _rank_delta(value: int | None) -> str:
    if value is None:
        return "新進"
    return f"前次第 {value} 名"


def _names(values: tuple[str, ...]) -> str:
    return "、".join(values)


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
