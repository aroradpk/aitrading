#!/usr/bin/env python3
"""Call quality: % correct vs % false alarm for 7 and for 5–7 combined.

Correct for a 7 = |move| ≥ 5% within 3 sessions (the 7 promise).
Correct for 5–7 combined = |move| ≥ 3% next day, and also within 3 sessions.
False alarm = 100% − correct.

Reads the latest scored CSV if present, else prints usage.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

DEFAULT = Path("/opt/cursor/artifacts/prediction_vs_actual_all_days.csv")


def rates(n: int, ok: int) -> str:
    if n == 0:
        return "n=0"
    return f"CORRECT {100 * ok / n:.1f}%   FALSE ALARM {100 * (n - ok) / n:.1f}%   (n={n})"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not path.exists():
        print(f"Missing {path}. Run the prediction-vs-actual eval first.")
        sys.exit(1)
    df = pd.read_csv(path)
    print("How to read: a call is CORRECT if the stock moved at least the promised size.")
    print("False alarm = we flagged it and the move was smaller.\n")

    s7 = df[df.expected == 5]
    print("Score 7  |  promise: ~5% next day     ", rates(len(s7), int((s7.actual_abs >= 5).sum())))
    print("Score 6  |  promise: ~4% next day     ", rates(len(df[df.expected == 4]), int((df[df.expected == 4].actual_abs >= 4).sum())))
    print("Score 5  |  promise: ~3% next day     ", rates(len(df[df.expected == 3]), int((df[df.expected == 3].actual_abs >= 3).sum())))
    g = df[df.expected >= 3]
    print("Scores 5–7 combined | next day ≥3%    ", rates(len(g), int((g.actual_abs >= 3).sum())))
    own_ok = (
        ((g.expected == 5) & (g.actual_abs >= 5))
        | ((g.expected == 4) & (g.actual_abs >= 4))
        | ((g.expected == 3) & (g.actual_abs >= 3))
    ).sum()
    print("Scores 5–7 combined | each own promise", rates(len(g), int(own_ok)))


if __name__ == "__main__":
    main()
