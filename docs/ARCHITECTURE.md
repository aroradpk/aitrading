# Architecture

This engine ranks **next-day intraday** setups after the NSE close. It is a research system. A strategy is not treated as profitable until walk-forward and out-of-sample metrics say so.

Current universe (point-in-time fixed list, not a scanned NSE membership series):

| Instrument | Kind | Yahoo ticker |
|---|---|---|
| Nifty 50 | Index | `^NSEI` |
| Bank Nifty | Index | `^NSEBANK` |
| Bajaj Finance | Equity | `BAJFINANCE.NS` |

## Design constraints

- Supervised models (LightGBM / XGBoost / sklearn GBM) predict **P(target is hit before stop during the next session)**. An LLM is **not** a price model.
- Features and strategy rules use only information known at session **T close**. Labels use session **T+1**.
- No shuffled k-fold on mixed dates. Splits are chronological.
- Parameter search is not allowed to peek at the test window.
- With only three names that still exist, survivorship is limited; expanding the universe later requires a point-in-time membership table.

## Data flow (after close)

```
OHLCV ingest (daily, optional 5m)
        │
        ▼
Feature store as-of T close
  OHLCV, returns, ATR, RSI, VWAP deviation,
  MAs, vol, volume ratio, RS vs Nifty,
  gap, range position, S/R distance,
  Nifty/BankNifty trend context
        │
        ▼
Strategy plugins → candidate setups
  (entry / SL / target / R:R / invalidation)
        │
        ▼
Quantitative shortlist (hard filters)
        │
        ▼
ML scorer (trained on historical candidates + T+1 labels)
        │
        ▼
LLM critic on shortlist only (optional)
  may reject a high ML score
        │
        ▼
Daily report: top 5 setups
```

Backtesting is a separate loop over the same candidate generator, labels, costs, and sizing. Training uses expanding or rolling walk-forward folds. The final reported numbers come from concatenated out-of-sample test folds, not from the training window.

## Modules

| Package | Responsibility |
|---|---|
| `app.universe` | Named instruments and kinds |
| `app.data` | SQLite store, Yahoo provider, synthetic provider |
| `app.features` | Leakage-safe technical and context features |
| `app.strategies` | Strategy interface + four starter rule sets |
| `app.ml` | Labels, dataset, model selection, scoring |
| `app.backtest` | Fills, NSE-like costs, sizing, metrics, regimes, walk-forward |
| `app.ai` | Optional LLM critic; rule-based critic if no API key |
| `app.report` | Top-5 daily markdown |
| `app.pipeline` | Orchestration |

## Strategy interface

Each strategy is a pure function of as-of features plus a trailing bar window ending at T. It returns zero or one `Candidate` with:

- side, entry (default next open), stop, target, R:R
- supporting rule factors
- invalidation text (setup expiry = next session unless filled)

Starter strategies (hypotheses, not edge claims):

1. `exhaustion_reversal` — multi-day run + RSI extreme + close near the extreme of the day.
2. `trend_pullback` — MA trend intact, close mean-reverts toward EMA20/VWAP without breaking structure.
3. `volatility_compression` — low ATR percentile, close near range edge, next-day expansion.
4. `index_aligned_momentum` — Bajaj Finance only: own momentum plus Nifty/BankNifty not opposing.

Replace these by implementing `Strategy` and registering in `app.strategies.registry`.

## ML pipeline

**Target:** binary `target_hit_before_stop` on the next session from the strategy’s own SL/target. If both levels trade in the same bar and path is unknown, the fill is **adverse-first** (stop wins). Timeout at the session close is a miss (`0`).

**Features:** only columns computed from bars `<= T`. No next-open, next-high, or future returns.

**Models:** LightGBM, XGBoost, `HistGradientBoostingClassifier`. Selection uses **validation-fold log-loss / AUC**, not test-fold PnL.

**Leakage checks:** unit tests assert feature as-of dates never include T+1 OHLC; split code rejects overlapping train/test dates.

## Backtesting methodology

- **Entry:** next session open (indices and stock).
- **Stop / target:** first-touch on the T+1 path. Daily bars use high/low with adverse-first if both hit. Optional 5-minute bars improve path realism when present.
- **Costs:** brokerage, STT, exchange, SEBI, GST, stamp, IPFT, slippage (bps). Equity vs index-future profiles are configurable.
- **Sizing:** fixed fraction of equity at risk (stop distance). Cap on concurrent names.
- **Regimes:** Nifty 20d return / realized vol buckets on T, not T+1.
- **Walk-forward:** train on `[t0, t1)`, validate `[t1, t2)`, test `[t2, t3)`. Metrics reported on test folds only.
- **Do not** tune stop/target percentages against concatenated test PnL.

Reported metrics: win rate, expectancy, profit factor, CAGR, max drawdown, Sharpe (daily), average trade, max losing streak, trade count, by year and regime.

## Database

SQLite file `data/local/engine.db` (gitignored).

- `instruments` — symbol, kind, yahoo ticker
- `daily_bars` — OHLCV keyed by `(symbol, date)`
- `intraday_bars` — optional 5m
- `features` — `(symbol, asof_date, name, value)`
- `candidates` — generated setups at T
- `labels` — T+1 outcomes
- `model_runs` — artifacts + validation metrics
- `predictions` — ML probabilities
- `backtest_trades` — fills after costs
- `news_items` — optional catalysts (may be empty)

## AI critic

The LLM (or deterministic critic) receives: structure, ML probability, index context, news if any, supporting/contradicting factors. It may **reject**. It does not invent a probability. If `OPENAI_API_KEY` is unset, the rule-based critic still runs.

## Execution realism limits

Yahoo daily bars are not NSE tick data. Index series are cash-index, not futures rolls. 5m history is short. Costs are a discount-broker approximation, not a broker contract. Treat live signals as research output until fills are validated against actual execution.
