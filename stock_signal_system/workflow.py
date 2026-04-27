from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowStep:
    order: int
    name: str
    skills: tuple[str, ...]
    system_modules: tuple[str, ...]
    output: str


ANALYSIS_WORKFLOW: tuple[WorkflowStep, ...] = (
    WorkflowStep(1, "RSS、新聞、政策、輿情蒐集", ("zai-cli", "web-access"), ("rss_sources.py",), "候選新聞與輿情資料"),
    WorkflowStep(2, "新聞清洗與排除雜訊", ("finance-sentiment",), ("rss_sources.py",), "去除不相關、重複、誤分類新聞"),
    WorkflowStep(3, "產業訊號分類", ("finance-sentiment", "finance-investment-researcher"), ("industry.py",), "產業訊號與催化因素"),
    WorkflowStep(4, "產業利基分析", ("finance-investment-researcher",), ("industry.py",), "產業利基、需求與風險摘要"),
    WorkflowStep(5, "台股上市/上櫃股票池建立", (), ("twse.py", "finmind.py", "yfinance_source.py"), "台股普通股股票池"),
    WorkflowStep(6, "日線 OHLCV / 財務資料擷取", ("yfinance-data", "funda-data"), ("twse.py", "finmind.py", "yfinance_source.py"), "日線、成交量與財務欄位"),
    WorkflowStep(7, "1H / 5M 資料匯入", (), ("csv_sources.py",), "盤中結構與觸發資料"),
    WorkflowStep(8, "基本面分析", ("stock-analysis", "finance-financial-analyst", "funda-data"), ("rule_score.py",), "成長、獲利、估值與財務品質"),
    WorkflowStep(9, "個股投資論點分析", ("stock-analysis", "finance-investment-researcher"), ("rule_score.py",), "個股受惠邏輯與反方風險"),
    WorkflowStep(10, "流動性檢查", ("stock-liquidity",), ("rule_score.py",), "成交量與可交易性"),
    WorkflowStep(11, "多因子訊號評分", ("stock-checker-analysis",), ("rule_score.py",), "產業、基本面、動能、技術與風險分數"),
    WorkflowStep(12, "產業與個股關聯檢查", ("stock-analysis", "stock-correlation"), ("rule_score.py",), "題材與個股業務關聯"),
    WorkflowStep(13, "日線蠟燭圖策略", (), ("candlestick.py",), "日線型態與支撐壓力"),
    WorkflowStep(14, "1H 趨勢結構", (), ("market_structure.py",), "HH/HL、LH/LL 與盤整狀態"),
    WorkflowStep(15, "5M 進場確認", (), ("market_structure.py", "candlestick.py"), "回測不破、IFVG 與流動性掃單"),
    WorkflowStep(16, "只做多策略過濾", (), ("rule_score.py",), "排除空方與低勝率多方"),
    WorkflowStep(17, "3-20 天波段條件判斷", ("stock-analysis",), ("candlestick.py", "rule_score.py"), "波段持有週期適配"),
    WorkflowStep(18, "進場、停損、出場條件", (), ("candlestick.py", "rule_score.py"), "具體交易計畫"),
    WorkflowStep(19, "候選股排序，最多 5 檔", ("stock-checker-analysis",), ("pipeline.py",), "每日觀察名單"),
    WorkflowStep(20, "產出完整中文報告", (), ("report.py", "translation.py"), "Markdown 中文報告"),
    WorkflowStep(21, "LINE broadcast 通知", (), ("notify.py",), "完整文字 LINE 通知"),
    WorkflowStep(22, "每日自動執行", (), ("scripts/run_daily.ps1",), "自動排程執行"),
    WorkflowStep(23, "追蹤成效與回測", ("spreadsheets", "stock-correlation", "stock-checker-analysis"), ("training_data.py",), "績效追蹤、回測與資料護欄"),
)


def workflow_summary_lines() -> list[str]:
    lines = []
    for step in ANALYSIS_WORKFLOW:
        skills = "、".join(step.skills) if step.skills else "My project"
        modules = "、".join(step.system_modules)
        lines.append(f"{step.order}. {step.name}｜{skills}｜{modules}")
    return lines
