from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.strategies.base import Candidate
from app.strategies.ema_rsi_config import EmaRsiConfig
from app.strategies.ema_rsi_indicators import add_s1_columns


@dataclass
class DailySetup:
    asof_date: date
    symbol: str
    side: str
    grade: str
    close: float
    atr: float
    stop: float
    target: float
    reward_risk: float
    day_low: float
    day_high: float
    supporting: list[str]
    risks: list[str]
    confirm_1h: bool | None
    confirm_15m: bool | None
    row: pd.Series


def planned_stop_target(
    side: str,
    entry: float,
    atr: float,
    setup_low: float,
    setup_high: float,
    cfg: EmaRsiConfig,
) -> tuple[float, float, float]:
    atr_stop = entry - cfg.sl_atr * atr if side == "long" else entry + cfg.sl_atr * atr
    struct = (
        setup_low - cfg.structure_buffer_atr * atr
        if side == "long"
        else setup_high + cfg.structure_buffer_atr * atr
    )
    if cfg.stop_mode == "structure":
        stop = struct
    elif cfg.stop_mode == "tighter":
        stop = max(atr_stop, struct) if side == "long" else min(atr_stop, struct)
    elif cfg.stop_mode == "wider":
        stop = min(atr_stop, struct) if side == "long" else max(atr_stop, struct)
    else:
        stop = atr_stop
    risk = abs(entry - stop)
    if cfg.tp_mode == "atr":
        target = entry + cfg.tp_atr * atr if side == "long" else entry - cfg.tp_atr * atr
    elif cfg.tp_mode == "pct":
        target = entry * (1 + cfg.tp_pct) if side == "long" else entry * (1 - cfg.tp_pct)
    else:
        target = entry + cfg.rr * risk if side == "long" else entry - cfg.rr * risk
    rr = abs(target - entry) / risk if risk else 0.0
    return stop, target, rr


def long_mask(x: pd.DataFrame, cfg: EmaRsiConfig) -> pd.Series:
    stacked = x["ema_20"] >= x["ema_50"]
    slope = x["ema20_slope_atr"] >= cfg.min_slope_atr
    accel = x["ema20_accel_atr"] >= cfg.min_accel_atr
    spread = x["ema_spread_atr"] >= cfg.min_spread_atr
    expand = x["ema_spread_exp_atr"] >= cfg.min_spread_exp_atr
    rsi_ok = x["rsi_cross_up_60"] & x["rsi_persist_below_60"] & (x["rsi_delta"] >= cfg.min_rsi_delta)
    ema50_ok = (x["ema50_slope_atr"] >= 0) if cfg.require_ema50_slope_agree else True
    return stacked & slope & accel & spread & expand & rsi_ok & ema50_ok


def short_mask(x: pd.DataFrame, cfg: EmaRsiConfig) -> pd.Series:
    stacked = x["ema_20"] <= x["ema_50"]
    slope = x["ema20_slope_atr"] <= -cfg.min_slope_atr
    accel = x["ema20_accel_atr"] <= -cfg.min_accel_atr
    spread = x["ema_spread_atr"] <= -cfg.min_spread_atr
    expand = x["ema_spread_exp_atr"] <= -cfg.min_spread_exp_atr
    rsi_ok = x["rsi_cross_down_40"] & x["rsi_persist_above_40"] & (x["rsi_delta"] <= -cfg.min_rsi_delta)
    price_ok = (x["close"] < x["ema_50"]) if cfg.require_price_below_ema50_short else True
    ema50_ok = (x["ema50_slope_atr"] <= 0) if cfg.require_ema50_slope_agree else True
    return stacked & slope & accel & spread & expand & rsi_ok & price_ok & ema50_ok


def _strong_long(row: pd.Series, cfg: EmaRsiConfig) -> bool:
    m = cfg.strong_mult
    return bool(
        row["ema20_slope_atr"] >= m * cfg.min_slope_atr
        and row["ema20_accel_atr"] >= m * max(cfg.min_accel_atr, 0.01)
        and row["ema_spread_exp_atr"] >= m * cfg.min_spread_exp_atr
    )


def _strong_short(row: pd.Series, cfg: EmaRsiConfig) -> bool:
    m = cfg.strong_mult
    return bool(
        row["ema20_slope_atr"] <= -m * cfg.min_slope_atr
        and row["ema20_accel_atr"] <= -m * max(cfg.min_accel_atr, 0.01)
        and row["ema_spread_exp_atr"] <= -m * cfg.min_spread_exp_atr
    )


def classify_grade(
    side: str,
    row: pd.Series,
    cfg: EmaRsiConfig,
    confirm_1h: bool | None,
    confirm_15m: bool | None,
) -> str:
    """Lower timeframes cannot create a setup. Disagreement only caps the grade."""
    strong_1d = _strong_long(row, cfg) if side == "long" else _strong_short(row, cfg)
    h1 = confirm_1h is True
    m15 = confirm_15m is True
    if strong_1d and h1 and m15:
        return "Strong Setup"
    if strong_1d or h1:
        return "Confirmed Setup"
    return "Early Setup"


