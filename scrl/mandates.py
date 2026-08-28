"""Trading mandates. One brain per holding period. Intraday is not this stack."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mandate:
    name: str
    label: str
    horizon_days: int
    analog_fwd_days: int
    kill_stale_earnings: bool
    earnings_max_age_days: int | None
    kill_near_expiry: bool
    expiry_buffer_days: int
    analog_straddle_blocks_entry: bool
    require_healthy_specialist: bool
    regime_blocks_entry: bool
    action_vocab: tuple[str, ...]


SWING = Mandate(
    name="swing",
    label="swing (1–4 weeks)",
    horizon_days=20,
    analog_fwd_days=10,
    kill_stale_earnings=True,
    earnings_max_age_days=20,
    kill_near_expiry=True,
    expiry_buffer_days=1,
    analog_straddle_blocks_entry=True,
    require_healthy_specialist=True,
    regime_blocks_entry=True,
    action_vocab=("DENY", "ALLOW_SMALL"),
)

POSITION = Mandate(
    name="position",
    label="position (1–3 months)",
    horizon_days=60,
    analog_fwd_days=20,
    kill_stale_earnings=True,
    earnings_max_age_days=60,
    kill_near_expiry=False,
    expiry_buffer_days=0,
    analog_straddle_blocks_entry=True,
    require_healthy_specialist=False,
    regime_blocks_entry=True,
    action_vocab=("DENY", "ALLOW_SMALL"),
)

LONGTERM = Mandate(
    name="longterm",
    label="long-term (quarters to years)",
    horizon_days=252,
    analog_fwd_days=60,
    kill_stale_earnings=False,
    earnings_max_age_days=None,
    kill_near_expiry=False,
    expiry_buffer_days=0,
    analog_straddle_blocks_entry=False,
    require_healthy_specialist=False,
    regime_blocks_entry=False,
    action_vocab=("WAIT", "HOLD", "ADD_SMALL", "TRIM"),
)

MANDATES = {"swing": SWING, "position": POSITION, "longterm": LONGTERM}


def get_mandate(name: str) -> Mandate:
    key = name.strip().lower().replace("-", "").replace("_", "")
    aliases = {
        "swing": "swing",
        "position": "position",
        "pos": "position",
        "longterm": "longterm",
        "long": "longterm",
        "invest": "longterm",
        "intraday": "intraday",
        "scalp": "intraday",
    }
    mapped = aliases.get(key, key)
    if mapped == "intraday":
        raise ValueError(
            "Intraday is a different system: 1-minute bars, costs, session clock, "
            "and NSE microstructure. Daily Yahoo data cannot support it. "
            "Use --mandate swing|position|longterm."
        )
    if mapped not in MANDATES:
        raise ValueError(f"Unknown mandate {name!r}. Use swing, position, or longterm.")
    return MANDATES[mapped]
