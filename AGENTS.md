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
- **Charts:** `python scripts/build_charts.py` (~7 min, not committed).
- **Transcripts:** `python scripts/fetch_transcripts.py` (download only when `offline_mode: false`).

If the API serves stale routes after code changes, restart the `aitrading-api` tmux session (port 8000).
