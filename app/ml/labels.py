from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class SessionOutcome:
    target_hit_before_stop: int
    exit_reason: str
    pnl_pct: float
    mfe_pct: float
    mae_pct: float
    exit_price: float


def rebase_levels(close_ref: float, stop: float, target: float, fill: float, side: str) -> tuple[float, float]:
    if close_ref <= 0:
        return stop, target
    stop_pct = abs(close_ref - stop) / close_ref
    target_pct = abs(target - close_ref) / close_ref
    if side == "long":
        return fill * (1 - stop_pct), fill * (1 + target_pct)
    return fill * (1 + stop_pct), fill * (1 - target_pct)


def simulate_next_session(
    side: str,
    fill: float,
    stop: float,
    target: float,
    next_bar: pd.Series,
    adverse_first: bool = True,
) -> SessionOutcome:
    high = float(next_bar["high"])
    low = float(next_bar["low"])
    close = float(next_bar["close"])
    if side == "long":
        hit_stop = low <= stop
        hit_target = high >= target
        mfe = (high - fill) / fill
        mae = (low - fill) / fill
        if hit_stop and hit_target:
            reason = "stop" if adverse_first else "target"
        elif hit_stop:
            reason = "stop"
        elif hit_target:
            reason = "target"
        else:
            reason = "close"
        exit_price = {"stop": stop, "target": target, "close": close}[reason]
        pnl = (exit_price - fill) / fill
        hit = 1 if reason == "target" else 0
    else:
        hit_stop = high >= stop
        hit_target = low <= target
        mfe = (fill - low) / fill
        mae = (fill - high) / fill
        if hit_stop and hit_target:
            reason = "stop" if adverse_first else "target"
        elif hit_stop:
            reason = "stop"
        elif hit_target:
            reason = "target"
        else:
            reason = "close"
        exit_price = {"stop": stop, "target": target, "close": close}[reason]
        pnl = (fill - exit_price) / fill
        hit = 1 if reason == "target" else 0
    return SessionOutcome(
        target_hit_before_stop=hit,
        exit_reason=reason,
        pnl_pct=pnl,
        mfe_pct=mfe,
        mae_pct=mae,
        exit_price=exit_price,
    )
