# You Need To Provide

以下是要讓系統從範例版變成可每日使用版時，你需要提供或決定的內容。

## 必填

1. 股票市場範圍
   - 已設定：台股上市/上櫃

2. 交易方向
   - 已設定：只做多

3. 投資/交易週期
   - 已設定：波段 3-20 天

4. 資料來源
   - FinMind token
   - 券商 API 選擇與憑證
   - 或你提供每日 CSV

5. 1H 與 5M 資料
   - CSV 欄位：`symbol,datetime,open,high,low,close,volume`
   - 若由券商 API 取得，需要 API key/憑證與商品代碼格式

6. LINE 通知
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - 若使用 broadcast 給所有好友，不需要 `LINE_TO`
   - 若使用單一對象 push，才需要 `LINE_TO`，也就是 userId/groupId/roomId
   - 若需要 webhook server，還要 `LINE_CHANNEL_SECRET`

## 建議提供

1. 最大單筆風險
   - 例如每筆最多虧總資金 0.5% 或 1%

2. 最大持股數
   - 已設定：每日最多關注 5 檔

3. 產業黑名單/白名單
   - 例如不碰生技、不碰處置股、只追 AI/電力/半導體

4. 流動性門檻
   - 最低成交量
   - 最低成交金額

5. 估值門檻
   - PE 上限
   - 毛利率/營業利益率下限
   - 負債權益比上限

6. 交易時段
   - 已設定：台股盤中

7. 通知格式偏好
   - 已設定：簡短摘要，只通知高優先標的

## 現在還缺你提供

1. `FINMIND_TOKEN` 或券商 API 選擇與憑證。
2. LINE Developers 的 Channel access token。
3. 你的實際股票池。如果不提供，系統會以可取得的台股上市/上櫃資料為候選。
4. 單筆最大風險，例如總資金 0.5% 或 1%。

## 目前可先用範例資料跑

```powershell
python -m stock_signal_system.cli validate-config --config configs/local.example.json
python -m stock_signal_system.cli run --config configs/local.example.json
```
