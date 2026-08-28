from scrl.features import RETRIEVAL_COLS, build_features
from scrl.retrieval import retrieve
from scrl.synthetic import synthetic_bundle


def test_retrieval_library_does_not_include_unrealized_future():
    feat = build_features(synthetic_bundle(n=900, seed=4))
    as_of = feat.dropna(subset=RETRIEVAL_COLS).index[700]
    analogs = retrieve(feat, as_of=as_of, k=20, min_history=100)
    assert analogs.n >= 15
    latest_neighbor = analogs.neighbors.index.max()
    sessions = feat.loc[:as_of].index
    loc_asof = sessions.get_loc(as_of)
    loc_n = sessions.get_loc(latest_neighbor)
    assert loc_asof - loc_n >= 10


def test_retrieval_60d_library_does_not_include_unrealized_future():
    feat = build_features(synthetic_bundle(n=1100, seed=4))
    as_of = feat.dropna(subset=RETRIEVAL_COLS).index[900]
    analogs = retrieve(feat, as_of=as_of, k=20, min_history=100, horizon_days=60)
    assert analogs.horizon_days == 60
    assert analogs.n >= 15
    latest_neighbor = analogs.neighbors.index.max()
    sessions = feat.loc[:as_of].index
    loc_asof = sessions.get_loc(as_of)
    loc_n = sessions.get_loc(latest_neighbor)
    assert loc_asof - loc_n >= 60


def test_straddle_flag_matches_quartiles():
    feat = build_features(synthetic_bundle(n=900, seed=5))
    as_of = feat.dropna(subset=RETRIEVAL_COLS).index[-30]
    analogs = retrieve(feat, as_of=as_of, k=25, min_history=80)
    product = analogs.fwd_10["p25"] * analogs.fwd_10["p75"]
    assert analogs.straddles_zero == (product < 0)
