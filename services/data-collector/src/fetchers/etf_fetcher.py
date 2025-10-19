"""
ETF Data Fetcher using EODHD

ETFs are treated the same as stocks in EODHD API.
"""

from datetime import date
from typing import List, Dict, Optional
import structlog
from .eodhd_fetcher import EODHDFetcher
import os

logger = structlog.get_logger()


class ETFDataFetcher:
    """Fetch ETF data using EODHD (same as stocks)."""

    def __init__(self):
        """Initialize EODHD fetcher for ETFs."""
        api_key = os.getenv("EODHD_API_KEY")
        if not api_key:
            raise ValueError("EODHD_API_KEY environment variable is required")
        self.eodhd_fetcher = EODHDFetcher(api_key)

    async def fetch_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> List[Dict]:
        """Fetch OHLCV price data for an ETF."""
        return await self.eodhd_fetcher.fetch_prices(ticker, start_date, end_date)

    async def fetch_etf_details(self, ticker: str) -> Optional[Dict]:
        """Fetch ETF-specific details (not yet implemented)."""
        logger.warning("etf_details_not_implemented", ticker=ticker)
        return None

    async def fetch_holdings(self, ticker: str) -> Optional[List[Dict]]:
        """Fetch ETF holdings (not yet implemented)."""
        logger.warning("etf_holdings_not_implemented", ticker=ticker)
        return None
