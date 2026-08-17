from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from app.core.config import get_settings
from app.core.paths import technical_charts_dir
from app.engines.technical import build_snapshot


def _ema_series(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi_series(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return pd.to_numeric(rsi, errors="coerce").fillna(50.0)


def chart_path_for_move(symbol: str, move_date: str) -> Path:
    return technical_charts_dir() / symbol / f"{move_date}.png"


def render_move_chart(
    frame: pd.DataFrame,
    move: dict,
    *,
    output_path: Path | None = None,
) -> Path:
    settings = get_settings()
    lookback = int(settings.charts.lookback_bars)
    move_date = pd.Timestamp(move["date"])
    if move_date not in frame.index:
        subset = frame[frame.index <= move_date]
    else:
        subset = frame.loc[:move_date]
    window = subset.tail(lookback).copy()
    if window.empty:
        raise ValueError(f"No OHLCV window for {move['symbol']} on {move['date']}")

    symbol = move["symbol"]
    output_path = output_path or chart_path_for_move(symbol, move["date"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    snapshot = move.get("technical_snapshot") or build_snapshot(subset)
    tags = snapshot.get("tags", [])[:8]
    formations = [f.get("name", f.get("id", "")) for f in snapshot.get("formations", [])][:3]

    ema20 = _ema_series(window["close"], 20)
    ema50 = _ema_series(window["close"], 50)
    ema200 = _ema_series(window["close"], 200)
    rsi = _rsi_series(window["close"])

    support = float(window["low"].min())
    resistance = float(window["high"].max())

    fig, (ax_price, ax_rsi) = plt.subplots(
        2,
        1,
        figsize=(10, 6),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
        facecolor="#0b1220",
    )
    for ax in (ax_price, ax_rsi):
        ax.set_facecolor("#121a2b")
        ax.tick_params(colors="#9fb0d3", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#33415f")

    dates = window.index
    ax_price.plot(dates, window["close"], color="#e8eefc", linewidth=1.4, label="Close")
    ax_price.plot(dates, ema20, color="#3b82f6", linewidth=1.0, label="EMA20")
    ax_price.plot(dates, ema50, color="#f59e0b", linewidth=1.0, label="EMA50")
    ax_price.plot(dates, ema200, color="#a855f7", linewidth=1.0, label="EMA200")
    ax_price.axhline(support, color="#22c55e", linestyle="--", linewidth=0.8, alpha=0.7, label="Support")
    ax_price.axhline(resistance, color="#ef4444", linestyle="--", linewidth=0.8, alpha=0.7, label="Resistance")
    ax_price.scatter([dates[-1]], [window["close"].iloc[-1]], color="#3b82f6", s=40, zorder=5)

    move_1d = move.get("move_1d_pct")
    move_1w = move.get("move_1w_pct")
    title = (
        f"{symbol} — {move['date']} | {move.get('direction', '').upper()} "
        f"| 1D {move_1d}%"
    )
    if move_1w is not None:
        title += f" | 1W {move_1w}%"
    ax_price.set_title(title, color="#e8eefc", fontsize=11, loc="left")
    ax_price.legend(loc="upper left", fontsize=7, facecolor="#121a2b", edgecolor="#33415f", labelcolor="#e8eefc")
    ax_price.set_ylabel("Price", color="#9fb0d3", fontsize=9)
    ax_price.grid(True, color="#24304a", alpha=0.5)

    ax_rsi.plot(dates, rsi, color="#38bdf8", linewidth=1.2)
    ax_rsi.axhline(70, color="#ef4444", linestyle=":", linewidth=0.7, alpha=0.6)
    ax_rsi.axhline(30, color="#22c55e", linestyle=":", linewidth=0.7, alpha=0.6)
    ax_rsi.set_ylim(0, 100)
    ax_rsi.set_ylabel("RSI", color="#9fb0d3", fontsize=9)
    ax_rsi.grid(True, color="#24304a", alpha=0.5)

    annotation_lines = []
    if tags:
        annotation_lines.append("Tags: " + ", ".join(tags))
    if formations:
        annotation_lines.append("Formations: " + ", ".join(formations))
    if snapshot.get("position_bias"):
        annotation_lines.append(f"Bias: {snapshot['position_bias']}")
    if annotation_lines:
        fig.text(
            0.01,
            0.01,
            "\n".join(annotation_lines),
            color="#9fb0d3",
            fontsize=7,
            va="bottom",
            ha="left",
        )

    ax_rsi.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=25)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    fig.savefig(output_path, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def render_charts_for_moves(symbol: str, frame: pd.DataFrame, moves: list[dict]) -> int:
    count = 0
    for move in moves:
        try:
            path = render_move_chart(frame, move)
            move["chart_file"] = f"technical/charts/{symbol}/{path.name}"
            count += 1
        except Exception:
            continue
    return count
