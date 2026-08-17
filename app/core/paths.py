from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"


def data_dir() -> Path:
    from app.core.config import get_settings

    path = ROOT_DIR / get_settings().data_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def ohlcv_daily_dir() -> Path:
    path = data_dir() / "ohlcv" / "daily"
    path.mkdir(parents=True, exist_ok=True)
    return path


def moves_dir() -> Path:
    path = data_dir() / "moves"
    path.mkdir(parents=True, exist_ok=True)
    return path


def universe_dir() -> Path:
    path = data_dir() / "universe"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir() -> Path:
    path = data_dir() / "reports" / "daily"
    path.mkdir(parents=True, exist_ok=True)
    return path


def technical_snapshots_dir() -> Path:
    path = data_dir() / "technical" / "snapshots"
    path.mkdir(parents=True, exist_ok=True)
    return path
