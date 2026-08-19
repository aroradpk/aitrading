from __future__ import annotations

import pandas as pd

from app.strategies.base import Candidate, rr_prices


class TrendPullback:
    name = "trend_pullback"

    def generate(self, row: pd.Series) -> Candidate | None:
        close = float(row["close"])
        sma20 = float(row.get("sma_20_dist", 0))
        sma50 = float(row.get("sma_50_dist", 0))
        ema_dist = float(row.get("ema_20_dist", 0))
        rsi = float(row["rsi_14"])
        atr_pct = float(row["atr_pct"])
        if any(pd.isna(x) for x in (sma20, sma50, ema_dist, rsi, atr_pct)):
            return None
        stop_pct = max(0.8 * atr_pct, 0.004)
        target_pct = 1.3 * stop_pct
        if sma50 > 0.005 and -0.012 <= ema_dist <= 0.004 and 42 <= rsi <= 58:
            side = "long"
            supporting = [
                "Close holds above the 50-day average",
                "Pullback into the 20-day EMA band",
                f"RSI {rsi:.1f} mid-range, not exhausted",
            ]
            risks = ["A failed bounce can turn the pullback into a breakdown."]
        elif sma50 < -0.005 and -0.004 <= ema_dist <= 0.012 and 42 <= rsi <= 58:
            side = "short"
            supporting = [
                "Close holds below the 50-day average",
                "Rally into the 20-day EMA band",
                f"RSI {rsi:.1f} mid-range, not exhausted",
            ]
            risks = ["A squeeze through the EMA can run against the short."]
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
            entry_condition="Enter at next open in the direction of the 50-day trend after the pullback close.",
            invalidation="Invalid if next open trades through the 50-day average against the setup.",
        )
