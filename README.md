"""SCRL — Situation-Conditioned Research Loop

What this repo is
-----------------
A 2026-buildable **research loop**, not a broker bot and not a catalog of AI
trading products. It implements only the pieces from the capability list that
can be made *mechanically honest*: numbers first, language second, silence
allowed.

Conviction ranking (what was built vs skipped)
----------------------------------------------
Built (high conviction / high process-accuracy)

1. When NOT to trade (`scrl/permission.py`)
   Highest-value output. DENY is the default. Accuracy here means *the rule
   fired for the reason it claims*, not that the market will fall.

2. Market regime detection (`scrl/regime.py`)
   3-state Gaussian mixture on Nifty 20d return/vol, vol-of-vol, trend
   strength, and Brent 20d return. Entropy gates specialists.

3. Historical situation retrieval (`scrl/retrieval.py`)
   Point-in-time kNN. Neighbor episodes must have already realized their
   10-day forward return. Reports a distribution, not a single analog.

4. Event → company via factor residual (`scrl/factors.py`)
   Rolling OLS: equity ~ Nifty + Brent + USDINR. Residual is the part oil
   and the index do not explain. No LLM sentiment.

5. Counterfactuals (`scrl/counterfactual.py`)
   Three stress worlds pushed through the same betas. Not probabilities.

6. Adversary / horizon police (`scrl/adversary.py`)
   Mechanical kills: stale earnings vs holding period, expiry, analog n < 15.

7. Walk-forward specialist health (`scrl/specialists.py`)
   Trend, fade, cash. In-sample Sharpe is ignored.

8. Degradation check (`scrl/degradation.py`)
   Rolling IC of “distance from 52-week high” vs forward 10d.

Skipped on purpose (low conviction in 2026)

- Autonomous strategy discovery (overfit factory)
- Automated feature search (multiple-testing theatre)
- LLM news “causal graphs” without a point-in-time news store
- Live order routing / ChatGPT + broker
- Target prices and confidence percentages

Run
---
    pip install -e .
    pytest
    python -m scrl.cli analyze RELIANCE.NS --horizon 20 --last-earnings 2026-07-17

The ticket will usually say DENY. That is the product.
"""
