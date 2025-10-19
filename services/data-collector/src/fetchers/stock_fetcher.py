"""
Stock Data Fetcher using yfinance

Fetches stock price and fundamental data, converts to Polars for efficiency.
"""

import polars as pl
import yfinance as yf
from datetime import date, datetime
from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger()


class StockDataFetcher:
    """Fetch stock data using yfinance and convert to Polars."""

    async def fetch_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> List[Dict]:
        """
        Fetch OHLCV price data for a stock.

        Args:
            ticker: Stock symbol
            start_date: Start date
            end_date: End date

        Returns:
            List of price dictionaries
        """
        try:
            # Fetch data using yfinance
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning("no_price_data", ticker=ticker)
                return []

            # Convert pandas to Polars (fast conversion)
            df = pl.from_pandas(hist.reset_index())

            # Rename columns to match our schema
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
            info = stock.info
            exchange = info.get("exchange", "")
            name = info.get("longName", ticker)

            # Convert to list of dicts
            prices = df.to_dicts()

            # Add metadata to first record for asset creation
            if prices:
                prices[0]["name"] = name
                prices[0]["exchange"] = exchange

            logger.info(
                "prices_fetched", ticker=ticker, count=len(prices), exchange=exchange
            )

            return prices

        except Exception as e:
            logger.error("fetch_prices_failed", ticker=ticker, error=str(e))
            return []

    async def fetch_fundamentals(self, ticker: str) -> Optional[Dict]:
        """
        Fetch fundamental data for a stock.

        Args:
            ticker: Stock symbol

        Returns:
            Dictionary of fundamental metrics
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            if not info:
                logger.warning("no_fundamental_data", ticker=ticker)
                return None

            # Extract fundamental metrics
            fundamentals = {
                "period_end_date": date.today(),
                "period_type": "annual",
                # Valuation
                "market_cap": info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "pe_ratio": info.get("trailingPE"),
                "pb_ratio": info.get("priceToBook"),
                "ps_ratio": info.get("priceToSalesTrailing12Months"),
                "peg_ratio": info.get("pegRatio"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                # Profitability
                "gross_margin": info.get("grossMargins"),
                "operating_margin": info.get("operatingMargins"),
                "profit_margin": info.get("profitMargins"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                # Financial health
                "current_ratio": info.get("currentRatio"),
                "quick_ratio": info.get("quickRatio"),
                "debt_to_equity": info.get("debtToEquity"),
                # Cash flow
                "operating_cash_flow": info.get("operatingCashflow"),
                "free_cash_flow": info.get("freeCashflow"),
                # Income statement
                "revenue": info.get("totalRevenue"),
                "gross_profit": info.get("grossProfits"),
                "ebitda": info.get("ebitda"),
                "net_income": info.get("netIncomeToCommon"),
                "eps": info.get("trailingEps"),
                # Growth
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                # Dividend
                "dividend_yield": info.get("dividendYield"),
                "dividend_per_share": info.get("dividendRate"),
                "payout_ratio": info.get("payoutRatio"),
            }

            # Remove None values
            fundamentals = {k: v for k, v in fundamentals.items() if v is not None}

            logger.info("fundamentals_fetched", ticker=ticker, metrics=len(fundamentals))

            return fundamentals

        except Exception as e:
            logger.error("fetch_fundamentals_failed", ticker=ticker, error=str(e))
            return None

    async def get_stock_info(self, ticker: str) -> Optional[Dict]:
        """
        Get basic stock information.

        Args:
            ticker: Stock symbol

        Returns:
            Basic info dict
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            return {
                "ticker": ticker,
                "name": info.get("longName", ticker),
                "exchange": info.get("exchange", ""),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "country": info.get("country", "USA"),
            }

        except Exception as e:
            logger.error("get_stock_info_failed", ticker=ticker, error=str(e))
            return None
