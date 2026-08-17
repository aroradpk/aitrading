# aitrading

Personal stock analysis workstation focused on **technical pattern memory** with optional fundamental/event overlays later.

## What it does (Phase 0–1)

- Selects **top 20 rising Nifty Next 50 stocks** (positive 1-year trend) plus indices
- Downloads **daily OHLCV** into `data/ohlcv/daily/` (free via Yahoo Finance / NSE `.NS` symbols)
- Detects historical moves: **≥5% (1D)** / **≥10% (1W)** for stocks, **≥2% (1D)** for indices
- Saves **technical snapshots** before each move (RSI, SMA, candlestick tags, S/R, weekly context)
- Builds a **daily conviction watchlist** by matching today's chart to past big-move setups

## Run & start scripts

| What | Script / command | Network? |
| --- | --- | --- |
| **Install deps** (Linux/Cloud) | `./scripts/cloud-agent-install.sh` | pip only |
| **Install deps** (Windows) | `.\scripts\windows-install.ps1` | pip only |
| **Start dashboard** (Linux/Cloud) | `./scripts/cloud-agent-start.sh` | **No** — reads `data/` only |
| **Start dashboard** (manual) | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` | **No** |
| **Rebuild watchlist offline** | `python scripts/run_pipeline.py` | **No** when `offline_mode: true` |
| **Full refresh from web** | `offline_mode: false` then `python scripts/run_pipeline.py` | Yes (Yahoo, NSE, PIB) |

Cloud Agent VM uses `.cursor/environment.json` → `install` + `start` point at the scripts above.

**Offline is the default:** `config/settings.yaml` has `offline_mode: true`. The committed `data/` folder is enough to open http://localhost:8000 with no API pulls.

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
./scripts/cloud-agent-start.sh
```

Or manually:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** — watchlist, moves, themes, and backtest load from `data/` on disk.

### Windows Git Bash (MINGW64) — `python: No such file or directory`

If `python` points to a missing path (e.g. `AppData/Local/Python/bin/python`), **do not use bare `python`**. The repo is on `main`; fix your local venv:

```powershell
# PowerShell once — creates .venv
cd D:\aitrading
git pull origin main
powershell -ExecutionPolicy Bypass -File .\scripts\windows-install.ps1
```

```bash
# Git Bash — always use venv
cd /d/aitrading
source .venv/Scripts/activate
./scripts/venv-python.sh scripts/scan_historical_moves.py
./scripts/venv-python.sh scripts/build_watchlist.py
```

Or without activate:

```bash
.venv/Scripts/python.exe scripts/scan_historical_moves.py
```

**Optional** — rebuild watchlist from disk only (still no network):

```bash
python scripts/run_pipeline.py
```

### Refresh data from the web

1. Set `offline_mode: false` in `config/settings.yaml`
2. Run:

```bash
python scripts/run_pipeline.py   # ~2-5 min; hits Yahoo, NSE, PIB
```

3. Set `offline_mode: true` again if you want to lock to disk-only.

## Connect to the local `data/` folder in VS Code

1. **File → Open Folder…** and select your cloned repo (e.g. `~/projects/aitrading`).
2. Start the server (see **Run & start scripts** above) — no pipeline required if `data/` is present.
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
| `scripts/run_pipeline.py` | **Offline** (`offline_mode: true`): rebuild watchlist + themes only. **Online**: full fetch pipeline |
| `scripts/run_backtest.py` | Walk-forward backtest → `data/reports/backtest/` (uses local OHLCV only) |

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

## Analysis methodology

### Technical (primary gate for long setups)

- **Indicators allowed:** EMA(20, 50, 200) and RSI only — no SMA/MACD/etc.
- **Trend first:** `long_term_uptrend` / `short_term_uptrend` (EMA stack) required for long conviction (`position_focus: long` in settings). Short/intraday shorts will use downtrend tags later.
- **Price action:** Support/resistance, Fibonacci retracements, Elliott impulse/corrective tags, chart formations (wedge, triangle, flag, H&S — see `config/technical/chart_formations.json`).
- **Candlesticks** (hammer, engulfing, etc.) count **only** when paired with a formation, S/R, or Fib level.
- Formations detected in `app/engines/chart_patterns.py`.

### Fundamentals

- Prefer **QoQ and YoY** profit/sales growth vs prior quarter and same quarter last year (Screener CSV columns).
- **Vs expectations:** EPS actual vs estimate, or profit growth vs `data/fundamentals/expectations/{SYMBOL}.json`. See `config/fundamentals/expectations_guide.md` for where to find consensus (Tickertape/Trendlyne manual for now).

### Events

- Classifies concalls, analyst/investor meets separately from generic announcements.
- **Content analysis** on title text before scoring (`app/engines/event_content.py`). Interactive events without positive/negative signals are flagged `requires_transcript` and scored **0** until transcript/PDF text is available.

## Configuration

Edit `config/settings.yaml` for thresholds, universe size, conviction weights, and **`offline_mode`** (default `true` = no Yahoo/NSE/PIB calls).

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
