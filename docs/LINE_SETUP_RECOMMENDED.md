# Recommended LINE Bot Setup

我建議使用 LINE Messaging API 的 push message，而不是舊版 LINE Notify。原因是 Messaging API 可維護性較好，也能之後擴充成互動式 bot。

## 你需要手動完成

1. 到 LINE Developers 建立 Provider。
2. 建立 Messaging API channel。
3. 取得 Channel access token。
4. 取得 Channel secret。
5. 把 bot 加為好友，或邀請進群組。
6. 啟動本專案的 webhook server 取得 `userId` 或 `groupId`。

## 本機取得 LINE_TO

先設定：

```powershell
$env:LINE_CHANNEL_SECRET="你的 Channel secret"
python -m stock_signal_system.line_bot_server
```

用 ngrok 或 Cloudflare Tunnel 把本機 `8080` 暴露成 HTTPS，填到 LINE Developers 的 webhook URL。

當你傳訊息給 bot 時，終端會印出：

```text
LINE user/group IDs: Uxxxxxxxx
```

把它設為：

```powershell
$env:LINE_TO="Uxxxxxxxx"
```

## 每日推播設定

```powershell
$env:FINMIND_TOKEN="你的 FinMind token"
$env:LINE_CHANNEL_ACCESS_TOKEN="你的 Channel access token"
$env:LINE_TO="Uxxxxxxxx"
```

設定檔已預留：

```json
{
  "line_channel_access_token_env": "LINE_CHANNEL_ACCESS_TOKEN",
  "line_to_env": "LINE_TO",
  "notification_min_score": 80,
  "notification_mode": "high_priority_summary"
}
```

目前可用兩種通知模式：

- `high_priority_summary`: 簡短摘要，只列分數達 `80` 以上的高優先標的。
- `full_report`: 把完整 Markdown 報告文字化後傳到 LINE。若報告過長，系統會切成最多 5 則 LINE 文字訊息。

## Broadcast 給所有好友

如果要推播給所有已加好友的使用者，不需要 `LINE_TO`。設定檔使用：

```json
{
  "line_channel_access_token_env": "LINE_CHANNEL_ACCESS_TOKEN",
  "line_to_env": null,
  "line_broadcast": true,
  "notification_mode": "full_report"
}
```

然後只要設定：

```powershell
$env:LINE_CHANNEL_ACCESS_TOKEN="你的 Channel access token"
```

系統會呼叫 LINE broadcast endpoint，把同一則摘要送給所有好友。這會計入 LINE 官方帳號的月訊息用量。
## 報告過長時的建議做法

LINE Messaging API 適合傳送摘要與連結，不適合直接 broadcast 任意 Markdown/PDF 附件。

本專案每日會同時產生：

- `reports/stock_signals_YYYY-MM-DD.md`
- `reports/stock_signals_YYYY-MM-DD.html`

若要讓好友點連結閱讀完整報告，請先把 `reports/` 發布到 HTTPS 可讀網址，例如 GitHub Pages、Cloudflare Pages、Netlify、S3/R2 或自己的網站，然後在 config 裡設定：

```json
{
  "notification_mode": "report_link",
  "report_public_base_url": "https://你的網域/reports"
}
```

設定完成後，LINE 會發送簡短摘要與完整 HTML 報告連結。若未設定 `report_public_base_url`，系統仍會產生本機 HTML 檔，但 LINE 好友無法從自己的手機讀取你的本機路徑。

## 自動發布到 GitHub Pages

已安裝並登入 Git / Git Credential Manager 後，可以使用：

```powershell
.\scripts\publish_report_pages.ps1
```

這會自動找到 `reports/` 最新的 `stock_signals_*.html`，複製到本機 Pages repo，更新 `index.html`，然後 `git commit` 與 `git push`。

每日排程若要在產生報告後同步發布，請改執行：

```powershell
.\scripts\run_daily.ps1 -Config configs/rss.example.json -PublishPages
```

這個腳本會先執行 `refresh-data` 更新 RSS 與 TWSE OpenAPI 資料，再驗證設定、產生報告、發布 GitHub Pages。若當天只想更新 RSS、略過 TWSE，可用：

```powershell
.\scripts\run_daily.ps1 -Config configs/rss.example.json -PublishPages -SkipTwse
```
