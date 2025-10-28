"""
Financial Screener - Shared Package

This package contains shared utilities, models, and configuration used
across all microservices in the Financial Screener platform.
"""

__version__ = "0.1.0"
__author__ = "Financial Screener Team"

# Make commonly used imports available at package level
from financial_screener.config.settings import Settings, get_settings
from financial_screener.database.connection import (
    get_async_connection,
    get_sync_connection,
    get_db_cursor,
)

__all__ = [
    "Settings",
    "get_settings",
    "get_async_connection",
    "get_sync_connection",
    "get_db_cursor",
]
