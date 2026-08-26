# project_state — 當前狀態文檔

## 當前階段

正在做:璞玉方法論整合(模式 C)—— P1/P2/P7/P3/P6/P5(含P4)/P8 全部完成

已完成(璞玉整合輪):
- **報告 UI 第六輪:璞玉選股名單進互動技術分析側欄(2026-08-26)**:比照「綜合關注榜」的互動效果，`hybrid.py` 把 `_pristine_watchlist_section` 拆成 `_compute_pristine_watchlist`(純抓取+篩選，只跑一次 FinMind)+ `_pristine_watchlist_section`(純渲染 markdown 表格)+ `_pristine_watchlist_payload`(轉成 JSON 給圖表)，避免抓兩次資料。`_technical_chart_payload` 新增 `pristineWatchlist` 欄位。`report_hybrid_interactive.py` 側欄在「綜合關注榜」下方新增同樣樣式的「璞玉選股名單」`<section class="focus-card">`；`report_technical_chart_js.py` 新增 `renderPristineWatchlist()`，點擊項目直接切換 K 線圖（沿用先前修好的 `currentStock()` 全量查找邏輯，不受側欄篩選影響）。已用真實資料端到端驗證：面板顯示 7 檔真實通過篩選的股票，點擊後圖表正確切換到該股真實數據（現價/預估都對得上）。ruff/225 測試全過
- **報告 UI 第五輪:兩兩併排改回 2 欄、產業鏈同步訊號獨立一排(2026-08-26)**:第四輪用 `auto-fit(minmax(300px,1fr))` 在寬螢幕擠出 3 欄反而讓卡片內容(尤其 RSS 卡片網格)換行變多、單排更高，使用者回饋「被拉太長反而更擋路」。改用固定的 `.report-grid--two`(2 欄)只裝融資餘額動向/外資期貨未平倉/外資動向/RSS 產業訊號 四塊，產業鏈同步訊號因內容長度不固定移出 grid、自己佔一整排；grid 間距從 14px 收窄到 10px。移除不再使用的 `.report-grid--cards`。用真實快取資料(當天 TWSE/TAIFEX 快取直接命中，未打新網路請求)產生實際 HTML 並用瀏覽器量測座標驗證：4 張卡片正確排成 2x2(每張寬515px)，產業鏈同步訊號正確落在 grid 外、獨佔整排(寬1040px)。ruff/225 測試全過
- **報告 UI 第四輪:五個市場面區塊改併排卡片(2026-08-26)**:融資餘額動向/外資期貨未平倉/外資動向/產業鏈同步訊號/RSS 產業訊號 這五個原本各自全寬堆疊的區塊,改包成 `<article class="report-card">`,外層再包一個 `<div class="report-grid report-grid--cards">`(`report_hybrid_interactive.py` 新增 `.report-grid--cards { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }`),桌面版會自動併排、手機版自動變回單欄,縮短頁面總長度。璞玉指數動向與璞玉選股名單維持全寬(主軸區塊,故意不跟著併排)。用離線合成的 markdown 片段驗證過 `<article>`/`<div>` 巢狀結構正確渲染成三欄卡片(後被第五輪調整取代)。ruff/225 測試全過
- **報告 UI 第三輪迭代(2026-08-26)**:回應使用者五點回饋——(1) 表格版面/字體:候選股票分析原本單一 20 欄表格太密,拆成「核心決策欄」9 欄常駐表格(股票/名稱/產業/價位/Hybrid/停損/停利/組合決策/風險註記,字體放大到 14px)+「漏斗與籌碼細節」12 欄巢狀收合表格(選用,12px);選股優先順序表字體從 12px 提升到 13.5px。(2) **真 bug**:綜合關注榜點擊部分股票不會切換 K 線圖——`report_technical_chart_js.py` 的 `currentStock()` 誤用篩選後的 `visibleStocks()` 查找點擊的 symbol,被目前漏斗/價位篩選排除的關注榜個股點了沒反應;修正為優先用 symbol 查全量清單(`stockBySymbol`),已用真實資料驗證(2388.TW 原本被篩選排除,點擊後正確顯示其真實現價81.10/預估104.36)。(3) 進一步精簡:同上表格拆分。(4) **新增「璞玉選股名單」**:重跑 TIP 官方璞玉篩選規則(EPS/股利)於今日 Hybrid 分數最高的 15 檔候選(非全母池——FinMind 財報端點有速率限制`>=6.5秒/次`,全掃 90 檔候選要 25+ 分鐘不划算),新模組函式 `pristine_health.fetch_fundamentals_for_symbol`/`build_fundamentals_from_finmind_rows`,30 天長快取降低每日重跑成本,顯示位置緊接「璞玉指數動向」之後形成璞玉主軸區塊;已用真實資料驗證(今日15檔中7檔通過,含台積電外的多檔真實ROE/負債比/PE判讀)。(5) **籌碼快照 n/a 調查**:非「沒放進去」,是真的抓不到——追查發現 `_enrich_report_chip_snapshots`(`hybrid.py`)與 `load_histock_broker_summaries`(`chip_snapshot.py`)都有靜默吞掉例外的 `except: return`/`except: snapshot=None`,完全沒有任何 log。補上 warning log 後重新驗證,發現 HiStock 分點頁面(histock.tw/stock/branch.aspx)本身已改版——分點交易表格現在用前端 JS 動態渲染(`var jsonDatas = eval();`為空),不再是靜態 HTML,連台積電這種天天有分點資料的股票都抓不到，此為**外部網站改版導致既有 scraper 失效的既有 bug，非本次新增**，已記錄但尚未修——修正 HiStock 爬蟲需重新逆向其新的資料來源，是獨立於本輪的後續工作。ruff/225 測試全過,已用真實資料端到端驗證(含背景執行完整 pipeline,全程用 `run_tw_hybrid(notify=False)` 直接呼叫，未觸發任何 LINE 推播)
- **並行開發提醒**:同一時間有另一個 agent(使用者稱 Codex)在同一份工作目錄新增了 `stock_signal_system/tw_market_review.py`(獨立的「美股排版」台股盤後review渲染器)並修改了 `pipeline.py`/`test_pipeline.py` 把 `_save_tw_hybrid_audit` 的 `html_path` 改指向這個新頁面而非本輪一直在改的 `report_hybrid_interactive.py` 渲染結果。**本次只 commit 了自己動到的 7 個檔案，沒有碰、沒有 commit、也沒有刪除 Codex 那些改動**，因為兩邊可能是互相衝突的報告呈現方向，需要使用者決定要保留哪一條路線
- **報告 UI 迭代:璞玉觀點進互動圖表 + 精簡控制項(2026-08-26)**:回應使用者三點回饋——(1)「璞玉好像都沒有進到互動技術分析中」:新增 `_compute_pristine_relative_strength`/`_pristine_banner_text`(`hybrid.py`),璞玉指數相對強弱判讀只算一次,同時餵給「璞玉指數動向」區塊與互動圖表的 `pristineNote` payload 欄位;`report_technical_chart_js.py` 的 `init()` 讀取後寫入新的 `#techPristineNote` 橫幅,直接顯示在「互動技術分析」標題正下方。(2)「資訊似乎太多，不易判讀」:把「均線參數」「RSI/布林」數字輸入、訊號定義長說明文字、4 個非預設勾選的圖表標記(K線型態/漲停/月MACD/MA20量價)分別收進三個預設收合的 `<details>`,只留最核心的股票選單、三層漏斗、股價分類、6 個常用圖層勾選項常駐可見。(3)「調整完之前不要發送 LINE」:改用直接呼叫 `run_tw_hybrid(..., notify=False)` + `save_report_html` 產生預覽,不經過 `pipeline.py` 的 `_run_quant_hybrid_pipeline`(那裡才會真的呼叫 `send_notification`),已用真實資料驗證璞玉橫幅正確顯示、三個新 `<details>` 預設皆收合、原有預設勾選狀態不變、全程未觸發任何 LINE 推播。ruff/220 測試全過
- **報告 UI 重新設計 + 以璞玉為主軸重排版面(2026-08-26)**:視覺上,`report_markdown.py`(共用 CSS + Google Fonts)、`report_hybrid_interactive.py`(互動技術分析區塊樣式)、`report.py` 全面翻新配色與字體(Noto Serif TC 標題 + IBM Plex Mono 數字/代號,暖紙白+黃銅色主題),所有既有測試斷言的 id/class/預設勾選狀態逐一核對保留,ruff/pytest 全過,並用真實資料端到端截圖驗證 K 線圖、縮放、篩選功能不受影響。版面上,`hybrid.py` 的 `_save_report` 依「大盤溫度→璞玉指數動向(主軸,緊接濾網之後)→資金/籌碼面(融資餘額/外資期貨/外資動向)→產業面(產業鏈同步訊號/RSS)→選股與互動K線圖(核心功能)→候選股票分析→報告結論→333翻倍計畫部位管理→附錄(資料待補/投組模擬/驗證指標/權重診斷/新聞)」重新排序,已用 mock 過網路的離線 fixture 驗證 14 個 `## ` 標題與 2 個 HTML `<h2>`(選股優先順序表、互動技術分析)順序正確。**注意**:`reports/tw_hybrid_2026-08-26.md` 是重排版面「之前」跑出來的舊檔案,尚未反映新順序,需要下一次實際排程或手動重跑 pipeline 才會產生新順序的正式報告
- **切片 P8「產業鏈上中下游群體共識判讀」核心完成、流程驗證中**:新模組 `stock_signal_system/data/industry_chain.py` 從 `ic.tpex.org.tw` 取得上/中/下游成分股，使用 30 天快取並依 (子分類代碼, 股票代號) 去重；候選池訊號會正規化 `2330`/`2330.TW` 後，以同一產業鏈同一層 ≥2 檔判定共識。`hybrid.py` 已新增「產業鏈同步訊號」區塊，不影響既有排序。首次快取建立仍會請求各產業頁面，並非零額外網路請求；資料來源失敗或解析異常須在 audit JSON 標示資料缺口。
- **P8 資料源查證(2026-08-26)**:官方 `ic.tpex.org.tw` 產業價值鏈頁面已確認可爬；目前 parser、去重、代碼正規化與快取流程已實作。仍需以當日完整報告及 audit JSON 做端到端驗證，且網站 HTML 格式變更時需由 parser fixture／資料缺口檢查攔截。
- **切片 P5(含P4)「璞玉健康指標」完成**:新模組 `stock_signal_system/data/pristine_health.py`,`finmind.py` 擴充 3 個新方法(財報/資產負債表/股利)。核心是 `evaluate_pristine_screen` 純函式重跑 TIP 官方揭露的硬篩選規則(4季+3年EPS皆正、3年皆配息),取代原本要拿 331 檔完整清單的需求(P4 併入於此)。**刻意不做完整加權璞玉評分**——公式裡「產業地位/AI含金量」20% 與「市場非擁擠度百分位」10% 需要主觀產業標記與全市場排名,本專案沒這些資料,寧可誠實只提供可算出的子項(EPS/股利篩選、ROE%、負債比%、PE估值判讀)也不編造假精確總分。**刻意不接線進每日報告**——FinMind 逐股查詢有速率限制,對每日候選掃描不划算,列為未來可選的批次工具(尚無 CLI 指令)。18 個新測試,206 測試全過、ruff 乾淨,已用真實資料端到端驗證(台積電 2330 通過篩選,ROE 34.5%、負債比 30.9%,與已知財務常識相符)
- **切片 P6「外資期貨未平倉 + 官股分點買超」完成**:
  - 外資期貨(大盤層級):新模組 `stock_signal_system/data/foreign_futures_position.py`,接期交所 OpenAPI(只回最新一日,無歷史參數)。**刻意不產生多空判讀**,只顯示口數 + 固定提醒文字(方法論原文明確警告高檔空單常是搭配槓桿ETF的無風險套利,不是崩盤前兆),避免落入原文警告的誤判陷阱。`hybrid.py` 新增「外資期貨未平倉」報告區塊
  - 官股分點(個股層級):**零新增網路請求**——重用已在生產環境接線的 `broker_source.py`(HiStock 分點資料),新增 `stock_signal_system/data/official_broker.py` 靜態官股銀行關鍵字表,在 `chip_snapshot.py` 的 `_summarize_broker_snapshots` 內從既有的 top10 買超分點中拆出官股淨買超金額(`BrokerChipSummary.official_broker_net_buy`),經 CSV 欄位 `official_broker_net_buy` 傳遞到 `HybridRow`,顯示於候選股票分析表新增的「官股買超」欄與圖表籌碼快照面板
  - 尚未做:官股買超的「大型權值股」門檻過濾(方法論強調官股護盤標的通常是台積電/聯發科等權值股,本次先如實呈現數字未加過濾),列未來可選項目
  - 13 個新測試(官股關鍵字比對、分點彙總計算、期貨資料解析與三種判讀情境),188 測試全過、ruff 乾淨,已用真實資料端到端驗證(實測外資淨空單 85,380 口,恰好落在方法論原文舉例的 8~9 萬口範圍,提醒文字正確觸發)
