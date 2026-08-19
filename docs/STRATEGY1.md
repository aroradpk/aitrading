# Strategy 1 math (EMA20/EMA50 expansion + RSI momentum)

These are the formulas in code. Every value is as-of the current bar. Defaults are **starting points to test**, not tuned edges.

Primary timeframe is **1D**. 1H and 15m can upgrade the grade. They cannot create a setup if 1D failed.

## EMA

TradingView-style span EMA:

`EMA_n(t) = ewm(close, span=n, adjust=False)` with n = 20 and 50.

## Slope (normalized by ATR)

Over `slope_bars` k (default **3**):

- `ema20_slope_atr = (EMA20(t) - EMA20(t-k)) / ATR(t)`
- `ema50_slope_atr = (EMA50(t) - EMA50(t-k)) / ATR(t)`
- `ema20_slope_pct = EMA20(t)/EMA20(t-1) - 1` (1-bar percent, extra)

LONG needs `ema20_slope_atr >= min_slope_atr` (default **0.05 ATR over 3 days**).
SHORT needs `<= -min_slope_atr`.

## Slope acceleration

- `ema20_accel_atr = ema20_slope_atr(t) - ema20_slope_atr(t-1)`

LONG: `>= min_accel_atr` (default **0** = not flattening).
SHORT: `<= -min_accel_atr`.

That is the quantitative stand-in for “becoming progressively steeper”.

## Spread

- `ema_spread_abs = EMA20 - EMA50`
- `ema_spread_pct = spread_abs / close`
- `ema_spread_atr = spread_abs / ATR`

Expansion over `spread_bars` m (default **3**):

- `ema_spread_exp_atr = spread_atr(t) - spread_atr(t-m)`

LONG: spread_atr >= 0.05 and expansion >= 0.02
SHORT: spread_atr <= -0.05 and expansion <= -0.02

## RSI persistence and crossover

Wilder RSI(14), same as the rest of the engine.

LONG crossover: `RSI(t-1) < 60` and `RSI(t) >= 60`.
Persistence: the previous `rsi_persist_bars` (default **5**) all have RSI **< 60** (`rolling max of t-1..t-P < 60`).
Momentum: `RSI(t) - RSI(t-1) >= min_rsi_delta` (default **2 points**).

SHORT: cross below 40, previous 5 bars all **> 40**, delta <= -2.

SHORT also requires `close < EMA50` by default.

## Setup grades

If 1D rules fail → not a setup (`Failed Setup` is “no candidate”).

If 1D passes:

- **Early Setup**: 1D only, weak/moderate expansion
- **Confirmed Setup**: strong 1D *or* 1H agrees
- **Strong Setup**: strong 1D *and* 1H agrees *and* 15m agrees

If 1H/15m disagree, grade is capped. **1D is not cancelled.**

Strong 1D means slope, accel, and expansion each at least `strong_mult` (default **2x**) the minimums.

## Next-day entry (not the next open)

On T+1, using **forming** daily RSI (completed daily closes through T, plus last traded price as the in-progress daily close):

LONG: forming 1D RSI still > 60; last completed 1H still not against the long stack; 15m RSI prints <= 40 then **crosses back above 40**; confirmation candle is bullish (`close > open` by default). Fill is the **next 15m open**.

SHORT: mirror at 40/60.

15m RSI is computed on the **full 15m history**, then we only take actions on T+1 bars.

## Stops / targets (configurable)

Default: ATR stop `1.0 * ATR(T)`, target `1.5R`.
Also supported: structure stop (beyond T high/low), tighter/wider blend, ATR target.

## Two scorecards

**A. Setup quality** — ignore entry. Success if next day’s MFE in the setup direction is at least `0.5 ATR`.

**B. Trade quality** — only if the 15m bounce actually filled. Target before stop (adverse-first inside a bar), with costs.

Yahoo 15m is only ~60 days, so B has a small sample. Missing 15m = no trade, not a loss.

## Defaults that should be tested, not believed

| Knob | Default |
|---|---|
| slope_bars / spread_bars | 3 |
| min_slope_atr | 0.05 |
| min_accel_atr | 0 |
| min_spread_atr / exp | 0.05 / 0.02 |
| rsi persist | 5 bars |
| min RSI delta | 2 |
| 1D levels | 60 / 40 |
| 15m pullback/reject | 40 / 60 |
| price confirm | bullish/bearish candle |
| fill | next 15m open |
| SL / TP | 1 ATR / 1.5R |
| setup success | 0.5 ATR MFE next day |
