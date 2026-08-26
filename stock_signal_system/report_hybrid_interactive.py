"""Renders the interactive technical-chart dashboard for hybrid Chinese reports
('# Hybrid 量化每日選股報告' / '# Hybrid 台股每日分析報告')."""

from __future__ import annotations

import html
import json
import re

from stock_signal_system.report_markdown import BASIC_REPORT_CSS, GOOGLE_FONTS_LINK, render_markdown_body
from stock_signal_system.report_technical_chart_js import INTERACTIVE_CHART_JS


def hybrid_interactive_markdown_to_html(markdown: str, title: str) -> str:
    chart_payload = _extract_technical_chart_payload(markdown)
    clean_markdown = _strip_technical_chart_block(markdown)
    body_lines = render_markdown_body(clean_markdown)
    chart_json = json.dumps(chart_payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    chart_section = _interactive_chart_section() if chart_payload.get("stocks") else ""

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  {GOOGLE_FONTS_LINK}
  <style>
    {BASIC_REPORT_CSS}
    @media (prefers-reduced-motion: no-preference) {{
      @keyframes rise-in {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
      .tech-board, .rss-signal-card, .report-card, .candidate-panel {{ animation: rise-in .5s cubic-bezier(.2,.7,.3,1) both; }}
      .rss-signal-grid .rss-signal-card:nth-child(1) {{ animation-delay: .02s; }}
      .rss-signal-grid .rss-signal-card:nth-child(2) {{ animation-delay: .07s; }}
      .rss-signal-grid .rss-signal-card:nth-child(3) {{ animation-delay: .12s; }}
      .rss-signal-grid .rss-signal-card:nth-child(4) {{ animation-delay: .17s; }}
      .rss-signal-grid .rss-signal-card:nth-child(5) {{ animation-delay: .22s; }}
    }}
    .tech-board {{ margin: 26px 0 32px; border: 1px solid var(--line); border-radius: 14px; background: var(--paper-card); overflow: hidden; box-shadow: 0 24px 48px -32px rgba(60,45,20,.35); }}
    .tech-head {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 22px; border-bottom: 1px solid var(--line); background: linear-gradient(135deg, #2a2115 0%, #453522 100%); }}
    .tech-head h2 {{ margin: 0; padding: 0; border: 0; font-size: 21px; color: #f6ecd8; }}
    .tech-meta {{ color: #d8c9a8; font-size: 12.5px; font-family: var(--font-mono); }}
    .tech-grid {{ display: grid; grid-template-columns: 292px minmax(0, 1fr); gap: 0; }}
    .tech-controls {{ padding: 18px; border-right: 1px solid var(--line); background: #f6f0e2; }}
    .field {{ display: grid; gap: 6px; margin-bottom: 14px; }}
    .field label, .toggles legend {{ font-size: 11.5px; font-weight: 700; letter-spacing: .04em; color: var(--brass-deep); text-transform: uppercase; }}
    .field select, .field input {{ width: 100%; min-height: 38px; border: 1px solid #d8cba9; border-radius: 7px; padding: 6px 9px; background: #fffdf8; color: var(--ink); font-family: var(--font-mono); }}
    .field select:focus, .field input:focus {{ outline: 2px solid var(--brass); outline-offset: 1px; }}
    .control-note {{ margin: 6px 0 0; color: var(--ink-soft); font-size: 11.5px; line-height: 1.5; }}
    .stock-filter-stack {{ display: grid; gap: 8px; margin-top: 10px; }}
    .stock-filter-item {{ border: 1px solid #e2d6b8; border-radius: 10px; background: #fffdf8; padding: 9px 11px; }}
    .stock-filter-toggle {{ display: inline-flex; align-items: center; gap: 7px; font-size: 13px; color: var(--ink); font-weight: 700; accent-color: var(--brass); }}
    .stock-filter-toggle input {{ width: 16px; height: 16px; accent-color: var(--brass); }}
    .stock-filter-brief {{ margin: 6px 0 0 23px; color: var(--ink-soft); font-size: 11.5px; line-height: 1.5; }}
    .filter-tip {{ margin: 10px 0 0; padding: 11px 13px; border: 1px dashed #cbb888; border-radius: 10px; color: var(--ink-soft); font-size: 11.5px; line-height: 1.6; background: #f1e8d2; }}
    .chip-card {{ margin-top: 12px; border: 1px solid #e2d6b8; border-radius: 10px; background: #fffdf8; padding: 11px 13px; }}
    .chip-card h3 {{ margin: 0 0 8px; font-size: 12.5px; color: var(--brass-deep); font-family: var(--font-mono); text-transform: uppercase; letter-spacing: .05em; }}
    .chip-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 10px; }}
    .chip-metric {{ min-width: 0; }}
    .chip-metric b {{ display: block; color: var(--ink-soft); font-size: 10.5px; margin-bottom: 2px; }}
    .chip-metric span {{ display: block; color: var(--ink); font-family: var(--font-mono); font-size: 12px; line-height: 1.4; word-break: break-word; }}
    .focus-card {{ margin-bottom: 12px; border: 1px solid #e2d6b8; border-radius: 10px; background: #fffdf8; padding: 11px 13px; }}
    .focus-card h3 {{ margin: 0 0 8px; font-size: 12.5px; color: var(--brass-deep); font-family: var(--font-mono); text-transform: uppercase; letter-spacing: .05em; }}
    .focus-list {{ max-height: 226px; overflow-y: auto; border: 1px solid #e6dcc0; border-radius: 10px; background: #fffefb; }}
    .focus-item {{ display: flex; gap: 10px; align-items: flex-start; padding: 10px 11px; border-bottom: 1px solid #ede3c9; width: 100%; text-align: left; background: transparent; border-left: 0; border-right: 0; border-top: 0; appearance: none; cursor: pointer; transition: background .15s ease; font-family: inherit; }}
    .focus-item:last-child {{ border-bottom: 0; }}
    .focus-item:hover {{ background: #f4ecd7; }}
    .focus-item.is-active {{ background: #ecd9a9; }}
    .focus-rank {{ min-width: 28px; height: 28px; border-radius: 999px; background: var(--brass-deep); color: #fff8ea; display: grid; place-items: center; font-size: 11.5px; font-weight: 800; font-family: var(--font-mono); flex-shrink: 0; }}
    .focus-body {{ min-width: 0; flex: 1; }}
    .focus-title {{ font-size: 12px; font-weight: 800; color: var(--ink); line-height: 1.4; }}
    .focus-title span {{ color: var(--brass-deep); }}
    .focus-note {{ margin-top: 3px; color: var(--ink-soft); font-size: 11px; line-height: 1.5; }}
    .number-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
    .control-cell {{ display: grid; gap: 4px; min-width: 0; }}
    .control-cell span {{ color: var(--brass-deep); font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; }}
    .control-cell small {{ color: var(--ink-soft); font-size: 10.5px; line-height: 1.4; }}
    .toggles {{ border: 0; padding: 0; margin: 12px 0; display: flex; flex-wrap: wrap; gap: 8px; }}
    .toggles legend {{ flex-basis: 100%; margin-bottom: 4px; }}
    .toggles label {{ display: inline-flex; align-items: center; gap: 6px; min-height: 32px; border: 1px solid #d8cba9; border-radius: 999px; background: #fffdf8; padding: 4px 12px; font-size: 13px; color: var(--ink); white-space: nowrap; transition: border-color .15s ease, background .15s ease; }}
    @supports selector(:has(*)) {{
      .toggles label:has(input:checked) {{ border-color: var(--brass); background: #f1e3c1; color: var(--brass-deep); font-weight: 700; }}
      .stock-filter-toggle:has(input:checked) {{ color: var(--brass-deep); }}
      .tier-toggle:has(input:checked) {{ color: var(--brass-deep); font-weight: 700; }}
    }}
    .toggles input, .tier-toggle input {{ accent-color: var(--brass); }}
    .chart-toolbar {{ display: grid; gap: 12px; margin-bottom: 14px; }}
    .chart-toggles {{ margin: 0; padding: 13px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper-card); }}
    .chart-info-panel {{ display: grid; gap: 10px; padding: 13px; border: 1px solid var(--line); border-radius: 10px; background: linear-gradient(180deg, #fffdf8 0%, #f6f0e2 100%); }}
    .chart-info-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
    .chart-info-title {{ font-size: 13px; font-weight: 800; color: var(--ink); }}
    .chart-info-price {{ font-size: 27px; font-weight: 700; color: var(--ink); font-family: var(--font-mono); }}
    .chart-info-change {{ font-size: 15px; font-weight: 700; font-family: var(--font-mono); }}
    .chart-info-change.up {{ color: var(--up); }}
    .chart-info-change.down {{ color: var(--down); }}
    .chart-info-change.flat {{ color: var(--ink-soft); }}
    .chart-info-meta {{ color: var(--ink-soft); font-size: 12px; }}
    .chart-ohlc-grid {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }}
    .chart-ohlc-item {{ border: 1px solid var(--line); border-radius: 10px; background: var(--paper-card); padding: 8px 10px; }}
    .chart-ohlc-item b {{ display: block; color: var(--ink-soft); font-size: 10.5px; margin-bottom: 2px; text-transform: uppercase; letter-spacing: .04em; }}
    .chart-ohlc-item span {{ display: block; color: var(--ink); font-size: 14px; font-weight: 700; font-family: var(--font-mono); }}
    .chart-ma-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .chart-ma-chip {{ display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 4px 11px; background: var(--paper-card); border: 1px solid var(--line); font-size: 12px; font-family: var(--font-mono); color: var(--ink-soft); }}
    .chart-ma-dot {{ width: 8px; height: 8px; border-radius: 999px; }}
    .stock-summary-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
    .stock-summary-card {{ border: 1px solid var(--line); border-radius: 10px; background: var(--paper-card); padding: 10px 12px; }}
    .stock-summary-card b {{ display: block; color: var(--ink-soft); font-size: 10.5px; margin-bottom: 4px; text-transform: uppercase; letter-spacing: .04em; }}
    .stock-summary-card span {{ display: block; color: var(--ink); font-size: 14px; font-weight: 700; line-height: 1.45; font-family: var(--font-mono); }}
    .strategy-panel {{ margin-top: 16px; border: 1px solid var(--line); border-radius: 10px; background: var(--paper-card); overflow: hidden; }}
    .strategy-panel summary {{ cursor: pointer; list-style: none; padding: 11px 13px; color: var(--brass-deep); font-size: 13px; font-weight: 800; background: #f6f0e2; }}
    .strategy-panel summary::-webkit-details-marker {{ display: none; }}
    .strategy-panel summary::after {{ content: "展開"; float: right; color: var(--ink-soft); font-weight: 600; }}
    .strategy-panel[open] summary::after {{ content: "收合"; }}
    .tech-pristine-note {{ display: none; padding: 10px 22px; background: #2a2115; color: #f1e3c1; font-size: 12.5px; font-family: var(--font-mono); border-bottom: 1px solid var(--line); }}
    .tech-pristine-note:not(:empty) {{ display: block; }}
    .filter-detail {{ margin: 10px 0 0; }}
    .filter-detail p.control-note {{ margin: 0; padding: 12px 13px; }}
    .advanced-field {{ padding: 12px 13px; margin: 0; }}
    .advanced-field + .advanced-field {{ border-top: 1px solid var(--line); }}
    .toggle-more {{ margin: 0 0 12px; }}
    .toggle-more-body {{ margin: 0; border-top: 1px solid var(--line); border-radius: 0; }}
    .strategy-list {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; padding: 13px; }}
    .strategy-item {{ border: 1px solid var(--line); border-radius: 8px; background: var(--paper-card); padding: 10px 12px; font-size: 12px; min-height: 0; max-height: 92px; overflow: hidden; }}
    .strategy-item b {{ display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; color: var(--ink); margin-bottom: 4px; line-height: 1.4; }}
    .strategy-item span {{ display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; color: var(--ink-soft); line-height: 1.5; }}
    .tier-filter {{ margin-top: 10px; }}
    .tier-filter-title {{ font-size: 11.5px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--brass-deep); margin-bottom: 6px; }}
    .tier-toggle {{ display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--ink); padding: 4px 0; }}
    .tier-toggle input {{ width: 15px; height: 15px; }}
    .chart-zoom-bar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }}
    .zoom-btn {{ min-width: 40px; min-height: 36px; border: 1px solid #d8cba9; border-radius: 8px; background: var(--paper-card); color: var(--ink); font-size: 15px; font-weight: 800; cursor: pointer; padding: 0 13px; transition: background .15s ease, transform .1s ease; }}
    .zoom-btn:hover {{ background: #f1e3c1; }}
    .zoom-btn:active {{ transform: scale(.94); }}
    .zoom-btn.zoom-reset {{ font-size: 12.5px; font-weight: 700; font-family: var(--font-body); }}
    .zoom-status {{ color: var(--ink-soft); font-size: 12px; font-family: var(--font-mono); }}
    .chart-wrap {{ padding: 18px; min-width: 0; }}
    #technicalChart {{ width: 100%; height: 620px; display: block; border: 1px solid #d8cba9; border-radius: 8px; background: #ffffff; touch-action: pan-y; cursor: grab; box-shadow: inset 0 0 0 1px rgba(255,255,255,.6); }}
    #technicalChart.is-panning {{ cursor: grabbing; }}
    .chart-note {{ margin: 10px 0 0; color: var(--ink-soft); font-size: 12.5px; }}
    .chart-empty {{ display: grid; place-items: center; height: 100%; color: var(--ink-soft); font-size: 14px; }}
    .rss-signal-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 10px 0 18px; }}
    .rss-signal-card {{ border: 1px solid var(--line); border-left: 3px solid var(--brass); border-radius: 10px; background: var(--paper-card); padding: 14px; }}
    .rss-signal-card h3 {{ margin: 0 0 8px; font-size: 16px; font-family: var(--font-display); font-weight: 700; color: var(--ink); }}
    .rss-signal-card p {{ margin: 4px 0; color: var(--ink-soft); font-size: 13px; }}
    .rss-signal-card .rss-score {{ color: var(--brass-deep); font-weight: 800; font-family: var(--font-mono); }}
    .report-grid {{ display: grid; gap: 10px; margin: 16px 0 20px; align-items: start; }}
    .report-grid--two {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .report-grid--two .report-card {{ margin: 0; height: 100%; }}
    .report-card {{ border: 1px solid var(--line); border-radius: 14px; background: var(--paper-card); padding: 16px; overflow: hidden; box-shadow: 0 16px 32px -28px rgba(60,45,20,.4); }}
    .report-card h2 {{ margin-top: 0; margin-bottom: 12px; border-bottom: 0; padding-bottom: 0; padding-left: 0; border-left: 0; font-size: 18px; }}
    .report-card .table-wrap {{ margin-bottom: 0; }}
    .report-card .table-wrap table {{ font-size: 13.5px; min-width: 640px; }}
    .report-card .table-wrap th, .report-card .table-wrap td {{ padding: 8px 10px; line-height: 1.5; }}
    .report-card .scroll-box {{ max-height: 380px; overflow-y: auto; border: 1px solid var(--line); border-radius: 12px; background: #f6f0e2; padding: 10px 12px; }}
    .report-card .section-note {{ margin: 0 0 8px; color: var(--ink-soft); font-size: 12px; line-height: 1.5; }}
    .candidate-panel {{ margin: 14px 0 22px; border: 1px solid var(--line); border-radius: 12px; background: var(--paper-card); overflow: hidden; }}
    .candidate-panel summary {{ list-style: none; cursor: pointer; padding: 11px 13px; background: linear-gradient(180deg, #f6f0e2 0%, #ecdfc0 100%); color: var(--brass-deep); font-size: 14px; font-weight: 800; }}
    .candidate-panel summary::-webkit-details-marker {{ display: none; }}
    .candidate-panel summary::after {{ content: "展開"; float: right; color: var(--ink-soft); font-weight: 600; }}
    .candidate-panel[open] summary::after {{ content: "收合"; }}
    .candidate-panel .table-wrap {{ margin: 0; border: 0; border-top: 1px solid var(--line); border-radius: 0; }}
    .candidate-panel > .table-wrap table {{ font-size: 14px; min-width: 620px; }}
    .candidate-panel > .table-wrap th, .candidate-panel > .table-wrap td {{ padding: 9px 11px; line-height: 1.5; }}
    .candidate-detail-panel {{ border: 0; border-top: 1px solid var(--line); border-radius: 0; background: #f8f4e8; }}
    .candidate-detail-panel summary {{ list-style: none; cursor: pointer; padding: 9px 13px; color: var(--ink-soft); font-size: 12.5px; font-weight: 700; }}
    .candidate-detail-panel summary::-webkit-details-marker {{ display: none; }}
    .candidate-detail-panel summary::after {{ content: "展開"; float: right; color: var(--ink-soft); font-weight: 600; }}
    .candidate-detail-panel[open] summary::after {{ content: "收合"; }}
    .candidate-detail-panel .table-wrap {{ margin: 0; border: 0; border-top: 1px solid var(--line); border-radius: 0; }}
    .candidate-detail-panel .table-wrap table {{ font-size: 12px; min-width: 860px; }}
    details > summary {{ cursor: pointer; font-weight: 700; }}
    details[open] > summary {{ margin-bottom: 8px; }}
    @media (max-width: 980px) {{ .stock-summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
    @media (max-width: 900px) {{ .report-grid--two {{ grid-template-columns: 1fr; }} .chart-ohlc-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
    @media (max-width: 860px) {{ .tech-grid {{ grid-template-columns: 1fr; }} .tech-controls {{ border-right: 0; border-bottom: 1px solid var(--line); }} #technicalChart {{ height: 540px; }} .stock-summary-grid, .chart-ohlc-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
  </style>
</head>
  <body>
    <main>
    {"".join(body_lines).split('<div id="tech-section-marker"></div>', 1)[0]}
    {chart_section}
    {"".join(body_lines).split('<div id="tech-section-marker"></div>', 1)[1] if '<div id="tech-section-marker"></div>' in "".join(body_lines) else ""}
    </main>
  <script id="technicalChartData" type="application/json">{chart_json}</script>
  <script>window.__TECH_DATA__ = JSON.parse(document.getElementById("technicalChartData").textContent);</script>
  <script>{INTERACTIVE_CHART_JS}</script>
</body>
</html>
"""


def _extract_technical_chart_payload(markdown: str) -> dict:
    match = re.search(r"```technical-chart-data\s*(.*?)\s*```", markdown, flags=re.DOTALL)
    if not match:
        return {"defaults": {}, "agentPolicy": [], "stocks": []}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {"defaults": {}, "agentPolicy": [], "stocks": []}
    return payload if isinstance(payload, dict) else {"defaults": {}, "agentPolicy": [], "stocks": []}


def _strip_technical_chart_block(markdown: str) -> str:
    return re.sub(r"\n?```technical-chart-data\s*.*?\s*```\n?", "\n", markdown, flags=re.DOTALL)


def _interactive_chart_section() -> str:
    return """
    <section class="tech-board" aria-label="互動技術分析">
      <div class="tech-head">
        <h2>互動技術分析</h2>
        <div class="tech-meta">均線交叉、MACD、RSI、布林通道、K 線型態與量價檢查</div>
      </div>
      <div id="techPristineNote" class="tech-pristine-note"></div>
      <div class="tech-grid">
        <aside class="tech-controls">
          <div class="field">
            <label for="stockSelect">股票</label>
            <section class="focus-card">
              <h3>綜合關注榜</h3>
              <div id="focusWatchlistPanel" class="focus-list"></div>
            </section>
            <section class="focus-card">
              <h3>璞玉選股名單</h3>
              <div id="pristineWatchlistPanel" class="focus-list"></div>
            </section>
            <select id="stockSelect"></select>
            <div class="stock-filter-stack">
              <section class="stock-filter-item">
                <label class="stock-filter-toggle"><input id="legacyStrategyToggle" type="checkbox">第 1 層：品質底池（選股範圍）</label>
                <p class="stock-filter-brief">以流動性、均量、趨勢與基本品質篩出可研究的母池，回答「哪些股票值得看」。</p>
              </section>
              <section class="stock-filter-item">
                <label class="stock-filter-toggle"><input id="chipRadarToggle" type="checkbox" checked>第 2 層：主力動向（誰在買）</label>
                <p class="stock-filter-brief">看前十大主力買超、外資連買與主分點連買，確認有真實資金正在照顧。</p>
              </section>
              <section class="stock-filter-item">
                <label class="stock-filter-toggle"><input id="newStrategyToggle" type="checkbox">第 3 層：發動確認（何時買）</label>
                <p class="stock-filter-brief">以 K 值 &lt; 40、MA20 上升、盤整區間突破確認發動時點，回答「現在能不能進場」。</p>
              </section>
            </div>
            <section class="stock-filter-item tier-filter">
              <div class="tier-filter-title">股價分類</div>
              <label class="tier-toggle"><input id="tierLowToggle" type="checkbox" checked>低價位（30 元以下）</label>
              <label class="tier-toggle"><input id="tierMidToggle" type="checkbox" checked>中價位（30~80 元）</label>
              <label class="tier-toggle"><input id="tierHighToggle" type="checkbox" checked>高價位（80 元以上）</label>
            </section>
            <p class="filter-tip">三層漏斗：品質底池 → 主力動向 → 發動確認，通過越多層可信度越高；☆★◆ 買點標記彼此獨立，互不影響。</p>
            <details class="strategy-panel filter-detail">
              <summary>訊號定義說明</summary>
              <p class="control-note">☆短線買點＝剛突破 20MA+MACD 剛金叉(右側,第一優先)；★最佳買點＝剛突破 60MA+MACD 剛金叉(右側,次優先)；◆超跌抄底＝跌破季線且創波段新低但 KD 低檔背離(左側搶反彈,嚴設停損)。勾選多層時只顯示同時命中的股票；股價分類與漏斗層是「同時滿足」關係(綜合關注榜不受價位篩選影響，僅標示價位)。</p>
            </details>
            <section class="chip-card">
              <h3>籌碼快照</h3>
              <div id="chipSnapshotPanel" class="chip-grid"></div>
            </section>
          </div>
          <details class="strategy-panel">
            <summary>進階圖表參數（均線／RSI／布林，選填）</summary>
            <div class="field advanced-field">
              <label>均線參數</label>
              <div class="number-row">
                <label class="control-cell" for="maShort"><span>短均線</span><input id="maShort" type="number" min="2" max="80" title="短均線"><small>5 代表近 5 根 K 線平均，看短線動能。</small></label>
                <label class="control-cell" for="maMid"><span>中均線</span><input id="maMid" type="number" min="3" max="120" title="中均線"><small>20 代表近 20 根平均，看波段方向。</small></label>
                <label class="control-cell" for="maLong"><span>長均線</span><input id="maLong" type="number" min="5" max="240" title="長均線"><small>60 代表近 60 根平均，看主要趨勢。</small></label>
              </div>
              <p class="control-note">短均線看短線，中均線看波段，長均線看主要趨勢；短均線上穿中均線常代表黃金交叉。</p>
            </div>
            <div class="field advanced-field">
              <label>RSI / 布林</label>
              <div class="number-row">
                <label class="control-cell" for="rsiLow"><span>RSI 低檔線</span><input id="rsiLow" type="number" min="1" max="50" title="RSI 低檔線"><small>20 以下常代表低檔或弱勢鈍化。</small></label>
                <label class="control-cell" for="rsiHigh"><span>RSI 過熱線</span><input id="rsiHigh" type="number" min="50" max="99" title="RSI 過熱線"><small>80 以上常代表過熱或追高風險。</small></label>
                <label class="control-cell" for="bollingerSigma"><span>布林倍數</span><input id="bollingerSigma" type="number" min="1" max="4" step="0.5" title="布林倍數"><small>2 代表上下緣約 2 倍標準差。</small></label>
              </div>
              <p class="control-note">RSI 低檔線用來看低檔鈍化，過熱線用來看追高風險；布林倍數越大，突破門檻越嚴格。</p>
            </div>
          </details>
        </aside>
        <div class="chart-wrap">
          <div class="chart-toolbar">
            <fieldset class="toggles chart-toggles">
              <legend>顯示策略</legend>
              <label><input type="checkbox" data-layer="ma" checked> 均線與黃金交叉</label>
              <label><input type="checkbox" data-layer="bollinger" checked> 布林通道</label>
              <label><input type="checkbox" data-layer="support" checked> 支撐壓力</label>
              <label><input type="checkbox" data-layer="volume" checked> 成交量</label>
              <label><input type="checkbox" data-layer="macd" checked> MACD</label>
              <label><input type="checkbox" data-layer="rsi" checked> RSI</label>
            </fieldset>
            <details class="strategy-panel toggle-more">
              <summary>更多標記（選用）</summary>
              <fieldset class="toggles chart-toggles toggle-more-body">
                <label><input type="checkbox" data-layer="markers"> K 線型態標記</label>
                <label><input type="checkbox" data-layer="limitUp"> 近十日漲停標記</label>
                <label><input type="checkbox" data-layer="monthlyMacd"> 月均線 / MACD 金叉</label>
                <label><input type="checkbox" data-layer="ma20Volume"> MA20 附近量價放大</label>
              </fieldset>
            </details>
            <div id="stockSummaryPanel" class="stock-summary-grid"></div>
            <div id="chartInfoPanel" class="chart-info-panel"></div>
          </div>
          <div class="chart-zoom-bar">
            <button type="button" id="zoomOutBtn" class="zoom-btn" title="縮小">－</button>
            <button type="button" id="zoomInBtn" class="zoom-btn" title="放大">＋</button>
            <button type="button" id="zoomResetBtn" class="zoom-btn zoom-reset">重設縮放</button>
            <span id="zoomStatus" class="zoom-status"></span>
          </div>
          <canvas id="technicalChart" width="1120" height="620"></canvas>
          <p class="chart-note">滑鼠：滾輪縮放、拖曳平移、雙擊還原、點擊定位單日 K 棒。手機：雙指縮放、單指左右拖曳平移（上下滑動仍可捲動頁面）。若顯示資料不足，代表該股缺少完整 OHLCV 或技術資料。</p>
          <details class="strategy-panel">
            <summary>策略條件摘要</summary>
            <div id="strategyContext" class="strategy-context"></div>
            <div id="strategyList" class="strategy-list"></div>
          </details>
        </div>
      </div>
    </section>
    """


