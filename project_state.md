# project_state — 當前狀態文檔

## 當前階段

正在做:2026-07 新功能開發(模式 C)全部完成(含二次調整)

已完成(2026-07 新功能輪):
- 二次調整(2026-07-19):
  - **優先序對調**:☆短線買點(20MA 剛突破+MACD 剛金叉)改為第一優先,★最佳買點(60MA)為次優先;同時命中顯示「☆★雙重買點」且排第一優先。排序鍵、關注榜 priority、LINE 前綴(☆★)、報告與 JS 面板文案全部同步
  - **股價分類**:新增 `_price_tier`(低價位<30 / 中價位30~80含端點 / 高價位>80),顯示於候選股票分析表新增的「價位」欄、圖表 payload(`priceTier`)與個股摘要卡片
  - **配套移除選股 50 元價格上限**(`universe.py` 的 `MAX_UNIVERSE_PRICE` 刪除,保留 10 元下限與 5 千萬日均成交金額門檻),否則高價位分類永遠為空;`chip_backtest.py` 同步移除上限以維持「回測重放生產規則」的一致性,對應測試 fixture 改用低於 10 元的股票驗證下限。**注意:此變更會實質改變每日候選組成,高價股開始入池**
  - 測試從 152 增至 154,ruff 乾淨
- 買點微調(2026-07-19):★最佳買點的 60MA 條件從「收盤在 60MA 之上」改為「最近 2 個交易日內**剛向上突破** 60MA 且最新收盤仍在其上」(早已站上多日者不再標記);新增 **☆短線買點**(同邏輯但用 20MA),排序優先度僅次於 ★,兩者同時命中只顯示 ★。共用輔助函式 `_fresh_ma_breakout`/`_fresh_macd_golden_cross`,`HybridRow` 新增 `short_entry` 欄位,LINE 摘要 ☆ 前綴、圖表 payload 帶 `shortEntry`。測試從 145 增至 152
- 切片 A「★最佳買點」:`HybridRow` 新增 `best_entry` 欄位(收盤 ≥ 60MA 且 MACD DIF 於最近 2 個交易日內剛上穿訊號線;後續微調見上)。純標籤不篩選:報告排序與綜合關注榜優先顯示(priority 0、標籤「★最佳買點」)、LINE 摘要加 ★ 前綴、圖表 payload 帶 `bestEntry` 旗標。新增 6 個測試
- 切片 B「大盤外資動向」:新模組 `stock_signal_system/data/foreign_flow_trend.py` 彙總既有 TWSE T86 快取資料成大盤外資每日買賣超(張)、連買/連賣天數與偏多/偏空/中性判讀;`hybrid.py` 報告新增「外資動向」區塊(T86 失敗時降級為「外資資料暫缺」不中斷報告)。已用真實 TWSE 資料驗證。新增 5 個離線測試
- 切片 C「漏斗式重命名」:所有使用者可見文案改為 品質底池(選股範圍)→ 主力動向(誰在買)→ 發動確認(何時買)→ ★最佳買點 的漏斗順序;互動篩選介面重排並更新各層說明;內部欄位名(`legacy_hit`/`chip_radar_hit`/`new_strategy_hit`)與 DOM id 完全不變。測試斷言同步更新
- (前一輪)模式 E 舊專案積木化改造 8 個切片全部完成,細節見 git log(commits 579966e6 以前)與 ARCH.md

已完成(前一輪積木化改造,摘要):
- 切片 8:經使用者決定只拆最大的兩個檔案(其餘 4 個檔案略超 300 行但無明確自然邊界,回報比不划算,維持現狀):
  - `quant_research_platform/universe.py`(619→372行facade):拆出 `universe_strategies.py`(204行,策略通過判定與籌碼評分)、`universe_platform_geometry.py`(91行,箱型突破幾何計算)。`tests/test_hybrid_support.py`、`tests/test_universe.py` 直接 import 的私有函式全部維持可從 `quant_research_platform.universe` 匯入(re-export)
  - `stock_signal_system/cli_handlers.py`(497→85行facade):拆出 `cli_handlers_market_data.py`(303行,RSS/TWSE/TPEx/籌碼快照 refresh/verify 指令)、`cli_handlers_quant.py`(152行,量化平台 OHLCV/即時報價/回測指令)、`cli_step_timer.py`(25行,共用的 `_step_timer` context manager)。`tests/test_cli_handlers.py`、`tests/test_cli_quant_commands.py` 直接 import 的私有函式維持可從 `cli_handlers` 匯入
  - 拆分後 `ruff check .` 乾淨、134 個測試全數通過
