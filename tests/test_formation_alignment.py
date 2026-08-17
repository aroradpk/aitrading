from app.engines.move_detector import _elliott_alignment, _formation_alignment


def test_formation_conflict_caps_long_on_bearish_pattern() -> None:
    formations = [{"id": "head_shoulders", "name": "H&S", "bias": "bearish_reversal"}]
    assert _formation_alignment(formations, "long") == "conflict"
    assert _formation_alignment(formations, "short") == "support"


def test_elliott_conflict_for_long_in_down_impulse() -> None:
    tags = {"elliott_impulse_down"}
    assert _elliott_alignment(tags, "long") == "conflict"
    assert _elliott_alignment(tags, "short") == "support"
