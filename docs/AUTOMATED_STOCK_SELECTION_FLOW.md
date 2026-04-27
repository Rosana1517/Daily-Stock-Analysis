# 自動選股通知流程與 Skills 對應

本系統依照使用者指定流程執行：台股上市/上櫃、只做多、波段 3-20 天、每日最多關注 5 檔、盤中可通知、完整中文 LINE 報告。

| 步驟 | 流程任務 | 對應 skills | My project 模組 | 輸出 |
|---|---|---|---|---|
| 1 | RSS、新聞、政策、輿情蒐集 | zai-cli、web-access | rss_sources.py | 候選新聞與輿情資料 |
| 2 | 新聞清洗與排除雜訊 | finance-sentiment | rss_sources.py | 去除不相關、重複、誤分類新聞 |
| 3 | 產業訊號分類 | finance-sentiment、finance-investment-researcher | industry.py | 產業訊號與催化因素 |
| 4 | 產業利基分析 | finance-investment-researcher | industry.py | 產業利基、需求與風險摘要 |
| 5 | 台股上市/上櫃股票池建立 | My project | twse.py、finmind.py、yfinance_source.py | 台股普通股股票池 |
| 6 | 日線 OHLCV / 財務資料擷取 | yfinance-data、funda-data | twse.py、finmind.py、yfinance_source.py | 日線、成交量與財務欄位 |
| 7 | 1H / 5M 資料匯入 | My project | csv_sources.py | 盤中結構與觸發資料 |
| 8 | 基本面分析 | stock-analysis、finance-financial-analyst、funda-data | rule_score.py | 成長、獲利、估值與財務品質 |
| 9 | 個股投資論點分析 | stock-analysis、finance-investment-researcher | rule_score.py | 個股受惠邏輯與反方風險 |
| 10 | 流動性檢查 | stock-liquidity | rule_score.py | 成交量與可交易性 |
| 11 | 多因子訊號評分 | stock-checker-analysis | rule_score.py | 產業、基本面、動能、技術與風險分數 |
| 12 | 產業與個股關聯檢查 | stock-analysis、stock-correlation | rule_score.py | 題材與個股業務關聯 |
| 13 | 日線蠟燭圖策略 | My project | candlestick.py | 日線型態與支撐壓力 |
| 14 | 1H 趨勢結構 | My project | market_structure.py | HH/HL、LH/LL 與盤整狀態 |
| 15 | 5M 進場確認 | My project | market_structure.py、candlestick.py | 回測不破、IFVG 與流動性掃單 |
| 16 | 只做多策略過濾 | My project | rule_score.py | 排除空方與低勝率多方 |
| 17 | 3-20 天波段條件判斷 | stock-analysis | candlestick.py、rule_score.py | 波段持有週期適配 |
| 18 | 進場、停損、出場條件 | My project | candlestick.py、rule_score.py | 具體交易計畫 |
| 19 | 候選股排序，最多 5 檔 | stock-checker-analysis | pipeline.py | 每日觀察名單 |
| 20 | 產出完整中文報告 | My project | report.py、translation.py | Markdown 中文報告 |
| 21 | LINE broadcast 通知 | My project | notify.py | 完整文字 LINE 通知 |
| 22 | 每日自動執行 | My project | scripts/run_daily.ps1 | 自動排程執行 |
| 23 | 追蹤成效與回測 | spreadsheets、stock-correlation、stock-checker-analysis | training_data.py | 績效追蹤、回測與資料護欄 |

## 實作原則

- Skills 負責分析框架與研究判斷，My project 模組負責可重複執行的資料管線。
- `stock-analysis` 用於個股基本面、技術面、投資論點與風險。
- `stock-checker-analysis` 用於多因子分數、訊號摘要與風險旗標。
- 模型訓練與回測必須先套用 `training_data.py` 的資料護欄，避免黑天鵝與普漲行情造成過擬合。
- LINE 報告會列出本次流程，方便檢查每日分析是否有照標準走。
