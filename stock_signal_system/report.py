from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

from stock_signal_system.analysis_dashboard import DashboardMetrics, build_dashboard_metrics
from stock_signal_system.models import ChangeSummary, IndustrySignal, PriceBar, StockRecommendation
from stock_signal_system.translation import zh_text


def build_report(
    report_date: date,
    industry_signals: list[IndustrySignal],
    recommendations: list[StockRecommendation],
    change_summary: ChangeSummary | None = None,
    stock_universe_count: int | None = None,
    daily_history: dict[str, list[PriceBar]] | None = None,
) -> str:
    change_summary = change_summary or ChangeSummary()
    dashboards = build_dashboard_metrics(recommendations, daily_history)
    high_priority = [item for item in recommendations if item.score >= 70][:5]
    ranked_watchlist = recommendations[:5]
    new_candidates = [item for item in recommendations if item.score_delta is None][:3]
    continuing = [item for item in recommendations if item.score_delta is not None][:5]
    universe_text = f"{stock_universe_count} 檔" if stock_universe_count is not None else "上市/上櫃股票池"

    lines = [
        f"# 每日選股觀察報告 - {report_date.isoformat()}",
        "",
        "## 今日資料概況",
        "",
        f"- 資料日期：{report_date.isoformat()}",
        f"- 股票池：TWSE/TPEx OpenAPI 每日更新，納入 {universe_text}。",
        "- 策略框架：只做多、3-20 天波段、日線題材與蠟燭圖、1H 趨勢結構、5M 進場確認。",
        "- 分析方法：RSS/政策/輿情產業訊號、基本面品質、流動性、估值、量價、蠟燭圖、風險報酬、新鮮度與變化率。",
        "",
        "## 今日變化",
        "",
        f"- 新進候選：{_names(change_summary.new_symbols) or '無'}",
        f"- 移出觀察：{_names(change_summary.removed_symbols) or '無'}",
        f"- 分數轉強：{_names(change_summary.improved_symbols) or '無'}",
        f"- 分數轉弱：{_names(change_summary.weakened_symbols) or '無'}",
        f"- 新增產業訊號：{_names(change_summary.industry_new) or '無'}",
        "",
        "## 有效產業訊號",
        "",
    ]

    if not industry_signals:
        lines.append("- 今日沒有足夠乾淨且與產業相關的新聞證據。")
    for signal in industry_signals:
        catalysts = "；".join(zh_text(item) for item in signal.catalysts[:5])
        lines.append(
            f"- {zh_text(signal.industry)}：訊號分數 {signal.score:.1f}，證據 {signal.evidence_count} 則。催化因素：{catalysts or '無明確催化因素'}"
        )

    actionable = sum(1 for item in recommendations if item.score >= 60)
    watch_only = len(recommendations) - actionable
    lines.extend(
        [
            "",
            "## 工作台總覽",
            "",
            f"- 今日候選：{len(recommendations)} 檔；可行動觀察 {actionable} 檔，僅續觀察 {watch_only} 檔。",
            f"- 高優先觀察：{len(high_priority)} 檔；新進候選：{len(new_candidates)} 檔；續抱/續觀察：{len(continuing)} 檔。",
            "",
        ]
    )
    _append_dashboard_table(lines, ranked_watchlist, dashboards)

    lines.extend(["", "## 高優先觀察 3-5 檔", ""])
    _append_summary_list(lines, high_priority)

    lines.extend(["", "## 今日前 5 名觀察", ""])
    _append_summary_list(lines, ranked_watchlist)

    lines.extend(["", "## 新進候選 1-3 檔", ""])
    _append_summary_list(lines, new_candidates[:3])

    lines.extend(["", "## 續抱/續觀察", ""])
    _append_summary_list(lines, continuing[:5])

    lines.extend(["", "## 個股詳細分析", ""])
    if not recommendations:
        lines.append("今日沒有符合最低分數與只做多條件的標的。")
    else:
        for item in recommendations:
            _append_stock_detail(lines, item, dashboards.get(item.stock.symbol))

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
    body_lines: list[str] = []
    in_list = False
    table_rows: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body_lines.append("</ul>")
            in_list = False

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        body_lines.append(_table_to_html(table_rows))
        table_rows = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("|"):
            close_list()
            table_rows.append(line)
            continue
        flush_table()
        if not line:
            close_list()
            continue
        if line.startswith("# "):
            close_list()
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            close_list()
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            close_list()
            body_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- "):
            if not in_list:
                body_lines.append("<ul>")
                in_list = True
            body_lines.append(f"<li>{_inline_markdown(line[2:])}</li>")
        else:
            close_list()
            body_lines.append(f"<p>{_inline_markdown(line)}</p>")
    flush_table()
    close_list()

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --panel: #ffffff;
      --panel-soft: #f8fafc;
      --text: #1f2937;
      --muted: #667085;
      --line: #d9e2ec;
      --accent: #0f766e;
      --accent-soft: #e0f2f1;
      --danger: #b42318;
      --warning: #a15c07;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif;
      line-height: 1.7;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px 18px 56px;
    }}
    h1 {{
      margin: 0 0 18px;
      font-size: 30px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 26px 0 12px;
      padding: 14px 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      font-size: 20px;
    }}
    h3 {{
      margin: 22px 0 10px;
      padding-left: 10px;
      border-left: 4px solid var(--accent);
      font-size: 18px;
    }}
    p, ul, table {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin: 10px 0;
    }}
    p {{ padding: 12px 14px; }}
    ul {{ padding: 12px 16px 12px 34px; }}
    li {{ margin: 4px 0; }}
    strong {{ font-weight: 700; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: var(--panel-soft);
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }}
    tr:last-child td {{ border-bottom: 0; }}
    .report-shell {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 18px;
      box-shadow: 0 12px 32px rgba(15, 23, 42, 0.06);
    }}
    @media (max-width: 700px) {{
      main {{ padding: 18px 10px 44px; }}
      h1 {{ font-size: 23px; }}
      h2 {{ font-size: 18px; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="report-shell">
      {"".join(body_lines)}
    </div>
  </main>
</body>
</html>
"""


def public_report_url(base_url: str | None, report_path: Path) -> str | None:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/{report_path.name}"


def _append_dashboard_table(
    lines: list[str],
    items: list[StockRecommendation],
    dashboards: dict[str, DashboardMetrics],
) -> None:
    if not items:
        lines.append("- 今日無工作台標的。")
        return
    lines.extend(
        [
            "| 標的 | 分數 | 狀態 | 趨勢 | 量比 | 20日動能 | 風險 | 建議部位 |",
            "|---|---:|---|---|---:|---:|---|---|",
        ]
    )
    for item in items:
        metrics = dashboards.get(item.stock.symbol)
        lines.append(
            "| "
            f"{item.stock.symbol} {item.stock.name} | "
            f"{item.score:.1f} | "
            f"{_status(item)} | "
            f"{_trend_label(metrics)} | "
            f"{_ratio_label(metrics)} | "
            f"{_momentum_label(metrics)}"
            f" | {_risk_label(metrics)} | "
            f"{metrics.position_sizing if metrics else 'N/A'} |"
        )


def _append_summary_list(lines: list[str], items: list[StockRecommendation]) -> None:
    if not items:
        lines.append("- 尚無符合此分類的標的。")
        return
    for item in items:
        stock = item.stock
        leading_reason = zh_text(item.reasons[0]) if item.reasons else "符合多因子觀察條件"
        lines.append(f"- {stock.symbol} {stock.name}：{item.score:.1f} 分，{_status(item)}。主要理由：{leading_reason}")


def _append_stock_detail(lines: list[str], item: StockRecommendation, metrics: DashboardMetrics | None) -> None:
    stock = item.stock
    risk_lines = [f"- {zh_text(risk)}" for risk in item.risks] if item.risks else ["- 目前未偵測到明確的單一重大風險，但仍需控管部位。"]
    lines.extend(
        [
            f"### {stock.symbol} {stock.name} - {_rating_label(item.score)} ({item.score:.1f})",
            "",
            f"- 產業：{zh_text(stock.industry)}",
            f"- 今日狀態：{_status(item)}",
            f"- 分數變化：{_score_delta(item.score_delta)}；排名變化：{_rank_delta(item.rank_delta)}",
            f"- 新鮮度/變化率加分：{item.freshness_score:+.1f} / {item.change_score:+.1f}",
            "",
            "**核心結論**",
            "",
            f"- {stock.name} 目前屬於 {_status(item)}，適合以 3-20 天波段觀察，不建議脫離進出場規則追價。",
        ]
    )
    if metrics:
        lines.extend(
            [
                "",
                "**數據視角**",
                "",
                f"- 趨勢結構：{metrics.ma_alignment}，趨勢分數 {metrics.trend_score:.1f}，信心 {metrics.confidence}。",
                f"- 均線/價位：MA5 {_fmt(metrics.ma5)}、MA10 {_fmt(metrics.ma10)}、MA20 {_fmt(metrics.ma20)}；乖離 MA5 {_fmt_pct(metrics.bias_ma5_pct)}。",
                f"- 支撐/壓力：支撐 {_fmt(metrics.support_level)}，壓力 {_fmt(metrics.resistance_level)}，距 20 日高點 {_fmt_pct(metrics.drawdown_from_20d_high_pct)}。",
                f"- 量能/波動：量比 {metrics.volume_ratio:.2f}，20 日動能 {metrics.momentum_20d:+.1f}%，20 日均波動 {_fmt_pct(metrics.volatility_20d_pct)}。",
                f"- 風險等級：{metrics.risk_level}；建議部位：{metrics.position_sizing}",
            ]
        )
    lines.extend(
        [
            "",
            "**投資理由**",
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
            "**風險提醒**",
            "",
            *risk_lines,
        ]
    )
    if metrics:
        lines.extend(["", "**行動檢查清單**", "", *[f"- {step}" for step in metrics.checklist]])
    lines.append("")


def _score_delta(value: float | None) -> str:
    if value is None:
        return "新進"
    return f"{value:+.1f}"


def _status(item: StockRecommendation) -> str:
    return "新進候選" if item.score_delta is None else "續抱/續觀察"


def _rating_label(score: float) -> str:
    if score >= 80:
        return "高優先觀察"
    if score >= 70:
        return "可行動觀察"
    return "續觀察"


def _trend_label(metrics: DashboardMetrics | None) -> str:
    if not metrics:
        return "資料不足"
    return f"{metrics.ma_alignment} / {metrics.trend_score:.1f}"


def _ratio_label(metrics: DashboardMetrics | None) -> str:
    if not metrics:
        return "N/A"
    return f"{metrics.volume_ratio:.2f}"


def _momentum_label(metrics: DashboardMetrics | None) -> str:
    if not metrics:
        return "N/A"
    return f"{metrics.momentum_20d:+.1f}%"


def _risk_label(metrics: DashboardMetrics | None) -> str:
    return metrics.risk_level if metrics else "N/A"


def _rank_delta(value: int | None) -> str:
    if value is None:
        return "新進"
    if value > 0:
        return f"上升 {value} 名"
    if value < 0:
        return f"下降 {abs(value)} 名"
    return "持平"


def _names(values: tuple[str, ...]) -> str:
    return "、".join(values)


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}"


def _fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:+.1f}%"


def _inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def _table_to_html(rows: list[str]) -> str:
    parsed = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows]
    if not parsed:
        return ""
    header = parsed[0]
    body = [row for row in parsed[2:] if not _is_separator_row(row)]
    header_html = "".join(f"<th>{_inline_markdown(cell)}</th>" for cell in header)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{_inline_markdown(cell)}</td>" for cell in row) + "</tr>" for row in body
    )
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"


def _is_separator_row(row: list[str]) -> bool:
    return all(set(cell.replace(":", "").strip()) <= {"-"} for cell in row)
