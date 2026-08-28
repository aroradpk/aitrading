"""Three specialists plus cash. Signals are gated by regime; health is walk-forward only."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

@dataclass
class SpecialistCall:
    name: str
    fire: bool
    reason: str
    oos_hit_rate: float | None
    oos_mean: float | None
    healthy: bool


@dataclass
class SpecialistBoard:
    trend: SpecialistCall
    fade: SpecialistCall
    cash: SpecialistCall
    disagreement: bool


def _walk_forward(
    signal: pd.Series,
    fwd: pd.Series,
    train: int = 252,
    test: int = 21,
    step: int = 21,
) -> tuple[float | None, float | None]:
    aligned = pd.concat({"sig": signal, "fwd": fwd}, axis=1).dropna()
    if len(aligned) < train + test:
        return None, None
    hits = []
    means = []
    start = train
    while start + test <= len(aligned):
        window = aligned.iloc[start : start + test]
        active = window[window["sig"] != 0]
        if len(active) >= 3:
            pnl = np.sign(active["sig"]) * active["fwd"]
            hits.append(float((pnl > 0).mean()))
            means.append(float(pnl.mean()))
        start += step
    if not hits:
        return None, None
    return float(np.mean(hits)), float(np.mean(means))


def evaluate(
    feat: pd.DataFrame,
    regime_frame: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
) -> SpecialistBoard:
    work = feat.join(regime_frame[["state", "high_entropy"]], how="inner")
    if as_of is not None:
        work = work.loc[: pd.Timestamp(as_of)]
    last = work.iloc[-1]
    state = str(last["state"])
    high_ent = bool(last["high_entropy"])

    trend_sig = ((work["dist_ma20"] > 0) & (work["excess_20"] > 0) & (work["state"] == "trend")).astype(int)
    fade_sig = ((work["dist_ma20"] < -0.03) & (work["range_20"] < work["range_20"].rolling(60).median()) & (work["state"] == "chop")).astype(int)
    # walk-forward uses 5d forward of the equity
    th, tm = _walk_forward(trend_sig, work["fwd_5"])
    fh, fm = _walk_forward(fade_sig, work["fwd_5"])

    trend_fire = bool(trend_sig.iloc[-1] == 1 and not high_ent)
    fade_fire = bool(fade_sig.iloc[-1] == 1 and not high_ent)
    trend_healthy = th is not None and th >= 0.52 and (tm or 0) > 0
    fade_healthy = fh is not None and fh >= 0.52 and (fm or 0) > 0

    trend = SpecialistCall(
        name="trend_follow",
        fire=trend_fire,
        reason=f"state={state} dist_ma20={last['dist_ma20']:.3f} excess_20={last['excess_20']:.3f}",
        oos_hit_rate=th,
        oos_mean=tm,
        healthy=bool(trend_healthy),
    )
    fade = SpecialistCall(
        name="fade_oversold",
        fire=fade_fire,
        reason=f"state={state} dist_ma20={last['dist_ma20']:.3f} range_20={last['range_20']:.3f}",
        oos_hit_rate=fh,
        oos_mean=fm,
        healthy=bool(fade_healthy),
    )
    cash_fire = (not trend_fire) or (not trend_healthy) or high_ent
    if fade_fire and fade_healthy and not high_ent:
        cash_fire = False
    if trend_fire and trend_healthy and not high_ent:
        cash_fire = False
    cash = SpecialistCall(
        name="cash",
        fire=cash_fire or high_ent or (not trend_fire and not fade_fire),
        reason="default when specialists gated, unhealthy, or silent",
        oos_hit_rate=None,
        oos_mean=0.0,
        healthy=True,
    )
    disagreement = trend_fire and fade_fire
    return SpecialistBoard(trend=trend, fade=fade, cash=cash, disagreement=disagreement)
