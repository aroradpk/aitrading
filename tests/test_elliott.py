from app.engines.elliott import (
    _validate_abc_down,
    _validate_abc_up,
    _validate_impulse_down,
    _validate_impulse_up,
    load_elliott_rules,
)


def _rules() -> dict:
    rules = load_elliott_rules()
    load_elliott_rules.cache_clear()
    return rules


def test_impulse_up_requires_six_alternating_swings() -> None:
    rules = _rules()
    valid = [
        (0, 100.0, "trough"),
        (5, 110.0, "peak"),
        (10, 105.0, "trough"),
        (15, 120.0, "peak"),
        (20, 117.0, "trough"),
        (25, 125.0, "peak"),
    ]
    assert _validate_impulse_up(valid, rules) is True
    assert _validate_impulse_up(valid[:-1], rules) is False


def test_impulse_up_rejects_wave3_shorter_than_wave1() -> None:
    rules = _rules()
    invalid = [
        (0, 100.0, "trough"),
        (5, 120.0, "peak"),
        (10, 110.0, "trough"),
        (15, 125.0, "peak"),
        (20, 118.0, "trough"),
        (25, 126.0, "peak"),
    ]
    assert _validate_impulse_up(invalid, rules) is False


def test_impulse_down_mirror_rules() -> None:
    rules = _rules()
    valid = [
        (0, 125.0, "peak"),
        (5, 110.0, "trough"),
        (10, 115.0, "peak"),
        (15, 100.0, "trough"),
        (20, 105.0, "peak"),
        (25, 95.0, "trough"),
    ]
    assert _validate_impulse_down(valid, rules) is True


def test_abc_corrective_down_structure() -> None:
    rules = _rules()
    valid = [
        (0, 120.0, "peak"),
        (5, 110.0, "trough"),
        (10, 116.0, "peak"),
        (15, 108.0, "trough"),
    ]
    assert _validate_abc_down(valid, rules) is True


def test_abc_corrective_up_structure() -> None:
    rules = _rules()
    valid = [
        (0, 90.0, "trough"),
        (5, 100.0, "peak"),
        (10, 94.0, "trough"),
        (15, 102.0, "peak"),
    ]
    assert _validate_abc_up(valid, rules) is True


def test_loose_old_logic_would_have_tagged_any_trend() -> None:
    """Five alternating swings without valid wave ratios should not pass."""
    rules = _rules()
    almost = [
        (0, 100.0, "trough"),
        (5, 101.0, "peak"),
        (10, 100.5, "trough"),
        (15, 101.5, "peak"),
        (20, 100.8, "trough"),
        (25, 101.2, "peak"),
    ]
    assert _validate_impulse_up(almost, rules) is False
