import numpy as np
import pandas as pd

from scrl.features import build_features
from scrl.synthetic import synthetic_bundle


def test_forward_return_is_true_future():
    bundle = synthetic_bundle(n=400, seed=1)
    feat = build_features(bundle)
    t = feat.dropna(subset=["fwd_5"]).index[100]
    pos = bundle.equity.index.get_loc(t)
    expected = bundle.equity.iloc[pos + 5] / bundle.equity.iloc[pos] - 1
    assert abs(feat.loc[t, "fwd_5"] - expected) < 1e-12


def test_as_of_truncates():
    bundle = synthetic_bundle(n=400, seed=1)
    cut = bundle.equity.index[200]
    feat = build_features(bundle, as_of=cut)
    assert feat.index.max() == cut
    assert feat["close"].iloc[-1] == bundle.equity.loc[cut]


def test_no_inf_in_core_columns():
    feat = build_features(synthetic_bundle(n=500, seed=2))
    core = feat[["eq_ret_20", "bm_vol_20", "dist_ma20"]].replace([np.inf, -np.inf], np.nan)
    assert core.dropna().shape[0] > 200
