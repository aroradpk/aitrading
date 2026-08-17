from __future__ import annotations

from app.core.config import get_settings


def is_offline_mode() -> bool:
    return get_settings().offline_mode


def require_network(operation: str) -> None:
    if is_offline_mode():
        raise RuntimeError(
            f"{operation} is disabled while offline_mode=true. "
            "Use saved files under data/ or set offline_mode: false in config/settings.yaml."
        )
