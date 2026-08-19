from __future__ import annotations

import pandas as pd

from app.strategies.base import Candidate, rr_prices


class VolatilityCompression:
    name = "volatility_compression"

    def generate(self, row: pd.Series) -> Candidate | None:
        close = float(row["close"])
        atr_p = float(row.get("atr_percentile_60", 1.0))
        range_pos = float(row["range_pos"])
        rsi = float(row["rsi_14"])
        atr_pct = float(row["atr_pct"])
        if any(pd.isna(x) for x in (atr_p, range_pos, rsi, atr_pct)):
            return None
        if atr_p > 0.25:
            return None
        stop_pct = max(0.9 * atr_pct, 0.005)
        target_pct = 1.4 * stop_pct
        if range_pos >= 0.7 and rsi >= 55:
            side = "long"
            supporting = [
                f"60-day ATR percentile {atr_p:.2f} (compressed)",
                "Close near the high of a tight range",
                "RSI supports upside expansion",
            ]
            risks = ["Compression can resolve opposite the close."]
        elif range_pos <= 0.3 and rsi <= 45:
            side = "short"
            supporting = [
                f"60-day ATR percentile {atr_p:.2f} (compressed)",
                "Close near the low of a tight range",
                "RSI supports downside expansion",
            ]
            risks = ["A squeeze higher is common after quiet selling."]
        else:
            return None
        stop, target, rr = rr_prices(close, side, stop_pct, target_pct)
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
            entry_condition="Enter next open in the direction of the compressed close, expecting range expansion.",
            invalidation="Invalid if the next session remains inside yesterday's range through the first hour.",
        )
