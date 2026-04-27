# TWSE OpenAPI Integration

官方入口：https://openapi.twse.com.tw/

本系統選用以下 TWSE 官方 OpenAPI。

| 系統用途 | TWSE endpoint | 說明 |
| --- | --- | --- |
| 上市日線 OHLC 與成交量 | `/exchangeReport/STOCK_DAY_ALL` | 產生 `price_history_path` 可用的日線價格資料 |
| 上市估值 | `/exchangeReport/BWIBBU_ALL` | 本益比、殖利率、股價淨值比 |
| 上市公司基本資料 | `/opendata/t187ap03_L` | 公司代號、名稱、產業別、上市日、資本額 |
| 上市月營收 | `/opendata/t187ap05_L` | 月營收與年增率 |
| 上市重大訊息 | `/opendata/t187ap04_L` | 轉成新聞/事件 CSV，補充催化與風險事件 |
| 交易日 | `/holidaySchedule/holidaySchedule` | 可做排程避開休市日 |

## 不選用或僅輔助

- `/exchangeReport/MI_5MINS`: 這是集中市場每 5 秒委託成交統計，不是個股 5 分 K。
- `/exchangeReport/MI_INDEX`: 大盤統計資訊，適合作市場背景，不適合個股篩選。
- `/company/newlisting`: 只適合偵測新上市，不作每日核心篩選。

## 上櫃資料

TWSE OpenAPI 主要涵蓋上市公司。你的市場範圍是「上市/上櫃」，所以上櫃資料仍建議透過：

- FinMind
- TPEx/櫃買中心資料
- 券商 API

TWSE 這次先作為上市資料的官方合法基底。

## 使用方式

```powershell
python -m stock_signal_system.cli fetch-twse `
  --stocks-output data/twse_stocks.csv `
  --prices-output data/twse_price_daily.csv `
  --news-output data/twse_material_news.csv
```

輸出：

- `data/twse_stocks.csv`: 可作為 `stock_path`
- `data/twse_price_daily.csv`: 可作為日線價格輸入或每日歸檔
- `data/twse_material_news.csv`: 可作為新聞/事件輸入

## 限制

TWSE OpenAPI 不直接提供本系統需要的所有基本面欄位，例如毛利率、營業利益率、自由現金流率、負債權益比。`fetch-twse` 會以保守預設值產生欄位，正式分析仍應用 FinMind、財報資料或券商資料補齊。

