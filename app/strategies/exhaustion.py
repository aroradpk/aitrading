from __future__ import annotations

from app.strategies.base import Candidate, rr_prices
import pandas as pd


class ExhaustionReversal:
    name = "exhaustion_reversal"

    def generate(self, row: pd.Series) -> Candidate | None:
        rsi = float(row["rsi_14"])
        close = float(row["close"])
        range_pos = float(row["range_pos"])
        atr_pct = float(row["atr_pct"])
        if pd.isna(rsi) or pd.isna(range_pos) or pd.isna(atr_pct):
            return None
        stop_pct = max(0.85 * atr_pct, 0.005)
        target_pct = 1.25 * stop_pct
        supporting: list[str] = []
        risks: list[str] = ["Reversal against a persistent trend can fail at the open."]
        if rsi <= 28 and range_pos <= 0.25 and float(row["down_days_3"]) >= 2:
            side = "long"
            supporting = [
                f"RSI {rsi:.1f} oversold",
                "Close in lower quartile of the day",
                "At least two down days in last three",
            ]
        elif rsi >= 72 and range_pos >= 0.75 and float(row["up_days_3"]) >= 2:
            side = "short"
            supporting = [
                f"RSI {rsi:.1f} overbought",
                "Close in upper quartile of the day",
                "At least two up days in last three",
            ]
        else:
            return None
        stop, target, rr = rr_prices(close, side, stop_pct, target_pct)
        if side == "long" and float(row.get("nifty_sma_20_dist", 0)) < -0.03:
            risks.append("Nifty is extended below its 20-day average.")
        if side == "short" and float(row.get("nifty_sma_20_dist", 0)) > 0.03:
            risks.append("Nifty is extended above its 20-day average.")
        return Candidate(
            asof_date=row["date"],
            symbol=str(row["symbol"]),
            strategy=self.name,
            side=side,
            entry_price=close,
            stop_price=stop,
            target_price=target,
            reward_risk=rr,
            supporting=supporting,
            risks=risks,
            entry_condition="Buy/sell next session open, fading the prior exhaustion close.",
            invalidation="Setup dies if the next open gaps through the stop or the first hour extends the prior trend without a reversal candle.",
        )
