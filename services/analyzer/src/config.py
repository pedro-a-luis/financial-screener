"""
Configuration Management for Analyzer Service

Uses Pydantic Settings for type-safe configuration.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings have sensible defaults for development.
    Override in production using environment variables or .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql://financial:password@postgres:5432/financial_db?options=-c%20search_path%3Dfinancial_screener%2Cpublic",
        description="PostgreSQL connection string (with schema search_path)",
    )
    database_schema: str = Field(
        default="financial_screener",
        description="PostgreSQL schema name for this project",
    )

    # Redis (for Celery broker and result backend)
    redis_url: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection string",
    )

    # Celery
    celery_broker_url: str = Field(
        default="redis://redis:6379/0",
        description="Celery broker URL",
    )
    celery_result_backend: str = Field(
        default="redis://redis:6379/0",
        description="Celery result backend URL",
    )

    # Worker settings (tuned for Raspberry Pi)
    celery_worker_concurrency: int = Field(
        default=4,
        description="Number of concurrent worker processes (4 cores on Pi 5)",
    )
    celery_worker_prefetch_multiplier: int = Field(
        default=1,
        description="Number of tasks to prefetch (1 = one task at a time)",
    )
    celery_worker_max_tasks_per_child: int = Field(
        default=100,
        description="Restart worker after N tasks (prevent memory leaks)",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )

    # Application
    environment: str = Field(
        default="development",
        description="Environment (development, staging, production)",
    )

    # Performance tuning
    polars_thread_pool_size: int = Field(
        default=4,
        description="Polars thread pool size (match CPU cores)",
    )

    # Analysis settings
    min_data_points: int = Field(
        default=50,
        description="Minimum data points required for analysis",
    )
    screening_batch_size: int = Field(
        default=100,
        description="Number of stocks to screen in one batch",
    )

    # Cache TTL (seconds)
    cache_ttl_prices: int = Field(
        default=3600,
        description="Cache TTL for price data (1 hour)",
    )
    cache_ttl_fundamentals: int = Field(
        default=86400,
        description="Cache TTL for fundamentals (24 hours)",
    )
    cache_ttl_screening: int = Field(
        default=86400,
        description="Cache TTL for screening results (24 hours)",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set Polars thread pool size
        import polars as pl

        pl.Config.set_fmt_str_lengths(100)


# Global settings instance
settings = Settings()
