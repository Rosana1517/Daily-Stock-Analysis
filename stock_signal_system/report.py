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
    title = _markdown_title(content) or f"Stock Signals - {report_date.isoformat()}"
    path.write_text(markdown_to_html(content, title=title), encoding="utf-8")
    return path


def markdown_to_html(markdown: str, title: str) -> str:
    if markdown.startswith("# Hybrid Quant Daily Stock Report"):
        return hybrid_markdown_to_html(markdown, title)

    body_lines = []
    in_list = False
    table_lines: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            body_lines.append("</ul>")
            in_list = False

    def flush_table() -> None:
        if table_lines:
            body_lines.append(_markdown_table_to_html(table_lines))
            table_lines.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            flush_table()
            close_list()
            continue
        if _is_table_line(line):
            close_list()
            table_lines.append(line)
            continue
        flush_table()
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
    body {{ margin: 0; background: #f6f7f9; color: #202124; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif; line-height: 1.7; }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 28px 18px 56px; background: #fff; min-height: 100vh; }}
    h1 {{ font-size: 28px; margin: 0 0 20px; }}
    h2 {{ font-size: 21px; margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #e5e7eb; }}
    h3 {{ font-size: 18px; margin: 22px 0 8px; }}
    p {{ margin: 8px 0; }}
    ul {{ padding-left: 22px; margin: 8px 0 16px; }}
    li {{ margin: 5px 0; }}
    .table-wrap {{ overflow-x: auto; margin: 10px 0 22px; border: 1px solid #e5e7eb; border-radius: 8px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 860px; font-size: 14px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid #edf0f3; text-align: left; vertical-align: top; }}
    th {{ background: #f8fafc; font-weight: 700; color: #111827; }}
    tr:nth-child(even) td {{ background: #fbfcfd; }}
    tr:last-child td {{ border-bottom: 0; }}
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


def _markdown_title(markdown: str) -> str | None:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _is_table_line(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def _markdown_table_to_html(lines: list[str]) -> str:
    rows = [_split_table_row(line) for line in lines]
    if len(rows) >= 2 and all(_is_separator_cell(cell) for cell in rows[1]):
        header = rows[0]
        body = rows[2:]
    else:
        header = []
        body = rows
    parts = ['<div class="table-wrap"><table>']
    if header:
        parts.append("<thead><tr>")
        parts.extend(f"<th>{_inline_markdown(cell)}</th>" for cell in header)
        parts.append("</tr></thead>")
    parts.append("<tbody>")
    for row in body:
        parts.append("<tr>")
        parts.extend(f"<td>{_inline_markdown(cell)}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_cell(cell: str) -> bool:
    normalized = cell.strip().replace(":", "").replace("-", "")
    return normalized == ""


def hybrid_markdown_to_html(markdown: str, title: str) -> str:
    data = _parse_hybrid_markdown(markdown)
    top_rows = data.get("Top Ranking", [])
    industries = data.get("RSS Industry Signals", [])
    groups = data.get("Industry Groups", [])
    notes = _section_bullets(markdown, "Investment Notes")
    portfolio = _section_bullets(markdown, "Portfolio Simulation")
    news = _section_bullets(markdown, "News Feed")
    featured = top_rows[0] if top_rows else {}
    sentiment = _float_text(featured.get("Hybrid", "50"))
    gauge = max(0, min(100, sentiment))
    grouped_cards = groups[:8]

    industry_cards = "".join(
        f"""
        <article class="industry-card">
          <div>
            <span class="eyebrow">{html.escape(row.get('Bias', '觀察'))}</span>
            <h3>{html.escape(row.get('Industry', 'Market'))}</h3>
            <p>{html.escape(row.get('Symbols', ''))}</p>
          </div>
          <strong>{html.escape(row.get('Average Hybrid', row.get('RSS Score', '50')))}</strong>
        </article>
        """
        for row in grouped_cards
    )
    task_cards = "".join(
        f"""
        <li>
          <span>{html.escape(row.get('Industry', 'Market'))}</span>
          <b>{html.escape(row.get('RSS Score', '50'))}</b>
          <small>{html.escape(row.get('Key Catalyst', 'No catalyst'))}</small>
        </li>
        """
        for row in industries[:6]
    )
    ranking_rows = "".join(
        f"""
        <tr>
          <td>{index}</td>
          <td><b>{html.escape(row.get('Symbol', ''))}</b><small>{html.escape(row.get('Name', ''))}</small></td>
          <td>{html.escape(row.get('Industry', ''))}</td>
          <td><strong>{html.escape(row.get('Hybrid', ''))}</strong></td>
          <td>{html.escape(row.get('Kronos', ''))}</td>
          <td>{html.escape(row.get('Realtime', ''))}</td>
          <td>{html.escape(row.get('Action', ''))}</td>
        </tr>
        """
        for index, row in enumerate(top_rows[:12], start=1)
    )
    note_cards = "".join(f"<li>{_inline_markdown(item)}</li>" for item in notes[:5])
    portfolio_items = "".join(f"<li>{_inline_markdown(item)}</li>" for item in portfolio[:4])
    news_items = "".join(f"<li>{_inline_markdown(item)}</li>" for item in news[:6])

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #05070c;
      --panel: #0d1019;
      --panel-2: #121725;
      --line: #1f6d8e;
      --line-soft: rgba(0, 209, 255, .24);
      --text: #f8fbff;
      --muted: #8f9ab3;
      --cyan: #00d1ff;
      --green: #00ff9d;
      --amber: #ffb000;
      --red: #ff4d86;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 78% 12%, rgba(0, 209, 255, .12), transparent 28%),
        linear-gradient(135deg, #05070c 0%, #080b12 48%, #030409 100%);
      color: var(--text);
      font-family: "Microsoft JhengHei UI", "Noto Sans TC", "Segoe UI", sans-serif;
      line-height: 1.65;
    }}
    main {{ width: min(1180px, calc(100vw - 32px)); margin: 28px auto 56px; }}
    .topbar {{ display: grid; grid-template-columns: 1fr auto; gap: 12px; padding: 6px 0 18px; border-bottom: 1px solid rgba(255,255,255,.08); }}
    .search {{ height: 46px; border: 1px solid rgba(255,255,255,.12); border-radius: 8px; background: #11131d; color: #64708a; display: flex; align-items: center; padding: 0 16px; }}
    .btn {{ border: 0; border-radius: 8px; background: linear-gradient(135deg, #00b9e8, #006b8c); color: #00131d; font-weight: 800; padding: 0 28px; }}
    .layout {{ display: grid; grid-template-columns: 280px 1fr 276px; gap: 18px; margin-top: 14px; }}
    .panel {{ background: linear-gradient(180deg, rgba(18,23,37,.96), rgba(9,11,18,.96)); border: 1px solid rgba(64, 177, 228, .28); border-radius: 12px; box-shadow: 0 0 0 1px rgba(0,0,0,.45), 0 18px 55px rgba(0,0,0,.35); }}
    .side {{ padding: 14px; position: sticky; top: 16px; height: fit-content; }}
    .side h2, .section-title {{ margin: 0 0 14px; font-size: 15px; letter-spacing: .04em; }}
    .task-list {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }}
    .task-list li {{ border: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.03); border-radius: 8px; padding: 12px; position: relative; }}
    .task-list span {{ display: block; font-weight: 800; color: #fff; }}
    .task-list b {{ position: absolute; right: 12px; top: 12px; color: var(--amber); }}
    .task-list small {{ display: block; color: var(--muted); margin-top: 6px; max-height: 42px; overflow: hidden; }}
    .hero {{ padding: 22px 18px; min-height: 250px; }}
    .ticker {{ display: flex; gap: 14px; align-items: baseline; flex-wrap: wrap; }}
    .ticker h1 {{ margin: 0; font-size: 30px; letter-spacing: 0; }}
    .ticker .price {{ color: var(--green); font-size: 22px; font-weight: 900; }}
    .meta {{ color: var(--cyan); font-size: 13px; margin-top: 8px; }}
    .insight {{ border-top: 1px solid rgba(255,255,255,.08); margin-top: 18px; padding-top: 18px; }}
    .insight h2 {{ color: var(--cyan); font-size: 13px; text-align: center; letter-spacing: .12em; }}
    .insight p {{ font-size: 17px; font-weight: 700; margin: 8px 0 0; }}
    .gauge {{ padding: 20px; text-align: center; }}
    .gauge-ring {{ width: 174px; height: 174px; margin: 16px auto; border-radius: 50%; background: conic-gradient(var(--green) calc({gauge} * 1%), rgba(255,255,255,.08) 0); display: grid; place-items: center; box-shadow: 0 0 36px rgba(0,255,157,.18); }}
    .gauge-core {{ width: 128px; height: 128px; border-radius: 50%; background: #0c0f18; display: grid; place-items: center; }}
    .gauge strong {{ font-size: 48px; line-height: 1; }}
    .quick-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-top: 16px; }}
    .quick {{ padding: 16px; border: 1px solid rgba(64,177,228,.28); border-radius: 12px; background: #0c0f18; }}
    .quick span {{ color: var(--green); font-size: 13px; font-weight: 800; }}
    .quick b {{ display: block; margin-top: 6px; font-size: 18px; }}
    .strategy {{ margin-top: 18px; padding: 16px; }}
    .strategy ul, .news ul {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }}
    .strategy li, .news li {{ background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.08); border-radius: 8px; padding: 12px 14px; color: #dfe7f5; }}
    .industries {{ margin-top: 18px; padding: 16px; }}
    .industry-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .industry-card {{ display: flex; justify-content: space-between; gap: 12px; border: 1px solid rgba(0,209,255,.18); border-radius: 10px; padding: 14px; background: rgba(4,11,18,.68); }}
    .industry-card h3 {{ margin: 3px 0 4px; font-size: 18px; }}
    .industry-card p {{ margin: 0; color: var(--muted); font-size: 13px; }}
    .industry-card strong {{ color: var(--green); font-size: 22px; }}
    .eyebrow {{ color: var(--cyan); font-size: 11px; font-weight: 900; letter-spacing: .09em; text-transform: uppercase; }}
    .ranking {{ margin-top: 18px; padding: 16px; overflow: hidden; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid rgba(255,255,255,.07); text-align: left; }}
    th {{ color: var(--cyan); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }}
    td small {{ display: block; color: var(--muted); }}
    .news {{ margin-top: 18px; padding: 16px; }}
    @media (max-width: 980px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .side {{ position: static; }}
      .industry-grid, .quick-grid {{ grid-template-columns: 1fr; }}
      .topbar {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="topbar"><div class="search">輸入股票代碼，如 2330.TW、3661.TW、AAPL</div><button class="btn">分析</button></div>
    <div class="layout">
      <aside class="panel side">
        <h2>↻ RSS 產業訊號</h2>
        <ul class="task-list">{task_cards}</ul>
      </aside>
      <section>
        <article class="panel hero">
          <div class="ticker">
            <h1>{html.escape(featured.get('Name', 'Market'))}</h1>
            <span class="price">{html.escape(featured.get('Hybrid', '50'))}</span>
            <span>{html.escape(featured.get('Kronos', '0%'))}</span>
          </div>
          <div class="meta">{html.escape(featured.get('Symbol', ''))} · {html.escape(featured.get('Industry', ''))} · {html.escape(title.split(' - ')[-1])}</div>
          <div class="insight">
            <h2>KEY INSIGHTS</h2>
            <p>RSS 產業訊號、Kronos 預測、技術型態與即時盤勢共同形成 hybrid score。當分數高於 70 且預測報酬為正，列入買進觀察；若分數低於 50 或預測轉負，採取暫避或減碼。</p>
          </div>
        </article>
        <div class="quick-grid">
          <div class="quick"><span>操作建議</span><b>{html.escape(featured.get('Action', '觀察'))}</b></div>
          <div class="quick"><span>盤中狀態</span><b>{html.escape(featured.get('Realtime', '持平'))}</b></div>
        </div>
        <article class="panel industries"><h2 class="section-title">STRATEGY MAP 產業分類</h2><div class="industry-grid">{industry_cards}</div></article>
        <article class="panel strategy"><h2 class="section-title">STRATEGY POINTS 買入賣出策略</h2><ul>{note_cards}</ul></article>
        <article class="panel ranking"><h2 class="section-title">STOCK RANKING 股票排序</h2><table><thead><tr><th>#</th><th>股票</th><th>產業</th><th>Hybrid</th><th>Kronos</th><th>盤勢</th><th>策略</th></tr></thead><tbody>{ranking_rows}</tbody></table></article>
        <article class="panel news"><h2 class="section-title">NEWS FEED 相關資訊</h2><ul>{news_items}</ul></article>
      </section>
      <aside class="panel gauge">
        <h2>Market Sentiment</h2>
        <div class="gauge-ring"><div class="gauge-core"><strong>{gauge:.0f}</strong></div></div>
        <p>{'強勢' if gauge >= 70 else '中性' if gauge >= 50 else '偏弱'}</p>
        <ul class="task-list">{portfolio_items}</ul>
      </aside>
    </div>
  </main>
</body>
</html>
"""


def _parse_hybrid_markdown(markdown: str) -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = {}
    current_heading = ""
    table_lines: list[str] = []
    for raw in markdown.splitlines() + [""]:
        line = raw.strip()
        if line.startswith("## "):
            if table_lines:
                tables[current_heading] = _table_lines_to_dicts(table_lines)
                table_lines = []
            current_heading = line[3:]
            continue
        if _is_table_line(line):
            table_lines.append(line)
        elif table_lines:
            tables[current_heading] = _table_lines_to_dicts(table_lines)
            table_lines = []
    return tables


def _table_lines_to_dicts(lines: list[str]) -> list[dict[str, str]]:
    rows = [_split_table_row(line) for line in lines]
    if len(rows) < 2:
        return []
    header = rows[0]
    body = rows[2:] if all(_is_separator_cell(cell) for cell in rows[1]) else rows[1:]
    return [dict(zip(header, row)) for row in body]


def _section_bullets(markdown: str, section: str) -> list[str]:
    bullets = []
    active = False
    for line in markdown.splitlines():
        if line.startswith("## "):
            active = line[3:] == section
            continue
        if active and line.startswith("- "):
            bullets.append(line[2:])
    return bullets


def _float_text(value: str) -> float:
    try:
        return float(value.replace("%", "").strip())
    except ValueError:
        return 50.0
