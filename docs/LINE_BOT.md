# LINE Bot

## 設定

1. 在 LINE Developers 建立 Messaging API channel。
2. 取得 Channel access token 與 Channel secret。
3. 啟用 webhook。
4. 將 webhook URL 指到你部署的 server，例如 `https://example.com/line/webhook`。

## 取得 userId 或 groupId

本專案提供最小 webhook server，會驗證 `X-Line-Signature`，並在收到事件時印出 `userId`、`groupId` 或 `roomId`。

```powershell
$env:LINE_CHANNEL_SECRET="你的 channel secret"
python -m stock_signal_system.line_bot_server
```

本機測試可搭配 ngrok 或 Cloudflare Tunnel，把公開 HTTPS URL 接到本機 `8080`。

## 每日推播

把環境變數填好：

```powershell
$env:LINE_CHANNEL_ACCESS_TOKEN="你的 channel access token"
$env:LINE_TO="你的 userId 或 groupId"
```

設定 `configs/local.example.json`：

```json
{
  "line_channel_access_token_env": "LINE_CHANNEL_ACCESS_TOKEN",
  "line_to_env": "LINE_TO"
}
```

每日流程執行後會呼叫 LINE push message：

```powershell
python -m stock_signal_system.cli run --config configs/local.example.json
```

## 注意事項

- LINE webhook 必須驗簽，避免任何人偽造請求。
- Push message 只能送給符合 LINE 官方條件的使用者、群組或聊天室。
- 訊息有長度限制，本系統只推送摘要與報告路徑，完整內容保留在 Markdown 報告。

