from __future__ import annotations

import pandas as pd

from app.strategies.base import Candidate, rr_prices
from app.universe import BAJFINANCE


class IndexAlignedMomentum:
    name = "index_aligned_momentum"

    def generate(self, row: pd.Series) -> Candidate | None:
        if str(row["symbol"]) != BAJFINANCE.symbol:
            return None
        close = float(row["close"])
        ret5 = float(row["ret_5"])
        rs5 = float(row.get("rs_vs_nifty_5", 0.0))
        nifty = float(row.get("nifty_sma_20_dist", 0.0))
        bank = float(row.get("banknifty_ret_5", 0.0))
        rsi = float(row["rsi_14"])
        atr_pct = float(row["atr_pct"])
        if any(pd.isna(x) for x in (ret5, rs5, nifty, bank, rsi, atr_pct)):
            return None
        stop_pct = max(0.85 * atr_pct, 0.006)
        target_pct = 1.3 * stop_pct
        if ret5 > 0.02 and rs5 > 0.005 and nifty > 0 and bank > 0 and 52 <= rsi <= 68:
            side = "long"
            supporting = [
                "Bajaj Finance 5-day return positive",
                "Outperforming Nifty over 5 days",
                "Nifty above 20-day average and Bank Nifty 5-day return positive",
            ]
            risks = ["Stock-specific news can decouple from index alignment."]
        elif ret5 < -0.02 and rs5 < -0.005 and nifty < 0 and bank < 0 and 32 <= rsi <= 48:
            side = "short"
            supporting = [
                "Bajaj Finance 5-day return negative",
                "Underperforming Nifty over 5 days",
                "Nifty below 20-day average and Bank Nifty 5-day return negative",
            ]
            risks = ["Mean reversion in high-beta names can be violent."]
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
            entry_condition="Enter Bajaj Finance at next open only when Nifty and Bank Nifty agree with the stock's 5-day impulse.",
            invalidation="Invalid if Nifty opens against the aligned side or Bajaj Finance gaps through the stop.",
        )
