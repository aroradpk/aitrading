from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.core.paths import CONFIG_DIR, ROOT_DIR


class Thresholds(BaseModel):
    stock_1d_pct: float = 5.0
    stock_1w_pct: float = 10.0
    index_1d_pct: float = 2.0


class UniverseConfig(BaseModel):
    nifty_next_50_config: str = "config/nifty_next_50.json"
    active_count: int = 20
    yearly_trend_min_return_pct: float = 0.0


class IndexConfig(BaseModel):
    symbol: str
    yahoo: str
    type: str = "index"


class ConvictionWeights(BaseModel):
    technical: float = 0.50
    fundamental: float = 0.25
    events: float = 0.15
    theme: float = 0.10


class TechnicalConfig(BaseModel):
    timeframes: dict[str, str] = Field(default_factory=lambda: {"daily": "1d", "weekly": "1wk"})
    position_focus: str = "long"
    pattern_match_min_score: float = 0.45
    rsi_oversold: int = 35
    rsi_overbought: int = 65
    require_trend_for_setup: bool = True


class EventsConfig(BaseModel):
    lookback_days: int = 30
    move_alignment_days: int = 3
    pib_feed_url: str = "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=2"
    pib_cache_count: int = 100


class FundamentalsConfig(BaseModel):
    screener_import_dir: str = "data/fundamentals/import"
    min_score_metrics: int = 2


class BacktestConfig(BaseModel):
    conviction_min: float = 7.0
    signal_cooldown_days: int = 5
    forward_days_1d: int = 1
    forward_days_1w: int = 5
    stock_target_1d_pct: float = 5.0
    stock_target_1w_pct: float = 10.0
    index_target_1d_pct: float = 2.0


class Settings(BaseModel):
    data_dir: str = "data"
    offline_mode: bool = False
    thresholds: Thresholds = Field(default_factory=Thresholds)
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    indices: list[IndexConfig] = Field(default_factory=list)
    ohlcv: dict[str, Any] = Field(default_factory=dict)
    conviction_weights: ConvictionWeights = Field(default_factory=ConvictionWeights)
    technical: TechnicalConfig = Field(default_factory=TechnicalConfig)
    events: EventsConfig = Field(default_factory=EventsConfig)
    fundamentals: FundamentalsConfig = Field(default_factory=FundamentalsConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    trusted_source_domains: list[str] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    settings_path = CONFIG_DIR / "settings.yaml"
    if not settings_path.exists():
        return Settings()
    with settings_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return Settings.model_validate(raw)


def nifty_next_50_path() -> Path:
    settings = get_settings()
    path = ROOT_DIR / settings.universe.nifty_next_50_config
    if not path.exists():
        raise FileNotFoundError(f"Missing universe config: {path}")
    return path
