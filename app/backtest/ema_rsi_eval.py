from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.backtest.costs import CostModel, round_trip_cost
from app.backtest.metrics import by_regime, by_year, summarize_trades
from app.features.technical import regime_label
from app.strategies.ema_rsi_config import EmaRsiConfig
from app.strategies.ema_rsi_entry import find_next_day_entry, simulate_same_day
from app.strategies.ema_rsi_expansion import DailySetup, detect_daily_setups, planned_stop_target
from app.strategies.ema_rsi_indicators import add_s1_columns, last_bar_by_session
from app.universe import NIFTY, UNIVERSE


def _next_date(dates: list[date], current: date) -> date | None:
    later = [d for d in dates if d > current]
    return later[0] if later else None


def daily_hit_target_before_stop(side: str, fill: float, stop: float, target: float, bar: pd.Series) -> dict:
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    if side == "long":
        mfe_pct = (high - fill) / fill
        mae_pct = (low - fill) / fill
        hit_stop = low <= stop
        hit_tgt = high >= target
        pnl_close = (close - fill) / fill
    else:
        mfe_pct = (fill - low) / fill
        mae_pct = (fill - high) / fill
        hit_stop = high >= stop
        hit_tgt = low <= target
        pnl_close = (fill - close) / fill
    if hit_stop and hit_tgt:
        reason = "stop"
        hit = 0
    elif hit_stop:
        reason = "stop"
        hit = 0
    elif hit_tgt:
        reason = "target"
        hit = 1
    else:
        reason = "close"
        hit = 0
    return {"hit_target": hit, "reason": reason, "mfe_pct": mfe_pct, "mae_pct": mae_pct, "close_pnl_pct": pnl_close}


def setup_quality_row(setup: DailySetup, next_bar: pd.Series, cfg: EmaRsiConfig) -> dict:
    atr = setup.atr
    fill = float(next_bar["open"])
    if setup.side == "long":
        mfe_atr = (float(next_bar["high"]) - setup.close) / atr
        mae_atr = (float(next_bar["low"]) - setup.close) / atr
        mfe_pct_from_close = (float(next_bar["high"]) - setup.close) / setup.close
    else:
        mfe_atr = (setup.close - float(next_bar["low"])) / atr
        mae_atr = (setup.close - float(next_bar["high"])) / atr
        mfe_pct_from_close = (setup.close - float(next_bar["low"])) / setup.close
    stop, target_08, _ = planned_stop_target(
        setup.side, fill, setup.atr, setup.day_low, setup.day_high, cfg
    )
    # Force 0.8% target for this scorecard even if cfg uses a different tp_mode.
    target_08 = fill * (1 + cfg.setup_success_pct) if setup.side == "long" else fill * (1 - cfg.setup_success_pct)
    outcome_08 = daily_hit_target_before_stop(setup.side, fill, stop, target_08, next_bar)
    return {
        "setup_success": int(mfe_atr >= cfg.setup_success_mfe_atr),
        "setup_mfe_atr": float(mfe_atr),
        "setup_mae_atr": float(mae_atr),
        "setup_mfe_pct": float(mfe_pct_from_close),
        "hit_0_8_mfe_from_close": int(mfe_pct_from_close >= cfg.setup_success_pct),
        "next_open": fill,
        "hit_0_8_from_next_open_before_sl": outcome_08["hit_target"],
        "next_open_0_8_reason": outcome_08["reason"],
        "next_open_mfe_pct": outcome_08["mfe_pct"],
    }


