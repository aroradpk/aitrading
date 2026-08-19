from __future__ import annotations

import json

import pandas as pd

from app.backtest.ema_rsi_eval import evaluate_universe
from app.config import get_settings
from app.data.store import Store
from app.strategies.ema_rsi_config import EmaRsiConfig
from app.universe import UNIVERSE


def _jsonable(report: dict) -> dict:
    out = {k: v for k, v in report.items() if k not in {"setups", "trades"}}
    return json.loads(json.dumps(out, default=str))


def run_s1_backtest() -> dict:
    settings = get_settings()
    store = Store(settings.db_path)
    try:
        daily = {}
        m15 = {}
        h1 = {}
        for item in UNIVERSE:
            daily[item.symbol] = store.load_daily(item.symbol)
            if daily[item.symbol].empty:
                raise RuntimeError(f"No daily bars for {item.symbol}")
            try:
                m15[item.symbol] = store.load_tf_bars(item.symbol, "15m")
            except Exception:
                m15[item.symbol] = pd.DataFrame()
            try:
                h1[item.symbol] = store.load_tf_bars(item.symbol, "1h")
            except Exception:
                h1[item.symbol] = pd.DataFrame()
        report = evaluate_universe(daily, m15, h1, EmaRsiConfig(), capital=settings.initial_capital)
        payload = _jsonable(report)
        path = settings.artifact_dir / "s1_backtest_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
        if not report["setups"].empty:
            report["setups"].to_csv(settings.artifact_dir / "s1_setups.csv", index=False)
        if not report["trades"].empty:
            report["trades"].to_csv(settings.artifact_dir / "s1_trades.csv", index=False)
        payload["artifact"] = str(path)
        return payload
    finally:
        store.close()
