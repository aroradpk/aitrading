"""SCRL — personal trading/investing desk

This is not a signal service. It is a **mandate splitter**: swing, position, and
long-term are different jobs. Mixing them is how a 10-day coin flip becomes a
"long-term conviction" story.

What it does for *your* P&L
---------------------------
- **Swing (1–4 weeks):** mostly DENY. That is the edge — fewer bad trades.
- **Position (1–3 months):** same analog test on 20-day forwards.
- **Long-term:** HOLD/WAIT/ADD_SMALL/TRIM. A stale quarterly print is *not* a
  kill. A 10-day analog that straddles zero is *not* a reason to sell a
  compounder, and not a reason to start one either.
- **Intraday:** not in this repo. Daily bars cannot do it.

Daily habit
-----------
    python -m scrl.cli desk RELIANCE.NS --last-earnings 2026-07-17 --journal

Paper journal lives in `data/journal/paper.csv`. Override DENY only if you
log it. After months, compare journal P&L vs buy-and-hold vs "always traded."

Monetize later
--------------
If that file beats both baselines after costs, sell the *software/process*,
not stock tips (regulated in India). Do not skip the journal.
"""
