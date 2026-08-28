from scrl.pipeline import analyze
from scrl.report import render_text
from scrl.synthetic import synthetic_bundle


def test_pipeline_produces_deny_or_allow_on_synthetic():
    bundle = synthetic_bundle(n=1400, seed=11)
    result = analyze(
        ticker="SYNTH.NS",
        bundle=bundle,
        horizon_days=20,
        last_earnings=None,
        k_analogs=20,
    )
    assert result.close > 0
    assert result.permission.decision in {"DENY", "ALLOW_SMALL", "ALLOW"}
    assert result.analogs.n >= 15
    text = render_text(result)
    assert "PERMISSION:" in text
    assert "ADVERSARY" in text
    assert "no target price" in text