def htf_structure_agrees(htf_row: pd.Series | None, side: str) -> bool | None:
    if htf_row is None or pd.isna(htf_row.get("ema_20")) or pd.isna(htf_row.get("ema_50")):
        return None
    if side == "long":
        return bool(htf_row["ema_20"] >= htf_row["ema_50"] and htf_row.get("ema_spread_exp_atr", 0) >= 0)
    return bool(htf_row["ema_20"] <= htf_row["ema_50"] and htf_row.get("ema_spread_exp_atr", 0) <= 0)


def detect_daily_setups(
    frame: pd.DataFrame,
    symbol: str,
    cfg: EmaRsiConfig | None = None,
    htf_1h_by_date: dict | None = None,
    htf_15m_by_date: dict | None = None,
) -> list[DailySetup]:
    cfg = cfg or EmaRsiConfig()
    x = add_s1_columns(frame, cfg)
    longs = long_mask(x, cfg).fillna(False)
    shorts = short_mask(x, cfg).fillna(False)
    found: list[DailySetup] = []
    h1map = htf_1h_by_date or {}
    m15map = htf_15m_by_date or {}
    for idx in x.index[longs | shorts]:
        row = x.loc[idx]
        side = "long" if bool(longs.loc[idx]) else "short"
        asof = row["date"]
        c1 = htf_structure_agrees(h1map.get(asof), side) if cfg.use_1h_confirm else None
        c15 = htf_structure_agrees(m15map.get(asof), side) if cfg.use_15m_confirm else None
        grade = classify_grade(side, row, cfg, c1, c15)
        stop, target, rr = planned_stop_target(
            side, float(row["close"]), float(row["atr_14"]), float(row["low"]), float(row["high"]), cfg
        )
        supporting = [
            f"EMA20 {'>=' if side == 'long' else '<='} EMA50",
            f"spread_atr={float(row['ema_spread_atr']):.3f} exp={float(row['ema_spread_exp_atr']):.3f}",
            f"ema20_slope_atr={float(row['ema20_slope_atr']):.3f} accel={float(row['ema20_accel_atr']):.3f}",
            f"RSI {float(row['rsi_14']):.1f} cross with persist {cfg.rsi_persist_bars} bars",
        ]
        risks = ["1D setup only; next-day 15m bounce is still required to enter."]
        if c1 is False:
            risks.append("1H structure does not agree (grade capped, 1D not cancelled).")
        if c15 is False:
            risks.append("15m structure does not agree (grade capped, 1D not cancelled).")
        found.append(
            DailySetup(
                asof_date=asof,
                symbol=symbol,
                side=side,
                grade=grade,
                close=float(row["close"]),
                atr=float(row["atr_14"]),
                stop=stop,
                target=target,
                reward_risk=rr,
                day_low=float(row["low"]),
                day_high=float(row["high"]),
                supporting=supporting,
                risks=risks,
                confirm_1h=c1,
                confirm_15m=c15,
                row=row,
            )
        )
    return found


class EmaRsiExpansion:
    name = "ema_rsi_expansion"

    def __init__(self, cfg: EmaRsiConfig | None = None) -> None:
        self.cfg = cfg or EmaRsiConfig()

    def generate(self, row: pd.Series) -> Candidate | None:
        frame = pd.DataFrame([row])
        if "ema_50" not in frame.columns or pd.isna(row.get("ema_50")):
            return None
        # Single-row generate cannot compute persistence; scanner uses detect on full frames.
        setup_rows = detect_daily_setups(frame, str(row.get("symbol", "")), self.cfg)
        if not setup_rows:
            return None
        setup = setup_rows[0]
        return _candidate_from_setup(setup, self.cfg)


def _candidate_from_setup(setup: DailySetup, cfg: EmaRsiConfig) -> Candidate:
    bounce = cfg.ltf_rsi_long_pullback if setup.side == "long" else cfg.ltf_rsi_short_rally
    return Candidate(
        asof_date=setup.asof_date,
        symbol=setup.symbol,
        strategy="ema_rsi_expansion",
        side=setup.side,
        entry_price=setup.close,
        stop_price=setup.stop,
        target_price=setup.target,
        reward_risk=setup.reward_risk,
        supporting=setup.supporting + [f"grade={setup.grade}"],
        risks=setup.risks,
        entry_condition=(
            f"Do not enter at the next open. Wait for 15m RSI to {('dip to ~' + str(bounce) + ' then reclaim') if setup.side == 'long' else 'rally to ~' + str(bounce) + ' then reject'} "
            f"with a confirming candle. 1D RSI must still be on the setup side."
        ),
        invalidation="Failed if next day 1D RSI loses 60/40 or 15m never confirms the bounce/rejection before the close.",
    )


def setups_to_candidates(setups: list[DailySetup], cfg: EmaRsiConfig | None = None) -> list[Candidate]:
    cfg = cfg or EmaRsiConfig()
    return [_candidate_from_setup(item, cfg) for item in setups]
