from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache

from app.core.paths import CONFIG_DIR, theme_overrides_dir, theme_scores_dir
from app.engines.fundamental import load_fundamentals
from app.engines.universe import all_instruments
from app.ingest.pib_client import load_pib_feed, match_pib_for_symbol


@lru_cache
def load_theme_graph() -> dict:
    path = CONFIG_DIR / "themes" / "graph.json"
    return json.loads(path.read_text(encoding="utf-8"))


def themes_for_symbol(symbol: str) -> list[dict]:
    graph = load_theme_graph()
    symbol = symbol.upper()
    matched: list[dict] = []
    for theme in graph.get("themes", []):
        if symbol in theme.get("symbols", []):
            matched.append(theme)
    return matched


def _load_override(symbol: str) -> dict:
    path = theme_overrides_dir() / f"{symbol.upper()}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _metric_score(value: float | None, good_threshold: float, points: float) -> float:
    if value is None:
        return 0.0
    return points if value >= good_threshold else points * 0.5


def _build_scenarios(symbol: str, themes: list[dict], score: float) -> dict[str, str]:
    theme_names = ", ".join(theme["name"] for theme in themes[:3]) or "General market"
    return {
        "bull": (
            f"{symbol} benefits from {theme_names}; order book and capacity "
            f"expand faster than consensus. Theme score {score}/10 supports upside "
            f"if technical setup confirms."
        ),
        "base": (
            f"{symbol} tracks sector beta with steady execution on {theme_names}. "
            f"Returns depend on delivery vs guidance; no major thesis break."
        ),
        "bear": (
            f"{symbol} faces valuation compression or order delays despite "
            f"{theme_names} exposure. Macro slowdown or commodity shock could "
            f"invalidate near-term momentum."
        ),
    }


def score_themes(symbol: str) -> tuple[float, list[dict], dict]:
    symbol = symbol.upper()
    themes = themes_for_symbol(symbol)
    override = _load_override(symbol)
    fundamentals = load_fundamentals(symbol) or {}
    metrics = fundamentals.get("metrics", {})

    reasons: list[dict] = []
    raw = 0.0

    theme_count = len(themes)
    if theme_count:
        raw += min(3.0, theme_count * 1.0)
        for theme in themes:
            reasons.append(
                {
                    "layer": "theme",
                    "text": f"Theme exposure: {theme['name']} — {theme.get('macro', '')}",
                    "weight": "high",
                    "source": "config/themes/graph.json",
                    "theme_id": theme["id"],
                }
            )

    if any(theme.get("horizontal_enabler") for theme in themes):
        raw += 2.0
        reasons.append(
            {
                "layer": "theme",
                "text": "Horizontal enabler across multiple industries",
                "weight": "high",
                "source": "config/themes/graph.json",
            }
        )

    pib_hits = match_pib_for_symbol(symbol, load_pib_feed())
    if pib_hits:
        raw += min(2.0, len(pib_hits) * 0.5)
        reasons.append(
            {
                "layer": "theme",
                "text": f"PIB policy tailwind ({len(pib_hits)} recent matches)",
                "weight": "medium",
                "source": "pib.gov.in",
            }
        )

    raw += _metric_score(metrics.get("sales_growth_pct"), 10, 1.5)
    raw += _metric_score(metrics.get("roce_pct"), 15, 1.5)
    raw += _metric_score(metrics.get("profit_growth_pct"), 10, 1.0)

    if metrics.get("sales_growth_pct", 0) >= 10:
        reasons.append(
            {
                "layer": "theme",
                "text": f"Earnings growth proxy: sales growth {metrics['sales_growth_pct']}%",
                "weight": "medium",
                "source": fundamentals.get("source", "fundamentals"),
            }
        )

    for key, value in override.get("rubric", {}).items():
        if isinstance(value, (int, float)) and value > 0:
            raw += min(2.0, value * 0.4)
            reasons.append(
                {
                    "layer": "theme",
                    "text": f"Manual override: {key.replace('_', ' ')} = {value}",
                    "weight": "high",
                    "source": "data/themes/overrides",
                }
            )

    score = round(min(10.0, raw), 1)
    scenarios = _build_scenarios(symbol, themes, score)
    payload = {
        "symbol": symbol,
        "score": score,
        "themes": themes,
        "scenarios": scenarios,
        "reasons": reasons,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    theme_scores_dir().joinpath(f"{symbol}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return score, reasons, scenarios


def load_theme_score(symbol: str) -> dict | None:
    path = theme_scores_dir() / f"{symbol.upper()}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_all_theme_scores() -> dict[str, float]:
    scores: dict[str, float] = {}
    for instrument in all_instruments():
        if instrument.get("type") != "stock":
            continue
        symbol = instrument["symbol"]
        score, _, _ = score_themes(symbol)
        scores[symbol] = score
    summary_path = theme_scores_dir() / "_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "scores": scores,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return scores
