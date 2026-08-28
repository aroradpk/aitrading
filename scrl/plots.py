from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from scrl.pipeline import AnalysisResult


def save_analog_histogram(result: AnalysisResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fwd = result.analogs.neighbors["fwd_10"] if result.analogs.n else pd.Series(dtype=float)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    if len(fwd):
        axes[0].hist(fwd * 100, bins=12, color="#1f4e79", edgecolor="white")
    axes[0].axvline(0, color="#c0392b", linewidth=1)
    axes[0].set_title(f"Analog 10d forward returns (n={result.analogs.n})")
    axes[0].set_xlabel("%")
    names = list(result.regime.probabilities.keys())
    vals = [result.regime.probabilities[k] for k in names]
    axes[1].bar(names, vals, color=["#1f4e79", "#7f8c8d", "#c0392b"][: len(names)])
    axes[1].set_ylim(0, 1)
    axes[1].set_title(f"Regime mix  entropy={result.regime.entropy:.2f}")
    fig.suptitle(f"{result.ticker}  {result.as_of.date()}  {result.permission.decision}")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
