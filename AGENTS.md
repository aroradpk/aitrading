# NSE Setup Engine

Python 3.11+ research engine for next-day NSE intraday setups.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Commands

```bash
nse-setup ingest --source yahoo
nse-setup features
nse-setup train
nse-setup backtest
nse-setup report
nse-setup run-daily
```

Tests:

```bash
pytest
```

Live ingest needs network access to Yahoo Finance. Tests use synthetic bars and do not require market data.

## Scope (current)

Universe is fixed to Nifty 50 index, Bank Nifty index, and Bajaj Finance. Strategies are research hypotheses until out-of-sample backtests say otherwise.
