# Fundamental expectations (optional per symbol)

Place `data/fundamentals/expectations/{SYMBOL}.json` or embed under `expectations` in `data/fundamentals/{SYMBOL}.json`.

## Free / low-cost sources for India

| Source | What you get | How to use here |
| --- | --- | --- |
| **Screener.in** | QoQ/YoY in quarterly export | Add columns to CSV import (see `config/samples/screener_template.csv`) |
| **NSE result filings** | Actual vs headline in PDF title | Title keywords parsed in events layer; full PDF parsing later |
| **Tickertape / Trendlyne** | Consensus EPS & revenue estimates | Manual copy into expectations JSON (no free API) |
| **Moneycontrol estimates** | Broker consensus | Manual entry until we add import |
| **Company concall transcript** | Guidance vs street | Paste summary into events notes (future) |

## Example expectations file

```json
{
  "period": "Q1FY26",
  "profit_growth_pct": 15,
  "revenue_growth_pct": 12,
  "eps": 45,
  "source": "tickertape_manual",
  "as_of": "2026-08-01"
}
```

Scoring checks: QoQ > prior quarter, YoY > same quarter last year, actual metrics ≥ expectations.
