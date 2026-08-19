from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "local"
ARTIFACT_DIR = ROOT / "artifacts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NSE_", extra="ignore")

    db_path: Path = DATA_DIR / "engine.db"
    artifact_dir: Path = ARTIFACT_DIR
    initial_capital: float = 1_000_000.0
    risk_fraction: float = 0.01
    max_concurrent: int = 3
    slippage_bps: float = 3.0
    top_n: int = 5
    min_ml_probability: float = 0.0
    openai_model: str = "gpt-4o-mini"
    lookback_calendar_days: int = 1500

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
