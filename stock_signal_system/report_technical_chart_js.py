"""The interactive technical-chart client-side script, embedded verbatim into the hybrid interactive report HTML."""

from __future__ import annotations

INTERACTIVE_CHART_JS = r"""
(function () {
  const data = window.__TECH_DATA__ || {defaults: {}, stocks: []};
  const defaults = data.defaults || {};
  const state = {
    stockIndex: 0,
    activeSymbol: null,
    hoveredBarIndex: null,
    pinnedBarIndex: null,
    layout: null,
    filters: {chipRadar: true, newStrategy: false, oldStrategy: false},
    tiers: {low: true, mid: true, high: true},
    zoom: {start: null, count: null},
    layers: {ma: true, bollinger: true, support: true, volume: true, macd: true, rsi: true, markers: false, limitUp: false, monthlyMacd: false, ma20Volume: false}
  };
  const $ = (id) => document.getElementById(id);
  const canvas = $("technicalChart");
  if (!canvas || !data.stocks || data.stocks.length === 0) return;
  const ctx = canvas.getContext("2d");
  let chartWidth = 0;
  let chartHeight = 0;
  let labelBoxes = [];
  const MIN_VISIBLE_BARS = 10;
  const drag = {active: false, moved: false, startX: 0, startViewStart: 0};
  const pinch = {active: false, startDistance: 0, startCount: 0, startStart: 0, anchorRatio: 0.5};
  const controls = ["maShort", "maMid", "maLong", "rsiLow", "rsiHigh", "bollingerSigma"];
  const initial = {maShort: 5, maMid: 20, maLong: 60, rsiLow: 20, rsiHigh: 80, bollingerSigma: 2};

  function screeningFlags(stock) {
    return stock.screeningFlags || {};
  }

  function isChipRadar(stock) {
    return Boolean(screeningFlags(stock).chipRadar);
  }

  function isNewStrategy(stock) {
    return Boolean(screeningFlags(stock).newStrategy);
  }

  function isOldStrategy(stock) {
    const flags = screeningFlags(stock);
    return Boolean(flags.legacyMotherPoolHit ?? flags.legacy);
  }

  function tierKey(stock) {
    const tier = String(stock.priceTier || "");
    if (tier === "低價位") return "low";
    if (tier === "中價位") return "mid";
    if (tier === "高價位") return "high";
    return null;
  }

  function matchesTier(stock) {
    const key = tierKey(stock);
    if (key === null) return true;
    return Boolean(state.tiers[key]);
  }

  function anyTierSelected() {
    return state.tiers.low || state.tiers.mid || state.tiers.high;
  }

  function visibleStocks() {
    const active = [];
    if (state.filters.chipRadar) active.push("chipRadar");
    if (state.filters.newStrategy) active.push("newStrategy");
    if (state.filters.oldStrategy) active.push("oldStrategy");
    if (!active.length || !anyTierSelected()) return [];
    return (data.stocks || []).filter((stock) => {
      if (!matchesTier(stock)) return false;
      const checks = [];
      if (state.filters.chipRadar) checks.push(isChipRadar(stock));
      if (state.filters.newStrategy) checks.push(isNewStrategy(stock));
      if (state.filters.oldStrategy) checks.push(isOldStrategy(stock));
      return checks.length > 0 && checks.every(Boolean);
    });
  }

  function stockBySymbol(symbol) {
    return (data.stocks || []).find((stock) => stock.symbol === symbol) || null;
  }

  function currentStock() {
    const stocks = visibleStocks();
    if (!stocks.length) return null;
    if (state.activeSymbol) {
      const match = stocks.find((stock) => stock.symbol === state.activeSymbol);
      if (match) return match;
    }
    return stocks[Math.min(state.stockIndex, stocks.length - 1)] || null;
  }

  function totalBars() {
    const stock = currentStock();
    return (stock && stock.bars) ? stock.bars.length : 0;
  }

  function viewRange(total) {
    if (!total) return {start: 0, end: 0, count: 0};
    const minBars = Math.min(MIN_VISIBLE_BARS, total);
    const count = clamp(state.zoom.count === null ? total : state.zoom.count, minBars, total);
    const start = clamp(state.zoom.start === null ? total - count : state.zoom.start, 0, total - count);
    return {start, end: start + count, count};
  }

  function resetZoom() {
    state.zoom.start = null;
    state.zoom.count = null;
  }

  function anchorRatioFromClientX(clientX) {
    const layout = state.layout;
    if (!layout) return 0.5;
    const rect = canvas.getBoundingClientRect();
    const plotWidth = Math.max(1, layout.width - layout.pad.left - layout.pad.right);
    return clamp((clientX - rect.left - layout.pad.left) / plotWidth, 0, 1);
  }

  function applyZoom(factor, anchorRatio) {
    const total = totalBars();
    if (!total) return;
    const view = viewRange(total);
    const anchorIndex = view.start + anchorRatio * view.count;
    const minBars = Math.min(MIN_VISIBLE_BARS, total);
    const count = clamp(Math.round(view.count / factor), minBars, total);
    state.zoom.count = count;
    state.zoom.start = clamp(Math.round(anchorIndex - anchorRatio * count), 0, total - count);
    state.hoveredBarIndex = null;
    render();
  }

  function setZoomWindow(count, start) {
    const total = totalBars();
    if (!total) return;
    const minBars = Math.min(MIN_VISIBLE_BARS, total);
    const nextCount = clamp(Math.round(count), minBars, total);
    state.zoom.count = nextCount;
    state.zoom.start = clamp(Math.round(start), 0, total - nextCount);
    render();
  }

  function panByBars(deltaBars) {
    const total = totalBars();
    if (!total) return;
    const view = viewRange(total);
    state.zoom.count = view.count;
    state.zoom.start = clamp(Math.round(view.start + deltaBars), 0, total - view.count);
    render();
  }

  function barsPerPixel() {
    const layout = state.layout;
    if (!layout || !layout.step) return 0;
    return 1 / layout.step;
  }

  function updateZoomStatus() {
    const node = $("zoomStatus");
    if (!node) return;
    const total = totalBars();
    if (!total) {
      node.textContent = "";
      return;
    }
    const view = viewRange(total);
    node.textContent = view.count >= total ? `全區間 ${total} 根 K 棒` : `顯示第 ${view.start + 1}~${view.end} 根 / 共 ${total} 根`;
  }

  function init() {
    Object.keys(initial).forEach((key) => { $(key).value = defaults[key] || initial[key]; });
    $("stockSelect").addEventListener("change", () => {
      state.activeSymbol = null;
      state.stockIndex = Number($("stockSelect").value || 0);
      state.hoveredBarIndex = null;
      state.pinnedBarIndex = null;
      resetZoom();
      render();
    });
    [["chipRadarToggle", "chipRadar"], ["newStrategyToggle", "newStrategy"], ["legacyStrategyToggle", "oldStrategy"]].forEach(([id, key]) => {
      $(id).addEventListener("change", (event) => {
        state.filters[key] = event.target.checked;
        state.stockIndex = 0;
        state.activeSymbol = null;
        state.hoveredBarIndex = null;
        state.pinnedBarIndex = null;
        resetZoom();
        syncStockSelect();
        render();
      });
    });
    [["tierLowToggle", "low"], ["tierMidToggle", "mid"], ["tierHighToggle", "high"]].forEach(([id, key]) => {
      const node = $(id);
      if (!node) return;
      node.addEventListener("change", (event) => {
        state.tiers[key] = event.target.checked;
        state.stockIndex = 0;
        state.activeSymbol = null;
        state.hoveredBarIndex = null;
        state.pinnedBarIndex = null;
        resetZoom();
        syncStockSelect();
        render();
      });
    });
    bindZoomControls();
    controls.forEach((id) => $(id).addEventListener("input", render));
    document.querySelectorAll("[data-layer]").forEach((item) => {
      item.addEventListener("change", () => {
        state.layers[item.dataset.layer] = item.checked;
        render();
      });
    });
    canvas.addEventListener("mousemove", (event) => {
      if (drag.active) return;
      if (state.pinnedBarIndex !== null) return;
      const index = pickBarIndexFromEvent(event);
      if (index === state.hoveredBarIndex) return;
      state.hoveredBarIndex = index;
      render();
    });
    canvas.addEventListener("mouseleave", () => {
      if (state.pinnedBarIndex !== null) return;
      state.hoveredBarIndex = null;
      render();
    });
    canvas.addEventListener("click", (event) => {
      if (drag.moved) {
        drag.moved = false;
        return;
      }
      const index = pickBarIndexFromEvent(event);
      if (index === null) {
        state.pinnedBarIndex = null;
      } else if (state.pinnedBarIndex === index) {
        state.pinnedBarIndex = null;
      } else {
        state.pinnedBarIndex = index;
      }
      render();
    });
    window.addEventListener("resize", render);
    syncStockSelect();
    renderFocusWatchlist();
    render();
  }

  function bindZoomControls() {
    const zoomIn = $("zoomInBtn");
    const zoomOut = $("zoomOutBtn");
    const zoomReset = $("zoomResetBtn");
    if (zoomIn) zoomIn.addEventListener("click", () => applyZoom(1.35, 0.5));
    if (zoomOut) zoomOut.addEventListener("click", () => applyZoom(1 / 1.35, 0.5));
    if (zoomReset) zoomReset.addEventListener("click", () => { resetZoom(); render(); });

    canvas.addEventListener("wheel", (event) => {
      if (!totalBars()) return;
      event.preventDefault();
      applyZoom(event.deltaY < 0 ? 1.2 : 1 / 1.2, anchorRatioFromClientX(event.clientX));
    }, {passive: false});

    canvas.addEventListener("dblclick", (event) => {
      event.preventDefault();
      resetZoom();
      render();
    });

    canvas.addEventListener("mousedown", (event) => {
      if (event.button !== 0 || !totalBars()) return;
      const view = viewRange(totalBars());
      drag.active = true;
      drag.moved = false;
      drag.startX = event.clientX;
      drag.startViewStart = view.start;
      canvas.classList.add("is-panning");
    });

    window.addEventListener("mousemove", (event) => {
      if (!drag.active) return;
      const deltaPx = event.clientX - drag.startX;
      if (Math.abs(deltaPx) > 3) drag.moved = true;
      if (!drag.moved) return;
      const view = viewRange(totalBars());
      state.zoom.count = view.count;
      setZoomWindow(view.count, drag.startViewStart - deltaPx * barsPerPixel());
    });

    window.addEventListener("mouseup", () => {
      if (!drag.active) return;
      drag.active = false;
      canvas.classList.remove("is-panning");
    });

    canvas.addEventListener("touchstart", (event) => {
      if (!totalBars()) return;
      const view = viewRange(totalBars());
      if (event.touches.length === 2) {
        pinch.active = true;
        drag.active = false;
        pinch.startDistance = touchDistance(event.touches);
        pinch.startCount = view.count;
        pinch.startStart = view.start;
        pinch.anchorRatio = anchorRatioFromClientX((event.touches[0].clientX + event.touches[1].clientX) / 2);
      } else if (event.touches.length === 1) {
        drag.active = true;
        drag.moved = false;
        drag.startX = event.touches[0].clientX;
        drag.startViewStart = view.start;
      }
    }, {passive: true});

    canvas.addEventListener("touchmove", (event) => {
      if (pinch.active && event.touches.length === 2) {
        event.preventDefault();
        const distance = touchDistance(event.touches);
        if (pinch.startDistance <= 0) return;
        const total = totalBars();
        const minBars = Math.min(MIN_VISIBLE_BARS, total);
        const count = clamp(Math.round(pinch.startCount * (pinch.startDistance / Math.max(distance, 1))), minBars, total);
        const anchorIndex = pinch.startStart + pinch.anchorRatio * pinch.startCount;
        setZoomWindow(count, anchorIndex - pinch.anchorRatio * count);
        return;
      }
      if (drag.active && event.touches.length === 1) {
        const deltaPx = event.touches[0].clientX - drag.startX;
        if (Math.abs(deltaPx) <= 4) return;
        event.preventDefault();
        drag.moved = true;
        const view = viewRange(totalBars());
        setZoomWindow(view.count, drag.startViewStart - deltaPx * barsPerPixel());
      }
    }, {passive: false});

    const endTouch = (event) => {
      if (event.touches.length < 2) pinch.active = false;
      if (event.touches.length === 0) {
        drag.active = false;
        drag.moved = false;
      }
    };
    canvas.addEventListener("touchend", endTouch, {passive: true});
    canvas.addEventListener("touchcancel", endTouch, {passive: true});
  }

  function touchDistance(touches) {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
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
    if (stocks.length) {
      select.value = String(state.stockIndex);
    }
  }

  function renderFocusWatchlist() {
    const node = $("focusWatchlistPanel");
    if (!node) return;
    const items = (data.focusStocks || []).slice(0, 12);
    if (!items.length) {
      node.innerHTML = '<div style="padding:10px 8px; color:#64748b; font-size:12px;">目前沒有綜合關注榜資料。</div>';
      return;
    }
    node.innerHTML = items.map((item) => `
      <button type="button" class="focus-item${state.activeSymbol === item.symbol ? " is-active" : ""}" data-symbol="${escapeHtml(item.symbol || "")}">
        <div class="focus-rank">${escapeHtml(String(item.rank || ""))}</div>
        <div class="focus-body">
          <div class="focus-title">${escapeHtml(item.symbol || "")} ${escapeHtml(item.name || "")} <span>${escapeHtml(item.label || "")}</span></div>
          <div class="focus-note">${escapeHtml(item.reason || "")}。${escapeHtml(item.action || "")}。${item.priceTier ? escapeHtml(item.priceTier) + " / " : ""}Hybrid ${escapeHtml(formatNumber(item.hybridScore, 1))} / 技術 ${escapeHtml(formatNumber(item.technicalScore, 1))}</div>
        </div>
      </button>
    `).join("");
    node.querySelectorAll("[data-symbol]").forEach((button) => {
      button.addEventListener("click", () => {
        state.activeSymbol = button.dataset.symbol || null;
        const stocks = visibleStocks();
        const index = stocks.findIndex((stock) => stock.symbol === state.activeSymbol);
        if (index >= 0) {
          state.stockIndex = index;
          $("stockSelect").value = String(index);
        }
        state.hoveredBarIndex = null;
        state.pinnedBarIndex = null;
        renderFocusWatchlist();
        render();
      });
    });
  }

  function renderChipSnapshot(stock) {
    const node = $("chipSnapshotPanel");
    if (!node) return;
    const chip = stock.chipSnapshot || {};
    const metrics = [
      ["前十大主力強度", formatNumber(chip.top10MainForceBuyStrength, 1)],
      ["前十大主力淨買超", formatNumber(chip.top10MainForceNetBuy, 0)],
      ["外資連買天數", formatNumber(chip.foreignBuyStreakDays, 0)],
      ["主分點連買天數", formatNumber(chip.branchMainForceBuyStreakDays, 0)],
      ["主分點名稱", chip.branchMainForceLeader || "n/a"],
      ["籌碼資料日期", chip.chipDataDate || "n/a"],
      ["籌碼來源狀態", chip.chipDataSourceStatus || "n/a"],
      ["前十大主力券商", chip.top10MainForceBrokers || "n/a"]
    ];
    node.innerHTML = metrics.map(([label, value]) => `<div class="chip-metric"><b>${escapeHtml(label)}</b><span>${escapeHtml(String(value))}</span></div>`).join("");
  }

  function renderStockSummary(stock) {
    const node = $("stockSummaryPanel");
    if (!node) return;
    const range = stock.priceRange || {};
    const cards = [
      ["風險評估", `${stock.riskLevel || "n/a"}｜${stock.riskNote || "n/a"}`],
      ["股價分類", stock.priceTier || "n/a"],
      ["偏多偏空判定", stock.marketBias || "n/a"],
      ["價格區間", `${formatNumber(range.low, 2)} ~ ${formatNumber(range.high, 2)}`],
      ["報告結論", `${stock.decision || "n/a"}｜現價 ${formatNumber(stock.currentClose, 2)} / 預估 ${formatNumber(stock.predictedClose, 2)}`]
    ];
    node.innerHTML = cards.map(([label, value]) => `<div class="stock-summary-card"><b>${escapeHtml(label)}</b><span>${escapeHtml(String(value))}</span></div>`).join("");
  }

  function renderChartInfo(stock, p) {
    const node = $("chartInfoPanel");
    if (!node) return;
    const bars = stock.bars || [];
    if (!bars.length) {
      node.innerHTML = '<div class="chart-info-title">缺少完整 OHLCV / 技術資料</div>';
      return;
    }
    const index = activeBarIndex(stock);
    const bar = bars[index];
    const prev = bars[index - 1] || null;
    const closes = bars.map((item) => item.close);
    const ma5 = sma(closes, p.maShort)[index];
    const ma20 = sma(closes, p.maMid)[index];
    const ma60 = sma(closes, p.maLong)[index];
    const change = prev ? bar.close - prev.close : 0;
    const changePct = prev && prev.close ? (change / prev.close) * 100 : 0;
    const changeClass = change > 0 ? "up" : change < 0 ? "down" : "flat";
    const pinText = state.pinnedBarIndex !== null ? "已鎖定" : "滑鼠移動可切換，點擊可鎖定";
    node.innerHTML = `
      <div class="chart-info-head">
        <div>
          <div class="chart-info-title">${escapeHtml(bar.date || "")}｜${escapeHtml(pinText)}</div>
          <div class="chart-info-price">${escapeHtml(formatNumber(bar.close, 2))}</div>
        </div>
        <div class="chart-info-change ${changeClass}">
          ${escapeHtml(formatSignedNumber(change, 2))} (${escapeHtml(formatSignedNumber(changePct, 2))}%)
        </div>
      </div>
      <div class="chart-ohlc-grid">
        ${infoCell("開", formatNumber(bar.open, 2))}
        ${infoCell("高", formatNumber(bar.high, 2))}
        ${infoCell("低", formatNumber(bar.low, 2))}
        ${infoCell("收", formatNumber(bar.close, 2))}
        ${infoCell("量", formatInteger(bar.volume))}
      </div>
      <div class="chart-ma-row">
        ${maChip("#2563eb", `${p.maShort}MA ${formatNumber(ma5, 2)}`)}
        ${maChip("#ef4444", `${p.maMid}MA ${formatNumber(ma20, 2)}`)}
        ${maChip("#d4a017", `${p.maLong}MA ${formatNumber(ma60, 2)}`)}
      </div>
    `;
  }

  function infoCell(label, value) {
    return `<div class="chart-ohlc-item"><b>${escapeHtml(label)}</b><span>${escapeHtml(String(value))}</span></div>`;
  }

  function maChip(color, text) {
    return `<span class="chart-ma-chip"><span class="chart-ma-dot" style="background:${color};"></span>${escapeHtml(text)}</span>`;
  }

  function activeFilterLabels() {
    const labels = [];
    if (state.filters.oldStrategy) labels.push("品質底池");
    if (state.filters.chipRadar) labels.push("主力動向");
    if (state.filters.newStrategy) labels.push("發動確認");
    const tiers = [];
    if (state.tiers.low) tiers.push("低價位");
    if (state.tiers.mid) tiers.push("中價位");
    if (state.tiers.high) tiers.push("高價位");
    if (tiers.length && tiers.length < 3) labels.push(`價位：${tiers.join("／")}`);
    return labels;
  }

  function renderStrategyContext(stock) {
    const node = $("strategyContext");
    if (!node) return;
    const labels = activeFilterLabels();
    const flags = screeningFlags(stock);
    const hits = [
      (flags.legacyMotherPoolHit ?? flags.legacy) ? "品質底池命中" : null,
      flags.chipRadar ? "主力動向命中" : null,
      flags.newStrategy ? "發動確認命中" : null,
      flags.shortEntry ? "☆短線買點" : null,
      flags.bestEntry ? "★最佳買點" : null
    ].filter(Boolean).join(" / ") || "未命中";
    node.innerHTML = `
      <div class="strategy-list" style="padding-top:12px;">
        <div class="strategy-item"><b>目前篩選模式</b><span>${escapeHtml(labels.join(" + ") || "未勾選策略")}</span></div>
        <div class="strategy-item"><b>該股實際命中</b><span>${escapeHtml(hits)}</span></div>
        <div class="strategy-item"><b>漏斗三層</b><span>品質底池（哪些值得看）→ 主力動向（誰在買）→ 發動確認（何時買，K 值 &lt; 40、MA20 上升、盤整突破）。</span></div>
        <div class="strategy-item"><b>☆/★ 買點定義</b><span>☆短線買點＝收盤剛突破 20MA 且 MACD 剛金叉（第一優先）；★最佳買點＝剛突破 60MA 且 MACD 剛金叉（次優先）；同時命中顯示 ☆★。</span></div>
      </div>
    `;
  }

  function renderStrategyList(stock) {
    const list = $("strategyList");
    if (!list) return;
    const items = (stock.strategySummary || []).filter((item) => strategyVisible(item.strategy)).slice(0, 5);
    if (!items.length) {
      list.innerHTML = '<div class="strategy-item"><b>目前沒有可顯示的策略摘要</b><span>該股可能缺少完整技術資料，或目前圖層皆已關閉。</span></div>';
      return;
    }
    list.innerHTML = items.map((item) => `<div class="strategy-item"><b>${escapeHtml(item.strategy)}｜${escapeHtml(item.status)}</b><span>${escapeHtml(item.agent)}｜${escapeHtml(item.use)}</span></div>`).join("");
  }

  function strategyVisible(strategy) {
    const text = String(strategy || "");
    if (text.includes("均線") || text.includes("支撐") || text.includes("壓力")) return state.layers.ma || state.layers.support;
    if (text.includes("RSI")) return state.layers.rsi;
    if (text.includes("布林")) return state.layers.bollinger;
    if (text.includes("量價")) return state.layers.volume || state.layers.ma20Volume;
    if (text.includes("漲停")) return state.layers.limitUp;
    if (text.includes("MACD")) return state.layers.macd || state.layers.monthlyMacd;
    return true;
  }

  function params() {
    const value = (id) => Number($(id).value);
    return {
      maShort: value("maShort"),
      maMid: value("maMid"),
      maLong: value("maLong"),
      rsiLow: value("rsiLow"),
      rsiHigh: value("rsiHigh"),
      bollingerSigma: value("bollingerSigma"),
      bollingerPeriod: defaults.bollingerPeriod || 20,
      rsiPeriod: defaults.rsiPeriod || 14,
      macdFast: defaults.macdFast || 12,
      macdSlow: defaults.macdSlow || 26,
      macdSignal: defaults.macdSignal || 9
    };
  }

  function render() {
    const stock = currentStock();
    if (!stock) {
      renderFocusWatchlist();
      const message = anyTierSelected() ? "目前沒有符合勾選條件的股票。" : "請至少勾選一種股價分類。";
      drawEmptyState(message);
      const panel = $("chartInfoPanel");
      if (panel) panel.innerHTML = `<div class="chart-info-title">${escapeHtml(message)}</div>`;
      updateZoomStatus();
      return;
    }
    renderFocusWatchlist();
    renderChipSnapshot(stock);
    renderStockSummary(stock);
    renderStrategyContext(stock);
    renderStrategyList(stock);
    if (!stock.bars || stock.bars.length === 0) {
      drawEmptyState(`${stock.symbol} 缺少完整 OHLCV / 技術資料`);
      renderChartInfo(stock, params());
      updateZoomStatus();
      return;
    }
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    chartWidth = rect.width;
    chartHeight = rect.height;
    labelBoxes = [];
    canvas.width = Math.max(720, Math.floor(rect.width * ratio));
    canvas.height = Math.floor(rect.height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw(stock, params(), rect.width, rect.height);
    renderChartInfo(stock, params());
    updateZoomStatus();
  }

  function activeBarIndex(stock) {
    const count = (stock.bars || []).length;
    if (!count) return 0;
    const view = viewRange(count);
    const lo = view.start;
    const hi = Math.max(view.start, view.end - 1);
    if (state.pinnedBarIndex !== null) return clamp(state.pinnedBarIndex, lo, hi);
    if (state.hoveredBarIndex !== null) return clamp(state.hoveredBarIndex, lo, hi);
    return hi;
  }

  function pickBarIndexFromEvent(event) {
    const stock = currentStock();
    if (!stock || !state.layout) return null;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const layout = state.layout;
    if (x < layout.pad.left || x > layout.width - layout.pad.right) return null;
    const view = layout.view || {start: 0, end: stock.bars.length};
    const raw = view.start + Math.floor((x - layout.pad.left) / Math.max(layout.step, 1));
    return clamp(raw, view.start, Math.max(view.start, view.end - 1));
  }

  function drawEmptyState(message) {
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(720, Math.floor(rect.width * ratio));
    canvas.height = Math.floor(rect.height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, rect.width, rect.height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, rect.width, rect.height);
    ctx.fillStyle = "#64748b";
    ctx.font = "14px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(message, rect.width / 2, rect.height / 2);
    ctx.textAlign = "left";
  }

  function draw(stock, p, width, height) {
    const bars = stock.bars || [];
    const closes = bars.map((bar) => bar.close);
    const pad = {left: 56, right: 18, top: 30, bottom: 28};
    const panes = {
      price: {top: pad.top, height: height * 0.52},
      volume: {top: height * 0.56, height: 72},
      macd: {top: height * 0.71, height: 76},
      rsi: {top: height * 0.86, height: 62}
    };
    const view = viewRange(bars.length);
    const chartW = width - pad.left - pad.right;
    const step = chartW / Math.max(1, view.count);
    const x = (i) => pad.left + (i - view.start) * step + step * 0.5;
    state.layout = {pad, panes, width, height, step, view};
    const maValues = [sma(closes, p.maShort), sma(closes, p.maMid), sma(closes, p.maLong)];
    const boll = bollinger(closes, p.bollingerPeriod, p.bollingerSigma);
    // Price axis follows the visible window so zooming actually rescales.
    const priceValues = [];
    for (let i = view.start; i < view.end; i += 1) {
      priceValues.push(bars[i].high, bars[i].low);
      maValues.forEach((series) => { if (Number.isFinite(series[i])) priceValues.push(series[i]); });
      if (Number.isFinite(boll.upper[i])) priceValues.push(boll.upper[i]);
      if (Number.isFinite(boll.lower[i])) priceValues.push(boll.lower[i]);
    }
    const priceMin = Math.min(...priceValues) * 0.995;
    const priceMax = Math.max(...priceValues) * 1.005;
    const yPrice = scale(priceMin, priceMax, panes.price.top + panes.price.height, panes.price.top);
    ctx.clearRect(0, 0, width, height);
    drawPane(panes.price, width, "價格 / K 線");
    for (let i = view.start; i < view.end; i += 1) {
      drawCandle(bars[i], x(i), Math.max(2, step * 0.62), yPrice);
    }
    if (state.layers.bollinger) {
      line(boll.upper, x, yPrice, "#8b5cf6", 1.4);
      line(boll.lower, x, yPrice, "#8b5cf6", 1.4);
    }
    if (state.layers.ma) {
      line(maValues[0], x, yPrice, "#2563eb", 1.6);
      line(maValues[1], x, yPrice, "#ef4444", 1.6);
      line(maValues[2], x, yPrice, "#d4a017", 1.6);
      drawCrossMarkers(closes, p.maShort, p.maMid, x, yPrice);
    }
    if (state.layers.support) drawSupportResistance(stock, yPrice, width);
    if (state.layers.markers) drawMarkers(bars, x, yPrice);
    if (state.layers.limitUp || state.layers.ma20Volume) drawConditionMarkers(bars, closes, x, yPrice);
    drawAxis(priceMin, priceMax, yPrice, panes.price, width);
    if (state.layers.volume) drawVolume(bars, x, step, panes.volume, width);
    if (state.layers.macd) drawMacd(closes, x, panes.macd, width, p);
    if (state.layers.rsi) drawRsi(closes, x, panes.rsi, width, p);
    drawHeader(stock, width);
    drawSelectionOverlay(stock, x, yPrice);
  }

  function drawSelectionOverlay(stock, x, yPrice) {
    const bars = stock.bars || [];
    if (!bars.length) return;
    const index = activeBarIndex(stock);
    const bar = bars[index];
    const layout = state.layout;
    if (!layout) return;
    const xx = x(index);
    ctx.strokeStyle = state.pinnedBarIndex !== null ? "#0f766e" : "#94a3b8";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(xx, layout.panes.price.top);
    ctx.lineTo(xx, layout.height - layout.pad.bottom);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.strokeStyle = "#111827";
    ctx.strokeRect(xx - Math.max(4, layout.step * 0.35), yPrice(Math.max(bar.open, bar.close)) - 2, Math.max(8, layout.step * 0.7), Math.max(6, Math.abs(yPrice(bar.open) - yPrice(bar.close)) + 4));
  }

  function drawHeader(stock, width) {
    ctx.fillStyle = "#111827";
    ctx.font = "700 15px system-ui, sans-serif";
    ctx.fillText(`${stock.symbol} ${stock.name} | ${stock.industry}`, 16, 20);
    ctx.textAlign = "right";
    ctx.fillStyle = stock.bucket === "exclude" ? "#b91c1c" : "#0f766e";
    ctx.fillText(`${stock.decision} | 技術 ${formatNumber(stock.technicalScore, 1)}`, width - 18, 20);
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
      const value = Number(stock[key]);
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
    const view = (state.layout && state.layout.view) || {start: 0, end: values.length};
    const markers = [];
    for (let i = Math.max(1, view.start); i < Math.min(view.end, values.length); i += 1) {
      if (!Number.isFinite(shortMa[i - 1]) || !Number.isFinite(longMa[i - 1]) || !Number.isFinite(shortMa[i]) || !Number.isFinite(longMa[i])) continue;
      const golden = shortMa[i - 1] <= longMa[i - 1] && shortMa[i] > longMa[i];
      const death = shortMa[i - 1] >= longMa[i - 1] && shortMa[i] < longMa[i];
      if (golden || death) {
        markers.push({x: x(i), y: y(values[i]) + (golden ? -14 : 16), text: golden ? "金叉" : "死叉", color: golden ? "#dc2626" : "#16a34a"});
      }
    }
    markers.slice(-1).forEach((item) => label(item.x, item.y, item.text, item.color));
  }

  function drawMarkers(bars, x, y) {
    const signals = [];
    const view = (state.layout && state.layout.view) || {start: 0, end: bars.length};
    const start = Math.max(3, view.start, view.end - 45);
    for (let i = start; i < view.end; i += 1) {
      const prev = bars.slice(i - 3, i);
      if (!prev.length) continue;
      if (bars[i].close > Math.max(...prev.map((bar) => bar.high))) {
        signals.push({index: i, price: bars[i].high, text: "突破", color: "#7c3aed", offset: -18});
      } else if (bars[i].close < Math.min(...prev.map((bar) => bar.low))) {
        signals.push({index: i, price: bars[i].low, text: "轉弱", color: "#0f766e", offset: 18});
      } else if (isLongUpper(bars[i])) {
        signals.push({index: i, price: bars[i].high, text: "上影", color: "#b91c1c", offset: -12});
      } else if (isDoji(bars[i]) && i >= bars.length - 18) {
        signals.push({index: i, price: bars[i].close, text: "十字", color: "#475569", offset: 0});
      }
    }
    signals.slice(-2).forEach((item) => label(x(item.index), y(item.price) + item.offset, item.text, item.color));
  }

  function drawConditionMarkers(bars, closes, x, y) {
    const signals = [];
    const ma20 = sma(closes, 20);
    const view = (state.layout && state.layout.view) || {start: 0, end: bars.length};
    const start = Math.max(1, view.start, view.end - 45);
    for (let i = start; i < view.end; i += 1) {
      const previous = bars[i - 1];
      if (state.layers.limitUp && previous && bars[i].close / previous.close - 1 >= 0.095 && !hasThreeLimitUps(bars, i)) {
        signals.push({index: i, price: bars[i].high, text: "漲停", color: "#dc2626", offset: -28});
      }
      const average20 = ma20[i];
      const ratio = volumeRatioAt(bars, i, 20);
      const nearMa20 = Number.isFinite(average20) && Math.abs(bars[i].close - average20) / average20 <= 0.02;
      if (state.layers.ma20Volume && nearMa20 && bars[i].close > bars[i].open && ratio >= 1.5) {
        signals.push({index: i, price: bars[i].close, text: "MA20量增", color: "#ea580c", offset: -22});
      }
    }
    signals.slice(-2).forEach((item) => label(x(item.index), y(item.price) + item.offset, item.text, item.color));
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
    if (index + 1 < window) return 0;
    const chunk = bars.slice(index + 1 - window, index + 1);
    const average = chunk.reduce((sum, bar) => sum + bar.volume, 0) / chunk.length;
    return average ? bars[index].volume / average : 0;
  }

  function drawVolume(bars, x, step, pane, width) {
    drawPane(pane, width, "成交量");
    const view = (state.layout && state.layout.view) || {start: 0, end: bars.length};
    let maxVol = 1;
    for (let i = view.start; i < view.end; i += 1) maxVol = Math.max(maxVol, bars[i].volume);
    for (let i = view.start; i < view.end; i += 1) {
      const bar = bars[i];
      const h = (bar.volume / maxVol) * (pane.height - 22);
      ctx.fillStyle = bar.close >= bar.open ? "#fecaca" : "#bbf7d0";
      ctx.fillRect(x(i) - step * 0.32, pane.top + pane.height - h, Math.max(1, step * 0.64), h);
    }
  }

  function drawMacd(closes, x, pane, width, p) {
    drawPane(pane, width, "MACD");
    const macd = macdSeries(closes, p.macdFast, p.macdSlow, p.macdSignal);
    const view = (state.layout && state.layout.view) || {start: 0, end: closes.length};
    const values = [];
    for (let i = view.start; i < view.end; i += 1) {
      [macd.hist[i], macd.macd[i], macd.signal[i]].forEach((value) => {
        if (Number.isFinite(value)) values.push(value);
      });
    }
    const min = Math.min(...values, -0.01);
    const max = Math.max(...values, 0.01);
    const y = scale(min, max, pane.top + pane.height - 8, pane.top + 18);
    const zero = y(0);
    ctx.strokeStyle = "#cbd5e1";
    ctx.beginPath();
    ctx.moveTo(56, zero);
    ctx.lineTo(width - 18, zero);
    ctx.stroke();
    for (let i = view.start; i < Math.min(view.end, macd.hist.length); i += 1) {
      const value = macd.hist[i];
      if (!Number.isFinite(value)) continue;
      ctx.fillStyle = value >= 0 ? "#dc2626" : "#16a34a";
      ctx.fillRect(x(i) - 2, Math.min(zero, y(value)), 4, Math.max(1, Math.abs(zero - y(value))));
    }
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
    const box = {x: Math.max(4, Math.min(chartWidth - w - 4, x - w / 2)), y: Math.max(40, y - 12), w, h};
    if (labelBoxes.some((item) => boxesOverlap(item, box))) return;
    labelBoxes.push(box);
    ctx.fillStyle = color;
    ctx.fillRect(box.x, box.y, w, h);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(text, box.x + 5, box.y + 13);
  }

  function boxesOverlap(a, b) {
    return !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
  }

  function line(values, x, y, color, width) {
    const view = (state.layout && state.layout.view) || {start: 0, end: values.length};
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.beginPath();
    let started = false;
    for (let i = Math.max(0, view.start); i < Math.min(view.end, values.length); i += 1) {
      const value = values[i];
      if (!Number.isFinite(value)) continue;
      if (!started) {
        ctx.moveTo(x(i), y(value));
        started = true;
      } else {
        ctx.lineTo(x(i), y(value));
      }
    }
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
    values.forEach((value, index) => {
      out[index] = index === 0 ? value : value * k + out[index - 1] * (1 - k);
    });
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

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function formatNumber(value, digits = 2) {
    if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "n/a";
    return Number(value).toFixed(digits);
  }

  function formatSignedNumber(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "n/a";
    const number = Number(value);
    return `${number >= 0 ? "+" : ""}${number.toFixed(digits)}`;
  }

  function formatInteger(value) {
    if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "n/a";
    return Number(value).toLocaleString("zh-Hant-TW", {maximumFractionDigits: 0});
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
