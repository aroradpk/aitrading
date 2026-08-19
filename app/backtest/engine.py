from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.backtest.costs import CostModel, round_trip_cost
from app.features.technical import regime_label
from app.ml.labels import rebase_levels, simulate_next_session
from app.ml.dataset import next_session_map


@dataclass
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    risk_fraction: float = 0.01
    max_concurrent: int = 3
    cost_model: CostModel | None = None
    min_probability: float = 0.0


def _qty_for_risk(capital: float, fill: float, stop: float, risk_fraction: float) -> float:
    risk_per_unit = abs(fill - stop)
    if risk_per_unit <= 0:
        return 0.0
    rupees = capital * risk_fraction
    return rupees / risk_per_unit


def run_backtest(
    candidates: pd.DataFrame,
    bars: dict[str, pd.DataFrame],
    feature_lookup: pd.DataFrame,
    config: BacktestConfig,
    fold: str = "all",
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    nxt = next_session_map(bars)
    nifty_feat = feature_lookup[feature_lookup["symbol"] == "NIFTY"] if not feature_lookup.empty else feature_lookup
    nifty_by_date = {row.asof_date: row for row in nifty_feat.itertuples(index=False)} if not nifty_feat.empty else {}
    ordered = candidates.sort_values(["asof_date", "probability"] if "probability" in candidates.columns else ["asof_date"]).copy()
    if "probability" in ordered.columns:
        ordered = ordered.sort_values(["asof_date", "probability"], ascending=[True, False])
    capital = config.initial_capital
    cost_model = config.cost_model or CostModel()
    trades = []
    for asof, group in ordered.groupby("asof_date", sort=True):
        picked = []
        for row in group.itertuples(index=False):
            if "probability" in group.columns and float(getattr(row, "probability", 1.0)) < config.min_probability:
                continue
            if len(picked) >= config.max_concurrent:
                break
            if any(item.symbol == row.symbol for item in picked):
                continue
            picked.append(row)
        for row in picked:
            key = (row.symbol, row.asof_date)
            if key not in nxt:
                continue
            session = nxt[key]
            fill = float(session["open"])
            stop, target = rebase_levels(float(row.entry_price), float(row.stop_price), float(row.target_price), fill, row.side)
            qty = _qty_for_risk(capital, fill, stop, config.risk_fraction)
            if qty <= 0:
                continue
            outcome = simulate_next_session(row.side, fill, stop, target, session)
            notional_in = qty * fill
            notional_out = qty * outcome.exit_price
            costs = round_trip_cost(notional_in, notional_out, row.symbol, cost_model)
            gross = qty * (outcome.exit_price - fill) * (1 if row.side == "long" else -1)
            pnl = gross - costs
            capital += pnl
            nifty_row = nifty_by_date.get(row.asof_date)
            regime = regime_label(pd.Series(nifty_row._asdict())) if nifty_row is not None else "unknown"
            trades.append(
                {
                    "fold": fold,
                    "asof_date": row.asof_date,
                    "fill_date": session["date"],
                    "symbol": row.symbol,
                    "strategy": row.strategy,
                    "side": row.side,
                    "entry": fill,
                    "exit": outcome.exit_price,
                    "qty": qty,
                    "pnl": pnl,
                    "pnl_pct": pnl / notional_in if notional_in else 0.0,
                    "costs": costs,
                    "exit_reason": outcome.exit_reason,
                    "regime": regime,
                }
            )
    return pd.DataFrame(trades)
