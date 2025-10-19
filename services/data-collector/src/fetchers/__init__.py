"""
Data Fetchers Module

Modular fetchers for different asset types.
"""

from .stock_fetcher import StockDataFetcher
from .etf_fetcher import ETFDataFetcher
from .bond_fetcher import BondDataFetcher
from .alphavantage_fetcher import AlphaVantageFetcher
from .eodhd_fetcher import EODHDFetcher

__all__ = [
    "StockDataFetcher",
    "ETFDataFetcher",
    "BondDataFetcher",
    "AlphaVantageFetcher",
    "EODHDFetcher",
]
