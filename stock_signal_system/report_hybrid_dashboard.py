"""Renders the '# Hybrid Quant Daily Stock Report' dark dashboard HTML."""

from __future__ import annotations

import html

from stock_signal_system.report_markdown import inline_markdown, is_separator_cell, is_table_line, split_table_row


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
    note_cards = "".join(f"<li>{inline_markdown(item)}</li>" for item in notes[:5])
    portfolio_items = "".join(f"<li>{inline_markdown(item)}</li>" for item in portfolio[:4])
    news_items = "".join(f"<li>{inline_markdown(item)}</li>" for item in news[:6])

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
        if is_table_line(line):
            table_lines.append(line)
        elif table_lines:
            tables[current_heading] = _table_lines_to_dicts(table_lines)
            table_lines = []
    return tables


def _table_lines_to_dicts(lines: list[str]) -> list[dict[str, str]]:
    rows = [split_table_row(line) for line in lines]
    if len(rows) < 2:
        return []
    header = rows[0]
    body = rows[2:] if all(is_separator_cell(cell) for cell in rows[1]) else rows[1:]
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
