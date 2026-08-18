# Local analysis data (committed to git)

See **Run & start scripts** in the repo root `README.md` for how to start the app without pulling from APIs.

Set `offline_mode: true` in `config/settings.yaml` (default) to guarantee the app only reads from here — no Yahoo/NSE/PIB calls.

| Folder | Contents |
| --- | --- |
| `universe/active.json` | 5-scrip intraday book (3 stocks + 2 indices) |
| `ohlcv/daily/*.parquet` | Daily price history for those 5 |
| `intraday/ledger.jsonl` | Setup log + next-session MFE (learning loop) |
| `intraday/adr_profile.json` | Per-scrip ADR20 and 1.25× range targets |
| `ohlcv/daily/*.parquet` | Daily price history per symbol |
| `moves/{SYMBOL}/` | Historical big-move events + `_summary.json` |
| `technical/snapshots/` | Chart state before each big move |
| `events/nse/{SYMBOL}.json` | NSE corporate announcements cache |
| `events/pib/` | PIB RSS feed cache |
| `fundamentals/{SYMBOL}.json` | Imported Screener metrics |
| `themes/scores/{SYMBOL}.json` | Per-symbol theme scores |
| `reports/daily/` | Daily conviction watchlist JSON |
| `reports/backtest/` | Walk-forward backtest results |
| `technical/charts/` | Pre-move PNG charts (EMA + RSI) |
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
