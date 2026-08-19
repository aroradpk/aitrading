from __future__ import annotations

import numpy as np
import pandas as pd


def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min()) if len(dd) else 0.0


def _max_losing_streak(pnls: pd.Series) -> int:
    streak = best = 0
    for value in pnls:
        if value < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def summarize_trades(trades: pd.DataFrame, initial_capital: float, start: object | None = None, end: object | None = None) -> dict:
    if trades.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "cagr": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "avg_trade": 0.0,
            "max_losing_streak": 0,
        }
    wins = trades[trades["pnl"] > 0]["pnl"]
    losses = trades[trades["pnl"] < 0]["pnl"]
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(losses.abs().sum()) if len(losses) else 0.0
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    daily = trades.groupby("fill_date", as_index=True)["pnl"].sum().sort_index()
    equity = initial_capital + daily.cumsum()
    days = max((pd.Timestamp(daily.index[-1]) - pd.Timestamp(daily.index[0])).days, 1)
    ending = float(equity.iloc[-1])
    cagr = (ending / initial_capital) ** (365.0 / days) - 1.0 if ending > 0 else -1.0
    ret = daily / initial_capital
    sharpe = float(np.sqrt(252) * ret.mean() / ret.std(ddof=1)) if ret.std(ddof=1) > 0 else 0.0
    return {
        "trades": int(len(trades)),
        "win_rate": float((trades["pnl"] > 0).mean()),
        "expectancy": float(trades["pnl"].mean()),
        "profit_factor": float(profit_factor),
        "cagr": float(cagr),
        "max_drawdown": _max_drawdown(equity),
        "sharpe": sharpe,
        "avg_trade": float(trades["pnl"].mean()),
        "max_losing_streak": _max_losing_streak(trades["pnl"]),
        "ending_equity": ending,
    }


def by_year(trades: pd.DataFrame, initial_capital: float) -> dict[str, dict]:
    if trades.empty:
        return {}
    frame = trades.copy()
    frame["year"] = pd.to_datetime(frame["fill_date"]).dt.year.astype(str)
    return {year: summarize_trades(group, initial_capital) for year, group in frame.groupby("year")}


def by_regime(trades: pd.DataFrame, initial_capital: float) -> dict[str, dict]:
    if trades.empty:
        return {}
    return {regime: summarize_trades(group, initial_capital) for regime, group in trades.groupby("regime")}
