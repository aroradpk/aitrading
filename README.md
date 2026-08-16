# aitrading

Local AI trading sandbox with a FastAPI backend and a simple dashboard for analysis and paper trades.

## Development

```bash
./scripts/cloud-agent-install.sh
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` for the dashboard.

## Tests

```bash
source .venv/bin/activate
pytest
```
