# AGENTS.md

## Workflow

- After completing a roadmap phase (tests passing, PR ready), **merge the PR to `main` automatically** unless the user says otherwise.
- Mark draft PRs ready for review before merging.
- Start the next phase on a new branch: `cursor/<phase-description>-e4a2`.

## Cursor Cloud specific instructions

- **Offline default:** `config/settings.yaml` has `offline_mode: true`. The committed `data/` snapshot is the source of truth; no Yahoo/NSE/PIB calls on normal startup.
- **Install / update:** `./scripts/cloud-agent-install.sh` (or `pip install -r requirements.txt` in `.venv`).
- **Start API:** `./scripts/cloud-agent-start.sh` or `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- **Tests:** `pytest`.
- **Trading book:** 5 scrips in `config/intraday_universe.json` (HDFCBANK, BAJFINANCE, M&M, NIFTY_50, NIFTY_BANK). Do not scan 20–40 names for **intraday**. `config/nifty_next_50.json` is kept for a later **swing** universe only.
- **Target trades:** High-conviction **rare take** = today's open already gapped **75–99%** of that name's book target, **one name per day** (largest gap). Hit = that session's high vs prior close >= target. `python scripts/eval_rare_takes.py`. EOD washout watch is research-only (~22% hit). 80% hit at 3–4 trades/week is not on this book.
- **ADR / targets:** ADR20 is context only. Targets live on each instrument in `config/intraday_universe.json`.
- **Pattern scoring:** Layer sum only (cap 7). Coil / rumble / live volume are flags, not forced 5/6/7. Late ±5% close bar still caps at 4.
- **Validate big moves:** `python scripts/validate_prior_day_moves.py` (defaults to the 3 stocks).
- **Charts:** `python scripts/build_charts.py` (not committed).
- **Transcripts:** `python scripts/fetch_transcripts.py` (download only when `offline_mode: false`).

- **Yahoo 15m/1h:** Yahoo only serves ~60 calendar days of 15m. If the VM clock is ahead of Yahoo’s last bar, `scripts/fetch_intraday.py` will fail; daily parquet is enough for the next-session ledger. Do not commit `data/ohlcv/15m` or `1h`.

### Viewing the dashboard (Cloud Agent VM)

The API listens on **port 8000 inside the VM** (`uvicorn` on `0.0.0.0:8000`). `http://localhost:8000` on your **laptop** is not the VM unless port forwarding is active — that mismatch usually shows as an endlessly loading preview.

**Option A — Desktop pane (most reliable):**

1. Open the **Desktop** pane for this agent run.
2. Launch **Chrome** or **Firefox** in the VM.
3. Go to `http://127.0.0.1:8000` (or `http://localhost:8000` inside that VM browser).

**Option B — Port forward from Cursor:**

1. In the agent run UI, open **Ports** (plug icon).
2. Forward **8000**.
3. Click **Open in Browser** (or use the forwarded URL Cursor shows).

**Sanity check (inside VM):** `curl http://127.0.0.1:8000/health` should return `{"status":"ok"}`.
