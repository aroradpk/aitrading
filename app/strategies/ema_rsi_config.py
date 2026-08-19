from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EmaRsiConfig:
    """All thresholds are defaults to test, not claimed optima."""

    ema_fast: int = 20
    ema_slow: int = 50
    rsi_length: int = 14
    atr_length: int = 14
    slope_bars: int = 3
    spread_bars: int = 3
    min_slope_atr: float = 0.05
    min_accel_atr: float = 0.0
    min_spread_atr: float = 0.05
    min_spread_exp_atr: float = 0.02
    strong_mult: float = 2.0
    rsi_long_level: float = 60.0
    rsi_short_level: float = 40.0
    rsi_persist_bars: int = 5
    min_rsi_delta: float = 2.0
    require_price_below_ema50_short: bool = True
    require_ema50_slope_agree: bool = False
    ltf_rsi_long_pullback: float = 40.0
    ltf_rsi_short_rally: float = 60.0
    price_confirm: str = "bullish_close"  # bullish_close | close_above_prev_high
    enter_next_bar_open: bool = True
    stop_mode: str = "atr"  # atr | structure | tighter | wider
    sl_atr: float = 1.0
    structure_buffer_atr: float = 0.1
    tp_mode: str = "rr"  # rr | atr
    rr: float = 1.5
    tp_atr: float = 1.5
    setup_success_mfe_atr: float = 0.5
    use_1h_confirm: bool = True
    use_15m_confirm: bool = True

    def as_dict(self) -> dict:
        return asdict(self)