- 切片 7:加入 `ruff` 作為 lint 質量閘門(`pyproject.toml` 的 `[tool.ruff]`,規則集 `E9,F`,並新增 `dev` optional-dependency)。跑 `python -m ruff check .` 時發現三個跟 report.py 死代碼相同模式的問題,一併修正:
  - `quant_research_platform/daily_stock_bridge.py`:`stock_name`/`stock_industry` 重複定義,刪除永遠不會執行的第一版
  - `stock_signal_system/data/rss_sources.py`:`_classify_industries` 重複定義(連帶其專屬的 `INDUSTRY_RULES` 常數與 `_matches_rule` 輔助函式,約 70 行),刪除死代碼後第二版(`INDUSTRY_RULES_ZH`)才是實際生效的分類規則
  - 另修正 4 處未使用的區域變數/import(`data.py`、`hybrid.py`、`market_regime/regime_classifier.py`、`analysis_workflow.py`、`cli_handlers.py`、`pipeline.py`)
  - `python -m ruff check .` 現在乾淨通過,134 個測試維持全數通過
  - 試跑 mypy 評估雜訊量:除了上述已修的重複定義外,還有 18 個既存型別錯誤分散在 13 個檔案,經使用者決定**暫不**納入本次質量閘門(避免為了型別檢查而觸碰不相關的業務邏輯),記錄在下方已知問題供未來處理
- 切片 6(測試部分):`quant_research_platform/hybrid.py`(1608行,核心策略融合引擎)原本只有 `run_tw_hybrid`/`_apply_sector_diversification`/`_chip_score`/`_load_bars`/`_screening_priority_groups`/`_has_real_broker_snapshot`/`_overall_focus_rows` 有測試。新增 `tests/test_hybrid_scoring.py`(23個測試),補齊以下純函式的覆蓋:`_kronos_score`/`_realtime_score`(評分公式與 clamp)、`_quote_intraday_status`/`_action`/`_risk_note`(決策與風險文字的所有分支)、`_industry_bias`/`_group_rows_by_industry`/`_portfolio_rows`(產業分組與投資組合分桶)、`_volume_ratio`/`_support_resistance`(量價指標)、`_cross_status`/`_ma_position_status`/`_rsi_status`(技術指標狀態判斷)。全數測試通過,總測試數從 111 增至 134
- 切片 5:體檢發現 `stock_signal_system/low_reversal_screener.py`(1215行)完全沒有被 `cli.py`/`pipeline.py`/任何 GitHub Actions workflow 呼叫,也無任何設定檔或文件提及,只留下兩份 2026-05 手動產生的報告輸出。經使用者確認為廢棄功能,已刪除該模組與對應的 `reports/low_reversal_screener_2026-05-08.html`、`reports/low_reversal_screener_2026-05-09.html`,刪除前後 111 個測試皆通過(本無測試依賴此模組)
- 拆分 `stock_signal_system/report.py`(原 1535 行)依職責切成四個檔案:
  - `report.py`(148行,facade):`build_report`/`save_report`/`save_report_html`/`markdown_to_html`(dispatcher)/`public_report_url`,對外 import 路徑完全不變
  - `report_markdown.py`(173行):三種渲染器共用的 markdown 解析原語(表格、行內語法、標題擷取等)
  - `report_hybrid_dashboard.py`(235行):`# Hybrid Quant Daily Stock Report` 深色儀表板渲染
  - `report_hybrid_interactive.py`(246行):`# Hybrid 量化每日選股報告`/`# Hybrid 台股每日分析報告` 互動技術圖表渲染
  - `report_technical_chart_js.py`(770行):互動圖表的前端 JS 樣板,純字串資源、非 Python 邏輯,不受 300 行規則實質影響(規則精神是限制邏輯複雜度,不是限制樣板字串長度)
  - 拆分後 111 個測試全數通過,並手動驗證三種渲染路徑(預設/dashboard/互動式)輸出正常
- 刪除根目錄未進版控的暫存/除錯殘留檔案(`AGENTS.md`、`WORKSPACE_REATTACH_REPORT.md`、`.cache_verify_tpex/`、`.cache_verify_twse/`、`tmp_preview_hybrid/`)
- 刪除已廢棄的 `agents/` 舊架構樁模組與對應測試 `tests/test_legacy_agents.py`(已確認功能完全由 `quant_research_platform/agent_workflow.py` 取代,無其他程式碼引用舊模組)
- 產出並經使用者確認 PRD.md / ARCH.md 初稿
- 發現並移除 `stock_signal_system/report.py` 中重複定義的死代碼函式 `_interactive_chart_section`(第二次定義永遠覆蓋第一次,前一版 ~900 行永遠不會執行),檔案從 2438 行降至 1535 行,全數測試通過後 commit
- 為 `report.py` 補齊測試:新增 `build_report`(含產業訊號/推薦股票/空清單情境)、`save_report`、以及 `hybrid_markdown_to_html`(dark dashboard 版型)的測試,`tests/test_report_html.py` 從 4 個測試擴充到 8 個,全數通過

## 已知問題

