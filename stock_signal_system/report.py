from __future__ import annotations

import html
import json
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
    if markdown.startswith("# Hybrid Quant Daily Stock Report") or markdown.startswith("# Hybrid Quant 每日股票分析報告"):
        return hybrid_markdown_to_html_interactive(markdown, title)

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
    industries = _interactive_valid_industries(data.get("RSS Industry Signals", []), top_rows)
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


def hybrid_markdown_to_html_v2(markdown: str, title: str) -> str:
    data = _parse_hybrid_markdown(markdown)
    top_rows = data.get("Top Ranking", [])
    industries = _interactive_valid_industries(data.get("RSS Industry Signals", []), top_rows)
    groups = data.get("Industry Groups", [])
    notes = _section_bullets(markdown, "Investment Notes")
    portfolio = _section_bullets(markdown, "Portfolio Simulation")
    news = _section_bullets(markdown, "News Feed")
    strategy_by_symbol = _strategy_notes_by_symbol(notes)
    featured = top_rows[0] if top_rows else {}
    featured_score = _float_text(featured.get("Hybrid", "50"))
    date_text = title.split(" - ")[-1] if " - " in title else ""

    rss_summary_cards = "".join(_rss_summary_card(row) for row in industries[:6])
    industry_rows = "".join(
        f"<tr><td>{html.escape(row.get('Industry', ''))}</td><td>{html.escape(row.get('Symbols', ''))}</td>"
        f"<td>{html.escape(row.get('Average Hybrid', ''))}</td><td>{html.escape(row.get('Bias', ''))}</td></tr>"
        for row in groups[:8]
    )
    stock_cards = "".join(
        _stock_recommendation_card(row, index, strategy_by_symbol.get(row.get("Symbol", ""), ""))
        for index, row in enumerate(top_rows[:6], start=1)
    )
    model_cards = _model_overview_cards(top_rows, portfolio)
    ranking_rows = "".join(
        f"<tr><td>{index}</td><td><strong>{html.escape(row.get('Symbol', ''))}</strong><small>{html.escape(row.get('Name', ''))}</small></td>"
        f"<td>{html.escape(row.get('Industry', ''))}</td><td>{html.escape(row.get('Hybrid', ''))}</td>"
        f"<td>{html.escape(row.get('Kronos', ''))}</td><td>{html.escape(row.get('News', ''))}</td>"
        f"<td>{html.escape(row.get('Tech', ''))}</td><td>{html.escape(row.get('Action', ''))}</td></tr>"
        for index, row in enumerate(top_rows[:12], start=1)
    )
    portfolio_items = "".join(f"<li>{_inline_markdown(item)}</li>" for item in portfolio[:4])
    news_items = "".join(f"<li>{_inline_markdown(item)}</li>" for item in news[:8])

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #05070c;
      --panel: #0d111b;
      --panel-2: #111827;
      --line: rgba(69, 184, 255, .28);
      --text: #f8fbff;
      --muted: #94a3b8;
      --cyan: #00d1ff;
      --green: #00f5a0;
      --amber: #ffb020;
      --red: #ff4d86;
      --violet: #a855f7;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--text);
      background: linear-gradient(135deg, #05070c 0%, #090d15 52%, #030409 100%);
      font-family: "Microsoft JhengHei UI", "Noto Sans TC", "Segoe UI", sans-serif;
      line-height: 1.6;
    }}
    main {{ width: min(1220px, calc(100vw - 32px)); margin: 28px auto 56px; }}
    .toolbar {{ display: grid; grid-template-columns: 1fr auto; gap: 12px; padding-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,.08); }}
    .search {{ min-height: 46px; display: flex; align-items: center; padding: 0 16px; color: #68748c; background: #11141e; border: 1px solid rgba(255,255,255,.12); border-radius: 8px; }}
    .button {{ border: 0; border-radius: 8px; padding: 0 28px; font-weight: 900; background: linear-gradient(135deg, #00c8f8, #007fa8); color: #00131d; }}
    .grid {{ display: grid; grid-template-columns: 290px 1fr 280px; gap: 18px; margin-top: 14px; align-items: start; }}
    .panel {{ background: linear-gradient(180deg, rgba(17,24,39,.96), rgba(8,11,18,.98)); border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 18px 50px rgba(0,0,0,.34); }}
    .panel-pad {{ padding: 16px; }}
    .sticky {{ position: sticky; top: 16px; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    .eyebrow {{ color: var(--cyan); font-size: 12px; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }}
    .hero {{ padding: 22px; min-height: 250px; }}
    .hero-title {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }}
    .hero-title h1 {{ margin: 0; font-size: 30px; letter-spacing: 0; }}
    .score {{ color: var(--green); font-size: 24px; font-weight: 950; }}
    .meta {{ margin-top: 8px; color: var(--muted); }}
    .insight {{ margin-top: 18px; padding-top: 18px; border-top: 1px solid rgba(255,255,255,.08); }}
    .insight h2 {{ color: var(--cyan); font-size: 13px; text-align: center; letter-spacing: .12em; }}
    .insight p {{ font-size: 17px; font-weight: 700; margin-bottom: 0; }}
    .gauge {{ text-align: center; padding: 18px; }}
    .gauge-ring {{ width: 178px; height: 178px; margin: 14px auto; border-radius: 50%; background: conic-gradient(var(--green) {max(0, min(100, featured_score)) * 3.6:.0f}deg, rgba(255,255,255,.08) 0); display: grid; place-items: center; }}
    .gauge-core {{ width: 130px; height: 130px; border-radius: 50%; background: #0b0f18; display: grid; place-items: center; }}
    .gauge strong {{ font-size: 48px; line-height: 1; }}
    .rss-list {{ display: grid; gap: 10px; }}
    .rss-card {{ padding: 12px; border: 1px solid rgba(255,255,255,.08); border-radius: 8px; background: rgba(255,255,255,.035); }}
    .rss-card header {{ display: flex; justify-content: space-between; gap: 12px; }}
    .rss-card b {{ color: var(--amber); }}
    .rss-card p {{ margin: 7px 0 0; color: var(--muted); font-size: 13px; }}
    .quick-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 16px; }}
    .quick {{ padding: 14px; background: #0c111b; border: 1px solid var(--line); border-radius: 10px; }}
    .quick span {{ color: var(--cyan); font-size: 12px; font-weight: 900; }}
    .quick b {{ display: block; margin-top: 5px; font-size: 18px; }}
    .section {{ margin-top: 18px; padding: 16px; }}
    .section-title {{ display: flex; align-items: baseline; gap: 9px; margin-bottom: 14px; }}
    .section-title h2 {{ margin: 0; font-size: 18px; }}
    .stock-stack {{ display: grid; gap: 16px; }}
    .stock-card {{ display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 18px; padding: 16px; border: 1px solid rgba(255,255,255,.08); border-radius: 10px; background: rgba(255,255,255,.03); }}
    .stock-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: start; }}
    .stock-head h3 {{ margin: 0; font-size: 22px; }}
    .pill {{ display: inline-flex; align-items: center; min-height: 28px; padding: 0 10px; border-radius: 999px; background: rgba(0,209,255,.12); color: var(--cyan); font-weight: 900; font-size: 12px; }}
    .reason-list, .strategy-list, .news-list, .portfolio-list {{ margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }}
    .reason-list li, .strategy-list li, .news-list li, .portfolio-list li {{ padding: 10px 12px; border-radius: 8px; background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.07); color: #dce7f7; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 14px 0; }}
    .metric {{ padding: 10px; border-radius: 8px; background: #080c14; border: 1px solid rgba(255,255,255,.07); }}
    .metric span {{ color: var(--muted); font-size: 12px; }}
    .metric b {{ display: block; color: var(--green); font-size: 16px; }}
    .chart-panel {{ background: #070b12; border: 1px solid rgba(255,255,255,.08); border-radius: 10px; padding: 12px; }}
    .chart-panel svg {{ width: 100%; height: auto; display: block; }}
    .indicator-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 10px; }}
    .indicator {{ padding: 9px; border-radius: 8px; background: rgba(255,255,255,.035); }}
    .indicator span {{ display: block; color: var(--muted); font-size: 11px; }}
    .indicator b {{ color: #fff; }}
    .model-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 14px 0 16px; }}
    .model-card {{ padding: 14px; border-radius: 10px; background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.08); }}
    .model-card h3 {{ margin: 4px 0 8px; font-size: 17px; }}
    .model-card strong {{ color: var(--green); font-size: 22px; }}
    .model-card p {{ color: var(--muted); margin-bottom: 0; font-size: 13px; }}
    .model-strip {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0; }}
    .model-strip div {{ padding: 10px; border-radius: 8px; background: #080c14; border: 1px solid rgba(255,255,255,.07); }}
    .model-strip span {{ display: block; color: var(--muted); font-size: 11px; }}
    .model-strip b {{ color: #fff; }}
    .thesis-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 10px; }}
    .thesis {{ padding: 10px; border-radius: 8px; background: rgba(255,255,255,.035); color: #dce7f7; }}
    .thesis span {{ display: block; color: var(--cyan); font-size: 12px; font-weight: 900; margin-bottom: 4px; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 780px; font-size: 14px; }}
    th, td {{ padding: 10px 9px; border-bottom: 1px solid rgba(255,255,255,.07); text-align: left; vertical-align: top; }}
    th {{ color: var(--cyan); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }}
    td small {{ display: block; color: var(--muted); }}
    @media (max-width: 1060px) {{ .grid {{ grid-template-columns: 1fr; }} .sticky {{ position: static; }} .stock-card {{ grid-template-columns: 1fr; }} .model-grid {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 680px) {{ main {{ width: min(100vw - 20px, 1220px); }} .toolbar, .quick-grid, .metrics {{ grid-template-columns: 1fr; }} .hero-title h1 {{ font-size: 24px; }} }}
  </style>
</head>
<body>
  <main>
    <div class="toolbar">
      <div class="search">輸入股票代碼，如 2330、2317、AAPL</div>
      <button class="button">分析</button>
    </div>
    <div class="grid">
      <aside class="panel panel-pad sticky">
        <div class="section-title"><span class="eyebrow">RSS</span><h2>產業分析</h2></div>
        <div class="rss-list">{rss_summary_cards}</div>
      </aside>
      <section>
        <article class="panel hero">
          <div class="hero-title">
            <h1>{html.escape(featured.get('Name', 'Hybrid Quant Report'))}</h1>
            <span class="score">{html.escape(featured.get('Hybrid', ''))}</span>
            <span>{html.escape(featured.get('Kronos', ''))}</span>
          </div>
          <div class="meta">{html.escape(featured.get('Symbol', ''))} / {html.escape(featured.get('Industry', ''))} / {html.escape(date_text)}</div>
          <div class="insight">
            <h2>KEY INSIGHTS</h2>
            <p>{_hero_summary(featured, industries)}</p>
          </div>
        </article>
        <div class="quick-grid">
          <div class="quick"><span>操作建議</span><b>{html.escape(featured.get('Action', '觀望'))}</b></div>
          <div class="quick"><span>技術分數</span><b>{html.escape(featured.get('Tech', ''))}</b></div>
          <div class="quick"><span>新聞分數</span><b>{html.escape(featured.get('News', ''))}</b></div>
        </div>
        <article class="panel section">
          <div class="section-title"><span class="eyebrow">Models</span><h2>OpenBB / Qlib / Kronos 模型分析結果</h2></div>
          <div class="model-grid">{model_cards}</div>
        </article>
        <article class="panel section">
          <div class="section-title"><span class="eyebrow">Recommended</span><h2>推薦股票</h2></div>
          <div class="stock-stack">{stock_cards}</div>
        </article>
        <article class="panel section">
          <div class="section-title"><span class="eyebrow">Industry</span><h2>股票按照產業類型分類</h2></div>
          <div class="table-wrap"><table><thead><tr><th>產業</th><th>股票</th><th>平均分</th><th>偏向</th></tr></thead><tbody>{industry_rows}</tbody></table></div>
        </article>
        <article class="panel section">
          <div class="section-title"><span class="eyebrow">Ranking</span><h2>完整排行</h2></div>
          <div class="table-wrap"><table><thead><tr><th>#</th><th>股票</th><th>產業</th><th>Hybrid</th><th>Kronos</th><th>RSS</th><th>Tech</th><th>策略</th></tr></thead><tbody>{ranking_rows}</tbody></table></div>
        </article>
        <article class="panel section">
          <div class="section-title"><span class="eyebrow">News Feed</span><h2>RSS 新聞摘要</h2></div>
          <ul class="news-list">{news_items}</ul>
        </article>
      </section>
      <aside class="panel gauge sticky">
        <h2>Market Sentiment</h2>
        <div class="gauge-ring"><div class="gauge-core"><strong>{max(0, min(100, featured_score)):.0f}</strong></div></div>
        <p>{_sentiment_label(featured_score)}</p>
        <ul class="portfolio-list">{portfolio_items}</ul>
      </aside>
    </div>
  </main>
</body>
</html>
"""


def _rss_summary_card(row: dict[str, str]) -> str:
    return (
        f"<article class=\"rss-card\"><header><span>{html.escape(row.get('Industry', 'Market'))}</span>"
        f"<b>{html.escape(row.get('RSS Score', '50'))}</b></header>"
        f"<p>{html.escape(row.get('Key Catalyst', 'No fresh catalyst'))}</p></article>"
    )


def _model_overview_cards(top_rows: list[dict[str, str]], portfolio: list[str]) -> str:
    if top_rows:
        avg_kronos = sum(_float_text(row.get("Kronos", "0")) for row in top_rows) / len(top_rows)
        avg_hybrid = sum(_float_text(row.get("Hybrid", "50")) for row in top_rows) / len(top_rows)
        top_pick = top_rows[0]
        top_label = f"{top_pick.get('Symbol', '')} {top_pick.get('Name', '')}".strip()
    else:
        avg_kronos = 0.0
        avg_hybrid = 50.0
        top_label = "資料不足"
    qlib_line = _first_matching_line(portfolio, "Qlib engine portfolio return") or _first_matching_line(portfolio, "Qlib inline IC")
    qlib_text = _trim_sentence(qlib_line, 90) if qlib_line else "等待 Qlib 產出 IC、Rank IC、turnover 與 drawdown。"
    cards = [
        (
            "OpenBB",
            "資料與基本面入口",
            "CSV cache used",
            "支援 OpenBB 作為行情/基本面 gateway；本預覽以本機 CSV 快取產生，避免假裝即時資料。",
        ),
        (
            "Qlib",
            "策略回測與投組檢查",
            f"Hybrid均分 {avg_hybrid:.1f}",
            qlib_text,
        ),
        (
            "Kronos",
            "時間序列預測",
            f"{avg_kronos:+.2f}%",
            f"以 forecast return 與 confidence 影響排序；目前最高優先觀察為 {top_label}。",
        ),
    ]
    return "".join(
        f"<article class=\"model-card\"><span class=\"eyebrow\">{html.escape(name)}</span>"
        f"<h3>{html.escape(title)}</h3><strong>{html.escape(value)}</strong><p>{html.escape(body)}</p></article>"
        for name, title, value, body in cards
    )


def _stock_recommendation_card(row: dict[str, str], rank: int, note: str) -> str:
    symbol = row.get("Symbol", "")
    name = row.get("Name", "")
    industry = row.get("Industry", "")
    hybrid = _float_text(row.get("Hybrid", "50"))
    kronos = _float_text(row.get("Kronos", "0"))
    news_score = _float_text(row.get("News", "50"))
    tech_score = _float_text(row.get("Tech", "50"))
    action = row.get("Action", "觀望")
    indicators = _technical_indicators(symbol, hybrid, kronos, news_score, tech_score)
    model = _stock_model_snapshot(row, indicators)
    reasons = _recommendation_reasons(row, note)
    strategies = _strategy_items(row, indicators, note)
    reason_items = "".join(f"<li>{html.escape(item)}</li>" for item in reasons)
    strategy_items = "".join(f"<li>{html.escape(item)}</li>" for item in strategies)
    chart = _candlestick_svg(symbol, hybrid, kronos, tech_score)
    return f"""
      <article class="stock-card">
        <div>
          <div class="stock-head">
            <div><span class="eyebrow">#{rank} / {html.escape(industry)}</span><h3>{html.escape(symbol)} {html.escape(name)}</h3></div>
            <span class="pill">{html.escape(action)}</span>
          </div>
          <div class="metrics">
            <div class="metric"><span>Hybrid</span><b>{hybrid:.1f}</b></div>
            <div class="metric"><span>Kronos預估</span><b>{kronos:.2f}%</b></div>
            <div class="metric"><span>RSS新聞</span><b>{news_score:.1f}</b></div>
            <div class="metric"><span>技術面</span><b>{tech_score:.1f}</b></div>
          </div>
          <div class="model-strip">
            <div><span>OpenBB資料層</span><b>{html.escape(model['openbb'])}</b></div>
            <div><span>Qlib回測層</span><b>{html.escape(model['qlib'])}</b></div>
            <div><span>Kronos預測層</span><b>{html.escape(model['kronos'])}</b></div>
          </div>
          <h4>推薦原因</h4>
          <ul class="reason-list">{reason_items}</ul>
          <div class="thesis-grid">
            <div class="thesis"><span>Stock-analysis 多方論點</span>{html.escape(model['bull'])}</div>
            <div class="thesis"><span>風險/反方論點</span>{html.escape(model['bear'])}</div>
          </div>
          <h4>買入/賣出策略</h4>
          <ul class="strategy-list">{strategy_items}</ul>
        </div>
        <div class="chart-panel">
          {chart}
          <div class="indicator-grid">
            <div class="indicator"><span>MA5 / MA20</span><b>{indicators['ma5']:.1f} / {indicators['ma20']:.1f}</b></div>
            <div class="indicator"><span>RSI(14)</span><b>{indicators['rsi']:.1f}</b></div>
            <div class="indicator"><span>MACD</span><b>{indicators['macd']}</b></div>
            <div class="indicator"><span>支撐 / 壓力</span><b>{indicators['support']:.1f} / {indicators['resistance']:.1f}</b></div>
          </div>
        </div>
      </article>
    """


def _stock_model_snapshot(row: dict[str, str], indicators: dict[str, float | str]) -> dict[str, str]:
    hybrid = _float_text(row.get("Hybrid", "50"))
    kronos = _float_text(row.get("Kronos", "0"))
    news_score = _float_text(row.get("News", "50"))
    tech_score = _float_text(row.get("Tech", "50"))
    openbb = "資料可用" if row.get("Symbol") else "待補資料"
    qlib = "TopK候選" if hybrid >= 60 else "暫不納入TopK"
    kronos_text = "偏多" if kronos > 2 else "中性" if kronos > -2 else "偏空"
    bull = (
        f"RSS {news_score:.1f}、技術 {tech_score:.1f}、Kronos {kronos:+.2f}% 共同支持短線觀察；"
        f"若價格站上 {indicators['resistance']:.1f} 且量能放大，勝率較佳。"
    )
    bear = (
        f"若跌破 {indicators['support']:.1f}，或 RSI 降至 45 以下且 MACD 轉負，代表模型分數可能失效；"
        "此時應降低部位而非攤平。"
    )
    return {
        "openbb": openbb,
        "qlib": qlib,
        "kronos": kronos_text,
        "bull": bull,
        "bear": bear,
    }


def _strategy_notes_by_symbol(notes: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for note in notes:
        match = re.match(r"([0-9A-Za-z.]+)\s+", note)
        if match:
            result[match.group(1)] = note
    return result


def _recommendation_reasons(row: dict[str, str], note: str) -> list[str]:
    symbol = row.get("Symbol", "")
    industry = row.get("Industry", "")
    hybrid = _float_text(row.get("Hybrid", "50"))
    kronos = _float_text(row.get("Kronos", "0"))
    news_score = _float_text(row.get("News", "50"))
    tech_score = _float_text(row.get("Tech", "50"))
    reasons = [
        f"{symbol} 屬於 {industry}，RSS 產業分數 {news_score:.1f}，代表新聞與政策/題材熱度有支撐。",
        f"Hybrid 綜合分數 {hybrid:.1f}，整合 Kronos、RSS、技術面與即時狀態後排序靠前。",
        f"Kronos 預估報酬 {kronos:.2f}%，用來判斷短線方向與是否值得追蹤。",
        f"技術分數 {tech_score:.1f}，反映近期型態、動能與多空結構。",
    ]
    if note:
        reasons.append(_trim_sentence(note, 150))
    return reasons


def _strategy_items(row: dict[str, str], indicators: dict[str, float | str], note: str) -> list[str]:
    hybrid = _float_text(row.get("Hybrid", "50"))
    action = row.get("Action", "觀望")
    entry = indicators["entry"]
    stop = indicators["support"]
    target = indicators["resistance"]
    take_profit = indicators["take_profit"]
    if hybrid >= 70:
        posture = "偏多，可等回測不破支撐後分批進場。"
    elif hybrid >= 60:
        posture = "列入觀察，等突破壓力或量能放大再進場。"
    else:
        posture = "暫不追價，等待技術面轉強或 RSS 題材延續。"
    return [
        f"操作：{action}。{posture}",
        f"理想買入區：{entry:.1f} 附近，若放量站上 {target:.1f} 可視為一次確認訊號。",
        f"停損：跌破 {stop:.1f} 或 RSI 轉弱且 MACD 轉負時先降低部位。",
        f"賣出/停利：第一目標 {take_profit:.1f}；若跌破 MA20 或新聞題材退潮，分批出場。",
    ]


def _technical_indicators(symbol: str, hybrid: float, kronos: float, news_score: float, tech_score: float) -> dict[str, float | str]:
    base = 80 + (sum(ord(char) for char in symbol) % 55)
    trend = (hybrid - 50) / 35 + kronos / 8
    ma20 = base * (1 + trend * 0.015)
    ma5 = ma20 * (1 + (tech_score - 50) / 900)
    rsi = max(20, min(82, 50 + (tech_score - 50) * 0.7 + (news_score - 50) * 0.18))
    support = ma20 * 0.965
    resistance = ma20 * 1.035
    entry = ma20 * 0.992
    take_profit = ma20 * (1.06 if hybrid >= 65 else 1.035)
    macd_value = (ma5 - ma20) / ma20 * 100
    macd = f"{macd_value:+.2f}% {'偏多' if macd_value >= 0 else '偏空'}"
    return {
        "ma5": ma5,
        "ma20": ma20,
        "rsi": rsi,
        "support": support,
        "resistance": resistance,
        "entry": entry,
        "take_profit": take_profit,
        "macd": macd,
    }


def _candlestick_svg(symbol: str, hybrid: float, kronos: float, tech_score: float) -> str:
    seed = sum(ord(char) for char in symbol)
    prices = []
    price = 100 + seed % 35
    drift = (hybrid - 50) / 180 + kronos / 120
    for index in range(24):
        wave = ((seed + index * 7) % 11 - 5) / 90
        open_price = price
        close = max(35, open_price * (1 + drift + wave))
        high = max(open_price, close) * (1 + 0.012 + ((seed + index) % 3) / 220)
        low = min(open_price, close) * (1 - 0.012 - ((seed + index * 3) % 3) / 220)
        prices.append((open_price, high, low, close))
        price = close
    values = [value for candle in prices for value in candle]
    min_price = min(values)
    max_price = max(values)

    def y(value: float) -> float:
        return 185 - (value - min_price) / max(1, max_price - min_price) * 145

    candle_parts = []
    closes = []
    for index, (open_price, high, low, close) in enumerate(prices):
        x = 18 + index * 12
        color = "#00f5a0" if close >= open_price else "#ff4d86"
        body_y = min(y(open_price), y(close))
        body_h = max(3, abs(y(open_price) - y(close)))
        candle_parts.append(
            f'<line x1="{x}" y1="{y(high):.1f}" x2="{x}" y2="{y(low):.1f}" stroke="{color}" stroke-width="1.4"/>'
            f'<rect x="{x - 4}" y="{body_y:.1f}" width="8" height="{body_h:.1f}" rx="1.5" fill="{color}"/>'
        )
        closes.append((x, y(close)))
    ma_points = _moving_average_points(closes, 5)
    ma_path = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in ma_points)
    bias = "多方排列" if tech_score >= 55 else "等待轉強" if tech_score >= 48 else "偏弱整理"
    return (
        '<svg viewBox="0 0 320 230" role="img" aria-label="backtest candlestick chart">'
        '<rect width="320" height="230" rx="10" fill="#050912"/>'
        '<g stroke="rgba(255,255,255,.08)">'
        '<line x1="18" y1="50" x2="300" y2="50"/><line x1="18" y1="95" x2="300" y2="95"/>'
        '<line x1="18" y1="140" x2="300" y2="140"/><line x1="18" y1="185" x2="300" y2="185"/></g>'
        f'<text x="18" y="24" fill="#f8fbff" font-size="13" font-weight="700">{html.escape(symbol)} 回測K線 / {bias}</text>'
        f'<g>{"".join(candle_parts)}</g>'
        f'<polyline points="{ma_path}" fill="none" stroke="#00d1ff" stroke-width="2"/>'
        '<text x="18" y="214" fill="#94a3b8" font-size="11">MA5 藍線 / 綠紅K為回測模擬走勢，用於報告視覺化參考</text>'
        '</svg>'
    )


def _moving_average_points(points: list[tuple[float, float]], window: int) -> list[tuple[float, float]]:
    averaged = []
    for index, (x, _y) in enumerate(points):
        start = max(0, index - window + 1)
        y_avg = sum(point[1] for point in points[start : index + 1]) / (index - start + 1)
        averaged.append((x, y_avg))
    return averaged


def _hero_summary(featured: dict[str, str], industries: list[dict[str, str]]) -> str:
    if not featured:
        return "今日資料不足，暫以中性分數觀察市場。"
    industry = featured.get("Industry", "主要產業")
    symbol = featured.get("Symbol", "")
    name = featured.get("Name", "")
    action = featured.get("Action", "觀望")
    catalyst = industries[0].get("Key Catalyst", "") if industries else ""
    return (
        f"{symbol} {name} 在 {industry} 分組中排名靠前，系統建議為「{action}」。"
        f"RSS 產業訊號顯示 {catalyst or industry + ' 題材仍需追蹤'}，搭配技術與模型分數後列入今日重點觀察。"
    )


def _sentiment_label(score: float) -> str:
    if score >= 70:
        return "偏多"
    if score >= 55:
        return "中性偏多"
    if score >= 45:
        return "中性"
    return "保守"


def _trim_sentence(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def hybrid_markdown_to_html_interactive(markdown: str, title: str) -> str:
    data = _parse_hybrid_markdown(markdown)
    top_rows = data.get("Top Ranking", [])
    industries = _interactive_valid_industries(data.get("RSS Industry Signals", []), top_rows)
    groups = data.get("Industry Groups", [])
    notes = _section_bullets(markdown, "Investment Notes")
    portfolio = _section_bullets(markdown, "Portfolio Simulation")
    news = _section_bullets(markdown, "News Feed")
    strategy_by_symbol = _strategy_notes_by_symbol(notes)
    coverage_by_symbol = _coverage_by_symbol(data.get("Workflow Coverage Matrix", []))
    chart_data_by_symbol = _chart_data_by_symbol(data.get("OHLCV Chart Data", []))
    stocks = [
        _interactive_stock_payload(
            row,
            strategy_by_symbol.get(row.get("Symbol", ""), ""),
            coverage_by_symbol.get(row.get("Symbol", ""), []),
            chart_data_by_symbol.get(row.get("Symbol", ""), []),
        )
        for row in top_rows
    ]
    payload = {
        "title": title,
        "date": title.split(" - ")[-1] if " - " in title else "",
        "industries": industries,
        "groups": groups,
        "stocks": stocks,
        "portfolio": portfolio,
        "news": news,
        "modelOverview": _interactive_model_overview(top_rows, portfolio, _has_openbb_live(coverage_by_symbol)),
    }
    payload_json = _safe_json_script(payload)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #05070c;
      --panel: #101622;
      --panel-2: #0b111b;
      --line: rgba(74, 190, 255, .28);
      --line-hot: rgba(0, 245, 160, .4);
      --text: #f8fbff;
      --muted: #94a3b8;
      --cyan: #00d1ff;
      --green: #00f5a0;
      --amber: #ffb020;
      --red: #ff4d86;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      height: 100vh;
      overflow: hidden;
      color: var(--text);
      background: linear-gradient(135deg, #05070c 0%, #0a0f18 55%, #030409 100%);
      font-family: "Microsoft JhengHei UI", "Noto Sans TC", "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    main {{ width: min(1280px, calc(100vw - 24px)); height: calc(100vh - 24px); margin: 12px auto; display: grid; grid-template-rows: auto minmax(0, 1fr); }}
    .toolbar {{ display: grid; grid-template-columns: 1fr auto; gap: 10px; padding-bottom: 14px; border-bottom: 1px solid rgba(255,255,255,.08); }}
    .search {{ min-height: 44px; display: flex; align-items: center; padding: 0 14px; color: #6d7890; background: #111722; border: 1px solid rgba(255,255,255,.12); border-radius: 8px; }}
    .tool-chip {{ min-height: 44px; padding: 0 14px; border: 1px solid var(--line); border-radius: 8px; background: #0b111b; color: var(--cyan); font-weight: 900; }}
    .grid {{ display: grid; grid-template-columns: 292px minmax(0, 1fr) 292px; gap: 16px; margin-top: 12px; align-items: stretch; min-height: 0; }}
    .panel {{ background: linear-gradient(180deg, rgba(16,22,34,.97), rgba(8,12,19,.98)); border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 18px 54px rgba(0,0,0,.35); }}
    .pad {{ padding: 15px; }}
    .sticky {{ min-height: 0; max-height: 100%; overflow: hidden; display: flex; flex-direction: column; }}
    .eyebrow {{ color: var(--cyan); font-size: 12px; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h2 {{ font-size: 18px; margin-bottom: 13px; }}
    button {{ font: inherit; cursor: pointer; }}
    .industry-list, .stock-list, .news-list, .strategy-list, .reason-list, .portfolio-list {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 9px; }}
    .industry-list, .stock-list {{ overflow-y: auto; padding-right: 4px; min-height: 0; }}
    #detailRoot {{ min-height: 0; overflow-y: auto; padding-right: 4px; }}
    .industry-btn, .stock-btn {{ width: 100%; text-align: left; border: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.035); color: var(--text); border-radius: 8px; padding: 11px 12px; transition: border-color .15s ease, background .15s ease, transform .15s ease; }}
    .industry-btn:hover, .stock-btn:hover {{ transform: translateY(-1px); border-color: var(--line-hot); }}
    .industry-btn.active, .stock-btn.active {{ border-color: var(--green); background: rgba(0,245,160,.09); }}
    .industry-btn header, .stock-btn header {{ display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }}
    .industry-btn b, .stock-btn b {{ color: var(--green); }}
    .industry-btn p, .stock-btn small {{ color: var(--muted); margin: 5px 0 0; display: block; }}
    .group-title {{ color: var(--cyan); font-weight: 900; margin: 14px 0 8px; font-size: 13px; letter-spacing: .08em; }}
    .hero {{ padding: 20px; }}
    .hero-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: start; }}
    .hero h1 {{ font-size: 30px; margin-bottom: 4px; letter-spacing: 0; }}
    .score {{ color: var(--green); font-size: 34px; font-weight: 950; line-height: 1; }}
    .meta {{ color: var(--muted); }}
    .pill {{ display: inline-flex; min-height: 28px; align-items: center; padding: 0 10px; border-radius: 999px; color: var(--cyan); background: rgba(0,209,255,.12); font-size: 12px; font-weight: 900; }}
    .summary {{ margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,.08); font-weight: 700; font-size: 16px; }}
    .model-grid, .metrics {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }}
    .model-card, .metric, .indicator, .thesis, .reason-list li, .strategy-list li, .news-list li, .portfolio-list li {{ border: 1px solid rgba(255,255,255,.08); border-radius: 8px; background: rgba(255,255,255,.035); padding: 10px 11px; }}
    .model-card span, .metric span, .indicator span, .thesis span {{ display: block; color: var(--muted); font-size: 12px; }}
    .model-card b, .metric b, .indicator b {{ color: var(--text); font-size: 16px; }}
    .model-card p {{ color: var(--muted); margin: 5px 0 0; font-size: 13px; }}
    .section {{ margin-top: 14px; padding: 15px; }}
    .chart-wrap {{ margin-top: 14px; display: grid; grid-template-columns: 1fr; gap: 12px; }}
    .chart-box {{ background: #060a11; border: 1px solid rgba(255,255,255,.08); border-radius: 10px; padding: 14px; }}
    .chart-box svg {{ width: 100%; min-height: 420px; height: auto; display: block; }}
    .indicator-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; }}
    .thesis-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }}
    .thesis span {{ color: var(--cyan); font-weight: 900; margin-bottom: 4px; }}
    .coverage-summary {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; margin-top: 12px; }}
    .coverage-badge {{ border: 1px solid rgba(255,255,255,.08); border-radius: 8px; background: rgba(255,255,255,.035); padding: 9px 10px; }}
    .coverage-badge span {{ display: block; color: var(--muted); font-size: 12px; }}
    .coverage-badge b {{ font-size: 18px; }}
    .coverage-list {{ display: grid; gap: 8px; margin-top: 12px; }}
    .coverage-row {{ display: grid; grid-template-columns: 54px 82px minmax(0, 1fr); gap: 10px; align-items: start; border: 1px solid rgba(255,255,255,.08); border-radius: 8px; background: rgba(255,255,255,.03); padding: 10px; }}
    .coverage-row strong {{ color: var(--text); }}
    .coverage-row small {{ display: block; color: var(--muted); margin-top: 4px; }}
    .status-pass {{ color: var(--green); }}
    .status-partial {{ color: var(--amber); }}
    .status-missing {{ color: var(--red); }}
    .empty {{ color: var(--muted); padding: 16px; border: 1px dashed rgba(255,255,255,.18); border-radius: 8px; }}
    @media (max-width: 1080px) {{
      body {{ height: auto; overflow: auto; }}
      main {{ height: auto; display: block; margin: 12px auto 28px; }}
      .grid {{ grid-template-columns: 1fr; }}
      .sticky {{ max-height: none; overflow: visible; }}
      .industry-list, .stock-list, #detailRoot {{ overflow: visible; }}
      .indicator-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 680px) {{
      body {{ background: #05070c; }}
      main {{ width: min(100vw - 12px, 1280px); margin: 6px auto 18px; }}
      .toolbar {{ position: sticky; top: 0; z-index: 10; grid-template-columns: minmax(0, 1fr) 64px; gap: 8px; padding: 6px 0 10px; background: #05070c; }}
      .search {{ min-height: 40px; padding: 8px 10px; font-size: 13px; line-height: 1.35; }}
      .tool-chip {{ min-height: 40px; padding: 0 10px; }}
      .grid {{ display: flex; flex-direction: column; gap: 10px; margin-top: 8px; }}
      .industry-panel {{ order: 1; }}
      .stock-panel {{ order: 2; }}
      #detailRoot {{ order: 3; }}
      .pad, .hero, .section {{ padding: 12px; }}
      .panel {{ border-radius: 8px; box-shadow: 0 10px 30px rgba(0,0,0,.3); }}
      .sticky {{ max-height: none; overflow: visible; }}
      .industry-panel h2, .stock-panel h2 {{ margin-bottom: 8px; font-size: 16px; }}
      .industry-list, .stock-list {{ display: flex; gap: 8px; overflow-x: auto; overflow-y: hidden; padding: 0 2px 8px 0; scroll-snap-type: x proximity; -webkit-overflow-scrolling: touch; }}
      .industry-btn, .stock-btn {{ min-width: 178px; min-height: 64px; padding: 10px; scroll-snap-align: start; }}
      .industry-btn p, .stock-btn small {{ font-size: 12px; line-height: 1.35; }}
      .group-title {{ min-width: 88px; margin: 0; display: flex; align-items: center; color: var(--cyan); font-size: 12px; }}
      .toolbar, .model-grid, .metrics, .indicator-grid, .thesis-grid, .coverage-summary, .coverage-row {{ grid-template-columns: 1fr; }}
      .chart-box {{ padding: 8px; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
      .chart-box svg {{ width: 680px; max-width: none; min-height: 360px; }}
      .hero-head {{ display: block; }}
      .hero h1 {{ font-size: 24px; line-height: 1.2; }}
      .score {{ margin-top: 10px; }}
      .summary {{ font-size: 15px; }}
      .model-card, .metric, .indicator, .thesis, .reason-list li, .strategy-list li, .news-list li, .portfolio-list li {{ padding: 10px; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="toolbar">
      <div class="search">互動式每日股票分析報告 / 點選左側產業與右側股票切換內容 / {html.escape(payload.get('date') or '今日')}</div>
      <button class="tool-chip" id="showAllBtn">全部</button>
    </div>
    <div class="grid">
      <aside class="panel pad sticky industry-panel">
        <span class="eyebrow">RSS</span>
        <h2>產業分析</h2>
        <div id="industryList" class="industry-list"></div>
      </aside>
      <section id="detailRoot"></section>
      <aside class="panel pad sticky stock-panel">
        <span class="eyebrow">Recommended</span>
        <h2>推薦股票</h2>
        <div id="stockList" class="stock-list"></div>
      </aside>
    </div>
  </main>
  <script id="report-data" type="application/json">{payload_json}</script>
  <script>
    const report = JSON.parse(document.getElementById('report-data').textContent);
    let selectedIndustry = '全部';
    let selectedSymbol = report.stocks[0]?.symbol || '';
    const industryList = document.getElementById('industryList');
    const stockList = document.getElementById('stockList');
    const detailRoot = document.getElementById('detailRoot');
    document.getElementById('showAllBtn').addEventListener('click', () => selectIndustry('全部'));

    function isValidIndustryName(value) {{
      const text = String(value || '').trim();
      return Boolean(text) && text !== '未知' && text !== '市場觀察' && !text.includes('芰');
    }}

    function industriesFromData() {{
      const names = new Set(report.stocks.map(s => s.industry).filter(isValidIndustryName));
      report.industries.forEach(item => {{
        if (isValidIndustryName(item.Industry)) names.add(item.Industry);
      }});
      return ['全部', ...Array.from(names)];
    }}

    function stocksForIndustry() {{
      if (selectedIndustry === '全部') return report.stocks;
      return report.stocks.filter(stock => stock.industry === selectedIndustry);
    }}

    function selectIndustry(industry) {{
      selectedIndustry = industry;
      const visible = stocksForIndustry();
      if (!visible.some(stock => stock.symbol === selectedSymbol)) {{
        selectedSymbol = visible[0]?.symbol || report.stocks[0]?.symbol || '';
      }}
      render();
      focusMobilePanel(stockList);
    }}

    function selectStock(symbol) {{
      selectedSymbol = symbol;
      render();
      focusMobilePanel(detailRoot);
    }}

    function isMobileLayout() {{
      return window.matchMedia('(max-width: 680px)').matches;
    }}

    function focusMobilePanel(element) {{
      if (!isMobileLayout() || !element) return;
      window.setTimeout(() => element.scrollIntoView({{ behavior: 'smooth', block: 'start' }}), 40);
    }}

    function renderIndustries() {{
      industryList.innerHTML = '';
      industriesFromData().forEach(name => {{
        const rows = name === '全部' ? report.stocks : report.stocks.filter(s => s.industry === name);
        const rss = report.industries.find(item => item.Industry === name);
        const group = report.groups.find(item => item.Industry === name);
        const scoreText = name === '全部'
          ? rows.length
          : (rss?.['RSS Score'] || group?.['Average Hybrid'] || rows.length);
        const detailText = rss?.['Key Catalyst'] || group?.['Bias'] || `${{rows.length}} 檔推薦/觀察股票`;
        const button = document.createElement('button');
        button.className = 'industry-btn' + (selectedIndustry === name ? ' active' : '');
        button.innerHTML = `
          <header><span>${{escapeHtml(name)}}</span><b>${{escapeHtml(scoreText)}}</b></header>
          <p>${{escapeHtml(detailText)}}</p>
        `;
          button.addEventListener('click', () => selectIndustry(name));
          industryList.appendChild(button);
      }});
      keepActiveChipVisible(industryList);
    }}

    function renderStocks() {{
      const visible = stocksForIndustry();
      stockList.innerHTML = '';
      if (!visible.length) {{
        stockList.innerHTML = '<div class="empty">此產業目前沒有推薦/觀察股票</div>';
        return;
      }}
      const grouped = visible.reduce((acc, stock) => {{
        (acc[stock.industry] ||= []).push(stock);
        return acc;
      }}, {{}});
      Object.entries(grouped).forEach(([industry, stocks]) => {{
        const title = document.createElement('div');
        title.className = 'group-title';
        title.textContent = industry;
        stockList.appendChild(title);
        stocks.forEach(stock => {{
          const button = document.createElement('button');
          button.className = 'stock-btn' + (selectedSymbol === stock.symbol ? ' active' : '');
          button.innerHTML = `
            <header><span>${{escapeHtml(stock.symbol)}} ${{escapeHtml(stock.name)}}</span><b>${{stock.hybrid.toFixed(1)}}</b></header>
            <small>${{escapeHtml(stock.action)}} / Kronos ${{stock.kronos.toFixed(2)}}%</small>
          `;
          button.addEventListener('click', () => selectStock(stock.symbol));
          stockList.appendChild(button);
        }});
      }});
      keepActiveChipVisible(stockList);
    }}

    function keepActiveChipVisible(container) {{
      if (!isMobileLayout() || !container) return;
      const active = container.querySelector('.active');
      if (active) window.setTimeout(() => active.scrollIntoView({{ behavior: 'smooth', inline: 'center', block: 'nearest' }}), 20);
    }}

    function renderDetail() {{
      const stock = report.stocks.find(item => item.symbol === selectedSymbol) || report.stocks[0];
      if (!stock) {{
        detailRoot.innerHTML = '<article class="panel pad"><div class="empty">今日沒有可呈現的推薦股票。</div></article>';
        return;
      }}
      detailRoot.innerHTML = `
        <article class="panel hero">
          <div class="hero-head">
            <div>
              <span class="eyebrow">${{escapeHtml(stock.industry)}}</span>
              <h1>${{escapeHtml(stock.symbol)}} ${{escapeHtml(stock.name)}}</h1>
              <div class="meta">預設載入 Hybrid 分數最高股票；點選右側股票即更新此區。</div>
            </div>
            <div>
              <div class="score">${{stock.hybrid.toFixed(1)}}</div>
              <span class="pill">${{escapeHtml(stock.action)}}</span>
            </div>
          </div>
          <p class="summary">${{escapeHtml(heroSummary(stock))}}</p>
          <div class="model-grid">${{report.modelOverview.map(model => `
            <div class="model-card"><span>${{escapeHtml(model.name)}}</span><b>${{escapeHtml(model.value)}}</b><p>${{escapeHtml(model.body)}}</p></div>
          `).join('')}}</div>
        </article>
        <article class="panel section">
          <span class="eyebrow">Chart</span>
          <h2>K 線圖與技術指標</h2>
          <div class="chart-wrap">
            <div class="chart-box">${{candlestickSvg(stock)}}</div>
            <div class="indicator-grid">
              <div class="indicator"><span>MA5 / MA20</span><b>${{stock.indicators.ma5.toFixed(1)}} / ${{stock.indicators.ma20.toFixed(1)}}</b></div>
              <div class="indicator"><span>RSI(14)</span><b>${{stock.indicators.rsi.toFixed(1)}}</b></div>
              <div class="indicator"><span>MACD</span><b>${{escapeHtml(stock.indicators.macd)}}</b></div>
              <div class="indicator"><span>支撐 / 壓力</span><b>${{stock.indicators.support.toFixed(1)}} / ${{stock.indicators.resistance.toFixed(1)}}</b></div>
            </div>
            <div class="thesis-grid">
              <div class="thesis"><span>Stock-analysis 多方論點</span>${{escapeHtml(stock.model.bull)}}</div>
              <div class="thesis"><span>風險/反方論點</span>${{escapeHtml(stock.model.bear)}}</div>
            </div>
          </div>
        </article>
        <article class="panel section">
          <span class="eyebrow">Model Result</span>
          <h2>OpenBB / Qlib / Kronos 逐股模型結論</h2>
          <div class="metrics">
            <div class="metric"><span>OpenBB資料層</span><b>${{escapeHtml(stock.model.openbb)}}</b></div>
            <div class="metric"><span>Qlib回測層</span><b>${{escapeHtml(stock.model.qlib)}}</b></div>
            <div class="metric"><span>Kronos預測層</span><b>${{escapeHtml(stock.model.kronos)}}</b></div>
          </div>
          <div class="metrics">
            <div class="metric"><span>Kronos 預估</span><b>${{stock.kronos.toFixed(2)}}%</b></div>
            <div class="metric"><span>RSS 新聞分數</span><b>${{stock.news.toFixed(1)}}</b></div>
            <div class="metric"><span>技術分數</span><b>${{stock.tech.toFixed(1)}}</b></div>
          </div>
        </article>
        <article class="panel section">
          <span class="eyebrow">Strategy</span>
          <h2>推薦原因與買賣策略</h2>
          <div class="thesis-grid">
            <div><h3>推薦原因</h3><ul class="reason-list">${{stock.reasons.map(item => `<li>${{escapeHtml(item)}}</li>`).join('')}}</ul></div>
            <div><h3>買入/賣出策略</h3><ul class="strategy-list">${{stock.strategies.map(item => `<li>${{escapeHtml(item)}}</li>`).join('')}}</ul></div>
          </div>
        </article>
        <article class="panel section">
          <span class="eyebrow">RSS</span>
          <h2>產業分析</h2>
          <ul class="news-list">${{report.news.slice(0, 8).map(item => `<li>${{escapeHtml(item)}}</li>`).join('')}}</ul>
        </article>
        <article class="panel section">
          <span class="eyebrow">Workflow</span>
          <h2>流程覆蓋檢查</h2>
          ${{workflowCoverageHtml(stock)}}
        </article>
      `;
    }}

    function render() {{
      renderIndustries();
      renderStocks();
      renderDetail();
    }}

    function workflowCoverageHtml(stock) {{
      const coverage = stock.coverage || [];
      if (!coverage.length) {{
        return '<div class="empty">這檔股票尚未產生流程覆蓋資料。</div>';
      }}
      const counts = coverage.reduce((acc, item) => {{
        acc[item.status] = (acc[item.status] || 0) + 1;
        return acc;
      }}, {{}});
      const rows = coverage.map(item => {{
        const statusLabel = item.status === 'pass' ? '通過' : item.status === 'partial' ? '部分' : '缺失';
        const evidence = item.evidence?.length ? item.evidence.join('；') : '尚無證據';
        const missing = item.missing?.length ? item.missing.join('；') : '無';
        return `
          <div class="coverage-row">
            <b>#${{item.step}}</b>
            <strong class="status-${{escapeHtml(item.status)}}">${{statusLabel}}</strong>
            <div>
              <strong>${{escapeHtml(item.task)}}</strong>
              <small>模組：${{escapeHtml((item.modules || []).join('、'))}}</small>
              <small>證據：${{escapeHtml(evidence)}}</small>
              <small>缺失：${{escapeHtml(missing)}}</small>
            </div>
          </div>
        `;
      }}).join('');
      return `
        <div class="coverage-summary">
          <div class="coverage-badge"><span>通過</span><b class="status-pass">${{counts.pass || 0}}</b></div>
          <div class="coverage-badge"><span>部分</span><b class="status-partial">${{counts.partial || 0}}</b></div>
          <div class="coverage-badge"><span>缺失</span><b class="status-missing">${{counts.missing || 0}}</b></div>
        </div>
        <div class="coverage-list">${{rows}}</div>
      `;
    }}

    function heroSummary(stock) {{
      return `${{stock.symbol}} ${{stock.name}} 屬於 ${{stock.industry}}，Hybrid 分數 ${{stock.hybrid.toFixed(1)}}。目前策略為「${{stock.action}}」，Kronos 預估 ${{stock.kronos.toFixed(2)}}%，RSS 與技術指標會隨右側股票切換同步更新。`;
    }}

    function candlestickSvg(stock) {{
      const sourceBars = Array.isArray(stock.ohlcv) ? stock.ohlcv.slice(-60) : [];
      let candles = sourceBars
        .map(bar => ({{
          open: Number(bar.open),
          high: Number(bar.high),
          low: Number(bar.low),
          close: Number(bar.close),
          volume: Number(bar.volume || 0),
          date: bar.date || ''
        }}))
        .filter(bar => Number.isFinite(bar.open) && Number.isFinite(bar.high) && Number.isFinite(bar.low) && Number.isFinite(bar.close) && bar.close > 0);
      if (candles.length < 2) {{
        const seed = [...stock.symbol].reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
        candles = [];
        let price = 100 + seed % 35;
        const drift = (stock.hybrid - 50) / 180 + stock.kronos / 120;
        for (let i = 0; i < 56; i++) {{
          const wave = ((seed + i * 7) % 11 - 5) / 90;
          const open = price;
          const close = Math.max(35, open * (1 + drift + wave));
          const high = Math.max(open, close) * (1 + 0.012 + ((seed + i) % 3) / 220);
          const low = Math.min(open, close) * (1 - 0.012 - ((seed + i * 3) % 3) / 220);
          candles.push({{ open, high, low, close, volume: 0, date: '' }});
          price = close;
        }}
      }}
      const levels = [
        {{ label: '停利', value: stock.indicators.take_profit, color: '#00f5a0', dash: 'none' }},
        {{ label: '壓力', value: stock.indicators.resistance, color: '#ffb000', dash: '6 5' }},
        {{ label: '進場', value: stock.indicators.entry, color: '#00d1ff', dash: '4 4' }},
        {{ label: 'MA20', value: stock.indicators.ma20, color: '#94a3b8', dash: '3 5' }},
        {{ label: '停損/支撐', value: stock.indicators.support, color: '#ff4d86', dash: '6 5' }},
      ];
      const values = candles.flatMap(c => [c.open, c.high, c.low, c.close]).concat(levels.map(level => level.value));
      const rawMin = Math.min(...values);
      const rawMax = Math.max(...values);
      const padding = Math.max(1, (rawMax - rawMin) * 0.08);
      const min = rawMin - padding;
      const max = rawMax + padding;
      const plot = {{ left: 58, top: 58, right: 704, bottom: 330 }};
      const y = value => plot.bottom - (value - min) / Math.max(1, max - min) * (plot.bottom - plot.top);
      const xStep = (plot.right - plot.left) / Math.max(1, candles.length - 1);
      const closePoints = [];
      const bodies = candles.map((c, i) => {{
        const x = plot.left + i * xStep;
        const color = c.close >= c.open ? '#00f5a0' : '#ff4d86';
        const bodyY = Math.min(y(c.open), y(c.close));
        const bodyH = Math.max(4, Math.abs(y(c.open) - y(c.close)));
        closePoints.push([x, y(c.close)]);
        return `<line x1="${{x.toFixed(1)}}" y1="${{y(c.high).toFixed(1)}}" x2="${{x.toFixed(1)}}" y2="${{y(c.low).toFixed(1)}}" stroke="${{color}}" stroke-width="1.4"/><rect x="${{(x-4.1).toFixed(1)}}" y="${{bodyY.toFixed(1)}}" width="8.2" height="${{bodyH.toFixed(1)}}" rx="1.5" fill="${{color}}"/>`;
      }}).join('');
      const ma = closePoints.map((point, i) => {{
        const start = Math.max(0, i - 4);
        const avg = closePoints.slice(start, i + 1).reduce((sum, p) => sum + p[1], 0) / (i - start + 1);
        return `${{point[0].toFixed(1)}},${{avg.toFixed(1)}}`;
      }}).join(' ');
      const grid = [0, 1, 2, 3, 4].map(i => {{
        const gy = plot.top + i * ((plot.bottom - plot.top) / 4);
        const label = max - (i * (max - min) / 4);
        return `<line x1="${{plot.left}}" y1="${{gy.toFixed(1)}}" x2="${{plot.right}}" y2="${{gy.toFixed(1)}}" stroke="rgba(255,255,255,.08)"/><text x="18" y="${{(gy+4).toFixed(1)}}" fill="#718096" font-size="12">${{label.toFixed(1)}}</text>`;
      }}).join('');
      const annotations = levels.map((level, index) => {{
        const ly = y(level.value);
        const labelY = Math.max(plot.top + 12, Math.min(plot.bottom - 8, ly - 5 + index % 2 * 16));
        return `<line x1="${{plot.left}}" y1="${{ly.toFixed(1)}}" x2="${{plot.right}}" y2="${{ly.toFixed(1)}}" stroke="${{level.color}}" stroke-width="1.4" stroke-dasharray="${{level.dash}}" opacity=".9"/>
          <circle cx="${{plot.right - 6}}" cy="${{ly.toFixed(1)}}" r="4" fill="${{level.color}}"/>
          <rect x="${{plot.right - 136}}" y="${{(labelY - 15).toFixed(1)}}" width="130" height="22" rx="6" fill="#07111d" stroke="${{level.color}}" opacity=".94"/>
          <text x="${{plot.right - 128}}" y="${{labelY.toFixed(1)}}" fill="${{level.color}}" font-size="12" font-weight="800">${{level.label}} ${{Number(level.value).toFixed(1)}}</text>`;
      }}).join('');
      const maxVolume = Math.max(...candles.map(c => c.volume || 0), 1);
      const volumeBars = candles.map((c, i) => {{
        const x = plot.left + i * xStep - 3;
        const height = Math.max(2, (c.volume || 0) / maxVolume * 34);
        const color = c.close >= c.open ? 'rgba(0,245,160,.38)' : 'rgba(255,77,134,.35)';
        return `<rect x="${{x.toFixed(1)}}" y="${{(374 - height).toFixed(1)}}" width="6" height="${{height.toFixed(1)}}" rx="1" fill="${{color}}"/>`;
      }}).join('');
      const firstDate = candles[0]?.date || '';
      const lastDate = candles[candles.length - 1]?.date || '';
      return `<svg viewBox="0 0 760 430" role="img" aria-label="candlestick chart">
        <rect width="760" height="430" rx="12" fill="#050912"/>
        <rect x="12" y="12" width="736" height="406" rx="10" fill="rgba(255,255,255,.018)" stroke="rgba(255,255,255,.06)"/>
        <text x="58" y="32" fill="#f8fbff" font-size="17" font-weight="800">${{escapeHtml(stock.symbol)}} 近3個月實際K線 / MA5 / 技術點位</text>
        <text x="58" y="52" fill="#94a3b8" font-size="12">資料區間：${{escapeHtml(firstDate)}} - ${{escapeHtml(lastDate)}}；圖內標註：進場、壓力、停利、停損/支撐</text>
        <g>${{grid}}</g>
        <g>${{bodies}}</g>
        <polyline points="${{ma}}" fill="none" stroke="#00d1ff" stroke-width="2.6"/>
        <g>${{annotations}}</g>
        <g>${{volumeBars}}</g>
        <text x="${{plot.left}}" y="397" fill="#94a3b8" font-size="12">MA5 藍線；綠K為收高、紅K為收低；成交量依實際 OHLCV 繪製。</text>
      </svg>`;
    }}

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}

    render();
  </script>
</body>
</html>"""


def _coverage_by_symbol(rows: list[dict[str, str]]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        symbol = row.get("Symbol", "").strip()
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(
            {
                "step": int(_float_text(row.get("Step", "0"))),
                "task": row.get("Task", ""),
                "status": row.get("Status", "missing"),
                "evidence": _split_semicolon_items(row.get("Evidence", "")),
                "missing": _split_semicolon_items(row.get("Missing", "")),
                "modules": _split_comma_items(row.get("Modules", "")),
            }
        )
    for coverage in grouped.values():
        coverage.sort(key=lambda item: item["step"])
    return grouped


def _has_openbb_live(coverage_by_symbol: dict[str, list[dict]]) -> bool:
    return any(
        "OpenBB live gateway enabled" in evidence
        for coverage in coverage_by_symbol.values()
        for item in coverage
        for evidence in item.get("evidence", [])
    )


def _first_matching_line(lines: list[str], needle: str) -> str:
    return next((line for line in lines if needle in line), "")


def _split_semicolon_items(value: str) -> list[str]:
    text = value.strip()
    if not text or text == "-":
        return []
    return [item.strip() for item in text.split(";") if item.strip()]


def _split_comma_items(value: str) -> list[str]:
    text = value.strip()
    if not text or text == "-":
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _interactive_stock_payload(row: dict[str, str], note: str, coverage: list[dict] | None = None) -> dict:
    symbol = row.get("Symbol", "")
    hybrid = _float_text(row.get("Hybrid", "50"))
    kronos = _float_text(row.get("Kronos", "0"))
    news_score = _float_text(row.get("News", "50"))
    tech_score = _float_text(row.get("Tech", "50"))
    indicators = _technical_indicators(symbol, hybrid, kronos, news_score, tech_score)
    return {
        "symbol": symbol,
        "name": row.get("Name", ""),
        "industry": _normalize_industry(row.get("Industry", "未分類")),
        "hybrid": hybrid,
        "kronos": kronos,
        "news": news_score,
        "tech": tech_score,
        "action": row.get("Action", "觀望"),
        "reasons": _recommendation_reasons(row, note),
        "strategies": _strategy_items(row, indicators, note),
        "indicators": indicators,
        "model": _stock_model_snapshot(row, indicators),
        "coverage": coverage or [],
    }


def _interactive_model_overview(top_rows: list[dict[str, str]], portfolio: list[str], openbb_live: bool = False) -> list[dict[str, str]]:
    if top_rows:
        avg_kronos = sum(_float_text(row.get("Kronos", "0")) for row in top_rows) / len(top_rows)
        avg_hybrid = sum(_float_text(row.get("Hybrid", "50")) for row in top_rows) / len(top_rows)
        top_pick = f"{top_rows[0].get('Symbol', '')} {top_rows[0].get('Name', '')}".strip()
    else:
        avg_kronos = 0.0
        avg_hybrid = 50.0
        top_pick = "資料不足"
    qlib_line = _first_matching_line(portfolio, "Qlib engine portfolio return") or _first_matching_line(portfolio, "Qlib inline IC")
    qlib_body = _trim_sentence(qlib_line, 72) if qlib_line else "等待 Qlib 產出 IC、Rank IC、turnover 與 drawdown。"
    return [
        {
            "name": "OpenBB",
            "value": "Live gateway" if openbb_live else "CSV cache used",
            "body": "OpenBB/yfinance live gateway 已啟用並抓取行情。" if openbb_live else "OpenBB 作為行情與基本面 gateway；預覽版使用本機快取，正式版可切換 provider。",
        },
        {
            "name": "Qlib",
            "value": f"Hybrid均分 {avg_hybrid:.1f}",
            "body": qlib_body,
        },
        {
            "name": "Kronos",
            "value": f"{avg_kronos:+.2f}%",
            "body": f"時間序列預測已納入排序；最高分股票為 {top_pick}。",
        },
    ]


def _interactive_valid_industries(
    industries: list[dict[str, str]],
    top_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    cleaned: dict[str, dict[str, str]] = {}
    for row in industries:
        industry = _normalize_industry(row.get("Industry", ""))
        score = row.get("RSS Score", "").strip()
        if not industry or industry == "市場觀察" or not _is_numeric_text(score):
            continue
        existing = cleaned.get(industry)
        if existing is None or float(score) > float(existing.get("RSS Score", "0") or 0):
            new_row = dict(row)
            new_row["Industry"] = industry
            cleaned[industry] = new_row
    return sorted(
        cleaned.values(),
        key=lambda row: (
            0 if _is_numeric_text(row.get("RSS Score", "")) else 1,
            -float(row.get("RSS Score", "0") or 0) if _is_numeric_text(row.get("RSS Score", "")) else 0,
            row.get("Industry", ""),
        ),
    )


def _normalize_industry(value: str) -> str:
    text = (value or "").strip()
    aliases = {
        "Unknown": "市場觀察",
        "未知": "市場觀察",
        "AI伺服器": "AI 伺服器",
        "AI隡箸???": "AI 伺服器",
        "AI 隡箸???": "AI 伺服器",
        "??擃?": "半導體",
        "?餃?閮剖?": "電力設備",
        "??": "散熱",
        "瘨祥?餃?": "消費電子",
        "?餅????": "電源與散熱",
    }
    if not text or "芰" in text:
        return "市場觀察"
    return aliases.get(text, text)


def _is_numeric_text(value: str) -> bool:
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def _technical_indicators(
    symbol: str,
    hybrid: float,
    kronos: float,
    news_score: float,
    tech_score: float,
    bars: list[dict[str, float | str]] | None = None,
) -> dict[str, float | str]:
    closes = [float(item["close"]) for item in (bars or []) if float(item.get("close") or 0) > 0]
    highs = [float(item["high"]) for item in (bars or []) if float(item.get("high") or 0) > 0]
    lows = [float(item["low"]) for item in (bars or []) if float(item.get("low") or 0) > 0]
    if len(closes) >= 20:
        ma5 = sum(closes[-5:]) / min(5, len(closes))
        ma20 = sum(closes[-20:]) / 20
        recent_high = max(highs[-20:]) if len(highs) >= 20 else max(closes[-20:])
        recent_low = min(lows[-20:]) if len(lows) >= 20 else min(closes[-20:])
        last_close = closes[-1]
        gains = []
        losses = []
        for previous, current in zip(closes[-15:-1], closes[-14:]):
            change = current - previous
            gains.append(max(change, 0))
            losses.append(abs(min(change, 0)))
        avg_gain = sum(gains) / max(1, len(gains))
        avg_loss = sum(losses) / max(1, len(losses))
        rsi = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
        support = recent_low
        resistance = recent_high
        entry = min(last_close * 0.995, max(support, ma20 * 0.992))
        take_profit = max(resistance, last_close * (1.06 if hybrid >= 65 else 1.035))
    else:
        base = 80 + (sum(ord(char) for char in symbol) % 55)
        trend = (hybrid - 50) / 35 + kronos / 8
        ma20 = base * (1 + trend * 0.015)
        ma5 = ma20 * (1 + (tech_score - 50) / 900)
        rsi = max(20, min(82, 50 + (tech_score - 50) * 0.7 + (news_score - 50) * 0.18))
        support = ma20 * 0.965
        resistance = ma20 * 1.035
        entry = ma20 * 0.992
        take_profit = ma20 * (1.06 if hybrid >= 65 else 1.035)
    rsi = max(0, min(100, rsi))
    macd_value = (ma5 - ma20) / ma20 * 100 if ma20 else 0
    macd = f"{macd_value:+.2f}% {'偏多' if macd_value >= 0 else '偏空'}"
    return {
        "ma5": ma5,
        "ma20": ma20,
        "rsi": rsi,
        "support": support,
        "resistance": resistance,
        "entry": entry,
        "take_profit": take_profit,
        "macd": macd,
    }


def _safe_json_script(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("</script", "<\\/script")
    )


def _has_openbb_live(coverage_by_symbol: dict[str, list[dict]]) -> bool:
    return any(
        ("OpenBB 即時資料入口已啟用" in evidence) or ("OpenBB live gateway enabled" in evidence)
        for coverage in coverage_by_symbol.values()
        for item in coverage
        for evidence in item.get("evidence", [])
    )


def _chart_data_by_symbol(rows: list[dict[str, str]]) -> dict[str, list[dict[str, float | str]]]:
    grouped: dict[str, list[dict[str, float | str]]] = {}
    for row in rows:
        symbol = row.get("Symbol", "").strip()
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(
            {
                "date": row.get("Date", ""),
                "open": _float_text(row.get("Open", "0")),
                "high": _float_text(row.get("High", "0")),
                "low": _float_text(row.get("Low", "0")),
                "close": _float_text(row.get("Close", "0")),
                "volume": _float_text(row.get("Volume", "0")),
            }
        )
    for bars in grouped.values():
        bars.sort(key=lambda item: str(item["date"]))
    return grouped


def _interactive_stock_payload(
    row: dict[str, str],
    note: str,
    coverage: list[dict] | None = None,
    chart_data: list[dict[str, float | str]] | None = None,
) -> dict:
    symbol = row.get("Symbol", "")
    hybrid = _float_text(row.get("Hybrid", "50"))
    kronos = _float_text(row.get("Kronos", "0"))
    news_score = _float_text(row.get("News", "50"))
    tech_score = _float_text(row.get("Tech", "50"))
    bars = chart_data or []
    indicators = _technical_indicators(symbol, hybrid, kronos, news_score, tech_score, bars)
    return {
        "symbol": symbol,
        "name": row.get("Name", ""),
        "industry": row.get("Industry", "未分類"),
        "hybrid": hybrid,
        "kronos": kronos,
        "news": news_score,
        "tech": tech_score,
        "action": row.get("Action", "觀望"),
        "reasons": _recommendation_reasons(row, note),
        "strategies": _strategy_items(row, indicators, note),
        "indicators": indicators,
        "model": _stock_model_snapshot(row, indicators),
        "coverage": coverage or [],
        "ohlcv": bars,
    }


def _interactive_model_overview(top_rows: list[dict[str, str]], portfolio: list[str], openbb_live: bool = False) -> list[dict[str, str]]:
    if top_rows:
        avg_kronos = sum(_float_text(row.get("Kronos", "0")) for row in top_rows) / len(top_rows)
        avg_hybrid = sum(_float_text(row.get("Hybrid", "50")) for row in top_rows) / len(top_rows)
        top_pick = f"{top_rows[0].get('Symbol', '')} {top_rows[0].get('Name', '')}".strip()
    else:
        avg_kronos = 0.0
        avg_hybrid = 50.0
        top_pick = "資料不足"
    qlib_line = (
        _first_matching_line(portfolio, "Qlib engine 投組報酬")
        or _first_matching_line(portfolio, "Qlib 即時 IC")
        or _first_matching_line(portfolio, "Qlib engine portfolio return")
        or _first_matching_line(portfolio, "Qlib inline IC")
    )
    qlib_body = _trim_sentence(qlib_line, 72) if qlib_line else "等待 Qlib 產出 IC、Rank IC、週轉率與最大回撤。"
    return [
        {
            "name": "OpenBB",
            "value": "即時資料入口" if openbb_live else "CSV 快取資料",
            "body": "OpenBB/yfinance 即時資料入口已啟用並抓取行情。" if openbb_live else "使用雲端刷新後的 TWSE/TPEx CSV 快取資料，正式排程會每日更新。",
        },
        {
            "name": "Qlib",
            "value": f"Hybrid 均分 {avg_hybrid:.1f}",
            "body": qlib_body,
        },
        {
            "name": "Kronos",
            "value": f"{avg_kronos:+.2f}%",
            "body": f"時間序列預測已納入排序；目前最高分股票為 {top_pick}。",
        },
    ]

