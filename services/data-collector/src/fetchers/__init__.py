"""
Data Fetchers Module

Modular fetchers for different asset types.
"""

from .stock_fetcher import StockDataFetcher
from .etf_fetcher import ETFDataFetcher
from .bond_fetcher import BondDataFetcher

__all__ = ["StockDataFetcher", "ETFDataFetcher", "BondDataFetcher"]
