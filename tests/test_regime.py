from scrl.features import build_features
from scrl.regime import RegimeModel
from scrl.synthetic import synthetic_bundle


def test_regime_snapshot_has_three_named_states():
    feat = build_features(synthetic_bundle(n=1200, seed=3))
    model = RegimeModel().fit(feat)
    snap = model.snapshot(feat)
    assert snap.state in snap.probabilities
    assert abs(sum(snap.probabilities.values()) - 1.0) < 1e-6
    assert snap.entropy >= 0
    names = set(model.state_names.values())
    assert {"risk_off", "trend", "chop"} <= names or len(names) == 3
