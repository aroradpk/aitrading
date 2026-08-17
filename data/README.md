# Local analysis data (committed to git)

See **Run & start scripts** in the repo root `README.md` for how to start the app without pulling from APIs.

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

## Commands (no network)

```bash
./scripts/cloud-agent-start.sh          # Linux / Cloud Agent
# or
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

python scripts/run_pipeline.py          # rebuild watchlist/themes from disk only
python scripts/run_backtest.py          # backtest from local OHLCV
```

## Refresh from the web

Set `offline_mode: false` in `config/settings.yaml`, then:

```bash
python scripts/run_pipeline.py
```
