from __future__ import annotations

import json
import os
from dataclasses import dataclass

from app.strategies.base import Candidate


@dataclass
class Critique:
    accept: bool
    narrative: str
    extra_risks: list[str]


def _rule_based(candidate: Candidate, probability: float, news: list[str]) -> Critique:
    extra: list[str] = []
    reject = False
    if probability >= 0.7 and any("Nifty is extended" in item for item in candidate.risks):
        extra.append("High ML score fights a stretched index; treat as a fade against the tape.")
        reject = True
    if news and any("result" in item.lower() or "ban" in item.lower() for item in news):
        extra.append("Corporate/event headline present; event risk dominates the technical setup.")
        reject = True
    if probability < 0.5:
        extra.append("ML probability is near chance; size down or skip.")
    narrative = (
        f"{candidate.symbol} {candidate.strategy} {candidate.side} "
        f"ML P(target before stop)={probability:.2f}. "
        + ("Rejected by critic." if reject else "Critic did not override the quantitative rank.")
    )
    return Critique(accept=not reject, narrative=narrative, extra_risks=extra)


def critique_setup(candidate: Candidate, probability: float, news: list[str] | None = None) -> Critique:
    news = news or []
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _rule_based(candidate, probability, news)
    try:
        from urllib import request

        payload = {
            "model": os.environ.get("NSE_OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You review shortlisted NSE next-day setups. "
                        "You do not predict prices. You may reject a high ML score if context contradicts it. "
                        "Reply JSON: {\"accept\": bool, \"narrative\": str, \"extra_risks\": [str]}."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "candidate": candidate.to_row(),
                            "ml_probability": probability,
                            "news": news,
                            "supporting": candidate.supporting,
                            "risks": candidate.risks,
                        }
                    ),
                },
            ],
            "temperature": 0.1,
        }
        req = request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode())
        text = body["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        return Critique(
            accept=bool(parsed.get("accept", True)),
            narrative=str(parsed.get("narrative", "")),
            extra_risks=list(parsed.get("extra_risks", [])),
        )
    except Exception:
        return _rule_based(candidate, probability, news)
