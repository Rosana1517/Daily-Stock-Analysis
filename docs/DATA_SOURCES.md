# Data Sources

## RSS 來源分級

建議把 RSS 來源分成三層，不要把所有 feed 權重視為相同。

| 層級 | 用途 | 範例 |
| --- | --- | --- |
| primary | 主要新聞與政策訊號 | BBC Business、BBC Technology、NYTimes Business、TWSE News |
| community-bridge | 補充來源，需人工檢查穩定性 | Reddit 提到的 FeedX AP feed、OpenRSS、RSSHub、RSS-Bridge |
| paid/licensed | 正式商用或大量使用 | 鉅亨新聞 API/RSS、券商新聞、授權資料商 |

Reddit 討論串提到的重點是：沒有單一「最好」新聞 RSS，應挑可信新聞網站本身提供的 feed；也有人提到 RSSHub、OpenRSS、RSS-Bridge 與 FeedX AP feed。這些可以做候選池，但正式交易決策建議優先用官方 RSS、交易所公告與授權資料源。

目前設定在 `configs/rss_sources.example.json`，可用：

```powershell
python -m stock_signal_system.cli fetch-news --sources configs/rss_sources.example.json --output data/news_rss.csv
```

## FinMind

使用 `TaiwanStockPrice` 這類正式資料集，不爬網頁。系統 client 有：

- 快取：避免同一查詢重複打 API
- 限速：預設約 6.5 秒一次，保守落在 600 requests/hour 以內
- 退避重試：遇到 402/429/5xx 類狀況會等待後重試

```powershell
$env:FINMIND_TOKEN="你的 token"
python -m stock_signal_system.cli fetch-finmind --stock-id 2330 --start-date 2026-04-01 --end-date 2026-04-24
```

## yfinance

yfinance 適合研究與輔助，不是 Yahoo 官方授權 API。正式使用時：

- 使用 `pip install .[market]` 安裝 optional dependency
- 批次下載，不逐檔高頻打
- 開啟本地快取
- 不做秒級或分鐘級輪詢

```powershell
pip install .[market]
python -m stock_signal_system.cli fetch-yfinance --symbols AAPL MSFT 2330.TW --period 3mo
```

## 交易所與政府開放資料

台灣證券交易所與政府資料開放平台提供每日收盤行情等資料。正式部署建議優先採：

- TWSE 官方頁面或 OpenAPI 文件提供的資料
- data.gov.tw 標示授權的資料集
- 付費授權資料商，若需要再散布或商用

避免：

- 高頻抓取網頁 HTML
- 模擬瀏覽器繞過限制
- 忽略資料授權與再散布條款

