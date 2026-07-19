"""Renders the interactive technical-chart dashboard for hybrid Chinese reports
('# Hybrid 量化每日選股報告' / '# Hybrid 台股每日分析報告')."""

from __future__ import annotations

import html
import json
import re

from stock_signal_system.report_markdown import BASIC_REPORT_CSS, render_markdown_body
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
  <style>
    {BASIC_REPORT_CSS}
    .tech-board {{ margin: 24px 0 30px; border: 1px solid #d4dbe5; border-radius: 8px; background: #fbfcfd; overflow: hidden; }}
    .tech-head {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 18px; border-bottom: 1px solid #e4e9f0; background: #eef3f8; }}
    .tech-head h2 {{ margin: 0; padding: 0; border: 0; font-size: 20px; }}
    .tech-meta {{ color: #536071; font-size: 13px; }}
    .tech-grid {{ display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 0; }}
    .tech-controls {{ padding: 16px; border-right: 1px solid #e4e9f0; background: #f7f9fb; }}
    .field {{ display: grid; gap: 6px; margin-bottom: 12px; }}
    .field label, .toggles legend {{ font-size: 12px; font-weight: 700; color: #334155; }}
    .field select, .field input {{ width: 100%; min-height: 36px; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px 8px; background: white; color: #111827; }}
    .control-note {{ margin: 6px 0 0; color: #64748b; font-size: 12px; line-height: 1.45; }}
    .stock-filter-stack {{ display: grid; gap: 10px; margin-top: 8px; }}
    .stock-filter-item {{ border: 1px solid #dde5ee; border-radius: 10px; background: #ffffff; padding: 8px 10px; }}
    .stock-filter-toggle {{ display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: #1f2937; font-weight: 700; }}
    .stock-filter-toggle input {{ width: 16px; height: 16px; }}
    .stock-filter-brief {{ margin: 6px 0 0 22px; color: #64748b; font-size: 12px; line-height: 1.45; }}
    .filter-tip {{ margin: 10px 0 0; padding: 10px 12px; border: 1px dashed #cbd5e1; border-radius: 10px; color: #475569; font-size: 12px; line-height: 1.55; background: #f8fafc; }}
    .chip-card {{ margin-top: 12px; border: 1px solid #dde5ee; border-radius: 10px; background: #ffffff; padding: 10px 12px; }}
    .chip-card h3 {{ margin: 0 0 8px; font-size: 13px; color: #0f172a; }}
    .chip-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 10px; }}
    .chip-metric {{ min-width: 0; }}
    .chip-metric b {{ display: block; color: #334155; font-size: 11px; margin-bottom: 2px; }}
    .chip-metric span {{ display: block; color: #111827; font-size: 12px; line-height: 1.4; word-break: break-word; }}
    .focus-card {{ margin-bottom: 12px; border: 1px solid #dde5ee; border-radius: 10px; background: #ffffff; padding: 10px 12px; }}
    .focus-card h3 {{ margin: 0 0 8px; font-size: 13px; color: #0f172a; }}
    .focus-list {{ max-height: 220px; overflow-y: auto; border: 1px solid #e3eaf3; border-radius: 10px; background: linear-gradient(180deg, #fcfeff 0%, #f7fbff 100%); }}
    .focus-item {{ display: flex; gap: 10px; align-items: flex-start; padding: 10px 10px; border-bottom: 1px solid #e6edf5; width: 100%; text-align: left; background: transparent; border-left: 0; border-right: 0; border-top: 0; appearance: none; cursor: pointer; }}
    .focus-item:last-child {{ border-bottom: 0; }}
    .focus-item:hover {{ background: #eef7ff; }}
    .focus-item.is-active {{ background: #d9f0ff; }}
    .focus-rank {{ min-width: 30px; height: 30px; border-radius: 999px; background: #0f766e; color: #fff; display: grid; place-items: center; font-size: 12px; font-weight: 800; }}
    .focus-body {{ min-width: 0; flex: 1; }}
    .focus-title {{ font-size: 12px; font-weight: 800; color: #0f172a; line-height: 1.35; }}
    .focus-title span {{ color: #0f766e; }}
    .focus-note {{ margin-top: 3px; color: #475569; font-size: 11px; line-height: 1.45; }}
    .number-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
    .control-cell {{ display: grid; gap: 4px; min-width: 0; }}
    .control-cell span {{ color: #334155; font-size: 12px; font-weight: 700; }}
    .control-cell small {{ color: #64748b; font-size: 11px; line-height: 1.35; }}
    .toggles {{ border: 0; padding: 0; margin: 12px 0; display: flex; flex-wrap: wrap; gap: 8px; }}
    .toggles legend {{ flex-basis: 100%; margin-bottom: 2px; }}
    .toggles label {{ display: inline-flex; align-items: center; gap: 6px; min-height: 30px; border: 1px solid #d7dee8; border-radius: 999px; background: #ffffff; padding: 4px 10px; font-size: 13px; color: #1f2937; white-space: nowrap; }}
    .chart-toolbar {{ display: grid; gap: 12px; margin-bottom: 12px; }}
    .chart-toggles {{ margin: 0; padding: 12px; border: 1px solid #dde5ee; border-radius: 10px; background: #ffffff; }}
    .chart-info-panel {{ display: grid; gap: 10px; padding: 12px; border: 1px solid #dde5ee; border-radius: 10px; background: linear-gradient(180deg, #fbfdff 0%, #f4f8fc 100%); }}
    .chart-info-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
    .chart-info-title {{ font-size: 13px; font-weight: 800; color: #0f172a; }}
    .chart-info-price {{ font-size: 26px; font-weight: 800; color: #111827; }}
    .chart-info-change {{ font-size: 15px; font-weight: 700; }}
    .chart-info-change.up {{ color: #dc2626; }}
    .chart-info-change.down {{ color: #16a34a; }}
    .chart-info-change.flat {{ color: #475569; }}
    .chart-info-meta {{ color: #475569; font-size: 12px; }}
    .chart-ohlc-grid {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }}
    .chart-ohlc-item {{ border: 1px solid #e3eaf3; border-radius: 10px; background: #ffffff; padding: 8px 10px; }}
    .chart-ohlc-item b {{ display: block; color: #64748b; font-size: 11px; margin-bottom: 2px; }}
    .chart-ohlc-item span {{ display: block; color: #111827; font-size: 14px; font-weight: 700; }}
    .chart-ma-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .chart-ma-chip {{ display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 4px 10px; background: #ffffff; border: 1px solid #dde5ee; font-size: 12px; color: #334155; }}
    .chart-ma-dot {{ width: 8px; height: 8px; border-radius: 999px; }}
    .stock-summary-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
    .stock-summary-card {{ border: 1px solid #dde5ee; border-radius: 10px; background: #ffffff; padding: 10px 12px; }}
    .stock-summary-card b {{ display: block; color: #64748b; font-size: 11px; margin-bottom: 4px; }}
    .stock-summary-card span {{ display: block; color: #111827; font-size: 14px; font-weight: 700; line-height: 1.45; }}
    .strategy-panel {{ margin-top: 14px; border: 1px solid #dde5ee; border-radius: 10px; background: #ffffff; overflow: hidden; }}
    .strategy-panel summary {{ cursor: pointer; list-style: none; padding: 10px 12px; color: #334155; font-size: 13px; font-weight: 800; background: #f8fafc; }}
    .strategy-panel summary::-webkit-details-marker {{ display: none; }}
    .strategy-panel summary::after {{ content: "展開"; float: right; color: #64748b; font-weight: 600; }}
    .strategy-panel[open] summary::after {{ content: "收合"; }}
    .strategy-list {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; padding: 12px; }}
    .strategy-item {{ border: 1px solid #dde5ee; border-radius: 8px; background: #ffffff; padding: 10px 12px; font-size: 12px; min-height: 0; max-height: 92px; overflow: hidden; }}
    .strategy-item b {{ display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; color: #0f172a; margin-bottom: 4px; line-height: 1.4; }}
    .strategy-item span {{ display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; color: #475569; line-height: 1.5; }}
    .chart-wrap {{ padding: 16px; min-width: 0; }}
    #technicalChart {{ width: 100%; height: 620px; display: block; border: 1px solid #d8e0ea; border-radius: 6px; background: #ffffff; }}
    .chart-note {{ margin: 10px 0 0; color: #64748b; font-size: 13px; }}
    .chart-empty {{ display: grid; place-items: center; height: 100%; color: #64748b; font-size: 14px; }}
    .rss-signal-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 10px 0 18px; }}
    .rss-signal-card {{ border: 1px solid #dbe4ee; border-radius: 12px; background: #fbfdff; padding: 14px; }}
    .rss-signal-card h3 {{ margin: 0 0 8px; font-size: 16px; color: #0f172a; }}
    .rss-signal-card p {{ margin: 4px 0; color: #475569; font-size: 13px; }}
    .rss-signal-card .rss-score {{ color: #0f766e; font-weight: 800; }}
    .report-grid {{ display: grid; gap: 14px; margin: 18px 0 22px; }}
    .report-grid--two {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .report-card {{ border: 1px solid #dde5ee; border-radius: 14px; background: #ffffff; padding: 14px; overflow: hidden; }}
    .report-card h2 {{ margin-top: 0; margin-bottom: 10px; border-bottom: 0; padding-bottom: 0; font-size: 18px; }}
    .report-card .table-wrap {{ margin-bottom: 0; }}
    .report-card .table-wrap table {{ font-size: 12px; min-width: 760px; }}
    .report-card .table-wrap th, .report-card .table-wrap td {{ padding: 7px 8px; line-height: 1.45; }}
    .report-card .scroll-box {{ max-height: 380px; overflow-y: auto; border: 1px solid #dbe4ef; border-radius: 12px; background: #f8fbff; padding: 10px 12px; }}
    .report-card .section-note {{ margin: 0 0 8px; color: #64748b; font-size: 12px; line-height: 1.45; }}
    .candidate-panel {{ margin: 14px 0 22px; border: 1px solid #dde5ee; border-radius: 12px; background: #ffffff; overflow: hidden; }}
    .candidate-panel summary {{ list-style: none; cursor: pointer; padding: 10px 12px; background: linear-gradient(180deg, #f8fafc 0%, #eef3f8 100%); color: #0f172a; font-size: 14px; font-weight: 800; }}
    .candidate-panel summary::-webkit-details-marker {{ display: none; }}
    .candidate-panel summary::after {{ content: "展開"; float: right; color: #64748b; font-weight: 600; }}
    .candidate-panel[open] summary::after {{ content: "收合"; }}
    .candidate-panel .table-wrap {{ margin: 0; border: 0; border-top: 1px solid #e5e7eb; border-radius: 0; }}
    details > summary {{ cursor: pointer; font-weight: 700; }}
    details[open] > summary {{ margin-bottom: 8px; }}
    @media (max-width: 980px) {{ .stock-summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
    @media (max-width: 900px) {{ .report-grid--two {{ grid-template-columns: 1fr; }} .chart-ohlc-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
    @media (max-width: 860px) {{ .tech-grid {{ grid-template-columns: 1fr; }} .tech-controls {{ border-right: 0; border-bottom: 1px solid #e4e9f0; }} #technicalChart {{ height: 540px; }} .stock-summary-grid, .chart-ohlc-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
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
      <div class="tech-grid">
        <aside class="tech-controls">
          <div class="field">
            <label for="stockSelect">股票</label>
            <section class="focus-card">
              <h3>綜合關注榜</h3>
              <div id="focusWatchlistPanel" class="focus-list"></div>
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
            <p class="filter-tip">三層是漏斗：品質底池 → 主力動向 → 發動確認，通過越多層可信度越高。買點標記：★最佳買點＝收盤剛突破 60MA 且 MACD 剛金叉；☆短線買點＝剛突破 20MA 且 MACD 剛金叉，優先度僅次於 ★。勾選多層時只顯示同時命中的股票。</p>
            <section class="chip-card">
              <h3>籌碼快照</h3>
              <div id="chipSnapshotPanel" class="chip-grid"></div>
            </section>
          </div>
          <div class="field">
            <label>均線參數</label>
            <div class="number-row">
              <label class="control-cell" for="maShort"><span>短均線</span><input id="maShort" type="number" min="2" max="80" title="短均線"><small>5 代表近 5 根 K 線平均，看短線動能。</small></label>
              <label class="control-cell" for="maMid"><span>中均線</span><input id="maMid" type="number" min="3" max="120" title="中均線"><small>20 代表近 20 根平均，看波段方向。</small></label>
              <label class="control-cell" for="maLong"><span>長均線</span><input id="maLong" type="number" min="5" max="240" title="長均線"><small>60 代表近 60 根平均，看主要趨勢。</small></label>
            </div>
            <p class="control-note">短均線看短線，中均線看波段，長均線看主要趨勢；短均線上穿中均線常代表黃金交叉。</p>
          </div>
          <div class="field">
            <label>RSI / 布林</label>
            <div class="number-row">
              <label class="control-cell" for="rsiLow"><span>RSI 低檔線</span><input id="rsiLow" type="number" min="1" max="50" title="RSI 低檔線"><small>20 以下常代表低檔或弱勢鈍化。</small></label>
              <label class="control-cell" for="rsiHigh"><span>RSI 過熱線</span><input id="rsiHigh" type="number" min="50" max="99" title="RSI 過熱線"><small>80 以上常代表過熱或追高風險。</small></label>
              <label class="control-cell" for="bollingerSigma"><span>布林倍數</span><input id="bollingerSigma" type="number" min="1" max="4" step="0.5" title="布林倍數"><small>2 代表上下緣約 2 倍標準差。</small></label>
            </div>
            <p class="control-note">RSI 低檔線用來看低檔鈍化，過熱線用來看追高風險；布林倍數越大，突破門檻越嚴格。</p>
          </div>
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
              <label><input type="checkbox" data-layer="markers"> K 線型態標記</label>
              <label><input type="checkbox" data-layer="limitUp"> 近十日漲停標記</label>
              <label><input type="checkbox" data-layer="monthlyMacd"> 月均線 / MACD 金叉</label>
              <label><input type="checkbox" data-layer="ma20Volume"> MA20 附近量價放大</label>
            </fieldset>
            <div id="stockSummaryPanel" class="stock-summary-grid"></div>
            <div id="chartInfoPanel" class="chart-info-panel"></div>
          </div>
          <canvas id="technicalChart" width="1120" height="620"></canvas>
          <p class="chart-note">K 線圖支援滑鼠移動與點擊定位；若顯示資料不足，代表該股缺少完整 OHLCV 或技術資料。</p>
          <details class="strategy-panel">
            <summary>策略條件摘要</summary>
            <div id="strategyContext" class="strategy-context"></div>
            <div id="strategyList" class="strategy-list"></div>
          </details>
        </div>
      </div>
    </section>
    """


