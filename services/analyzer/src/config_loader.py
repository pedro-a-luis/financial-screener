"""
Configuration loader for model parameters.
Loads tunable parameters from YAML config file.
"""

import os
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel, Field


class ThresholdConfig(BaseModel):
    """Quality metric thresholds."""

    # Quality
    roe_excellent: float = 0.20
    roe_good: float = 0.15
    roe_minimum: float = 0.10
    roa_excellent: float = 0.10
    roa_good: float = 0.07
    debt_to_equity_max: float = 2.0
    current_ratio_min: float = 1.5
    profit_margin_min: float = 0.10

    # Growth
    revenue_growth_excellent: float = 0.20
    revenue_growth_good: float = 0.10
    earnings_growth_excellent: float = 0.15
    earnings_growth_good: float = 0.08
    negative_growth_threshold: float = -0.05

    # Risk
    volatility_low: float = 0.15
    volatility_high: float = 0.30
    beta_low: float = 0.8
    beta_high: float = 1.2
    sharpe_ratio_excellent: float = 2.0
    sharpe_ratio_good: float = 1.0
    max_drawdown_acceptable: float = -0.20

    # Valuation
    pe_ratio_undervalued: float = 15.0
    pe_ratio_overvalued: float = 30.0
    pb_ratio_undervalued: float = 1.5
    pb_ratio_overvalued: float = 3.0
    peg_ratio_fair: float = 1.0
    dividend_yield_attractive: float = 0.03


class RecommendationConfig(BaseModel):
    """Recommendation weights and thresholds."""

    # Weights
    quality_weight: float = Field(0.30, alias="quality_score")
    growth_weight: float = Field(0.25, alias="growth_score")
    risk_weight: float = Field(0.20, alias="risk_score")
    valuation_weight: float = Field(0.15, alias="valuation_score")
    sentiment_weight: float = Field(0.10, alias="sentiment_score")

    # Thresholds
    strong_buy: float = 0.80
    buy: float = 0.65
    hold: float = 0.45
    sell: float = 0.30

    class Config:
        populate_by_name = True


class SentimentConfig(BaseModel):
    """Sentiment analysis configuration."""

    positive_threshold: float = 0.6
    negative_threshold: float = 0.4
    news_lookback_days: int = 30
    min_news_articles: int = 5


class ScreeningConfig(BaseModel):
    """Screening criteria configuration."""

    # Stock
    stock_min_market_cap: float = 1_000_000_000
    stock_min_volume: int = 100_000
    stock_max_pe_ratio: float = 50.0
    stock_min_price: float = 5.0

    # ETF
    etf_min_aum: float = 100_000_000
    etf_max_expense_ratio: float = 0.01
    etf_min_volume: int = 50_000

    # Bond
    bond_min_credit_rating: str = "BBB"
    bond_max_duration: float = 10.0
    bond_min_yield: float = 0.02


class DataCollectionConfig(BaseModel):
    """Data collection configuration."""

    batch_size: int = 100
    rate_limit_delay: float = 1.0
    max_retries: int = 3
    timeout_seconds: int = 30
    cache_duration_hours: int = 24


class CeleryConfig(BaseModel):
    """Celery task configuration."""

    task_timeout: int = 300
    task_soft_timeout: int = 270
    max_retries: int = 3
    retry_backoff: bool = True
    retry_backoff_max: int = 600


class PerformanceConfig(BaseModel):
    """Performance tuning configuration."""

    polars_threads: int = 4
    enable_lazy_evaluation: bool = True
    chunk_size: int = 10_000
    enable_query_cache: bool = True


class ModelConfig(BaseModel):
    """Complete model configuration."""

    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    recommendation: RecommendationConfig = Field(
        default_factory=RecommendationConfig
    )
    sentiment: SentimentConfig = Field(default_factory=SentimentConfig)
    screening: ScreeningConfig = Field(default_factory=ScreeningConfig)
    data_collection: DataCollectionConfig = Field(
        default_factory=DataCollectionConfig
    )
    celery: CeleryConfig = Field(default_factory=CeleryConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)


class ConfigLoader:
    """Loads and manages model configuration."""

    _instance: "ConfigLoader" = None
    _config: ModelConfig = None

    def __new__(cls):
        """Singleton pattern to ensure single config instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize config loader."""
        if self._config is None:
            self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        # Try multiple config paths
        config_paths = [
            os.getenv("MODEL_CONFIG_PATH", ""),
            "/app/config/model-config.yaml",
            "/config/model-config.yaml",
            "config/model-config.yaml",
            "../../../config/model-config.yaml",
        ]

        config_data = {}
        for path in config_paths:
            if path and Path(path).exists():
                with open(path, "r") as f:
                    config_data = yaml.safe_load(f)
                print(f"Loaded config from: {path}")
                break
        else:
            print(
                "No config file found, using defaults. Searched paths:",
                config_paths,
            )

        # Parse config sections
        self._config = ModelConfig(
            thresholds=self._parse_thresholds(
                config_data.get("thresholds", {})
            ),
            recommendation=self._parse_recommendation(
                config_data.get("recommendation_weights", {}),
                config_data.get("recommendation_thresholds", {}),
            ),
            sentiment=SentimentConfig(**config_data.get("sentiment", {})),
            screening=self._parse_screening(config_data.get("screening", {})),
            data_collection=DataCollectionConfig(
                **config_data.get("data_collection", {})
            ),
            celery=CeleryConfig(**config_data.get("celery", {})),
            performance=PerformanceConfig(
                **config_data.get("performance", {})
            ),
        )

    def _parse_thresholds(self, config: Dict[str, Any]) -> ThresholdConfig:
        """Parse threshold configuration from nested structure."""
        flat_config = {}
        for category in ["quality", "growth", "risk", "valuation"]:
            if category in config:
                flat_config.update(config[category])
        return ThresholdConfig(**flat_config)

    def _parse_recommendation(
        self, weights: Dict[str, Any], thresholds: Dict[str, Any]
    ) -> RecommendationConfig:
        """Parse recommendation configuration."""
        combined = {**weights, **thresholds}
        return RecommendationConfig(**combined)

    def _parse_screening(self, config: Dict[str, Any]) -> ScreeningConfig:
        """Parse screening configuration from nested structure."""
        flat_config = {}
        if "stock" in config:
            for k, v in config["stock"].items():
                flat_config[f"stock_{k}"] = v
        if "etf" in config:
            for k, v in config["etf"].items():
                flat_config[f"etf_{k}"] = v
        if "bond" in config:
            for k, v in config["bond"].items():
                flat_config[f"bond_{k}"] = v
        return ScreeningConfig(**flat_config)

    @property
    def config(self) -> ModelConfig:
        """Get the configuration instance."""
        return self._config

    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_config()


# Global singleton instance
_config_loader = ConfigLoader()


def get_config() -> ModelConfig:
    """Get the global configuration instance."""
    return _config_loader.config


def reload_config() -> None:
    """Reload configuration from file."""
    _config_loader.reload()
