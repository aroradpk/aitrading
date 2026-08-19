# NSE next-day setup engine

Research system for **next-day intraday** setups on a fixed universe:

- Nifty 50
- Bank Nifty
- Bajaj Finance

An LLM is not the price model. LightGBM / XGBoost / sklearn GBMs estimate P(target is hit before stop on the next session). Strategies are hypotheses until out-of-sample backtests say otherwise.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for data flow, schema, ML, and backtest methodology.

```bash
pip install -r requirements.txt
pip install -e .
pytest
nse-setup ingest --source synthetic
nse-setup train
nse-setup report
```

Yahoo ingest (`--source yahoo`) needs network access. Tests use synthetic bars only.
