from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.core.paths import CONFIG_DIR, fundamentals_dir, fundamentals_import_dir


def _parse_number(value: str) -> float | None:
    if value is None:
        return None
    cleaned = str(value).strip().replace(",", "").replace("%", "")
    if cleaned in {"", "-", "NA", "N/A"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_symbol(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def import_screener_csv(csv_path: Path) -> dict[str, dict]:
    imported: dict[str, dict] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            symbol_key = None
            for key in row:
                if key and key.strip().lower() == "symbol":
                    symbol_key = key
                    break
            if not symbol_key:
                continue
            symbol = _normalize_symbol(row[symbol_key])
            if not symbol:
                continue

            metrics = {
                "market_cap": _parse_number(row.get("Market Cap") or row.get("Market cap")),
                "current_price": _parse_number(row.get("Current Price") or row.get("CMP")),
                "book_value": _parse_number(row.get("Book value") or row.get("Book Value")),
                "roce_pct": _parse_number(row.get("ROCE %") or row.get("ROCE")),
                "roe_pct": _parse_number(row.get("ROE %") or row.get("ROE")),
                "debt_to_eq": _parse_number(row.get("Debt / EQ") or row.get("Debt to equity")),
                "opm_pct": _parse_number(row.get("OPM %") or row.get("OPM")),
                "sales_growth_pct": _parse_number(
                    row.get("Sales growth %") or row.get("Sales growth")
                ),
                "profit_growth_pct": _parse_number(
                    row.get("Profit growth %") or row.get("Profit growth")
                ),
            }
            metrics = {key: value for key, value in metrics.items() if value is not None}
            payload = {
                "symbol": symbol,
                "source": "screener.in",
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "source_file": str(csv_path.name),
                "metrics": metrics,
            }
            imported[symbol] = payload
            output = fundamentals_dir() / f"{symbol}.json"
            output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return imported


def import_all_screener_files() -> dict[str, dict]:
    import_dir = fundamentals_import_dir()
    import_dir.mkdir(parents=True, exist_ok=True)
    combined: dict[str, dict] = {}
    for csv_path in sorted(import_dir.glob("*.csv")):
        combined.update(import_screener_csv(csv_path))
    if not combined and (CONFIG_DIR / "samples" / "screener_template.csv").exists():
        combined.update(import_screener_csv(CONFIG_DIR / "samples" / "screener_template.csv"))
    return combined


def load_fundamentals(symbol: str) -> dict | None:
    path = fundamentals_dir() / f"{symbol}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def score_fundamentals(symbol: str) -> tuple[float, list[dict]]:
    payload = load_fundamentals(symbol)
    if not payload:
        return 0.0, []

    metrics = payload.get("metrics", {})
    score = 0.0
    reasons: list[dict] = []

    price = metrics.get("current_price")
    book = metrics.get("book_value")
    if price and book and book > 0:
        premium = (price / book) - 1
        if premium < 0.25:
            score += 2.0
            reasons.append(
                {
                    "layer": "fundamental",
                    "text": f"Price near/book value support (P/B ~{premium:.0%})",
                    "weight": "medium",
                    "date": payload.get("imported_at", "")[:10],
                    "source": payload.get("source"),
                }
            )

    for field, label, threshold, points in (
        ("roce_pct", "ROCE", 15, 2.0),
        ("roe_pct", "ROE", 15, 1.5),
        ("sales_growth_pct", "Sales growth", 10, 2.0),
        ("profit_growth_pct", "Profit growth", 10, 2.0),
        ("opm_pct", "Operating margin", 15, 1.5),
    ):
        value = metrics.get(field)
        if value is None:
            continue
        if value >= threshold:
            score += points
            reasons.append(
                {
                    "layer": "fundamental",
                    "text": f"{label} {value}% (above {threshold}%)",
                    "weight": "high" if points >= 2 else "medium",
                    "date": payload.get("imported_at", "")[:10],
                    "source": payload.get("source"),
                }
            )

    debt = metrics.get("debt_to_eq")
    if debt is not None and debt <= 0.5:
        score += 1.0
        reasons.append(
            {
                "layer": "fundamental",
                "text": f"Low leverage (Debt/Eq {debt})",
                "weight": "medium",
                "date": payload.get("imported_at", "")[:10],
                "source": payload.get("source"),
            }
        )

    settings = get_settings()
    if len(reasons) < settings.fundamentals.min_score_metrics:
        return round(min(10.0, score), 1), reasons

    return round(min(10.0, score), 1), reasons
