# aitrading

Personal stock analysis workstation focused on **technical pattern memory** with optional fundamental/event overlays later.

## What it does (Phase 0–1)

- Trades a **5-scrip intraday book**: HDFCBANK, BAJFINANCE, M&M, Nifty 50, Bank Nifty
- Wider names (Nifty Next 50 list in `config/nifty_next_50.json`) are for a **later swing** feature — not the live book
- Downloads **daily + 15m/1h OHLCV** for those 5 into `data/ohlcv/`
- Scores next-session setups against **fixed per-scrip range targets** (HDFC 2%, BAJ/M&M 3%, Nifty 1%, Bank Nifty 1.2%). A **7** is live volume on the setup day.
- **Learns from outcomes** by logging every setup and refreshing hit rates (`data/intraday/`) — not a trained ML model

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
| `scripts/build_universe.py` | 5-scrip book from `config/intraday_universe.json` → `data/universe/active.json` |
| `scripts/fetch_ohlcv.py` | Daily price history → `data/ohlcv/daily/` |
| `scripts/fetch_intraday.py` | 15m/1h bars (not committed) → `data/ohlcv/{15m,1h}/` |
| `scripts/scan_historical_moves.py` | Find big moves + snapshots → `data/moves/` |
| `scripts/build_watchlist.py` | Today's conviction list + ledger rows → `data/reports/daily/` |
| `scripts/learn_intraday.py` | Fill next-session MFE, refresh `data/intraday/rule_stats.json` |
| `scripts/build_theme_scores.py` | Theme exposure scores → `data/themes/scores/` |
| `scripts/run_pipeline.py` | **Offline** (`offline_mode: true`): rebuild watchlist + themes + learn. **Online**: full fetch pipeline |
| `scripts/run_backtest.py` | Walk-forward backtest → `data/reports/backtest/` (uses local OHLCV only) |

## API endpoints

| Endpoint | Description |
| --- | --- |
| `GET /api/analysis/status` | Data folder health |
| `GET /api/analysis/universe` | Active stock/index universe |
| `GET /api/analysis/moves` | Historical big moves |
| `GET /api/analysis/watchlist/latest` | Latest conviction report |
| `GET /api/analysis/intraday/stats` | Next-session hit rates (trusted only at n≥20) |
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
- **Trend first:** `long_term_uptrend` / `short_term_uptrend` (EMA stack) required for long conviction (`position_focus: long`). Short setups require `*_downtrend` tags when `position_focus` is `short` or `both`.
- **Price action:** Support/resistance, Fibonacci retracements, **strict Elliott** impulse (5-wave rules) and ABC corrective tags, chart formations (wedge, triangle, flag, H&S — see `config/technical/chart_formations.json`). Elliott tags require trend alignment and valid wave ratios (wave 2 retrace, wave 3 not shortest, wave 4 non-overlap).
- **Formation bias:** Long setups cap technical score when bearish formations conflict (and vice versa for shorts).
- **Candlesticks** (hammer, engulfing, etc.) count **only** when paired with a formation, S/R, or Fib level.
- Formations detected in `app/engines/chart_patterns.py`.

### Fundamentals

- Prefer **QoQ and YoY** profit/sales growth vs prior quarter and same quarter last year (Screener CSV columns).
- **Vs expectations:** EPS actual vs estimate, or profit growth vs `data/fundamentals/expectations/{SYMBOL}.json`. See `config/fundamentals/expectations_guide.md` for where to find consensus (Tickertape/Trendlyne manual for now).

### Events

- Classifies concalls, analyst/investor meets separately from generic announcements.
- **Content analysis** on title text before scoring (`app/engines/event_content.py`). Interactive events without positive/negative signals are flagged `requires_transcript` and scored **0** until transcript/PDF text is available (Phase 6 caches NSE PDF text under `data/events/transcripts/`).

## Configuration

Edit `config/settings.yaml` for thresholds, universe size, conviction weights, and **`offline_mode`** (default `true` = no Yahoo/NSE/PIB calls).

Intraday book: `config/intraday_universe.json` (3 Nifty 50 names + Nifty 50 + Bank Nifty). Nifty Next 50 full list stays in `config/nifty_next_50.json` for a later swing universe.

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

Manual overrides: `data/themes/overrides/{SYMBOL}.json` with a `rubric` object (e.g. `{"order_book_visibility": 5}`). Rubric keys: `config/themes/rubric_guide.json`.

