from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pandas as pd

from app.core.config import get_settings
from app.core.paths import backtest_reports_dir, ohlcv_daily_dir
from app.engines.conviction import conviction_from_scores
from app.engines.events import score_events
from app.engines.fundamental import score_fundamentals
from app.engines.move_detector import load_moves, scan_today_setup
from app.engines.themes import score_themes
from app.engines.universe import all_instruments
from app.ingest.yfinance_client import load_ohlcv


def _forward_return(frame: pd.DataFrame, idx: int, days: int) -> float | None:
    if idx + days >= len(frame):
        return None
    entry = float(frame.iloc[idx]["close"])
    exit_close = float(frame.iloc[idx + days]["close"])
    return round((exit_close / entry - 1) * 100, 2)


def _moves_before(moves: list[dict], as_of: str) -> list[dict]:
    return [move for move in moves if move.get("date", "") < as_of]


def _conviction_bucket(conviction: float) -> str:
    if conviction >= 9:
        return "9-10"
    if conviction >= 8:
        return "8-9"
    if conviction >= 7:
        return "7-8"
    return "<7"


def _score_layers_cached(
    symbol: str,
    instrument_type: str,
    as_of: date,
    cache: dict[str, tuple[float, float, float]],
) -> tuple[float, float, float]:
    if instrument_type != "stock":
        return 0.0, 0.0, 0.0
    static = cache.get(symbol)
    if static is None:
        fundamental, _ = score_fundamentals(symbol)
        theme, _, _ = score_themes(symbol)
        static = (fundamental, theme)
        cache[symbol] = static
    fundamental, theme = static
    events, _ = score_events(symbol, as_of=as_of)
    return fundamental, events, theme


def _evaluate_signal(
    frame: pd.DataFrame,
    idx: int,
    *,
    symbol: str,
    instrument_type: str,
    historical_moves: list[dict],
    conviction_min: float,
    layer_cache: dict[str, tuple[float, float, float]],
) -> dict | None:
    as_of = frame.index[idx].date().isoformat()
    frame_slice = frame.iloc[: idx + 1]
    moves_before = _moves_before(historical_moves, as_of)
    setup = scan_today_setup(frame_slice, moves_before)

    as_of_date = frame.index[idx].date()
    fundamental = events = theme = 0.0
    if instrument_type == "stock":
        fundamental, events, theme = _score_layers_cached(
            symbol, instrument_type, as_of_date, layer_cache
        )

    scores = conviction_from_scores(
        technical=setup["technical_score"],
        fundamental=fundamental,
        events=events,
        theme=theme,
    )
    conviction = scores["final"]
    if conviction < conviction_min:
        return None

    settings = get_settings()
    bt = settings.backtest
    if instrument_type == "index":
        target_1d = bt.index_target_1d_pct
        target_1w = None
        fwd_1d = _forward_return(frame, idx, bt.forward_days_1d)
        fwd_1w = None
        hit_1d = fwd_1d is not None and fwd_1d >= target_1d
        hit_1w = None
    else:
        target_1d = bt.stock_target_1d_pct
        target_1w = bt.stock_target_1w_pct
        fwd_1d = _forward_return(frame, idx, bt.forward_days_1d)
        fwd_1w = _forward_return(frame, idx, bt.forward_days_1w)
        hit_1d = fwd_1d is not None and fwd_1d >= target_1d
        hit_1w = fwd_1w is not None and fwd_1w >= target_1w

    return {
        "symbol": symbol,
        "date": as_of,
        "instrument_type": instrument_type,
        "conviction": conviction,
        "scores": scores,
        "match_count": setup["match_count"],
        "entry_close": round(float(frame.iloc[idx]["close"]), 2),
        "fwd_1d_pct": fwd_1d,
        "fwd_1w_pct": fwd_1w,
        "target_1d_pct": target_1d,
        "target_1w_pct": target_1w,
        "hit_1d": hit_1d,
        "hit_1w": hit_1w,
    }