def evaluate_symbol(
    daily: pd.DataFrame,
    symbol: str,
    bars_15m: pd.DataFrame,
    bars_1h: pd.DataFrame,
    cfg: EmaRsiConfig,
    capital: float = 1_000_000.0,
    risk_fraction: float = 0.01,
    regime_daily: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    h1_map = last_bar_by_session(bars_1h, cfg) if bars_1h is not None and not bars_1h.empty else {}
    m15_map = last_bar_by_session(bars_15m, cfg) if bars_15m is not None and not bars_15m.empty else {}
    annotated_1h = add_s1_columns(bars_1h, cfg) if bars_1h is not None and not bars_1h.empty else None
    setups = detect_daily_setups(daily, symbol, cfg, h1_map, m15_map)
    dates = sorted(daily["date"].tolist())
    closes = {row.date: float(row.close) for row in daily.itertuples(index=False)}
    close_list = [closes[d] for d in dates]
    close_by_date = {d: i for i, d in enumerate(dates)}
    nifty_proxy = add_s1_columns(regime_daily if regime_daily is not None else daily, cfg)
    nifty_proxy["ret_5"] = nifty_proxy["close"].pct_change(5)
    nifty_proxy["vol_20"] = nifty_proxy["close"].pct_change().rolling(20).std()
    setup_rows = []
    trade_rows = []
    for setup in setups:
        nxt = _next_date(dates, setup.asof_date)
        if nxt is None:
            continue
        next_bar = daily[daily["date"] == nxt].iloc[0]
        quality = setup_quality_row(setup, next_bar, cfg)
        idx = close_by_date[setup.asof_date]
        daily_closes = close_list[: idx + 1]
        session = pd.DataFrame()
        if bars_15m is not None and not bars_15m.empty:
            entry = find_next_day_entry(setup, bars_15m, nxt, daily_closes, annotated_1h, cfg)
            if "session_date" in bars_15m.columns:
                session = bars_15m[bars_15m["session_date"] == nxt]
        else:
            entry = find_next_day_entry(setup, pd.DataFrame(), nxt, daily_closes, annotated_1h, cfg)
        nifty_row = nifty_proxy[nifty_proxy["date"] == setup.asof_date]
        regime = regime_label(nifty_row.iloc[0]) if not nifty_row.empty else "unknown"
        setup_rows.append(
            {
                "asof_date": setup.asof_date,
                "fill_date": nxt,
                "symbol": symbol,
                "side": setup.side,
                "grade": setup.grade,
                "confirm_1h": setup.confirm_1h,
                "confirm_15m": setup.confirm_15m,
                "entered": int(entry.entered),
                "failed_before_entry": int(entry.failed_before_entry),
                "entry_reason": entry.reason,
                "confirm_tf": entry.confirm_tf,
                "regime": regime,
                **quality,
            }
        )
        if not entry.entered:
            continue
        path = session if not session.empty else pd.DataFrame(
            [{"ts": None, "open": next_bar.open, "high": next_bar.high, "low": next_bar.low, "close": next_bar.close}]
        )
        sim = simulate_same_day(setup.side, entry.entry_price, entry.stop, entry.target, path, entry.entry_ts)
        risk = abs(entry.entry_price - entry.stop)
        qty = (capital * risk_fraction) / risk if risk else 0.0
        notional_in = qty * entry.entry_price
        notional_out = qty * sim["exit"]
        costs = round_trip_cost(notional_in, notional_out, symbol, CostModel())
        gross = qty * (sim["exit"] - entry.entry_price) * (1 if setup.side == "long" else -1)
        pnl = gross - costs
        r_mult = (pnl / (qty * risk)) if qty and risk else 0.0
        trade_rows.append(
            {
                "asof_date": setup.asof_date,
                "fill_date": nxt,
                "symbol": symbol,
                "strategy": "ema_rsi_expansion",
                "side": setup.side,
                "grade": setup.grade,
                "entry": entry.entry_price,
                "exit": sim["exit"],
                "qty": qty,
                "pnl": pnl,
                "pnl_pct": pnl / notional_in if notional_in else 0.0,
                "costs": costs,
                "exit_reason": sim["reason"],
                "regime": regime,
                "r_multiple": r_mult,
                "mfe": sim["mfe"],
                "mae": sim["mae"],
                "hit_target": sim["hit_target"],
                "confirm_tf": entry.confirm_tf,
            }
        )
    return pd.DataFrame(setup_rows), pd.DataFrame(trade_rows)


def evaluate_universe(
    daily_frames: dict[str, pd.DataFrame],
    m15_frames: dict[str, pd.DataFrame],
    h1_frames: dict[str, pd.DataFrame],
    cfg: EmaRsiConfig | None = None,
    capital: float = 1_000_000.0,
) -> dict:
    cfg = cfg or EmaRsiConfig()
    setups = []
    trades = []
    for item in UNIVERSE:
        s, t = evaluate_symbol(
            daily_frames[item.symbol],
            item.symbol,
            m15_frames.get(item.symbol, pd.DataFrame()),
            h1_frames.get(item.symbol, pd.DataFrame()),
            cfg,
            capital=capital,
            regime_daily=daily_frames[NIFTY.symbol],
        )
        setups.append(s)
        trades.append(t)
    setup_df = pd.concat([x for x in setups if not x.empty], ignore_index=True) if any(len(x) for x in setups) else pd.DataFrame()
    trade_df = pd.concat([x for x in trades if not x.empty], ignore_index=True) if any(len(x) for x in trades) else pd.DataFrame()
    n_setup = len(setup_df)
    n_confirm = int((setup_df["grade"].isin(["Confirmed Setup", "Strong Setup"])).sum()) if n_setup else 0
    n_entry = int(setup_df["entered"].sum()) if n_setup else 0
    trade_metrics = summarize_trades(trade_df, capital) if not trade_df.empty else summarize_trades(pd.DataFrame(), capital)
    if not trade_df.empty:
        trade_metrics["avg_r"] = float(trade_df["r_multiple"].mean())
        trade_metrics["avg_mfe"] = float(trade_df["mfe"].mean())
        trade_metrics["avg_mae"] = float(trade_df["mae"].mean())
        trade_metrics["win_rate_target_before_sl"] = float(trade_df["hit_target"].mean())
    setup_metrics = {
        "setups": n_setup,
        "setup_frequency_per_symbol_year": None,
        "confirmation_rate": n_confirm / n_setup if n_setup else 0.0,
        "entry_rate": n_entry / n_setup if n_setup else 0.0,
        "setup_success_rate": float(setup_df["setup_success"].mean()) if n_setup else 0.0,
        "hit_0_8_mfe_from_close_rate": float(setup_df["hit_0_8_mfe_from_close"].mean()) if n_setup else 0.0,
        "hit_0_8_from_next_open_before_sl_rate": float(setup_df["hit_0_8_from_next_open_before_sl"].mean())
        if n_setup
        else 0.0,
        "signals_with_15m_next_day": int((~setup_df["entry_reason"].isin(["no_15m_data", "no_15m_session"])).sum())
        if n_setup
        else 0,
        "entry_reason_counts": setup_df["entry_reason"].value_counts().to_dict() if n_setup else {},
        "setup_success_long": float(setup_df.loc[setup_df["side"] == "long", "setup_success"].mean())
        if n_setup and (setup_df["side"] == "long").any()
        else None,
        "setup_success_short": float(setup_df.loc[setup_df["side"] == "short", "setup_success"].mean())
        if n_setup and (setup_df["side"] == "short").any()
        else None,
        "by_symbol": setup_df.groupby("symbol")["setup_success"].mean().to_dict() if n_setup else {},
        "by_year": setup_df.assign(year=pd.to_datetime(setup_df["asof_date"]).dt.year.astype(str))
        .groupby("year")["setup_success"]
        .mean()
        .to_dict()
        if n_setup
        else {},
        "by_regime": setup_df.groupby("regime")["setup_success"].mean().to_dict() if n_setup else {},
        "by_grade": setup_df.groupby("grade")["setup_success"].agg(["count", "mean"]).to_dict() if n_setup else {},
    }
    if n_setup:
        years = max((pd.to_datetime(setup_df["asof_date"]).max() - pd.to_datetime(setup_df["asof_date"]).min()).days / 365.25, 1 / 12)
        setup_metrics["setup_frequency_per_symbol_year"] = n_setup / (len(UNIVERSE) * years)
    trade_split = {}
    if not trade_df.empty:
        trade_split["long"] = summarize_trades(trade_df[trade_df["side"] == "long"], capital)
        trade_split["short"] = summarize_trades(trade_df[trade_df["side"] == "short"], capital)
        trade_split["by_year"] = by_year(trade_df, capital)
        trade_split["by_regime"] = by_regime(trade_df, capital)
        trade_split["by_symbol"] = {
            sym: summarize_trades(group, capital) for sym, group in trade_df.groupby("symbol")
        }
        trade_split["by_grade"] = {
            grade: summarize_trades(group, capital) for grade, group in trade_df.groupby("grade")
        }
        trade_split["by_confirm_tf"] = {
            tf: summarize_trades(group, capital) for tf, group in trade_df.groupby("confirm_tf")
        }
    return {
        "config": cfg.as_dict(),
        "note": "Setup quality (A) and trade quality (B) are separate. 15m Yahoo history is short; missing 15m means no entry, not a losing trade.",
        "setup_quality": setup_metrics,
        "trade_quality": trade_metrics,
        "trade_splits": trade_split,
        "setups": setup_df,
        "trades": trade_df,
    }
