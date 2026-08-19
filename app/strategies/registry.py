from __future__ import annotations

from app.strategies.compression import VolatilityCompression
from app.strategies.exhaustion import ExhaustionReversal
from app.strategies.index_aligned import IndexAlignedMomentum
from app.strategies.pullback import TrendPullback

STRATEGIES = [
    ExhaustionReversal(),
    TrendPullback(),
    VolatilityCompression(),
    IndexAlignedMomentum(),
]


def get_strategies(names: list[str] | None = None):
    if not names:
        return list(STRATEGIES)
    wanted = set(names)
    return [item for item in STRATEGIES if item.name in wanted]
