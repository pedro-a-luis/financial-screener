"""
Bond Data Fetcher using EODHD

Bonds are treated similar to stocks in EODHD API.
"""

from datetime import date
from typing import List, Dict, Optional
import structlog
from .eodhd_fetcher import EODHDFetcher
import os

logger = structlog.get_logger()


class BondDataFetcher:
    """Fetch bond data using EODHD (similar to stocks)."""

    def __init__(self):
        """Initialize EODHD fetcher for bonds."""
        api_key = os.getenv("EODHD_API_KEY")
        if not api_key:
            raise ValueError("EODHD_API_KEY environment variable is required")
        self.eodhd_fetcher = EODHDFetcher(api_key)

    async def fetch_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> List[Dict]:
        """Fetch OHLCV price data for a bond."""
        return await self.eodhd_fetcher.fetch_prices(ticker, start_date, end_date)

    async def fetch_bond_details(self, ticker: str) -> Optional[Dict]:
        """Fetch bond-specific details (not yet implemented)."""
        logger.warning("bond_details_not_implemented", ticker=ticker)
        return None
