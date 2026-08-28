"""Append-only paper journal. Live orders are out of scope."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_PATH = Path("data/journal/paper.csv")
FIELDS = [
    "as_of",
    "ticker",
    "mandate",
    "decision",
    "today",
    "close",
    "override",
    "note",
]


@dataclass
class JournalEntry:
    as_of: date
    ticker: str
    mandate: str
    decision: str
    today: str
    close: float
    override: bool = False
    note: str = ""


def append(entry: JournalEntry, path: Path = DEFAULT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(
            {
                "as_of": entry.as_of.isoformat(),
                "ticker": entry.ticker,
                "mandate": entry.mandate,
                "decision": entry.decision,
                "today": entry.today,
                "close": f"{entry.close:.4f}",
                "override": "1" if entry.override else "0",
                "note": entry.note,
            }
        )
    return path


def load(path: Path = DEFAULT_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))
