"""
Bond Data Fetcher

Fetches bond data where available. Note that individual bond data
is limited in free APIs - bond ETFs work better with yfinance.
"""

import polars as pl
import yfinance as yf
from datetime import date
from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger()


class BondDataFetcher:
    """Fetch bond data (primarily bond ETFs via yfinance)."""

    async def fetch_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> List[Dict]:
        """
        Fetch price data for bonds (usually bond ETFs).

        Args:
            ticker: Bond/Bond ETF symbol
            start_date: Start date
            end_date: End date

        Returns:
            List of price dictionaries
        """
        try:
            bond = yf.Ticker(ticker)
            hist = bond.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning("no_bond_price_data", ticker=ticker)
                return []

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

            info = bond.info
            prices = df.to_dicts()

            if prices:
                prices[0]["name"] = info.get("longName", ticker)
                prices[0]["exchange"] = info.get("exchange", "")

            logger.info("bond_prices_fetched", ticker=ticker, count=len(prices))

            return prices

        except Exception as e:
            logger.error("fetch_bond_prices_failed", ticker=ticker, error=str(e))
            return []

    async def fetch_bond_details(self, ticker: str) -> Optional[Dict]:
        """
        Fetch bond-specific details.

        Limited data available via free APIs.
        For comprehensive bond data, would need:
        - treasurydirect.gov API (for US Treasuries)
        - FINRA TRACE (for corporate bonds)
        - Or manual data entry

        Args:
            ticker: Bond symbol

        Returns:
            Bond details dictionary
        """
        try:
            bond = yf.Ticker(ticker)
            info = bond.info

            if not info:
                return None

            # Limited bond data from yfinance
            details = {
                "issuer": info.get("longName"),
                "bond_type": self._infer_bond_type(ticker, info),
                # Most bond-specific data not available via yfinance
                # Would need additional data sources
            }

            details = {k: v for k, v in details.items() if v is not None}

            logger.info("bond_details_fetched", ticker=ticker)

            return details

        except Exception as e:
            logger.error("fetch_bond_details_failed", ticker=ticker, error=str(e))
            return None

    def _infer_bond_type(self, ticker: str, info: Dict) -> str:
        """
        Infer bond type from ticker and info.

        This is heuristic-based. For accurate data, need proper data source.
        """
        ticker_upper = ticker.upper()

        # Common bond ETF patterns
        if any(x in ticker_upper for x in ["TLT", "IEF", "SHY", "AGG"]):
            return "government"
        elif any(x in ticker_upper for x in ["LQD", "HYG", "JNK"]):
            return "corporate"
        elif any(x in ticker_upper for x in ["MUB", "TFI"]):
            return "municipal"
        elif "TIP" in ticker_upper:
            return "tips"

        # Default
        category = info.get("category", "").lower()
        if "government" in category or "treasury" in category:
            return "government"
        elif "corporate" in category:
            return "corporate"
        elif "municipal" in category:
            return "municipal"

        return "government"  # Default assumption
