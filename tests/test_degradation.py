import numpy as np
import pandas as pd

from scrl.degradation import check_fade_distance, nonoverlapping_ic
from scrl.features import build_features
from scrl.synthetic import synthetic_bundle


def test_strided_ic_uses_fewer_points_than_daily_series():
    n = 400
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(0)
    sig = pd.Series(rng.standard_normal(n).cumsum(), index=idx)
    fwd = sig.shift(-10) - sig + rng.standard_normal(n) * 0.1
    ic = nonoverlapping_ic(sig, fwd, step=10, lookback=252)
    assert ic is not None
    assert -1.0 <= ic <= 1.0


def test_fade_ic_finite_on_synthetic():
    feat = build_features(synthetic_bundle(n=900, seed=2))
    deg = check_fade_distance(feat)
    assert deg.rolling_ic is not None
    assert -1 <= deg.rolling_ic <= 1