- **切片 P3「融資餘額動向」完成**:新模組 `stock_signal_system/data/margin_balance_trend.py`(`load_recent_margin_balance_days` 逐日回溯抓 TWSE MI_MARGN 融資金額,自動跳過假日;`summarize_margin_balance_trend` 純函式判讀連續增減天數,連續≥3天且累計≥300億減少→「融資急縮(籌碼清洗)」、單日≥50億增加→「融資急增(追價風險)」)。`hybrid.py` 新增「融資餘額動向」報告區塊。**範疇界定**:這是方法論原文的大盤市場層級指標,刻意不接線既有的個股層級孤島模組 `capital_flow/margin_change.py`(需要逐股 FinMind 融資資料,對每日候選掃描不划算,列為未來可選項目),PRD.md 已記錄此決定與理由。6 個新測試,175 測試全過、ruff 乾淨,已用真實資料端到端驗證(實測融資餘額 5469.4 億、正確跳過週末)
- **資料源查證(2026-08-26)**:逐項查證 P3~P7 五項資料需求,四項找到真實免費 API、一項確認官方不公開改用替代方案:
  - P7 璞玉指數:`backend.taiwanindex.com.tw/api/indexes/IX0231/records`(從 TIP 官網前端 JS 反解出的非官方文件端點),已實測成功
  - P3 融資餘額(大盤):`www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json`,已實測成功
  - P6 外資期貨未平倉:期交所官方 OpenAPI `MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate`
  - P5 EPS/ROE/股利:FinMind `TaiwanStockFinancialStatements`(已實測含 EPS,免 token 基本額度可用)、`TaiwanStockBalanceSheet`、`TaiwanStockDividend`
  - P4 完整331檔成分股清單:確認官方不對外公開(下載 TIP 指數概覽 PDF 用 pdfplumber 解析,只揭露權重前十大),改為**併入 P5**——用 FinMind 財報資料重跑官方公開的選股邏輯,不強求取得原始清單
  - 詳見 PRD.md 8.6 節「資料源查證結果」表格
