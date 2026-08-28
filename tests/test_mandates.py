from datetime import date

import pytest

from scrl.adversary import critique
from scrl.mandates import get_mandate
from scrl.pipeline import analyze_desk
from scrl.report import render_desk
from scrl.synthetic import synthetic_bundle


def test_intraday_is_rejected():
    with pytest.raises(ValueError, match="Intraday is a different system"):
        get_mandate("intraday")


def test_longterm_does_not_kill_stale_earnings():
    rep = critique(
        as_of=date(2026, 8, 28),
        horizon_days=252,
        last_earnings=date(2026, 7, 17),
        analog_n=25,
        analog_straddles=True,
        days_to_expiry=32,
        residual_20=0.02,
        dist_52w_high=-0.18,
        mandate=get_mandate("longterm"),
    )
    assert not any("horizon mismatch" in k for k in rep.kills)


def test_desk_separates_mandates_on_synthetic():
    bundle = synthetic_bundle(n=1400, seed=11)
    desk = analyze_desk(ticker="SYNTH.NS", bundle=bundle, last_earnings="2025-01-15", k_analogs=20)
    assert set(desk) == {"swing", "position", "longterm"}
    assert desk["swing"].mandate.name == "swing"
    assert desk["longterm"].mandate.name == "longterm"
    # Stale earnings can kill swing; they must not force long-term DENY.
    assert desk["longterm"].permission.decision in {"WAIT", "HOLD", "ADD_SMALL", "TRIM"}
    text = render_desk(desk["swing"], desk["position"], desk["longterm"])
    assert "[SWING]" in text
    assert "INTRADAY: not available" in text
    assert "HOW THIS HELPS P&L" in text
