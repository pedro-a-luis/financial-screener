"""
Configuration for Technical Analyzer Service
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql://financial:password@postgres:5432/financial_db",
        description="PostgreSQL connection string",
    )

    database_schema: str = Field(
        default="financial_screener",
        description="PostgreSQL schema name",
    )

    # Redis (for future caching)
    redis_url: str = Field(
        default="redis://redis.redis.svc.cluster.local:6379/0",
        description="Redis connection string",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Batch settings
    batch_size: int = Field(
        default=1000,
        description="Number of tickers to process in one batch",
    )

    # Indicator calculation settings
    min_price_days: int = Field(
        default=252,
        description="Minimum number of price records required to calculate indicators (252 = 1 trading year)",
    )

    max_price_days: int = Field(
        default=500,
        description="Maximum number of recent price records to use for calculation",
    )

    # Connection pool settings
    pool_min_size: int = Field(
        default=2,
        description="Minimum database connection pool size",
    )

    pool_max_size: int = Field(
        default=10,
        description="Maximum database connection pool size",
    )

    # Processing settings
    skip_existing: bool = Field(
        default=True,
        description="Skip assets that already have up-to-date indicators",
    )

    force_recalculation: bool = Field(
        default=False,
        description="Force recalculation even if indicators are up to date",
    )
