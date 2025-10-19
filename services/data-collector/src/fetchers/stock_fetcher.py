"""
Stock Data Fetcher using EODHD

Fetches stock price and fundamental data using EODHD API exclusively.
https://eodhd.com/financial-apis/

Free tier: 20 API calls/day
Paid tier ($99.99/month): Unlimited access
"""

import os
from datetime import date
from typing import List, Dict, Optional
import structlog
from .eodhd_fetcher import EODHDFetcher

logger = structlog.get_logger()


class StockDataFetcher:
    """Fetch stock data using EODHD API."""

    def __init__(self):
        """Initialize EODHD fetcher."""
        self.eodhd_api_key = os.getenv("EODHD_API_KEY")
        if not self.eodhd_api_key:
            raise ValueError("EODHD_API_KEY environment variable is required")

        self.eodhd_fetcher = EODHDFetcher(self.eodhd_api_key)
        logger.info("eodhd_fetcher_initialized")

    async def fetch_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> List[Dict]:
        """
        Fetch OHLCV price data for a stock using EODHD.

        Args:
            ticker: Stock symbol
            start_date: Start date
            end_date: End date

        Returns:
            List of price dictionaries
        """
        return await self.eodhd_fetcher.fetch_prices(ticker, start_date, end_date)

    async def fetch_fundamentals(self, ticker: str) -> Optional[Dict]:
        """
        Fetch fundamental data for a stock using EODHD.

        Args:
            ticker: Stock symbol

        Returns:
            Dictionary of fundamental metrics
        """
        return await self.eodhd_fetcher.fetch_fundamentals(ticker)

    async def get_stock_info(self, ticker: str) -> Optional[Dict]:
        """
        Get basic stock information using EODHD.

        Args:
            ticker: Stock symbol

        Returns:
            Basic info dict
        """
        # For now, we'll get this from fundamentals
        fundamentals = await self.fetch_fundamentals(ticker)
        if fundamentals:
            return {
                "ticker": ticker,
                "name": ticker,  # EODHD fundamentals don't provide full company name easily
                "exchange": ticker.split('.')[-1] if '.' in ticker else "US",
                "sector": fundamentals.get("sector"),
                "industry": fundamentals.get("industry"),
                "country": "USA",  # Default, would need to parse from exchange
            }
        return None
