# aitrading

Personal stock analysis workstation focused on **technical pattern memory** with optional fundamental/event overlays later.

## What it does (Phase 0–1)

- Selects **top 20 rising Nifty Next 50 stocks** (positive 1-year trend) plus indices
- Downloads **daily OHLCV** into `data/ohlcv/daily/` (free via Yahoo Finance / NSE `.NS` symbols)
- Detects historical moves: **≥5% (1D)** / **≥10% (1W)** for stocks, **≥2% (1D)** for indices
- Saves **technical snapshots** before each move (RSI, SMA, candlestick tags, S/R, weekly context)
- Builds a **daily conviction watchlist** by matching today's chart to past big-move setups

## Quick start (offline — default)

The repo includes a **committed `data/`** snapshot. With `offline_mode: true` in `config/settings.yaml`, nothing is fetched from the web.

### Windows (PowerShell)

```powershell
cd D:\aitrading
git pull origin main
powershell -ExecutionPolicy Bypass -File .\scripts\windows-install.ps1
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Linux / macOS / Cloud Agent

```bash
./scripts/cloud-agent-install.sh
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** — watchlist, moves, themes, and backtest load from `data/` on disk.

Optional local rebuild (still no network): `python scripts/run_pipeline.py`

### Refresh data from the web

Set `offline_mode: false` in `config/settings.yaml`, then:

```bash
python scripts/run_pipeline.py   # ~2-5 min; hits Yahoo, NSE, PIB
```

## Connect to the local `data/` folder in VS Code

1. **File → Open Folder…** and select your cloned repo (e.g. `~/projects/aitrading`).
2. Run `python scripts/run_pipeline.py` once.
3. In the Explorer sidebar you'll see:

```
aitrading/
  data/                  ← committed analysis snapshot (browse in VS Code)
    universe/active.json
    ohlcv/daily/*.parquet
    moves/{SYMBOL}/
    technical/snapshots/
    reports/daily/
```

4. Click any `.json` file to inspect moves, snapshots, or watchlist reports.
5. Optional: install the **Parquet Viewer** or **Rainbow CSV** extension for `.parquet` files.

The FastAPI app reads from the same `data/` folder — VS Code and the UI always show the same files.

## Pipeline scripts

| Script | Purpose |
| --- | --- |
| `scripts/build_universe.py` | Top 20 rising Nifty Next 50 + indices → `data/universe/active.json` |
| `scripts/fetch_ohlcv.py` | Download price history → `data/ohlcv/daily/` |
| `scripts/scan_historical_moves.py` | Find big moves + snapshots → `data/moves/` |
| `scripts/build_watchlist.py` | Today's conviction list → `data/reports/daily/` |
| `scripts/build_theme_scores.py` | Theme exposure scores → `data/themes/scores/` |
| `scripts/run_pipeline.py` | Runs all of the above |

## API endpoints

| Endpoint | Description |
| --- | --- |
| `GET /api/analysis/status` | Data folder health |
| `GET /api/analysis/universe` | Active stock/index universe |
| `GET /api/analysis/moves` | Historical big moves |
| `GET /api/analysis/watchlist/latest` | Latest conviction report |
| `POST /api/analysis/watchlist/build` | Rebuild watchlist |
| `GET /api/analysis/themes/graph` | Macro theme graph |
| `GET /api/analysis/themes/{symbol}` | Per-symbol theme score |
| `POST /api/analysis/themes/build` | Rebuild theme scores |

## Data sources

- **Primary:** Yahoo Finance (`yfinance`) for EOD OHLCV — good for personal research, not official NSE feed.
- **TradingView:** No free API; use it to visually verify symbols, or export CSV and we can add an import path later.
- **Fundamentals / PIB / board meetings:** Phase 2 (not automated yet).

## Configuration

Edit `config/settings.yaml` for thresholds, universe size, and conviction weights.

Nifty Next 50 full list: `config/nifty_next_50.json` (update quarterly after index reconstitution).

## Phase 2 — Events & fundamentals

| Script | Purpose |
| --- | --- |
| `scripts/fetch_events.py` | NSE corporate announcements + PIB RSS cache |
| `scripts/import_fundamentals.py` | Import Screener CSV from `data/fundamentals/import/` |

Conviction now blends **technical (50%) + fundamental (25%) + events (15%) + theme (10%)**.

### Screener CSV import

1. Export CSV from [Screener.in](https://www.screener.in) for your stocks
2. Save to `data/fundamentals/import/my_export.csv`
3. Run `python scripts/import_fundamentals.py`
4. Or upload via dashboard **Data Status** tab

Template columns: see `config/samples/screener_template.csv`

## Phase 3 — Themes

| Script | Purpose |
| --- | --- |
| `scripts/build_theme_scores.py` | Score macro theme exposure → `data/themes/scores/` |

Theme graph: `config/themes/graph.json` maps macro themes to active-universe symbols.

Manual overrides: `data/themes/overrides/{SYMBOL}.json` with a `rubric` object (e.g. `{"order_book_visibility": 5}`).

### Theme API

| Endpoint | Description |
| --- | --- |
| `GET /api/analysis/themes/graph` | Macro theme graph |
| `GET /api/analysis/themes/{symbol}` | Theme score, scenarios, reasons |
| `POST /api/analysis/themes/build` | Rebuild all theme scores |

## Phase 4 — Backtest

Walk-forward backtest: when conviction was ≥7 historically, how often did price hit **5% (next day)** or **10% (5 sessions)**?

| Script | Purpose |
| --- | --- |
| `scripts/run_backtest.py` | Run backtest → `data/reports/backtest/latest.json` |

Configure in `config/settings.yaml` under `backtest:` (`conviction_min`, `signal_cooldown_days`, targets).

| Endpoint | Description |
| --- | --- |
| `GET /api/analysis/backtest/latest` | Latest backtest report |
| `POST /api/analysis/backtest/run` | Run walk-forward backtest |

Technical + events are walk-forward; fundamental/theme use current imported data (static overlay).

## Tests

```bash
source .venv/bin/activate
pytest
```

## Disclaimer

Personal research tool only. Not investment advice.