def _aggregate_summary(signals: list[dict]) -> dict:
    if not signals:
        return {
            "signals": 0,
            "hit_1d_rate": None,
            "hit_1w_rate": None,
            "avg_fwd_1d_pct": None,
            "avg_fwd_1w_pct": None,
            "by_conviction_bucket": {},
        }

    stock_signals = [s for s in signals if s.get("instrument_type") == "stock"]
    index_signals = [s for s in signals if s.get("instrument_type") == "index"]

    def hit_rate(items: list[dict], key: str) -> float | None:
        vals = [item[key] for item in items if item.get(key) is not None]
        if not vals:
            return None
        return round(sum(1 for v in vals if v) / len(vals), 3)

    def avg_fwd(items: list[dict], key: str) -> float | None:
        vals = [item[key] for item in items if item.get(key) is not None]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 2)

    buckets: dict[str, dict] = {}
    for signal in signals:
        bucket = _conviction_bucket(signal["conviction"])
        if bucket not in buckets:
            buckets[bucket] = {"signals": 0, "hit_1d": 0, "hit_1w": 0, "hit_1d_total": 0, "hit_1w_total": 0}
        buckets[bucket]["signals"] += 1
        if signal.get("hit_1d") is not None:
            buckets[bucket]["hit_1d_total"] += 1
            buckets[bucket]["hit_1d"] += int(signal["hit_1d"])
        if signal.get("hit_1w") is not None:
            buckets[bucket]["hit_1w_total"] += 1
            buckets[bucket]["hit_1w"] += int(signal["hit_1w"])

    by_bucket: dict[str, dict] = {}
    for bucket, stats in buckets.items():
        by_bucket[bucket] = {
            "signals": stats["signals"],
            "hit_1d_rate": round(stats["hit_1d"] / stats["hit_1d_total"], 3)
            if stats["hit_1d_total"]
            else None,
            "hit_1w_rate": round(stats["hit_1w"] / stats["hit_1w_total"], 3)
            if stats["hit_1w_total"]
            else None,
        }

    return {
        "signals": len(signals),
        "stock_signals": len(stock_signals),
        "index_signals": len(index_signals),
        "hit_1d_rate": hit_rate(signals, "hit_1d"),
        "hit_1w_rate": hit_rate(stock_signals, "hit_1w"),
        "avg_fwd_1d_pct": avg_fwd(signals, "fwd_1d_pct"),
        "avg_fwd_1w_pct": avg_fwd(stock_signals, "fwd_1w_pct"),
        "by_conviction_bucket": by_bucket,
    }


def run_backtest() -> dict:
    settings = get_settings()
    bt = settings.backtest
    generated_at = datetime.now(timezone.utc).isoformat()
    all_signals: list[dict] = []
    layer_cache: dict[str, tuple[float, float, float]] = {}

    for instrument in all_instruments():
        symbol = instrument["symbol"]
        instrument_type = instrument.get("type", "stock")
        path = ohlcv_daily_dir() / f"{symbol}.parquet"
        if not path.exists():
            continue

        frame = load_ohlcv(path)
        if len(frame) < 40:
            continue

        historical_moves = load_moves(symbol)
        last_signal_idx = -bt.signal_cooldown_days - 1

        max_idx = len(frame) - bt.forward_days_1w - 1
        for idx in range(30, max_idx):
            signal = _evaluate_signal(
                frame,
                idx,
                symbol=symbol,
                instrument_type=instrument_type,
                historical_moves=historical_moves,
                conviction_min=bt.conviction_min,
                layer_cache=layer_cache,
            )
            if signal is None:
                continue
            if idx - last_signal_idx < bt.signal_cooldown_days:
                continue
            all_signals.append(signal)
            last_signal_idx = idx

    all_signals.sort(key=lambda item: (item["date"], item["symbol"]), reverse=True)
    summary = _aggregate_summary(all_signals)

    payload = {
        "run_id": generated_at,
        "generated_at": generated_at,
        "config": {
            "conviction_min": bt.conviction_min,
            "signal_cooldown_days": bt.signal_cooldown_days,
            "stock_target_1d_pct": bt.stock_target_1d_pct,
            "stock_target_1w_pct": bt.stock_target_1w_pct,
            "index_target_1d_pct": bt.index_target_1d_pct,
            "note": (
                "Walk-forward technical + events (as_of). "
                "Fundamental/theme use current data (static overlay)."
            ),
        },
        "summary": summary,
        "signals": all_signals,
    }

    root = backtest_reports_dir()
    latest = root / "latest.json"
    stamped = root / f"{generated_at.replace(':', '-').replace('+00:00', 'Z')}.json"
    for path in (latest, stamped):
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_latest_backtest() -> dict | None:
    path = backtest_reports_dir() / "latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
