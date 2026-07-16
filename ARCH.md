# ARCH — 架構決策文檔

> 這份文件由「模式 E:舊專案改造」的體檢結果整理而成,反映現狀(as-is),並標記待改造目標(to-be)。

## 1. 積木清單(本專案現況)

### 入口層
- [x] 展示積木:靜態 `index.html`(GitHub Pages),無框架、無建置流程
- [x] 排程積木:GitHub Actions cron(`.github/workflows/daily_stock_analysis.yml` 等 4 支 workflow)

### 守門+調度層
- [ ] 身份積木:不需要(自用工具,無多使用者登入)
- [x] 邏輯積木:`stock_signal_system/pipeline.py` + `pipeline_helpers.py`(每日流程調度)、`cli.py` + `cli_handlers.py`(CLI 命令調度)、`config.py` + `validation.py`(設定驗證)、`quant_research_platform/workflow.py` + `analysis_workflow.py`(量化流程)、`market_regime_gate.py`(大盤狀態守門)

### 工具箱層
- [x] 連線積木:TWSE/TPEX 官方 API、FinMind、yfinance、twstock、`cloudflare-workers/twse-realtime-proxy`(即時報價代理,繞過 CORS)
- [x] 爬蟲積木:`stock_signal_system/data/`(twse.py、tpex.py、rss_sources.py、broker_source.py、chip_snapshot.py、regulatory_flags.py、screener_sources.py)
- [x] AI 積木:`quant_research_platform/hybrid.py`(策略融合)、`qlib_adapter.py`(對接 fork 版 pyqlib)、`market_regime/` 子模組群、Kronos 預測(外部 fork repo)
- [x] 通知積木:`stock_signal_system/notify.py`(LINE push/broadcast)、`line_bot_server.py`(webhook 接收端)
- [x] 記憶積木:`data/`(CSV 資料湖,已 .gitignore)、`reports/`(部分報告與發送記錄有進版控供 Pages 發布)、`recommendation_tracker.py`
- [x] 檔案積木:`report.py`(報告產生)、`report_retention.py`(保留策略)、`pages_publish.py`(發布到 Pages)

### 地基層(必選)
- [x] 版本控制積木:Git + GitHub,質量閘門為 pytest(`pyproject.toml` 定義);目前**無** lint/型別檢查閘門(見第 11 節待補項)
- [x] 部署積木:GitHub Pages(靜態託管),GitHub Actions 作為唯一「執行環境」(無常駐伺服器)

## 2. 形態與邊界

- **形態**:排程驅動的批次腳本(CLI + GitHub Actions),非常駐 Web 服務;`line_bot_server.py` 是唯一的常駐 server 角色,用途待確認(推測為接收 LINE webhook 事件,非核心每日流程必要)
- **運行位置**:雲端(GitHub Actions 執行),本機僅供開發/除錯(`scripts/run_daily.ps1`)
- **定位**:個人自用的完整生產系統,非 demo

## 3. 邊界問題答案

- **用戶範圍**:使用者本人自用,無併發使用者問題
- **數據歸屬**:股價/籌碼/新聞為公開資料,無個人隱私資料;推薦紀錄與追蹤結果存於 repo 內 CSV,歸使用者自己所有
- **認證和權限**:無登入系統;唯一的憑證是 LINE Channel Access Token(存 GitHub Secrets,經環境變數注入)
- **支付**:無
- **隱私合規**:不涉及歐盟使用者資料,無 GDPR 疑慮
- **性能上限**:排程批次執行,可接受單次跑幾分鐘;無即時性 SLA(realtime proxy 僅輔助非硬性要求)
- **成本上限**:GitHub Actions 免費額度 + Cloudflare Workers 免費層;第三方資料源(FinMind/yfinance)多為免費或有速率限制,超額時需 fallback 或降級
- **安全底線**:無使用者敏感資料;金鑰(LINE token、FinMind token 等)一律走 `.env`/GitHub Secrets,已於體檢確認無硬編碼外洩
- **可用性**:可接受單日排程失敗(watchdog 二次補跑機制已覆蓋此風險),無需 7x24 監控
- **第三方依賴**:TWSE/TPEX 官方 API、FinMind、yfinance、twstock、RSS 來源、LINE Messaging API、外部 fork(`Rosana1517/Kronos`、`qlib`、`OpenBB`)——外部 fork 若失效或 API 改版,quant_research_platform 的進階分析會受影響,但 stock_signal_system 主流程設計上不強依賴它們(dependencies 為空,quant 為 optional-dependencies)
- **上線平台**:Web(GitHub Pages 靜態展示)+ 排程後端(GitHub Actions),無 App
- **維護方式**:使用者本人維護,無 SLA 承諾

