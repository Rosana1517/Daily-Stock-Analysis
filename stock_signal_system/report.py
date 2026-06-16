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
    _prune_generated_report_html(report_dir)
    return path


def _prune_generated_report_html(report_dir: Path, keep_latest: int = 3) -> None:
    if keep_latest <= 0:
        return
    html_reports = sorted(report_dir.glob("stock_signals_*.html"), reverse=True)
    for old_path in html_reports[keep_latest:]:
        old_path.unlink(missing_ok=True)


def markdown_to_html(markdown: str, title: str) -> str:
    if markdown.startswith("# Hybrid Quant Daily Stock Report"):
        return hybrid_markdown_to_html(markdown, title)
    if markdown.startswith("# Hybrid 量化每日選股報告"):
        return hybrid_interactive_markdown_to_html(markdown, title)

    body_lines = _render_markdown_body(markdown)

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    {BASIC_REPORT_CSS}
  </style>
</head>
<body>
  <main>
    {"".join(body_lines)}
  </main>
</body>
</html>
"""


BASIC_REPORT_CSS = """
    body { margin: 0; background: #f6f7f9; color: #202124; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans TC", sans-serif; line-height: 1.7; }
    main { max-width: 1040px; margin: 0 auto; padding: 28px 18px 56px; background: #fff; min-height: 100vh; }
    h1 { font-size: 28px; margin: 0 0 20px; }
    h2 { font-size: 21px; margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #e5e7eb; }
    h3 { font-size: 18px; margin: 22px 0 8px; }
    p { margin: 8px 0; }
    ul { padding-left: 22px; margin: 8px 0 16px; }
    li { margin: 5px 0; }
    .table-wrap { overflow-x: auto; margin: 10px 0 22px; border: 1px solid #e5e7eb; border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; min-width: 860px; font-size: 14px; }
    th, td { padding: 9px 10px; border-bottom: 1px solid #edf0f3; text-align: left; vertical-align: top; }
    th { background: #f8fafc; font-weight: 700; color: #111827; }
    tr:nth-child(even) td { background: #fbfcfd; }
    tr:last-child td { border-bottom: 0; }
    strong { font-weight: 700; }
    @media (max-width: 560px) { main { padding: 20px 14px 44px; } h1 { font-size: 23px; } h2 { font-size: 19px; } }
"""


def _render_markdown_body(markdown: str) -> list[str]:
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
        if _is_supported_html_block(line):
            close_list()
            body_lines.append(line)
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
    return body_lines


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


def _is_supported_html_block(line: str) -> bool:
    normalized = line.strip().lower()
    if not (normalized.startswith("<") and normalized.endswith(">")):
        return False
    allowed_prefixes = (
        "<table",
        "</table",
        "<tr",
        "</tr",
        "<td",
        "</td",
        "<th",
        "</th",
        "<thead",
        "</thead",
        "<tbody",
        "</tbody",
        "<strong",
        "</strong",
        "<br",
    )
    return normalized.startswith(allowed_prefixes)


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


def hybrid_interactive_markdown_to_html(markdown: str, title: str) -> str:
    chart_payload = _extract_technical_chart_payload(markdown)
    clean_markdown = _strip_technical_chart_block(markdown)
    body_lines = _render_markdown_body(clean_markdown)
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
    .stock-filter-row {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 8px; }}
    .stock-filter-toggle {{ display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: #1f2937; }}
    .stock-filter-toggle input {{ width: 16px; height: 16px; }}
    .screening-columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }}
    .screening-card {{ border: 1px solid #dde5ee; border-radius: 10px; background: #ffffff; padding: 10px 12px; }}
    .screening-card h3 {{ margin: 0 0 8px; font-size: 13px; color: #0f172a; }}
    .screening-card ul {{ margin: 0; padding-left: 18px; }}
    .screening-card li {{ margin: 4px 0; font-size: 12px; color: #334155; }}
    .screening-card li.active {{ color: #0f766e; font-weight: 700; }}
    .screening-empty {{ margin: 0; font-size: 12px; color: #64748b; }}
    .chip-card {{ margin-top: 12px; border: 1px solid #dde5ee; border-radius: 10px; background: #ffffff; padding: 10px 12px; }}
    .chip-card h3 {{ margin: 0 0 8px; font-size: 13px; color: #0f172a; }}
    .chip-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 10px; }}
    .chip-metric {{ min-width: 0; }}
    .chip-metric b {{ display: block; color: #334155; font-size: 11px; margin-bottom: 2px; }}
    .chip-metric span {{ display: block; color: #111827; font-size: 12px; line-height: 1.4; word-break: break-word; }}
    .number-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
    .control-cell {{ display: grid; gap: 4px; min-width: 0; }}
    .control-cell span {{ color: #334155; font-size: 12px; font-weight: 700; }}
    .control-cell small {{ color: #64748b; font-size: 11px; line-height: 1.35; }}
    .toggles {{ border: 0; padding: 0; margin: 12px 0; display: flex; flex-wrap: wrap; gap: 8px; }}
    .toggles legend {{ flex-basis: 100%; margin-bottom: 2px; }}
    .toggles label {{ display: inline-flex; align-items: center; gap: 6px; min-height: 30px; border: 1px solid #d7dee8; border-radius: 999px; background: #ffffff; padding: 4px 10px; font-size: 13px; color: #1f2937; white-space: nowrap; }}
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
    @media (max-width: 860px) {{ .tech-grid {{ grid-template-columns: 1fr; }} .tech-controls {{ border-right: 0; border-bottom: 1px solid #e4e9f0; }} .screening-columns {{ grid-template-columns: 1fr; }} #technicalChart {{ height: 540px; }} }}
  </style>
</head>
<body>
  <main>
    {chart_section}
    {"".join(body_lines)}
  </main>
  <script>window.__TECH_DATA__ = {chart_json};</script>
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
        <div class="tech-meta">黃金交叉、MACD、RSI、布林通道、K 線型態與量價檢查</div>
      </div>
      <div class="tech-grid">
        <aside class="tech-controls">
          <div class="field">
            <label for="stockSelect">股票</label>
            <select id="stockSelect"></select>
            <div class="stock-filter-row">
              <label class="stock-filter-toggle"><input id="revisedOnlyToggle" type="checkbox">只看新版策略</label>
            </div>
            <div class="screening-columns">
              <section class="screening-card">
                <h3>舊策略股票</h3>
                <div id="legacyStockList"></div>
              </section>
              <section class="screening-card">
                <h3>新版策略股票</h3>
                <div id="revisedStockList"></div>
              </section>
            </div>
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
            <p class="control-note">短均線看短線動能，中均線看波段方向，長均線看主要趨勢；短均線上穿中均線會標示黃金交叉。</p>
          </div>
          <div class="field">
            <label>RSI / 布林</label>
            <div class="number-row">
              <label class="control-cell" for="rsiLow"><span>RSI 低檔線</span><input id="rsiLow" type="number" min="1" max="50" title="RSI 低檔線"><small>20 以下標示低檔或弱勢鈍化。</small></label>
              <label class="control-cell" for="rsiHigh"><span>RSI 過熱線</span><input id="rsiHigh" type="number" min="50" max="99" title="RSI 過熱線"><small>80 以上標示過熱與追高風險。</small></label>
              <label class="control-cell" for="bollingerSigma"><span>布林倍數</span><input id="bollingerSigma" type="number" min="1" max="4" step="0.5" title="布林標準差"><small>2 代表上下緣約 2 倍標準差。</small></label>
            </div>
            <p class="control-note">RSI 低檔線用來看低檔鈍化，過熱線用來看追高風險；布林倍數越大，突破門檻越嚴格。</p>
          </div>
          <fieldset class="toggles">
            <legend>顯示策略</legend>
            <label><input type="checkbox" data-layer="ma" checked> 均線與黃金交叉</label>
            <label><input type="checkbox" data-layer="bollinger" checked> 布林通道</label>
            <label><input type="checkbox" data-layer="support" checked> 支撐壓力</label>
            <label><input type="checkbox" data-layer="volume" checked> 成交量</label>
            <label><input type="checkbox" data-layer="macd" checked> MACD</label>
            <label><input type="checkbox" data-layer="rsi" checked> RSI</label>
            <label><input type="checkbox" data-layer="markers"> 精簡 K 線/三線標記</label>
            <label><input type="checkbox" data-layer="limitUp"> 近 10 日漲停</label>
            <label><input type="checkbox" data-layer="monthlyMacd"> 月均線 MACD 金叉</label>
            <label><input type="checkbox" data-layer="ma20Volume"> 日均線 20 均線放量陽線</label>
          </fieldset>
        </aside>
        <div class="chart-wrap">
          <canvas id="technicalChart" width="1120" height="620"></canvas>
          <p class="chart-note">圖表僅呈現可重算的研究條件；Devil veto、資料不足或低量突破不會被視為每日重點依據。</p>
          <details class="strategy-panel">
            <summary>策略條件摘要</summary>
            <div id="strategyList" class="strategy-list"></div>
          </details>
        </div>
      </div>
    </section>
    """


INTERACTIVE_CHART_JS = r"""
(function () {
  const data = window.__TECH_DATA__ || {defaults: {}, stocks: []};
  const defaults = data.defaults || {};
  const state = {stockIndex: 0, revisedOnly: false, layers: {ma: true, bollinger: true, support: true, volume: true, macd: true, rsi: true, markers: false, limitUp: false, monthlyMacd: false, ma20Volume: false}};
  const $ = (id) => document.getElementById(id);
  const canvas = $("technicalChart");
  if (!canvas || !data.stocks || data.stocks.length === 0) return;
  const ctx = canvas.getContext("2d");
  let chartWidth = 0;
  let chartHeight = 0;
  let labelBoxes = [];
  const controls = ["maShort", "maMid", "maLong", "rsiLow", "rsiHigh", "bollingerSigma"];
  const initial = {maShort: 5, maMid: 20, maLong: 60, rsiLow: 20, rsiHigh: 80, bollingerSigma: 2};
  function visibleStocks() {
    return state.revisedOnly ? data.stocks.filter((stock) => stock.screeningBucket === "revised" || stock.screeningBucket === "chip_breakout") : data.stocks;
  }

  function init() {
    const select = $("stockSelect");
    data.stocks.forEach((stock, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = `${stock.symbol} ${stock.name}｜${stock.decision}`;
      select.appendChild(option);
    });
    Object.keys(initial).forEach((key) => { $(key).value = defaults[key] || initial[key]; });
    select.addEventListener("change", () => { state.stockIndex = Number(select.value); render(); });
    populateStockLists();
    syncStockSelect();
    $("revisedOnlyToggle").addEventListener("change", (event) => {
      state.revisedOnly = event.target.checked;
      state.stockIndex = 0;
      syncStockSelect();
      render();
    });
    controls.forEach((id) => $(id).addEventListener("input", render));
    document.querySelectorAll("[data-layer]").forEach((item) => {
      item.addEventListener("change", () => { state.layers[item.dataset.layer] = item.checked; render(); });
    });
    window.addEventListener("resize", render);
    render();
  }

  function syncStockSelect() {
    const select = $("stockSelect");
    const stocks = visibleStocks();
    select.innerHTML = "";
    stocks.forEach((stock, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = `${stock.symbol} ${stock.name} | ${stock.decision}`;
      select.appendChild(option);
    });
    if (state.stockIndex >= stocks.length) state.stockIndex = 0;
    select.value = String(state.stockIndex);
  }

  function populateStockLists() {
    renderScreeningList("legacyStockList", data.stocks.filter((stock) => stock.screeningBucket === "legacy_watch"));
    renderScreeningList("revisedStockList", data.stocks.filter((stock) => stock.screeningBucket === "revised" || stock.screeningBucket === "chip_breakout"));
  }

  function renderScreeningList(id, stocks) {
    const node = $(id);
    if (!node) return;
    if (!stocks.length) {
      node.innerHTML = '<p class="screening-empty">目前沒有股票。</p>';
      return;
    }
    node.innerHTML = `<ul>${stocks.map((stock) => `<li data-symbol="${escapeHtml(stock.symbol)}">${escapeHtml(stock.symbol)} ${escapeHtml(stock.name)}</li>`).join("")}</ul>`;
  }

  function highlightActiveStock(symbol) {
    document.querySelectorAll(".screening-card li").forEach((item) => {
      item.classList.toggle("active", item.dataset.symbol === symbol);
    });
  }

  function renderChipSnapshot(stock) {
    const node = $("chipSnapshotPanel");
    if (!node) return;
    const chip = stock.chipSnapshot || {};
    const metrics = [
      ["前十大主力強度", formatChipNumber(chip.top10MainForceBuyStrength)],
      ["前十大主力淨買超", formatChipNumber(chip.top10MainForceNetBuy, 0)],
      ["外資連買天數", formatChipNumber(chip.foreignBuyStreakDays, 0)],
      ["主分點連買天數", formatChipNumber(chip.branchMainForceBuyStreakDays, 0)],
      ["主分點", chip.branchMainForceLeader || "n/a"],
      ["籌碼日期", chip.chipDataDate || "n/a"],
      ["來源狀態", chip.chipDataSourceStatus || "n/a"],
      ["主力分點", chip.top10MainForceBrokers || "n/a"],
    ];
    node.innerHTML = metrics.map(([label, value]) => `<div class="chip-metric"><b>${escapeHtml(label)}</b><span>${escapeHtml(String(value))}</span></div>`).join("");
  }

  function formatChipNumber(value, digits = 1) {
    if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "n/a";
    return Number(value).toFixed(digits);
  }

  function params() {
    const value = (id) => Number($(id).value);
    return {
      maShort: value("maShort"), maMid: value("maMid"), maLong: value("maLong"),
      rsiLow: value("rsiLow"), rsiHigh: value("rsiHigh"), bollingerSigma: value("bollingerSigma"),
      bollingerPeriod: defaults.bollingerPeriod || 20, rsiPeriod: defaults.rsiPeriod || 14,
      macdFast: defaults.macdFast || 12, macdSlow: defaults.macdSlow || 26, macdSignal: defaults.macdSignal || 9
    };
  }

  function renderStrategyList(stock) {
    const list = $("strategyList");
    if (!list) return;
    list.innerHTML = "";
    (stock.strategySummary || [])
      .filter((item) => strategyVisible(item.strategy))
      .slice(0, 2)
      .forEach((item) => {
        const node = document.createElement("div");
        node.className = "strategy-item";
        node.innerHTML = `<b>${escapeHtml(item.strategy)} | ${escapeHtml(item.status)}</b><span>${escapeHtml(item.use)}</span>`;
        list.appendChild(node);
      });
  }

  function strategyVisible(strategy) {
    const map = new Map([
      ["近 10 日漲停排除 3 連漲", "limitUp"],
      ["月均線 MACD 金叉向上", "monthlyMacd"],
      ["均線、趨勢與支撐壓力", "ma"],
      ["動能與波動", "rsi"],
      ["型態、量價與突破確認", "markers"],
    ]);
    const layer = map.get(strategy);
    return layer ? state.layers[layer] : true;
  }

  function render() {
    const stock = visibleStocks()[state.stockIndex];
    if (!stock || !stock.bars || stock.bars.length === 0) return;
    highlightActiveStock(stock.symbol);
    renderChipSnapshot(stock);
    renderStrategyList(stock);
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    chartWidth = rect.width;
    chartHeight = rect.height;
    labelBoxes = [];
    canvas.width = Math.max(720, Math.floor(rect.width * ratio));
    canvas.height = Math.floor(rect.height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw(stock, params(), rect.width, rect.height);
  }

  function renderStrategyList(stock) {
    const list = $("strategyList");
    list.innerHTML = "";
    (stock.strategySummary || []).filter((item) => strategyVisible(item.strategy)).slice(0, 3).forEach((item) => {
      const node = document.createElement("div");
      node.className = "strategy-item";
      node.innerHTML = `<b>${escapeHtml(item.strategy)}｜${escapeHtml(item.status)}</b><span>${escapeHtml(item.agent)}：${escapeHtml(item.use)}</span>`;
      list.appendChild(node);
    });
  }

  function strategyVisible(strategy) {
    const map = [
      ["近 10 日漲停排除 3 連漲", "limitUp"],
      ["月均線 MACD 金叉向上", "monthlyMacd"],
      ["日均線股價在 20 均線附近且放量陽線", "ma20Volume"],
      ["黃金交叉 / 死亡交叉", "ma"],
      ["MA20 風險線", "ma"],
      ["布林通道", "bollinger"],
      ["RSI", "rsi"],
      ["量價確認", "volume"],
      ["三線突破", "markers"],
      ["支撐壓力", "support"],
      ["當日 K 線", "markers"]
    ];
    const found = map.find(([name]) => strategy === name);
    return found ? state.layers[found[1]] : true;
  }

  function draw(stock, p, width, height) {
    const bars = stock.bars;
    const closes = bars.map((bar) => bar.close);
    const highs = bars.map((bar) => bar.high);
    const lows = bars.map((bar) => bar.low);
    ctx.clearRect(0, 0, width, height);
    const pad = {left: 56, right: 18, top: 30, bottom: 28};
    const panes = {price: {top: pad.top, height: height * 0.52}, volume: {top: height * 0.56, height: 72}, macd: {top: height * 0.71, height: 76}, rsi: {top: height * 0.86, height: 62}};
    const chartW = width - pad.left - pad.right;
    const step = chartW / Math.max(1, bars.length);
    const x = (i) => pad.left + i * step + step * 0.5;
    const maValues = [sma(closes, p.maShort), sma(closes, p.maMid), sma(closes, p.maLong)];
    const boll = bollinger(closes, p.bollingerPeriod, p.bollingerSigma);
    const priceValues = highs.concat(lows, maValues.flat().filter(Number.isFinite), boll.upper.filter(Number.isFinite), boll.lower.filter(Number.isFinite));
    const priceMin = Math.min(...priceValues) * 0.995;
    const priceMax = Math.max(...priceValues) * 1.005;
    const yPrice = scale(priceMin, priceMax, panes.price.top + panes.price.height, panes.price.top);
    drawPane(panes.price, width, "價格 / K 線");
    bars.forEach((bar, i) => drawCandle(bar, x(i), Math.max(2, step * 0.62), yPrice));
    if (state.layers.bollinger) {
      line(boll.upper, x, yPrice, "#8b5cf6", 1.4);
      line(boll.lower, x, yPrice, "#8b5cf6", 1.4);
    }
    if (state.layers.ma) {
      line(maValues[0], x, yPrice, "#ef4444", 1.6);
      line(maValues[1], x, yPrice, "#2563eb", 1.6);
      line(maValues[2], x, yPrice, "#0f766e", 1.6);
      drawCrossMarkers(closes, p.maShort, p.maMid, x, yPrice);
    }
    if (state.layers.support) drawSupportResistance(stock, yPrice, width);
    if (state.layers.markers) drawMarkers(bars, x, yPrice);
    if (state.layers.limitUp || state.layers.ma20Volume) drawConditionMarkers(bars, closes, x, yPrice, p);
    drawAxis(priceMin, priceMax, yPrice, panes.price, width);

    if (state.layers.volume) drawVolume(bars, x, step, panes.volume, width);
    if (state.layers.macd) drawMacd(closes, x, panes.macd, width, p);
    if (state.layers.rsi) drawRsi(closes, x, panes.rsi, width, p);
    drawHeader(stock, width);
  }

  function drawHeader(stock, width) {
    ctx.fillStyle = "#111827";
    ctx.font = "700 15px system-ui, sans-serif";
    ctx.fillText(`${stock.symbol} ${stock.name}｜${stock.industry}`, 16, 20);
    ctx.textAlign = "right";
    ctx.fillStyle = stock.bucket === "exclude" ? "#b91c1c" : "#0f766e";
    ctx.fillText(`${stock.decision}｜技術 ${stock.technicalScore}`, width - 18, 20);
    ctx.textAlign = "left";
  }

  function drawPane(pane, width, label) {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, pane.top - 1, width, pane.height + 2);
    ctx.strokeStyle = "#e5e7eb";
    ctx.beginPath();
    ctx.moveTo(0, pane.top + pane.height);
    ctx.lineTo(width, pane.top + pane.height);
    ctx.stroke();
    ctx.fillStyle = "#64748b";
    ctx.font = "12px system-ui, sans-serif";
    ctx.fillText(label, 12, pane.top + 16);
  }

  function drawCandle(bar, cx, w, y) {
    const up = bar.close >= bar.open;
    ctx.strokeStyle = up ? "#dc2626" : "#16a34a";
    ctx.fillStyle = up ? "#fee2e2" : "#dcfce7";
    ctx.beginPath();
    ctx.moveTo(cx, y(bar.high));
    ctx.lineTo(cx, y(bar.low));
    ctx.stroke();
    const top = y(Math.max(bar.open, bar.close));
    const bottom = y(Math.min(bar.open, bar.close));
    ctx.fillRect(cx - w / 2, top, w, Math.max(1, bottom - top));
    ctx.strokeRect(cx - w / 2, top, w, Math.max(1, bottom - top));
  }

  function drawSupportResistance(stock, y, width) {
    [["support", "#0891b2", "支撐"], ["resistance", "#f59e0b", "壓力"]].forEach(([key, color, label]) => {
      const value = stock[key];
      if (!Number.isFinite(value)) return;
      const yy = y(value);
      ctx.strokeStyle = color;
      ctx.setLineDash([6, 5]);
      ctx.beginPath();
      ctx.moveTo(56, yy);
      ctx.lineTo(width - 18, yy);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color;
      ctx.fillText(`${label} ${value.toFixed(2)}`, 64, yy - 4);
    });
  }

  function drawCrossMarkers(values, shortWindow, longWindow, x, y) {
    const shortMa = sma(values, shortWindow);
    const longMa = sma(values, longWindow);
    const markers = [];
    for (let i = 1; i < values.length; i += 1) {
      if (!Number.isFinite(shortMa[i - 1]) || !Number.isFinite(longMa[i - 1]) || !Number.isFinite(shortMa[i]) || !Number.isFinite(longMa[i])) continue;
      const golden = shortMa[i - 1] <= longMa[i - 1] && shortMa[i] > longMa[i];
      const death = shortMa[i - 1] >= longMa[i - 1] && shortMa[i] < longMa[i];
      if (golden || death) markers.push({x: x(i), y: y(values[i]) + (golden ? -14 : 16), text: golden ? "金叉" : "死叉", color: golden ? "#dc2626" : "#16a34a", index: i});
    }
    markers.slice(-1).forEach((item) => label(item.x, item.y, item.text, item.color));
  }

  function drawMarkers(bars, x, y) {
    const signals = [];
    const start = Math.max(3, bars.length - 45);
    for (let i = 3; i < bars.length; i += 1) {
      if (i < start) continue;
      const prev = bars.slice(i - 3, i);
      if (bars[i].close > Math.max(...prev.map((bar) => bar.high))) {
        signals.push({index: i, price: bars[i].high, text: "突破", color: "#7c3aed", priority: 3, offset: -18});
      } else if (bars[i].close < Math.min(...prev.map((bar) => bar.low))) {
        signals.push({index: i, price: bars[i].low, text: "跌破", color: "#0f766e", priority: 3, offset: 18});
      } else if (isLongUpper(bars[i])) {
        signals.push({index: i, price: bars[i].high, text: "上影", color: "#b91c1c", priority: 2, offset: -12});
      } else if (isDoji(bars[i]) && i >= bars.length - 18) {
        signals.push({index: i, price: bars[i].close, text: "十字", color: "#475569", priority: 1, offset: 0});
      }
    }
    signals
      .sort((a, b) => b.priority - a.priority || b.index - a.index)
      .slice(0, 2)
      .sort((a, b) => a.index - b.index)
      .forEach((item) => label(x(item.index), y(item.price) + item.offset, item.text, item.color));
  }

  function drawConditionMarkers(bars, closes, x, y, p) {
    const signals = [];
    const ma20 = sma(closes, 20);
    const start = Math.max(1, bars.length - 45);
    for (let i = start; i < bars.length; i += 1) {
      const bar = bars[i];
      const previous = bars[i - 1];
      if (state.layers.limitUp && previous && bar.close / previous.close - 1 >= 0.095 && !hasThreeLimitUps(bars, i)) {
        signals.push({index: i, price: bar.high, text: "漲停", color: "#dc2626", priority: 3, offset: -28});
      }
      const average20 = ma20[i];
      const volumeRatio = volumeRatioAt(bars, i, 20);
      const nearMa20 = Number.isFinite(average20) && Math.abs(bar.close - average20) / average20 <= 0.02;
      const bullish = bar.close > bar.open;
      if (state.layers.ma20Volume && nearMa20 && bullish && volumeRatio >= 1.5) {
        signals.push({index: i, price: bar.close, text: "MA20量陽", color: "#ea580c", priority: 2, offset: -22});
      }
    }
    signals
      .sort((a, b) => b.priority - a.priority || b.index - a.index)
      .slice(0, 2)
      .sort((a, b) => a.index - b.index)
      .forEach((item) => label(x(item.index), y(item.price) + item.offset, item.text, item.color));
  }

  function hasThreeLimitUps(bars, index) {
    if (index < 3) return false;
    for (let start = Math.max(1, index - 9); start <= index - 2; start += 1) {
      const flags = [start, start + 1, start + 2].map((i) => bars[i].close / bars[i - 1].close - 1 >= 0.095);
      if (flags.every(Boolean)) return true;
    }
    return false;
  }

  function volumeRatioAt(bars, index, window) {
    if (index + 1 < window) return null;
    const chunk = bars.slice(index + 1 - window, index + 1);
    const average = chunk.reduce((sum, bar) => sum + bar.volume, 0) / chunk.length;
    return average ? bars[index].volume / average : null;
  }

  function drawVolume(bars, x, step, pane, width) {
    drawPane(pane, width, "成交量");
    const maxVol = Math.max(...bars.map((bar) => bar.volume), 1);
    bars.forEach((bar, i) => {
      const h = (bar.volume / maxVol) * (pane.height - 22);
      ctx.fillStyle = bar.close >= bar.open ? "#fecaca" : "#bbf7d0";
      ctx.fillRect(x(i) - step * 0.32, pane.top + pane.height - h, Math.max(1, step * 0.64), h);
    });
  }

  function drawMacd(closes, x, pane, width, p) {
    drawPane(pane, width, "MACD");
    const macd = macdSeries(closes, p.macdFast, p.macdSlow, p.macdSignal);
    const values = macd.hist.concat(macd.macd, macd.signal).filter(Number.isFinite);
    const min = Math.min(...values, -0.01);
    const max = Math.max(...values, 0.01);
    const y = scale(min, max, pane.top + pane.height - 8, pane.top + 18);
    const zero = y(0);
    ctx.strokeStyle = "#cbd5e1";
    ctx.beginPath();
    ctx.moveTo(56, zero);
    ctx.lineTo(width - 18, zero);
    ctx.stroke();
    macd.hist.forEach((value, i) => {
      if (!Number.isFinite(value)) return;
      ctx.fillStyle = value >= 0 ? "#dc2626" : "#16a34a";
      ctx.fillRect(x(i) - 2, Math.min(zero, y(value)), 4, Math.max(1, Math.abs(zero - y(value))));
    });
    line(macd.macd, x, y, "#2563eb", 1.2);
    line(macd.signal, x, y, "#f97316", 1.2);
  }

  function drawRsi(closes, x, pane, width, p) {
    drawPane(pane, width, "RSI");
    const values = rsiSeries(closes, p.rsiPeriod);
    const y = scale(0, 100, pane.top + pane.height - 8, pane.top + 18);
    [p.rsiLow, p.rsiHigh].forEach((level) => {
      ctx.strokeStyle = "#cbd5e1";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(56, y(level));
      ctx.lineTo(width - 18, y(level));
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#64748b";
      ctx.fillText(String(level), 18, y(level) + 4);
    });
    line(values, x, y, "#9333ea", 1.5);
  }

  function drawAxis(min, max, y, pane, width) {
    ctx.fillStyle = "#64748b";
    ctx.font = "11px system-ui, sans-serif";
    [min, (min + max) / 2, max].forEach((value) => {
      ctx.fillText(value.toFixed(2), width - 60, y(value) + 4);
    });
  }

  function label(x, y, text, color) {
    ctx.font = "11px system-ui, sans-serif";
    const h = 18;
    const w = ctx.measureText(text).width + 10;
    const minX = 4;
    const maxX = Math.max(minX, chartWidth - w - 4);
    const minY = 40;
    const maxY = Math.max(minY, Math.min(chartHeight * 0.42, chartHeight - h - 6));
    let safeX = x - w / 2;
    if (x > chartWidth - w - 18) safeX = x - w - 10;
    if (x < w + 18) safeX = x + 10;
    safeX = Math.min(Math.max(minX, safeX), maxX);
    const anchorY = Math.min(Math.max(minY, y), maxY);
    const offsets = [0, -22, 22, -44, 44, -66, 66];
    let safeY = anchorY;
    for (const offset of offsets) {
      const candidateY = Math.min(Math.max(minY, anchorY + offset), maxY);
      const box = {x: safeX, y: candidateY - 12, w, h};
      if (!labelBoxes.some((item) => boxesOverlap(item, box))) {
        safeY = candidateY;
        labelBoxes.push(box);
        break;
      }
      safeY = candidateY;
    }
    ctx.fillStyle = color;
    ctx.fillRect(safeX, safeY - 12, w, h);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(text, safeX + 5, safeY + 1);
  }

  function boxesOverlap(a, b) {
    return !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
  }

  function line(values, x, y, color, width) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    let started = false;
    values.forEach((value, i) => {
      if (!Number.isFinite(value)) return;
      if (!started) { ctx.moveTo(x(i), y(value)); started = true; }
      else ctx.lineTo(x(i), y(value));
    });
    ctx.stroke();
    ctx.lineWidth = 1;
  }

  function scale(min, max, outMin, outMax) {
    const span = Math.max(max - min, 0.0001);
    return (value) => outMin + ((value - min) / span) * (outMax - outMin);
  }

  function sma(values, window) {
    return values.map((_, index) => {
      if (index + 1 < window) return null;
      return values.slice(index + 1 - window, index + 1).reduce((sum, value) => sum + value, 0) / window;
    });
  }

  function ema(values, span) {
    const k = 2 / (span + 1);
    const out = [];
    values.forEach((value, index) => { out[index] = index === 0 ? value : value * k + out[index - 1] * (1 - k); });
    return out;
  }

  function macdSeries(values, fast, slow, signalSpan) {
    const fastLine = ema(values, fast);
    const slowLine = ema(values, slow);
    const macd = values.map((_, i) => fastLine[i] - slowLine[i]);
    const signal = ema(macd, signalSpan);
    return {macd, signal, hist: macd.map((value, i) => value - signal[i])};
  }

  function rsiSeries(values, period) {
    return values.map((_, index) => {
      if (index < period) return null;
      const deltas = values.slice(index - period + 1, index + 1).map((value, i, list) => i === 0 ? value - values[index - period] : value - list[i - 1]);
      const gain = deltas.filter((value) => value > 0).reduce((sum, value) => sum + value, 0) / period;
      const loss = Math.abs(deltas.filter((value) => value < 0).reduce((sum, value) => sum + value, 0) / period);
      return loss === 0 ? 100 : 100 - (100 / (1 + gain / loss));
    });
  }

  function bollinger(values, period, sigma) {
    const mid = sma(values, period);
    const upper = values.map((_, index) => {
      if (index + 1 < period) return null;
      const chunk = values.slice(index + 1 - period, index + 1);
      const mean = mid[index];
      const sd = Math.sqrt(chunk.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / period);
      return mean + sd * sigma;
    });
    const lower = values.map((_, index) => {
      if (index + 1 < period) return null;
      const chunk = values.slice(index + 1 - period, index + 1);
      const mean = mid[index];
      const sd = Math.sqrt(chunk.reduce((sum, value) => sum + Math.pow(value - mean, 2), 0) / period);
      return mean - sd * sigma;
    });
    return {mid, upper, lower};
  }

  function drawHeader(stock, width) {
    ctx.fillStyle = "#111827";
    ctx.font = "700 15px system-ui, sans-serif";
    ctx.fillText(`${stock.symbol} ${stock.name} | ${stock.industry}`, 16, 20);
    ctx.textAlign = "right";
    ctx.fillStyle = stock.bucket === "exclude" ? "#b91c1c" : "#0f766e";
    ctx.fillText(`${stock.decision} | 技術 ${stock.technicalScore}`, width - 18, 20);
    ctx.textAlign = "left";
  }

  function drawSupportResistance(stock, y, width) {
    [["support", "#0891b2", "支撐"], ["resistance", "#f59e0b", "壓力"]].forEach(([key, color, text]) => {
      const value = stock[key];
      if (!Number.isFinite(value)) return;
      const yy = y(value);
      ctx.strokeStyle = color;
      ctx.setLineDash([6, 5]);
      ctx.beginPath();
      ctx.moveTo(56, yy);
      ctx.lineTo(width - 18, yy);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color;
      ctx.fillText(`${text} ${value.toFixed(2)}`, 64, yy - 4);
    });
  }

  function drawCrossMarkers(values, shortWindow, longWindow, x, y) {
    const shortMa = sma(values, shortWindow);
    const longMa = sma(values, longWindow);
    const markers = [];
    for (let i = 1; i < values.length; i += 1) {
      if (!Number.isFinite(shortMa[i - 1]) || !Number.isFinite(longMa[i - 1]) || !Number.isFinite(shortMa[i]) || !Number.isFinite(longMa[i])) continue;
      const golden = shortMa[i - 1] <= longMa[i - 1] && shortMa[i] > longMa[i];
      const death = shortMa[i - 1] >= longMa[i - 1] && shortMa[i] < longMa[i];
      if (golden || death) {
        markers.push({
          x: x(i),
          y: y(values[i]) + (golden ? -14 : 16),
          text: golden ? "金叉" : "死叉",
          color: golden ? "#dc2626" : "#16a34a",
          index: i,
        });
      }
    }
    markers.slice(-1).forEach((item) => label(item.x, item.y, item.text, item.color));
  }

  function drawMarkers(bars, x, y) {
    const signals = [];
    const start = Math.max(3, bars.length - 45);
    for (let i = 3; i < bars.length; i += 1) {
      if (i < start) continue;
      const prev = bars.slice(i - 3, i);
      if (bars[i].close > Math.max(...prev.map((bar) => bar.high))) {
        signals.push({index: i, price: bars[i].high, text: "突破", color: "#7c3aed", priority: 3, offset: -18});
      } else if (bars[i].close < Math.min(...prev.map((bar) => bar.low))) {
        signals.push({index: i, price: bars[i].low, text: "跌破", color: "#0f766e", priority: 3, offset: 18});
      } else if (isLongUpper(bars[i])) {
        signals.push({index: i, price: bars[i].high, text: "上影", color: "#b91c1c", priority: 2, offset: -12});
      } else if (isDoji(bars[i]) && i >= bars.length - 18) {
        signals.push({index: i, price: bars[i].close, text: "十字", color: "#475569", priority: 1, offset: 0});
      }
    }
    signals
      .sort((a, b) => b.priority - a.priority || b.index - a.index)
      .slice(0, 1)
      .sort((a, b) => a.index - b.index)
      .forEach((item) => label(x(item.index), y(item.price) + item.offset, item.text, item.color));
  }

  function drawConditionMarkers(bars, closes, x, y, p) {
    const signals = [];
    const ma20 = sma(closes, 20);
    const start = Math.max(1, bars.length - 45);
    for (let i = start; i < bars.length; i += 1) {
      const bar = bars[i];
      const previous = bars[i - 1];
      if (state.layers.limitUp && previous && bar.close / previous.close - 1 >= 0.095 && !hasThreeLimitUps(bars, i)) {
        signals.push({index: i, price: bar.high, text: "漲停", color: "#dc2626", priority: 3, offset: -28});
      }
      const average20 = ma20[i];
      const volumeRatio = volumeRatioAt(bars, i, 20);
      const nearMa20 = Number.isFinite(average20) && Math.abs(bar.close - average20) / average20 <= 0.02;
      const bullish = bar.close > bar.open;
      if (state.layers.ma20Volume && nearMa20 && bullish && volumeRatio >= 1.5) {
        signals.push({index: i, price: bar.close, text: "MA20量陽", color: "#ea580c", priority: 2, offset: -22});
      }
    }
    signals
      .sort((a, b) => b.priority - a.priority || b.index - a.index)
      .slice(0, 1)
      .sort((a, b) => a.index - b.index)
      .forEach((item) => label(x(item.index), y(item.price) + item.offset, item.text, item.color));
  }

  function drawVolume(bars, x, step, pane, width) {
    drawPane(pane, width, "成交量");
    const maxVol = Math.max(...bars.map((bar) => bar.volume), 1);
    bars.forEach((bar, i) => {
      const h = (bar.volume / maxVol) * (pane.height - 22);
      ctx.fillStyle = bar.close >= bar.open ? "#fecaca" : "#bbf7d0";
      ctx.fillRect(x(i) - step * 0.32, pane.top + pane.height - h, Math.max(1, step * 0.64), h);
    });
  }

  function isDoji(bar) {
    return Math.abs(bar.close - bar.open) / Math.max(bar.high - bar.low, 0.0001) <= 0.12;
  }

  function isLongUpper(bar) {
    const body = Math.abs(bar.close - bar.open);
    return bar.high - Math.max(bar.open, bar.close) >= body * 2;
  }

  function escapeHtml(text) {
    return String(text || "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  }

  init();
})();
"""


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
