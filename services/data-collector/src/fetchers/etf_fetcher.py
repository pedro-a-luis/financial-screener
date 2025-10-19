"""
ETF Data Fetcher using yfinance

Fetches ETF price data and ETF-specific metrics.
"""

import polars as pl
import yfinance as yf
from datetime import date
from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger()


class ETFDataFetcher:
    """Fetch ETF data using yfinance."""

    async def fetch_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> List[Dict]:
        """
        Fetch OHLCV price data for an ETF.

        Args:
            ticker: ETF symbol
            start_date: Start date
            end_date: End date

        Returns:
            List of price dictionaries
        """
        try:
            etf = yf.Ticker(ticker)
            hist = etf.history(start=start_date, end=end_date)

            if hist.empty:
                return []

            # Convert to Polars
            df = pl.from_pandas(hist.reset_index())

            df = df.rename(
                {
                    "Date": "date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )

            # Add metadata
            info = etf.info
            prices = df.to_dicts()

            if prices:
                prices[0]["name"] = info.get("longName", ticker)
                prices[0]["exchange"] = info.get("exchange", "")

            logger.info("etf_prices_fetched", ticker=ticker, count=len(prices))

            return prices

        except Exception as e:
            logger.error("fetch_etf_prices_failed", ticker=ticker, error=str(e))
            return []

    async def fetch_etf_details(self, ticker: str) -> Optional[Dict]:
        """
        Fetch ETF-specific details.

        Args:
            ticker: ETF symbol

        Returns:
            ETF details dictionary
        """
        try:
            etf = yf.Ticker(ticker)
            info = etf.info

            if not info:
                return None

            details = {
                "expense_ratio": info.get("annualReportExpenseRatio"),
                "aum": info.get("totalAssets"),
                "inception_date": info.get("fundInceptionDate"),
                "ytd_return": info.get("ytdReturn"),
                "fund_family": info.get("fundFamily"),
                "benchmark_index": info.get("category"),
            }

            # Remove None values
            details = {k: v for k, v in details.items() if v is not None}

            logger.info("etf_details_fetched", ticker=ticker, fields=len(details))

            return details

        except Exception as e:
            logger.error("fetch_etf_details_failed", ticker=ticker, error=str(e))
            return None

    async def fetch_holdings(self, ticker: str) -> List[Dict]:
        """
        Fetch ETF holdings (top holdings).

        Note: yfinance has limited holdings data.
        For comprehensive holdings, would need additional data sources.

        Args:
            ticker: ETF symbol

        Returns:
            List of holding dictionaries
        """
        try:
            etf = yf.Ticker(ticker)

            # Try to get holdings (may not be available for all ETFs)
            holdings = []

            # yfinance doesn't always provide holdings
            # This is a placeholder - in production, you'd use:
            # - etfdb.com scraping
            # - Manual data entry
            # - Paid data providers

            logger.info("etf_holdings_fetched", ticker=ticker, count=len(holdings))

            return holdings

        except Exception as e:
            logger.error("fetch_etf_holdings_failed", ticker=ticker, error=str(e))
            return []