- **切片 P7「璞玉指數動向」完成**:新模組 `stock_signal_system/data/pristine_index.py`(`fetch_pristine_index_history` 抓每日指數點位、`evaluate_relative_strength` 純函式比較近5個交易日璞玉 vs TAIEX 漲跌幅並判讀「璞玉抗跌(資金避風港)/璞玉走弱/同步」)。`hybrid.py` 報告新增「璞玉指數動向」區塊(重用 `market_regime_gate._fetch_taiex_closes` 取 TAIEX,抓取失敗降級為「資料暫缺」不中斷報告)。7 個新測試(純函式判讀四情境 + 日期解析),169 測試全過、ruff 乾淨,已用真實資料端到端驗證(實測顯示璞玉+0.94% vs TAIEX+2.49%,判讀「璞玉走弱」)
- **切片 P2「333 部位管理原則」完成**:報告新增靜態文字區塊(`_position_management_playbook_section`),說明 30% 分趟出場+拉回再進場的通用資金管理觀念與 1.3³≈2.2 倍複利算法。純教育性質、零資料源、內容不含任何股票代號或個人化指令,明確聲明「不追蹤個人部位、不下單、不提供個人化投資建議」。插入位置在報告「推薦追蹤(勝率閉環)」之後。新增 2 個測試(文案含免責聲明字句 + 內容跨呼叫穩定不變),162 測試全過、ruff 乾淨,已用 UTF-8 檔案輸出人工核對文案(避免終端機 cp950 編碼誤判)
- **切片 P1「◆超跌抄底」完成**:`HybridRow` 新增 `dip_reversal` 欄位,判定=跌破 60MA + 收盤創近 20 日新低 + KD 低檔背離(K<40 且 K 未同步破底);純用既有 OHLCV,新增 `_stochastic_k_series`/`_is_dip_reversal`。與 ★/☆ 完全獨立、可同時標記;綜合關注榜 priority=2(☆0/★1 之後、三者全中之前)、LINE 前綴 ◆、圖表 payload 帶 `dipReversal`、報告與 JS/HTML 文案同步。新增 7 個測試(3 正 3 反 + 顯示/排序),160 測試全過、ruff 乾淨、端到端渲染驗證通過
- 完成六階段方法論 vs 現架構的比對分析(見下方「璞玉整合切片計劃」),確立三項設計決策:分切片逐步做、★/☆ 剛突破與 ◆ 超跌抄底分開標記、333 做成通用規則說明
- 比對重點發現:`data/capital_flow/`(含 `margin_change.py` 融資分析)是**已寫好但沒接線的孤島模組**(僅自己的測試在用),P3 可直接接不用重寫