## 4. 技術棧(鎖定,不因臨時建議就換)

| 層 | 選型 | 理由 |
|---|---|---|
| 語言 | Python ≥3.9 | 現有全部核心邏輯與資料處理已用 Python 完成 |
| 排程/CI | GitHub Actions | 免費、與 GitHub Pages 部署天然整合 |
| 資料來源 | TWSE/TPEX 官方 API、FinMind、yfinance、twstock | 台股資料的標準免費/低成本來源組合 |
| 量化擴充 | pyqlib(fork)、OpenBB(fork)、Kronos(fork) | 現有 hybrid 策略已依賴這些 fork,更換需重新驗證全部評分邏輯,暫不更動 |
| 通知 | LINE Messaging API | 現有 notify.py 已封裝完成 |
| 前端展示 | 純 HTML(無框架) | 需求僅是連結列表,無需引入框架 |
| 部署 | GitHub Pages(靜態)+ Cloudflare Workers(即時報價代理) | 免費、現有 worker.js 已運作 |

## 5. 目錄結構和分層邏輯(現況)

```
_github_daily_stock_analysis/
├── PRD.md / ARCH.md / project_state.md   ← 本次新增的全局文檔
├── .env.example                          ← 變數名清單,無真實值
├── .gitignore                            ← 含 .env、data/、py-yfinance 快取
├── index.html                            ← GitHub Pages 展示層
├── pyproject.toml                        ← 套件定義、CLI entry points、pytest 設定
├── .github/workflows/                    ← 4 支排程/CI/部署入口
├── stock_signal_system/                  ← 主系統套件(核心業務邏輯)
│   ├── cli.py / cli_handlers.py          ← 調度層:命令入口
│   ├── pipeline.py / pipeline_helpers.py ← 調度層:每日流程主邏輯
│   ├── config.py / validation.py         ← 調度層:設定驗證
│   ├── data/                             ← 工具箱:爬蟲/連線(twse, tpex, finmind, rss...)
│   ├── strategies/                       ← 工具箱:AI/邏輯運算(candlestick, rule_score, market_structure)
│   ├── notify.py / line_bot_server.py    ← 工具箱:通知
│   ├── report.py(2438行) / report_retention.py / pages_publish.py ← 工具箱:檔案/報告產出
│   └── recommendation_tracker.py         ← 工具箱:記憶(追蹤紀錄)
├── quant_research_platform/              ← 量化研究擴充套件(獨立於主流程,optional）
│   ├── hybrid.py(1608行)                ← 核心策略融合引擎
│   ├── universe.py / backtest.py / market_regime/ / qlib_adapter.py
│   └── agent_workflow.py                 ← 現行 agent 工作流(取代已刪除的 agents/)
├── cloudflare-workers/twse-realtime-proxy/ ← 獨立 JS Worker,即時報價代理
├── configs/                               ← 設定範例(*.example.json)
├── data/                                  ← 執行期資料快取(不進版控)
├── docs/                                  ← 現有文件層(策略框架、資料源、ADR 等)
├── scripts/                                ← 本機手動執行腳本(PowerShell)
├── reports/                                ← 每日報告產出(部分進版控供 Pages)
└── tests/                                  ← pytest 測試(對應兩大套件)
```

## 6. 核心模組劃分

| 模組 | 職責 | 邊界 |
|---|---|---|
| `stock_signal_system` | 每日主流程:資料→策略評分→報告→通知 | 是唯一每日排程實際執行的套件,`quant_research_platform` 透過 `daily_stock_bridge.py` 銜接進來,不直接互相 import 內部細節 |
| `quant_research_platform` | 獨立的量化研究/回測引擎,提供更進階的 hybrid 策略、選股池、市場狀態判斷 | 可獨立於每日流程被 CLI(`quant-research`)呼叫做研究用途,對 stock_signal_system 是「可選依賴」 |
| `cloudflare-workers` | 即時報價代理,繞過前端直接呼叫 TWSE 的 CORS/延遲限制 | 獨立部署單元,與 Python 主體無程式碼耦合,僅透過 HTTP 呼叫 |
| `.github/workflows` | 排程觸發與部署骨架 | 是系統唯一的「常駐執行」載體,本機 `scripts/*.ps1` 僅供除錯用途,不應成為生產依賴 |