### Phase 8 — Theme editor UI

Dashboard **Themes** tab includes:

- **Theme graph editor** — edit theme name, macro, symbol list; saves to `config/themes/graph.json`
- **Rubric override editor** — per-symbol manual scores → `data/themes/overrides/{SYMBOL}.json`

| Endpoint | Description |
| --- | --- |
| `PUT /api/analysis/themes/graph` | Save theme graph |
| `GET /api/analysis/themes/rubric-guide` | Rubric field definitions |
| `GET/PUT/DELETE /api/analysis/themes/overrides/{symbol}` | Read/write/clear overrides |
| `PATCH /api/analysis/themes/{theme_id}/symbols` | Assign/remove symbol on a theme |

## Phase 9 — Short & intraday setups

Swing **short** and **intraday** (daily-bar proxy) setups alongside long watchlist entries.

```yaml
technical:
  position_focus: both   # long | short | both
  intraday:
    enabled: true
    stock_target_1d_pct: 2.5
    position_side: short
```

Watchlist UI filters: All / Long / Short / Intraday.

## Phase 10 — Elliott wave tightening

Strict Elliott detection in `app/engines/elliott.py` (rules in `config/technical/chart_formations.json` → `elliott`):

| Rule | Impulse up/down |
| --- | --- |
| Structure | 6 alternating swings (5 waves) |
| Wave 2 | 23.6%–78.6% retrace of wave 1 |
| Wave 3 | Not the shortest among waves 1, 3, 5 |
| Wave 4 | Does not overlap wave 1 territory |
| Trend | Tags only when EMA trend aligns (`require_trend_alignment`) |
| Min leg | Each impulse leg ≥ 1.5% of price (`min_leg_pct`) |

Tags: `elliott_impulse_up`, `elliott_impulse_down`, `elliott_abc_corrective_down`, `elliott_abc_corrective_up`.

Setup scoring also checks **formation bias** and **Elliott alignment** with long/short side (conflict caps technical at 3.0).

### OHLCV: NSE bhavcopy fallback (deferred)

Not implemented. When added later: keep `data/ohlcv/daily/*.parquet` as source of truth; use Yahoo for refresh; bhavcopy only for reconciliation (adj vs raw differences).

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

### Phase 7 — Backtest tuning

Grid-search `conviction_min` and `signal_cooldown_days` without re-running the full walk-forward for each combo (signals collected once at `tuning_conviction_floor`, then filtered).

| Script | Purpose |
| --- | --- |
| `scripts/tune_backtest.py` | Grid search → `data/reports/backtest/tuning_latest.json` |

Configure grids in `config/settings.yaml` under `backtest:` (`tuning_conviction_min_grid`, `tuning_cooldown_days_grid`, `tuning_min_signals`).

| Endpoint | Description |
| --- | --- |
| `POST /api/analysis/backtest/tune` | Run parameter grid |
| `GET /api/analysis/backtest/tuning/latest` | Latest tuning report |

## Phase 5 — Chart PNG snapshots

Pre-move charts saved to `data/technical/charts/{SYMBOL}/{date}.png` (EMA 20/50/200, RSI, S/R, tags).

| Script | Purpose |
| --- | --- |
| `scripts/build_charts.py` | Regenerate PNGs from existing moves (offline) |
| `scripts/scan_historical_moves.py` | Also builds charts when `charts.enabled: true` |

| Endpoint | Description |
| --- | --- |
| `GET /api/analysis/charts/{symbol}/{date}` | PNG for a historical move |

## Phase 6 — NSE transcript PDF analysis

Concall / earnings-call PDFs linked from NSE announcements are downloaded (when online), text-extracted, and cached for content scoring.

| Script | Purpose |
| --- | --- |
| `scripts/fetch_transcripts.py` | Download transcript PDFs → `data/events/transcripts/{SYMBOL}/` |

| Endpoint | Description |
| --- | --- |
| `GET /api/analysis/events/{symbol}/transcripts` | List transcript PDF candidates + cache status |
| `POST /api/analysis/events/transcripts/fetch` | Fetch missing PDFs (409 when `offline_mode: true`) |

Offline: use cached `*.txt` + `*.json` under `data/events/transcripts/`. Re-run fetch with `offline_mode: false` to refresh.

## Tests

```bash
source .venv/bin/activate
pytest
```

## Disclaimer

Personal research tool only. Not investment advice.
