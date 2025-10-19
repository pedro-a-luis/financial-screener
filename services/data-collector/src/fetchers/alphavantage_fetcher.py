"""
Alpha Vantage Data Fetcher

Fallback fetcher when yfinance fails.
Uses Alpha Vantage API (25 calls/day free tier).
"""

import asyncio
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
import requests
import structlog

logger = structlog.get_logger()

# Rate limiting: 5 calls per minute = 12 seconds between calls
RATE_LIMIT_DELAY = 12.0


class AlphaVantageFetcher:
    """Fetch stock data using Alpha Vantage API."""

    def __init__(self, api_key: str):
        """
        Initialize Alpha Vantage fetcher.

        Args:
            api_key: Alpha Vantage API key
        """
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"
        self.last_call_time = None

    async def _rate_limit(self):
        """Enforce rate limiting (5 calls per minute)."""
        if self.last_call_time:
            elapsed = (datetime.now() - self.last_call_time).total_seconds()
            if elapsed < RATE_LIMIT_DELAY:
                wait_time = RATE_LIMIT_DELAY - elapsed
                logger.info("rate_limit_wait", seconds=wait_time)
                await asyncio.sleep(wait_time)

        self.last_call_time = datetime.now()

    async def fetch_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> List[Dict]:
        """
        Fetch OHLCV price data for a stock.

        Args:
            ticker: Stock symbol (without exchange suffix)
            start_date: Start date
            end_date: End date

        Returns:
            List of price dictionaries
        """
        try:
            # Remove exchange suffix if present (Alpha Vantage doesn't use them)
            clean_ticker = ticker.split('.')[0]

            await self._rate_limit()

            # Use TIME_SERIES_DAILY_ADJUSTED for comprehensive data
            params = {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": clean_ticker,
                "outputsize": "full",  # Get full history
                "apikey": self.api_key,
            }

            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Check for API errors
            if "Error Message" in data:
                logger.error("alphavantage_error", ticker=ticker, error=data["Error Message"])
                return []

            if "Note" in data:
                logger.warning("alphavantage_rate_limit", ticker=ticker, note=data["Note"])
                return []

            # Extract time series data
            time_series = data.get("Time Series (Daily)", {})
            if not time_series:
                logger.warning("no_alphavantage_data", ticker=ticker)
                return []

            # Convert to our format
            prices = []
            for date_str, values in time_series.items():
                price_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                # Filter by date range
                if start_date <= price_date <= end_date:
                    prices.append({
                        "date": price_date,
                        "open": float(values["1. open"]),
                        "high": float(values["2. high"]),
                        "low": float(values["3. low"]),
                        "close": float(values["4. close"]),
                        "volume": int(float(values["6. volume"])),
                    })

            # Sort by date
            prices.sort(key=lambda x: x["date"])

            # Get company info from global quote
            if prices:
                quote_info = await self._fetch_quote(clean_ticker)
                if quote_info:
                    prices[0]["name"] = quote_info.get("name", ticker)
                    prices[0]["exchange"] = quote_info.get("exchange", "")

            logger.info(
                "alphavantage_prices_fetched",
                ticker=ticker,
                count=len(prices),
            )

            return prices

        except Exception as e:
            logger.error("alphavantage_fetch_failed", ticker=ticker, error=str(e))
            return []

    async def _fetch_quote(self, ticker: str) -> Optional[Dict]:
        """
        Fetch current quote data for metadata.

        Args:
            ticker: Stock symbol

        Returns:
            Dictionary with name and exchange
        """
        try:
            await self._rate_limit()

            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": ticker,
                "apikey": self.api_key,
            }

            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            quote = data.get("Global Quote", {})
            if not quote:
                return None

            return {
                "name": ticker,  # Alpha Vantage doesn't provide full name in quote
                "exchange": "",  # Not provided
                "symbol": quote.get("01. symbol", ticker),
            }

        except Exception as e:
            logger.error("alphavantage_quote_failed", ticker=ticker, error=str(e))
            return None

    async def fetch_fundamentals(self, ticker: str) -> Optional[Dict]:
        """
        Fetch fundamental data for a stock.

        Args:
            ticker: Stock symbol

        Returns:
            Dictionary of fundamental metrics
        """
        try:
            # Remove exchange suffix
            clean_ticker = ticker.split('.')[0]

            await self._rate_limit()

            # Use OVERVIEW for fundamental data
            params = {
                "function": "OVERVIEW",
                "symbol": clean_ticker,
                "apikey": self.api_key,
            }

            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data or "Symbol" not in data:
                logger.warning("no_alphavantage_fundamentals", ticker=ticker)
                return None

            # Extract fundamental metrics
            fundamentals = {
                "period_end_date": date.today(),
                "market_cap": self._safe_float(data.get("MarketCapitalization")),
                "pe_ratio": self._safe_float(data.get("PERatio")),
                "pb_ratio": self._safe_float(data.get("PriceToBookRatio")),
                "ps_ratio": self._safe_float(data.get("PriceToSalesRatioTTM")),
                "peg_ratio": self._safe_float(data.get("PEGRatio")),
                "dividend_yield": self._safe_float(data.get("DividendYield")),
                "eps": self._safe_float(data.get("EPS")),
                "revenue": self._safe_float(data.get("RevenueTTM")),
                "net_income": self._safe_float(data.get("NetIncomeTTM")),
                "profit_margin": self._safe_float(data.get("ProfitMargin")),
                "operating_margin": self._safe_float(data.get("OperatingMarginTTM")),
                "return_on_assets": self._safe_float(data.get("ReturnOnAssetsTTM")),
                "return_on_equity": self._safe_float(data.get("ReturnOnEquityTTM")),
                "debt_to_equity": self._safe_float(data.get("DebtToEquity")),
                "current_ratio": self._safe_float(data.get("CurrentRatio")),
                "quick_ratio": self._safe_float(data.get("QuickRatio")),
                "beta": self._safe_float(data.get("Beta")),
                "shares_outstanding": self._safe_float(data.get("SharesOutstanding")),
                "revenue_growth_yoy": None,  # Not directly available
                "earnings_growth_yoy": None,  # Not directly available
                "book_value_per_share": self._safe_float(data.get("BookValue")),
                "sector": data.get("Sector"),
                "industry": data.get("Industry"),
            }

            logger.info("alphavantage_fundamentals_fetched", ticker=ticker)
            return fundamentals

        except Exception as e:
            logger.error("alphavantage_fundamentals_failed", ticker=ticker, error=str(e))
            return None

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float."""
        if value is None or value == "None" or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
