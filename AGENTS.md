# AGENTS.md

## Workflow

- After completing a roadmap phase (tests passing, PR ready), **merge the PR to `main` automatically** unless the user says otherwise.
- Mark draft PRs ready for review before merging.
- Start the next phase on a new branch: `cursor/<phase-description>-e4a2`.

## Cursor Cloud specific instructions

- **Offline default:** `config/settings.yaml` has `offline_mode: true`. The committed `data/` snapshot is the source of truth; no Yahoo/NSE/PIB calls on normal startup.
- **Install / update:** `./scripts/cloud-agent-install.sh` (or `pip install -r requirements.txt` in `.venv`).
- **Start API:** `./scripts/cloud-agent-start.sh` or `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- **Tests:** `pytest` (30+ tests).
- **Backtest:** `python scripts/run_backtest.py` (~1–2 min). Tuning reuses one signal pass: `python scripts/tune_backtest.py`.
- **Position focus:** `technical.position_focus` in settings (`long` | `short` | `both`); intraday block for tighter short proxy on daily bars.
- **Conviction model:** Technical **0–7** + research (fundamentals + events/meetings) **0–3** = conviction **0–10**. Theme is a separate **1–5 bonus** column (`theme_bonus`), not in conviction.
- **Pattern scoring:** `app/engines/pattern_scoring.py` — ladder, not a yes/no 5% test. **5** = daily coil, expect ~**3% next day**. **6** = daily rumble (range ≥ 2.5%, close not ±5%), expect ~**4% next day**. **7** = rumble + **15m compressing wedge and 1h rounding at EMA20**, volume not dead; expect ~**5% within 3 sessions** (next-day 5% is too noisy). Hourly Fib and 15m/1h coils are cherries, not a 7-gate. Late ±5% close is never a 7. Report quality with `python scripts/eval_call_quality.py`: **CORRECT %** vs **FALSE ALARM %** for 7, and for 5–7 combined. Intraday cache: `python scripts/fetch_intraday.py` when `offline_mode: false`.
- **Validate big moves:** `python scripts/validate_prior_day_moves.py --symbols ABB,MOTHERSON,ADANIPOWER`
- **Charts:** `python scripts/build_charts.py` (~7 min, not committed).
- **Transcripts:** `python scripts/fetch_transcripts.py` (download only when `offline_mode: false`).

If the API serves stale routes after code changes, restart the `aitrading-api` tmux session (port 8000).

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