已完成(2026-07 新功能輪):
- 三次調整(2026-07-20):
  - **股價分類篩選控制項**:上一輪只做了「顯示」沒做篩選,本次在互動報告左側補上「股價分類」三個勾選框(預設全開),與漏斗三層以 AND 合併過濾下拉選單與圖表;三個都不勾時顯示「請至少勾選一種股價分類」。綜合關注榜維持完整排名不受價位篩選影響,但每列補上價位標示
  - **K 線圖縮放/平移**:桌機滾輪(以游標為錨點)、拖曳平移、雙擊還原、+/-/重設按鈕;手機雙指 pinch 縮放、單指水平拖曳平移(canvas 用 `touch-action: pan-y` 保留頁面垂直捲動)。縮放採「可見索引範圍」實作(`state.zoom` + `viewRange()`),Y 軸價格區間、成交量/MACD/RSI 副圖與各種標記都依可見範圍重算,最少可縮至 10 根 K 棒
  - 驗證方式:`node --check` 檢查產出 JS 語法、模擬 DOM 端到端跑真實圖表 JS(確認錨點縮放、重設還原、繪圖座標不越界、價位篩選三種狀態);新增 1 個 HTML 渲染測試,共 155 個測試通過
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

- 璞玉方法論整合輪(P1/P2/P7/P3/P6/P5含P4/P8)**全部完成**。P5 若要接進實際使用(CLI 指令或排程)需另外決定頻率。本輪 commit 尚未推送,待使用者確認後推送
- 使用者要求「做完一起 push」——本輪 P7/P3/P6/P5 五個 commit 尚未推送,待全部確認後一次推送
- 前一輪(K 線縮放/價位篩選)仍待使用者於每日排程後**在手機上實測**雙指縮放與單指平移

