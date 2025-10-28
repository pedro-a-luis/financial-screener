"""
Centralized configuration using Pydantic Settings

This module provides validated configuration for all services using
environment variables and .env files.
"""

from functools import lru_cache
from typing import Optional
from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration"""

    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", extra="ignore")

    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    user: str = Field(..., description="Database user")
    password: str = Field(..., description="Database password")
    database: str = Field(..., description="Database name")
    schema: str = Field(default="financial_screener", description="Database schema")

    # Connection pool settings
    pool_min_size: int = Field(default=5, description="Minimum connection pool size")
    pool_max_size: int = Field(default=20, description="Maximum connection pool size")
    pool_timeout: int = Field(default=30, description="Pool connection timeout (seconds)")

    @property
    def dsn(self) -> str:
        """Get PostgreSQL DSN connection string"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

    @property
    def async_dsn(self) -> str:
        """Get async PostgreSQL DSN (for asyncpg)"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class EODHDSettings(BaseSettings):
    """EODHD API configuration"""

    model_config = SettingsConfigDict(env_prefix="EODHD_", env_file=".env", extra="ignore")

    api_key: str = Field(..., description="EODHD API key")
    base_url: str = Field(
        default="https://eodhd.com/api", description="EODHD API base URL"
    )
    daily_quota: int = Field(default=100000, description="Daily API call quota")
    timeout: int = Field(default=30, description="API request timeout (seconds)")

    # Rate limiting
    max_concurrent_requests: int = Field(
        default=10, description="Maximum concurrent API requests"
    )
    retry_attempts: int = Field(default=3, description="Number of retry attempts")
    retry_backoff_factor: float = Field(
        default=2.0, description="Exponential backoff factor"
    )


class RedisSettings(BaseSettings):
    """Redis cache and queue configuration"""

    model_config = SettingsConfigDict(env_prefix="REDIS_", env_file=".env", extra="ignore")

    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: Optional[str] = Field(default=None, description="Redis password")

    # Connection pool
    max_connections: int = Field(default=50, description="Maximum Redis connections")

    # TTL defaults (seconds)
    default_ttl: int = Field(default=3600, description="Default cache TTL (1 hour)")
    short_ttl: int = Field(default=300, description="Short cache TTL (5 minutes)")
    long_ttl: int = Field(default=86400, description="Long cache TTL (24 hours)")

    @property
    def url(self) -> str:
        """Get Redis URL"""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class LoggingSettings(BaseSettings):
    """Logging configuration"""

    model_config = SettingsConfigDict(env_prefix="LOG_", env_file=".env", extra="ignore")

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format (json or console)")
    show_locals: bool = Field(default=False, description="Show local variables in logs")


class Settings(BaseSettings):
    """Main application settings"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Environment
    environment: str = Field(default="production", description="Environment name")
    debug: bool = Field(default=False, description="Debug mode")

    # Service identification
    service_name: str = Field(default="financial-screener", description="Service name")
    service_version: str = Field(default="0.1.0", description="Service version")

    # Sub-configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    eodhd: EODHDSettings = Field(default_factory=EODHDSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is one of allowed values"""
        allowed = ["development", "staging", "production"]
        if v.lower() not in allowed:
            raise ValueError(f"Environment must be one of: {', '.join(allowed)}")
        return v.lower()


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    This function uses lru_cache to ensure settings are loaded once
    and reused across the application.

    Returns:
        Settings: Application settings

    Example:
        from financial_screener import get_settings

        settings = get_settings()
        db_dsn = settings.database.dsn
    """
    return Settings()


# Convenience function for DATABASE_URL environment variable
def get_database_url_from_env() -> Optional[str]:
    """
    Get DATABASE_URL from environment if present.

    This supports the common DATABASE_URL format used by many platforms.

    Returns:
        Optional[str]: Database URL or None
    """
    import os

    return os.getenv("DATABASE_URL")
