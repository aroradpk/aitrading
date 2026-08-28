from datetime import date

from scrl.adversary import critique
from scrl.calendar_nse import days_to_monthly_expiry
from scrl.permission import decide
from scrl.regime import RegimeSnapshot
from scrl.retrieval import AnalogSet
from scrl.specialists import SpecialistBoard, SpecialistCall
import pandas as pd


def _board(trend=False, fade=False, disagree=False):
    dummy = SpecialistCall("x", False, "", 0.6, 0.001, True)
    trend_c = SpecialistCall("trend_follow", trend, "t", 0.6, 0.001, True)
    fade_c = SpecialistCall("fade_oversold", fade, "f", 0.6, 0.001, True)
    cash = SpecialistCall("cash", not (trend or fade), "c", None, 0.0, True)
    return SpecialistBoard(trend=trend_c, fade=fade_c, cash=cash, disagreement=disagree)


def test_adversary_kills_stale_earnings():
    rep = critique(
        as_of=date(2026, 8, 24),
        horizon_days=20,
        last_earnings=date(2026, 7, 17),
        analog_n=25,
        analog_straddles=True,
        days_to_expiry=1,
        residual_20=0.0,
        dist_52w_high=-0.18,
    )
    assert rep.killed
    assert any("horizon mismatch" in k for k in rep.kills)
    assert any("expiry" in k for k in rep.kills)


def test_permission_denies_high_entropy():
    regime = RegimeSnapshot(
        date=pd.Timestamp("2026-08-24"),
        state="chop",
        probabilities={"chop": 0.4, "trend": 0.3, "risk_off": 0.3},
        entropy=1.05,
        high_entropy=True,
    )
    analogs = AnalogSet(
        n=25,
        neighbors=pd.DataFrame(),
        fwd_10={"p25": -0.02, "median": 0.0, "p75": 0.02},
        fwd_excess_10={"p25": -0.01, "median": 0.0, "p75": 0.01},
        straddles_zero=True,
        same_sign=False,
        median_10=0.0,
    )
    adv = critique(
        as_of=date(2026, 8, 24),
        horizon_days=20,
        last_earnings=None,
        analog_n=25,
        analog_straddles=True,
        days_to_expiry=days_to_monthly_expiry(date(2026, 8, 24)),
        residual_20=0.01,
        dist_52w_high=-0.05,
    )
    perm = decide(regime, analogs, _board(), adv, as_of=date(2026, 8, 24))
    assert perm.decision == "DENY"
    assert perm.cash_weight == 1.0
