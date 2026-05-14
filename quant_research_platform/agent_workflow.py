from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


class ScoredRow(Protocol):
    symbol: str
    name: str
    industry: str
    kronos_return: float
    kronos_score: float
    news_score: float
    technical_score: float
    realtime_score: float
    hybrid_score: float
    risk_note: str
    technical_evidence: tuple[str, ...]


@dataclass(frozen=True)
class AgentDecision:
    agent: str
    symbol: str
    score: float
    stance: str
    evidence: tuple[str, ...]
    veto: bool = False


@dataclass(frozen=True)
class AgentWorkflowResult:
    market_intelligence: tuple[AgentDecision, ...]
    technical: tuple[AgentDecision, ...]
    quant: tuple[AgentDecision, ...]
    devil_advocate: tuple[AgentDecision, ...]
    portfolio_manager: tuple[AgentDecision, ...]


AGENT_NAMES = (
    "Market_Intelligence_Agent",
    "Technical_Analyst_Agent",
    "Quant_Research_Agent",
    "Devil_Advocate_Agent",
    "Portfolio_Manager_Agent",
)

PORTFOLIO_BUCKETS = {
    "include_daily_report": "include",
    "watch_only": "watch",
    "exclude_by_veto": "exclude",
    "exclude_data_insufficient": "exclude",
}


def run_five_agent_workflow(rows: list[ScoredRow]) -> AgentWorkflowResult:
    market = _market_intelligence(rows)
    technical = tuple(_technical(row) for row in rows)
    quant = tuple(_quant(row) for row in rows)
    devil = tuple(_devil(row) for row in rows)
    portfolio = tuple(
        _portfolio_manager(row, market, tech, q, d)
        for row, tech, q, d in zip(rows, technical, quant, devil)
    )
    return AgentWorkflowResult(market, technical, quant, devil, portfolio)


def agent_workflow_markdown(result: AgentWorkflowResult, limit: int = 12) -> list[str]:
    lines = [
        "## 五代理決策看板",
        "",
        "- Market_Intelligence_Agent：只整理 RSS、政策、產業與輿情主題，不直接推薦股票。",
        "- Technical_Analyst_Agent：只分析 K 線、多週期、突破、量價與結構，不使用新聞情緒。",
        "- Quant_Research_Agent：只輸出因子分數、預期報酬、信心度與 false positive 檢查。",
        "- Devil_Advocate_Agent：檢查假突破、出貨、過熱、AI 無證據與過度偏多，具 veto 權限。",
        "- Portfolio_Manager_Agent：只整合其他代理結論並決定是否進入每日報告，不自行分析股票。",
        "",
        "| 股票 | 市場情報 | 技術分析 | 量化研究 | 反方審查 | 組合決策 | 最終分數 |",
        "|---|---:|---:|---:|---|---|---:|",
    ]
    decisions = portfolio_decision_map(result)
    for tech, quant, devil in zip(result.technical[:limit], result.quant[:limit], result.devil_advocate[:limit]):
        manager = decisions[tech.symbol]
        market_score = _market_score_for_symbol(result.market_intelligence, tech.symbol)
        devil_text = "否決" if devil.veto else _zh_stance(devil.stance)
        lines.append(
            f"| {manager.symbol} | {market_score:.1f} | {tech.score:.1f} | {quant.score:.1f} | "
            f"{devil_text} | {_zh_decision(manager.stance)} | {manager.score:.1f} |"
        )
    lines.extend(["", "### Technical_Analyst_Agent 證據", "", "| 股票 | 技術證據 |", "|---|---|"])
    for tech in result.technical[:limit]:
        lines.append(f"| {tech.symbol} | {'；'.join(tech.evidence)} |")
    return lines


def portfolio_decision_map(result: AgentWorkflowResult) -> dict[str, AgentDecision]:
    return {decision.symbol: decision for decision in result.portfolio_manager}


def portfolio_decision_bucket(decision: AgentDecision | None) -> str:
    return PORTFOLIO_BUCKETS.get(decision.stance if decision else "", "exclude")


def portfolio_decision_label(decision: AgentDecision | None) -> str:
    return _zh_decision(decision.stance) if decision else "資料不足排除"


def _market_intelligence(rows: list[ScoredRow]) -> tuple[AgentDecision, ...]:
    groups: dict[str, list[ScoredRow]] = {}
    for row in rows:
        groups.setdefault(row.industry, []).append(row)
    decisions = []
    for industry, group in sorted(groups.items(), key=lambda item: _average_news(item[1]), reverse=True):
        score = _average_news(group)
        decisions.append(
            AgentDecision(
                agent="Market_Intelligence_Agent",
                symbol=industry,
                score=score,
                stance=_stance(score),
                evidence=(
                    f"industry_theme={industry}",
                    f"rss_policy_sentiment_score={score:.1f}",
                    f"covered_names={len(group)}",
                ),
            )
        )
    return tuple(decisions)


def _technical(row: ScoredRow) -> AgentDecision:
    source_evidence = tuple(getattr(row, "technical_evidence", ()))
    evidence = source_evidence + (
        f"technical_score={row.technical_score:.1f}",
        f"realtime_score={row.realtime_score:.1f}",
        "news_sentiment_excluded=true",
    )
    return AgentDecision("Technical_Analyst_Agent", row.symbol, row.technical_score, _stance(row.technical_score), evidence)