- `report_hybrid_dashboard.py`/`report_hybrid_interactive.py` 內的私有輔助函式(`_extract_technical_chart_payload`、`_parse_hybrid_markdown`、`_section_bullets`、`_float_text` 等)僅透過上層整合測試間接覆蓋,尚無獨立單元測試
- `quant_research_platform/hybrid.py`(1608行)測試覆蓋已補強,但**尚未實際拆分成多檔案**,經使用者決定暫不處理;它比 `report.py` 更複雜——`run_tw_hybrid` 本身橫跨資料載入、五代理工作流、通知發送、CSV/報告輸出等多個關注點,拆分前需要先確認要按什麼邊界切
- mypy 型別檢查:目前有 18 個既存錯誤分散在 13 個檔案(如 `recommendation_tracker.py`、`market_regime/sector_rotation.py`、`market_regime/regime_classifier.py`、`data/capital_flow/dealer_behavior.py`、`notify.py`、`data/twse.py`、`data/chip_snapshot.py`、`hybrid.py`、`pipeline.py`、`cli_handlers.py` 等),多為次要型別不精確問題,經使用者決定暫不納入質量閘門,未來若要修正建議逐檔處理並各自跑對應測試
- `stock_signal_system/low_reversal_screener.py`(1215行)無對應測試檔,尚未處理
- 目前質量閘門只有 `pytest`,缺 lint 與型別檢查
- CI 依賴三個外部 fork repo(`Rosana1517/Kronos`、`qlib`、`OpenBB`)的 default branch,未鎖定 commit hash,屬供應鏈風險(非本次改造範圍,僅記錄)
- `line_bot_server.py` 用途待確認(是否為每日流程必要組件,或僅輔助用途)

## 下一步

- 2026-07 新功能三切片已完成;請使用者於下一次每日排程執行後,對照 PRD.md 8.5 節驗收清單實際檢查報告與 LINE 推播內容
- 若未來想繼續降低檔案行數,剩餘候選:`candlestick.py`(399行)、`qlib_adapter.py`(368行)、`chip_snapshot.py`(342行)、`screener_sources.py`(337行)、`cli_handlers_market_data.py`(303行)、`daily_stock_bridge.py`(311行)——皆屬次要,無強烈自然拆分邊界

---

## 切片計劃(全部,風險由低到高排序)

| # | 切片 | 涉及積木 | 涉及檔案 | 狀態 |
|---|---|---|---|---|
| 1 | 地基整理:清雜訊、刪廢棄模組、補三份全局文檔 | 版本控制積木 | `agents/`、根目錄暫存檔、PRD.md/ARCH.md/project_state.md | ✅ 已完成 |
| 2 | 確認文檔內容(使用者審閱 PRD/ARCH) | — | PRD.md、ARCH.md | ⬜ 待使用者確認 |
| 3 | 為 `report.py` 補齊測試(在拆分前先固定行為,避免拆分引入回歸) | 檔案積木 | `stock_signal_system/report.py`、`tests/test_report_html.py` | ✅ 已完成(含意外發現並移除的死代碼) |
| 4 | 拆分 `report.py`:依職責切出報告排版/HTML產生/多格式輸出等獨立檔案 | 檔案積木 | `stock_signal_system/report.py` → 拆出新檔 | ✅ 已完成 |
| 5 | 為 `low_reversal_screener.py` 補測試後視情況拆分 | AI/邏輯積木 | `stock_signal_system/low_reversal_screener.py` | ✅ 已完成(確認廢棄無人呼叫,經使用者同意直接刪除) |
| 6 | 為 `hybrid.py` 補充測試覆蓋率後評估拆分範圍(核心策略引擎,風險最高,需最謹慎) | AI 積木 | `quant_research_platform/hybrid.py` | 🟡 測試已補,實際拆分待確認 |
| 7 | 視需要補上 lint(如 ruff)與型別檢查(如 mypy)質量閘門 | 版本控制積木 | `pyproject.toml`、CI workflow | ✅ ruff 已加入,mypy 經使用者決定暫緩 |
| 8 | 其餘 300~620 行區間檔案視情況拆分 | 各工具箱積木 | `universe.py`、`cli_handlers.py`、`candlestick.py` 等 | ✅ 已拆 universe.py、cli_handlers.py;其餘 4 檔經使用者決定維持現狀 |

---

## 每次開新對話,第一條訊息這樣說:

```
先讀項目根目錄的 PRD.md、ARCH.md、project_state.md,了解當前狀態,然後我們來做「具體任務」
```

## 每個切片完成後,按順序執行:

1. 手動跑一遍,對照 PRD 驗收清單逐條檢查
2. 跑 lint(若已建立)
3. 跑型別檢查(若已建立)
4. 跑 `pytest`
5. 更新本文件(三件事:已完成/已知問題/下一步)
6. git commit,寫清楚這次提交做了什麼
