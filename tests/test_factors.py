from datetime import date

from scrl.factors import rolling_factor_residual, snapshot
from scrl.synthetic import synthetic_bundle


def test_factor_snapshot_has_finite_betas():
    bundle = synthetic_bundle(n=400, seed=9)
    fac = rolling_factor_residual(bundle, window=60)
    snap = snapshot(fac)
    assert snap.date is not None
    assert abs(snap.beta_benchmark) < 5
    assert snap.r_squared == snap.r_squared