## 7. 數據模型設計(現況,CSV-based,無資料庫)

- **股票基本資料**:`symbol, name, market(上市/上櫃), industry`
- **價格資料(三層)**:`symbol, datetime, open, high, low, close, volume`(日線/1H/5M 各自獨立 CSV)
- **籌碼快照**:法人買賣超、主力進出等欄位(見 `chip_snapshot.py`)
- **新聞資料**:RSS 來源 + 分類標籤
- **推薦紀錄**(`reports/recommendation_log.csv` 等):candidate、評分細項、進場價、停損/停利價、追蹤狀態

## 8. 服務端 vs 客戶端邊界

- 全部運算(策略評分、資料抓取、LINE 推播)都在 GitHub Actions(服務端)執行
- `index.html` 純展示,不含任何邏輯或金鑰
- 唯一對外暴露的是 Cloudflare Worker 代理端點,僅轉發公開行情查詢,不經手金鑰或使用者資料

## 9. 狀態管理方案

- 無前端狀態管理需求(靜態展示頁)
- 「狀態」主要是:`reports/` 內的每日產出檔案 + `recommendation_tracker` 的持倉/追蹤狀態 CSV + 當日 LINE marker 檔(避免重複發送)
- 跨執行的狀態透過 commit 進 repo 的方式持久化(無外部資料庫)

## 10. API 設計(對外部依賴,而非自建 API)

| 端點/介面 | 方法 | 用途 |
|---|---|---|
| TWSE/TPEX 官方 API | HTTP GET | 官方日線/籌碼資料 |
| FinMind API | HTTP GET(需 token) | 補充財務/籌碼資料 |
| yfinance / twstock | Python 套件呼叫 | 備援價格資料源 |
| Cloudflare Worker 代理 | HTTP GET | 即時報價(繞過 CORS) |
| LINE Messaging API | HTTP POST | 推播通知 |

## 11. 檔案上限規則與待改造項(健檢結果)

- **規則**:單一檔案不超過 300 行,快到上限就拆出獨立檔案
- **已完成**:`stock_signal_system/report.py`(原 2438行)先移除重複定義的死代碼(~900行),補齊測試後拆分為 `report.py`(facade,148行)+ `report_markdown.py`(173行,共用 markdown 解析)+ `report_hybrid_dashboard.py`(235行)+ `report_hybrid_interactive.py`(246行)+ `report_technical_chart_js.py`(770行,純 JS 樣板字串,不受 300 行規則實質約束)
- **已刪除**:`stock_signal_system/low_reversal_screener.py`(1215行)體檢時發現完全未被 `cli.py`/`pipeline.py`/任何 workflow 呼叫,經使用者確認為廢棄功能後直接刪除,連同其對應的兩份手動報告輸出
- **仍待處理**(依風險排序,已列入 project_state.md 切片計劃):
  1. `quant_research_platform/hybrid.py`(1608行,核心策略融合)——優先度最高,是目前檔案清單中風險最高的項目
  2. 其餘 300~620 行區間檔案(`universe.py`, `cli_handlers.py`, `candlestick.py`, `qlib_adapter.py`, `chip_snapshot.py`, `screener_sources.py`, `daily_stock_bridge.py`, `rss_sources.py`)——次要,視情況拆
- **質量閘門**:`pytest` + `ruff`(`E9,F` 規則集,`python -m ruff check .`)。mypy 型別檢查經評估後暫不納入——現有程式碼有 18 個既存型別錯誤分散在 13 個檔案,經使用者決定先不處理,避免為了補型別檢查而觸碰不相關的業務邏輯(見 project_state.md 已知問題)
- **供應鏈風險**:CI 會 clone 三個外部 fork repo 的 default branch(非鎖定 commit hash),長期建議改為鎖定版本,但不影響 stock_signal_system 主流程(quant 為 optional）
