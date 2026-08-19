from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from app.ai.analyst import critique_setup
from app.strategies.base import Candidate


def _candidate_from_row(row: pd.Series) -> Candidate:
    supporting = row.supporting_json
    risks = row.risk_json
    if isinstance(supporting, str):
        supporting = json.loads(supporting)
    if isinstance(risks, str):
        risks = json.loads(risks)
    return Candidate(
        asof_date=row.asof_date,
        symbol=row.symbol,
        strategy=row.strategy,
        side=row.side,
        entry_price=row.entry_price,
        stop_price=row.stop_price,
        target_price=row.target_price,
        reward_risk=row.reward_risk,
        supporting=list(supporting or []),
        risks=list(risks or []),
        invalidation=row.invalidation,
        entry_condition=getattr(row, "entry_condition", "Enter at next session open."),
    )


def render_daily_report(
    scored: pd.DataFrame,
    asof: date,
    path: Path,
    top_n: int = 5,
) -> str:
    lines = [f"# Top 5 Next-Day Setups", f"", f"As-of close: **{asof.isoformat()}**", f""]
    if scored.empty:
        lines.append("No candidates survived quantitative filters for this date.")
        text = "\n".join(lines) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return text
    ranked = scored.sort_values("probability", ascending=False).head(top_n)
    lines.append("| # | Stock | Strategy | Probability | Entry | SL | Target | R:R |")
    lines.append("|---|---|---|---|---|---|---|---|")
    accepted_rows = []
    for i, row in enumerate(ranked.itertuples(index=False), start=1):
        cand = _candidate_from_row(pd.Series(row._asdict()))
        news = json.loads(getattr(row, "news_json", "[]") or "[]")
        critique = critique_setup(cand, float(row.probability), news)
        marker = "" if critique.accept else " (critic reject)"
        lines.append(
            f"| {i} | {row.symbol}{marker} | {row.strategy} | {row.probability:.3f} | "
            f"{row.entry_price:.2f} | {row.stop_price:.2f} | {row.target_price:.2f} | {row.reward_risk:.2f} |"
        )
        accepted_rows.append((i, row, cand, critique))
    lines.append("")
    for i, row, cand, critique in accepted_rows:
        lines.append(f"## {i}. {row.symbol} — {row.strategy}")
        lines.append(f"- Side: {row.side}")
        lines.append(f"- Entry condition: {cand.entry_condition}")
        lines.append(f"- Stop: {row.stop_price:.2f}  Target: {row.target_price:.2f}  R:R: {row.reward_risk:.2f}")
        lines.append(f"- ML P(target before stop next session): {row.probability:.3f}")
        lines.append("- Why it qualifies:")
        for item in cand.supporting:
            lines.append(f"  - {item}")
        lines.append("- Risks / contradicting factors:")
        for item in cand.risks + critique.extra_risks:
            lines.append(f"  - {item}")
        lines.append(f"- Invalidation: {cand.invalidation}")
        lines.append(f"- Critic: {critique.narrative}")
        lines.append("")
    lines.append("Entry prices are the prior close used to set percentage stops/targets; live fill is the next session open.")
    lines.append("This report is research output, not a trade recommendation.")
    text = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text
