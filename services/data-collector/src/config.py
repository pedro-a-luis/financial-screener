"""
Configuration for Data Collector Service
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

    # API Keys (optional, for enhanced data)
    eodhd_api_key: str = Field(
        default="",
        description="EODHD API key (primary data source)",
    )

    alpha_vantage_api_key: str = Field(
        default="",
        description="Alpha Vantage API key (fallback)",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    # Batch settings
    batch_size: int = Field(
        default=100,
        description="Number of tickers to process in one batch",
    )

    # Data retention
    max_history_days: int = Field(
        default=1825,  # 5 years
        description="Maximum days of historical data to fetch",
    )
