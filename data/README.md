# Local analysis data (committed to git)

This folder is **versioned** so you can clone the repo and run the dashboard without downloading anything.

Set `offline_mode: true` in `config/settings.yaml` (default) to guarantee the app only reads from here — no Yahoo/NSE/PIB calls.

| Folder | Contents |
| --- | --- |
| `universe/active.json` | Top 20 rising Nifty Next 50 stocks + indices |
| `ohlcv/daily/*.parquet` | Daily price history per symbol |
| `moves/{SYMBOL}/` | Historical big-move events + `_summary.json` |
| `technical/snapshots/` | Chart state before each big move |
| `events/nse/{SYMBOL}.json` | NSE corporate announcements cache |
| `events/pib/` | PIB RSS feed cache |
| `fundamentals/{SYMBOL}.json` | Imported Screener metrics |
| `themes/scores/{SYMBOL}.json` | Per-symbol theme scores |
| `reports/daily/` | Daily conviction watchlist JSON |
| `reports/backtest/` | Walk-forward backtest results |
| `sources/` | Misc API response caches |

**Refresh from the web:** set `offline_mode: false`, then run `python scripts/run_pipeline.py`.

**Offline rebuild** (watchlist/themes only): `python scripts/run_pipeline.py` with `offline_mode: true`.

Start server: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
