"""
Shared data models for the Financial Screener application.

These models are used across all microservices for consistent data structures.
Following the modular building blocks approach - small, focused, reusable.
"""

from .asset import Asset, AssetType
from .stock import Stock, StockPrice, StockFundamentals
from .etf import ETF, ETFDetails, ETFHolding
from .bond import Bond, BondDetails, BondType
from .news import NewsArticle, Sentiment, SentimentSummary
from .recommendation import Recommendation, RecommendationLevel, ScreeningResult
from .portfolio import Portfolio, PortfolioHolding, Transaction, TransactionType

__all__ = [
    # Asset models
    "Asset",
    "AssetType",
    # Stock models
    "Stock",
    "StockPrice",
    "StockFundamentals",
    # ETF models
    "ETF",
    "ETFDetails",
    "ETFHolding",
    # Bond models
    "Bond",
    "BondDetails",
    "BondType",
    # News models
    "NewsArticle",
    "Sentiment",
    "SentimentSummary",
    # Recommendation models
    "Recommendation",
    "RecommendationLevel",
    "ScreeningResult",
    # Portfolio models
    "Portfolio",
    "PortfolioHolding",
    "Transaction",
    "TransactionType",
]
