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
                "qoq_profit_growth_pct": _parse_number(
                    row.get("QoQ profit growth %") or row.get("QoQ Profit growth %")
                ),
                "yoy_profit_growth_pct": _parse_number(
                    row.get("YoY profit growth %") or row.get("YoY Profit growth %")
                ),
                "qoq_sales_growth_pct": _parse_number(
                    row.get("QoQ sales growth %") or row.get("QoQ Sales growth %")
                ),
                "yoy_sales_growth_pct": _parse_number(
                    row.get("YoY sales growth %") or row.get("YoY Sales growth %")
                ),
                "eps_estimate": _parse_number(row.get("EPS estimate") or row.get("EPS Estimate")),
                "eps_actual": _parse_number(row.get("EPS actual") or row.get("EPS Actual")),
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


def load_expectations(symbol: str) -> dict | None:
    payload = load_fundamentals(symbol)
    if payload and payload.get("expectations"):
        return payload["expectations"]
    path = fundamentals_dir() / "expectations" / f"{symbol}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def score_fundamentals(symbol: str) -> tuple[float, list[dict]]:
    payload = load_fundamentals(symbol)
    if not payload:
        return 0.0, []

    metrics = payload.get("metrics", {})
    expectations = load_expectations(symbol) or {}
    score = 0.0
    reasons: list[dict] = []
    source = payload.get("source")
    as_of = payload.get("imported_at", "")[:10]

    qoq_profit = metrics.get("qoq_profit_growth_pct")
    yoy_profit = metrics.get("yoy_profit_growth_pct")
    qoq_sales = metrics.get("qoq_sales_growth_pct")
    yoy_sales = metrics.get("yoy_sales_growth_pct")

    if qoq_profit is not None:
        if qoq_profit > 0:
            score += 2.0
            reasons.append(
                {
                    "layer": "fundamental",
                    "text": f"QoQ profit growth {qoq_profit}% (better than prior quarter)",
                    "weight": "high",
                    "date": as_of,
                    "source": source,
                }
            )
        else:
            reasons.append(
                {
                    "layer": "fundamental",
                    "text": f"QoQ profit growth {qoq_profit}% (weaker than prior quarter)",
                    "weight": "low",
                    "date": as_of,
                    "source": source,
                }
            )

    if yoy_profit is not None:
        if yoy_profit > 0:
            score += 2.0
            reasons.append(
                {
                    "layer": "fundamental",
                    "text": f"YoY profit growth {yoy_profit}% (better than same quarter last year)",
                    "weight": "high",
                    "date": as_of,
                    "source": source,
                }
            )

    if qoq_sales is not None and qoq_sales > 0:
        score += 1.0
        reasons.append(
            {
                "layer": "fundamental",
                "text": f"QoQ sales growth {qoq_sales}%",
                "weight": "medium",
                "date": as_of,
                "source": source,
            }
        )

    if yoy_sales is not None and yoy_sales > 0:
        score += 1.0
        reasons.append(
            {
                "layer": "fundamental",
                "text": f"YoY sales growth {yoy_sales}%",
                "weight": "medium",
                "date": as_of,
                "source": source,
            }
        )

    eps_actual = metrics.get("eps_actual")
    eps_estimate = metrics.get("eps_estimate") or expectations.get("eps")
    if eps_actual is not None and eps_estimate is not None:
        if eps_actual >= eps_estimate:
            score += 2.5
            reasons.append(
                {
                    "layer": "fundamental",
                    "text": f"EPS {eps_actual} vs estimate {eps_estimate} (beat/met expectations)",
                    "weight": "high",
                    "date": as_of,
                    "source": source or expectations.get("source", "expectations"),
                }
            )
        else:
            reasons.append(
                {
                    "layer": "fundamental",
                    "text": f"EPS {eps_actual} missed estimate {eps_estimate}",
                    "weight": "low",
                    "date": as_of,
                    "source": source,
                }
            )

    exp_profit = expectations.get("profit_growth_pct")
    actual_profit = metrics.get("profit_growth_pct") or yoy_profit
    if exp_profit is not None and actual_profit is not None:
        if actual_profit >= exp_profit:
            score += 2.0
            reasons.append(
                {
                    "layer": "fundamental",
                    "text": (
                        f"Profit growth {actual_profit}% vs expectation {exp_profit}% "
                        f"({expectations.get('source', 'manual')})"
                    ),
                    "weight": "high",
                    "date": as_of,
                    "source": expectations.get("source", "expectations"),
                }
            )

    price = metrics.get("current_price")
    book = metrics.get("book_value")
    if price and book and book > 0:
        premium = (price / book) - 1
        if premium < 0.25:
            score += 1.0
            reasons.append(
                {
                    "layer": "fundamental",
                    "text": f"Price near/book value support (P/B ~{premium:.0%})",
                    "weight": "medium",
                    "date": as_of,
                    "source": source,
                }
            )

    for field, label, threshold, points in (
        ("roce_pct", "ROCE", 15, 1.5),
        ("roe_pct", "ROE", 15, 1.0),
        ("sales_growth_pct", "Sales growth", 10, 1.0),
        ("profit_growth_pct", "Profit growth", 10, 1.0),
        ("opm_pct", "Operating margin", 15, 1.0),
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
                    "weight": "medium",
                    "date": as_of,
                    "source": source,
                }
            )

    debt = metrics.get("debt_to_eq")
    if debt is not None and debt <= 0.5:
        score += 0.5
        reasons.append(
            {
                "layer": "fundamental",
                "text": f"Low leverage (Debt/Eq {debt})",
                "weight": "medium",
                "date": as_of,
                "source": source,
            }
        )

    settings = get_settings()
    if not reasons and len(metrics) < settings.fundamentals.min_score_metrics:
        return 0.0, reasons

    return round(min(10.0, score), 1), reasons
