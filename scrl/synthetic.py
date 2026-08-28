"""Deterministic synthetic markets for tests (no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scrl.data import MarketBundle


def synthetic_bundle(n: int = 1600, seed: int = 7) -> MarketBundle:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-02", periods=n)
    # Three crude regimes cycled every ~250 days: trend, chop, risk-off.
    nifty = [1000.0]
    brent = [70.0]
    fx = [80.0]
    rel = [800.0]
    for t in range(1, n):
        phase = (t // 250) % 3
        if phase == 0:  # trend
            mu_n, sig_n = 0.0006, 0.008
            mu_b, sig_b = 0.0002, 0.012
        elif phase == 1:  # chop
            mu_n, sig_n = 0.0, 0.006
            mu_b, sig_b = 0.0, 0.010
        else:  # risk-off
            mu_n, sig_n = -0.0008, 0.018
            mu_b, sig_b = 0.0010, 0.025
        dn = mu_n + sig_n * rng.standard_normal()
        db = mu_b + sig_b * rng.standard_normal()
        dfx = -0.3 * dn + 0.004 * rng.standard_normal()
        nifty.append(nifty[-1] * (1 + dn))
        brent.append(max(20.0, brent[-1] * (1 + db)))
        fx.append(max(50.0, fx[-1] * (1 + dfx)))
        # RELIANCE: 0.9 nifty + 0.15 brent + idiosyncratic
        dr = 0.9 * dn + 0.15 * db + 0.007 * rng.standard_normal()
        rel.append(rel[-1] * (1 + dr))
    return MarketBundle(
        equity=pd.Series(rel, index=idx, name="close"),
        benchmark=pd.Series(nifty, index=idx, name="close"),
        brent=pd.Series(brent, index=idx, name="close"),
        usd_inr=pd.Series(fx, index=idx, name="close"),
        ticker="SYNTH.NS",
    )