---

## 璞玉方法論整合切片計劃(2026-07-21 起,依 value/effort + 風險排序)

| # | 切片 | 資料需求 | 涉及檔案 | 狀態 |
|---|---|---|---|---|
| P1 | ◆超跌抄底(跌破季線+創新低+KD低檔背離),與 ★/☆ 分開標記 | 無(既有 OHLCV) | `hybrid.py`、`daily_stock_bridge.py`、`report_technical_chart_js.py`、`report_hybrid_interactive.py`、`tests/test_hybrid_scoring.py` | ✅ 已完成 |
| P2 | 333 通用規則說明區塊(衛教式,不做個人化下單) | 無 | `hybrid.py` 報告 | ✅ 已完成 |
| P7 | 璞玉指數 IX0231 收盤追蹤 + 大盤相對強弱 | ✅ TIP 官網逆解 API(已驗證) | `stock_signal_system/data/pristine_index.py`(新)、`hybrid.py` | ✅ 已完成 |
| P3 | 融資餘額動向(大盤市場層級,不含個股 `capital_flow/margin_change.py` 接線——列未來可選) | ✅ TWSE MI_MARGN API(已驗證) | `data/margin_balance_trend.py`(新)、`hybrid.py` | ✅ 已完成 |
| P6 | 大盤情緒:外資期貨空單 + 官股分點買超 | ✅ TAIFEX OpenAPI(期貨);官股分點=重用既有 broker_source.py,零新請求 | `data/foreign_futures_position.py`(新)、`data/official_broker.py`(新)、`chip_snapshot.py`、`hybrid.py` | ✅ 已完成 |
| P5(含P4) | 璞玉健康評分(EPS/ROE/股利 3 年連續)+ 自行重跑選股邏輯當母池(P4 完整清單官方不公開,併入此切片) | ✅ FinMind 財報(已驗證含EPS/ROE/股利) | `data/pristine_health.py`(新)、`data/finmind.py` | ✅ 已完成(核心邏輯,未接每日報告) |
| P8 | 產業鏈上中下游群體共識判讀 | ✅ `ic.tpex.org.tw` 產業價值鏈資訊平台(已驗證可爬) | `data/industry_chain.py`(新)、`hybrid.py` | ✅ 已完成 |

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
