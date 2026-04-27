# Operations

## 每日自動執行

Windows 工作排程器可以每天固定時間執行：

```powershell
python -m stock_signal_system.cli run --config C:\Users\Tong\.codex\專案\configs\local.example.json
```

建議排程時間：

- 盤前：整理隔夜新聞、政策與國際市場訊號
- 盤後：更新收盤價、量能、籌碼與財報資料

## 通知

`notification_webhook_env` 可以設定成環境變數名稱，例如：

```json
{
  "notification_webhook_env": "STOCK_SIGNAL_WEBHOOK_URL"
}
```

系統會從 `STOCK_SIGNAL_WEBHOOK_URL` 讀取 webhook URL，送出 JSON：

```json
{
  "title": "每日選股觀察 - 2026-04-24",
  "body": "今日關注：2330 台積電(82.0)。完整報告：reports/stock_signals_2026-04-24.md"
}
```

可接到自建 webhook、Slack、Discord、LINE proxy 或 n8n workflow。

也可以直接接 LINE Messaging API，詳見 `docs/LINE_BOT.md`。

```json
{
  "line_channel_access_token_env": "LINE_CHANNEL_ACCESS_TOKEN",
  "line_to_env": "LINE_TO"
}
```

## 下一階段資料來源

- 新聞與輿情：RSS、Google News、GDELT、社群平台、券商晨報摘要
- 政策：行政院、金管會、經濟部、能源署、各國央行與產業補助公告
- 股票資料：交易所日收盤、券商 API、FinMind、yfinance、財報資料庫
- 基本面：營收、毛利率、營業利益率、現金流、負債、估值倍數

## 風控欄位

正式使用前建議加入：

- 最大單一持股比重
- 產業集中度上限
- 停損與停利規則
- 流動性門檻
- 財報公布與法說會事件日
- 黑名單與人工排除清單