def _quant(row: ScoredRow) -> AgentDecision:
    false_positive_penalty = 12.0 if abs(row.kronos_return) < 0.005 and row.hybrid_score >= 70 else 0.0
    score = _clamp(row.kronos_score * 0.70 + row.realtime_score * 0.20 + row.technical_score * 0.10 - false_positive_penalty)
    evidence = (
        f"kronos_return={row.kronos_return:.2%}",
        f"kronos_score={row.kronos_score:.1f}",
        f"false_positive_penalty={false_positive_penalty:.1f}",
    )
    return AgentDecision("Quant_Research_Agent", row.symbol, score, _stance(score), evidence)


def _devil(row: ScoredRow) -> AgentDecision:
    false_breakout_flag = row.technical_score < 45 and row.realtime_score < 50
    distribution_flag = row.realtime_score < 45 and row.hybrid_score >= 62
    overheat_flag = row.hybrid_score >= 75 and row.kronos_return < 0.01
    ai_hallucination_flag = row.hybrid_score >= 70 and row.news_score < 45 and row.kronos_return <= 0
    overbullish_flag = sum((row.kronos_return < 0, row.technical_score < 50, row.realtime_score < 50)) >= 2
    checks = (
        false_breakout_flag,
        distribution_flag,
        overheat_flag,
        ai_hallucination_flag,
        overbullish_flag,
        _has_red_flag_risk_note(row.risk_note),
    )
    hit_count = sum(1 for item in checks if item)
    block = false_breakout_flag or distribution_flag or ai_hallucination_flag
    veto = block or hit_count >= 2
    veto_level = "block" if block else "watch" if veto else "none"
    score = _clamp(100 - hit_count * 22)
    evidence = (
        f"false_breakout_flag={false_breakout_flag}",
        f"distribution_flag={distribution_flag}",
        f"overheat_flag={overheat_flag}",
        f"ai_hallucination_flag={ai_hallucination_flag}",
        f"overbullish_flag={overbullish_flag}",
        f"veto_level={veto_level}",
        f"red_flags={hit_count}",
        f"risk_note={row.risk_note}",
    )
    return AgentDecision("Devil_Advocate_Agent", row.symbol, score, "veto" if veto else _stance(score), evidence, veto=veto)


def _portfolio_manager(
    row: ScoredRow,
    market: Iterable[AgentDecision],
    technical: AgentDecision,
    quant: AgentDecision,
    devil: AgentDecision,
) -> AgentDecision:
    market_score = next((item.score for item in market if item.symbol == row.industry), None)
    data_insufficient = market_score is None or not all((technical.evidence, quant.evidence, devil.evidence))
    market_value = 50.0 if market_score is None else market_score
    raw_score = market_value * 0.20 + technical.score * 0.25 + quant.score * 0.35 + devil.score * 0.20
    final_score = 0.0 if devil.veto or data_insufficient else _clamp(raw_score)
    if data_insufficient:
        stance = "exclude_data_insufficient"
    elif devil.veto:
        stance = "exclude_by_veto"
    else:
        stance = "include_daily_report" if final_score >= 62 else "watch_only"
    evidence = (
        f"market={market_value:.1f}",
        f"technical={technical.score:.1f}",
        f"quant={quant.score:.1f}",
        f"devil={devil.score:.1f}",
        f"veto_level={_evidence_value(devil.evidence, 'veto_level')}",
        f"data_insufficient={data_insufficient}",
    )
    return AgentDecision("Portfolio_Manager_Agent", row.symbol, final_score, stance, evidence, veto=devil.veto)


def _has_red_flag_risk_note(risk_note: str) -> bool:
    note = risk_note.casefold()
    stable_terms = ("stable", "風險穩定")
    return bool(note and not any(term in note for term in stable_terms))


def _evidence_value(evidence: tuple[str, ...], key: str) -> str:
    prefix = f"{key}="
    return next((item.removeprefix(prefix) for item in evidence if item.startswith(prefix)), "unknown")


def _average_news(rows: list[ScoredRow]) -> float:
    return sum(row.news_score for row in rows) / len(rows) if rows else 50.0


def _market_score_for_symbol(market_decisions: Iterable[AgentDecision], symbol: str) -> float:
    items = tuple(market_decisions)
    return sum(item.score for item in items) / len(items) if items else 50.0


def _stance(score: float) -> str:
    if score >= 70:
        return "bullish"
    if score <= 45:
        return "bearish"
    return "neutral"


def _zh_stance(stance: str) -> str:
    return {
        "bullish": "偏多",
        "bearish": "偏空",
        "neutral": "中性",
        "veto": "否決",
    }.get(stance, stance)


def _zh_decision(decision: str) -> str:
    return {
        "include_daily_report": "納入每日報告",
        "exclude_by_veto": "因否決排除",
        "exclude_data_insufficient": "資料不足排除",
        "watch_only": "觀察名單",
    }.get(decision, decision)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
