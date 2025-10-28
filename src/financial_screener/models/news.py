"""
News and sentiment models.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional


class Sentiment(str, Enum):
    """Sentiment classification."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


@dataclass
class NewsArticle:
    """
    News article model.

    Simple building block for news data.
    """

    id: Optional[int]
    asset_id: Optional[int]
    ticker: Optional[str]

    # Article details
    title: str
    description: Optional[str]
    content: Optional[str]
    url: str

    # Source info
    source: str
    author: Optional[str]
    published_date: datetime

    # Categorization
    category: Optional[str] = None
    tags: Optional[List[str]] = None

    # Sentiment (filled by sentiment engine)
    sentiment: Optional[Sentiment] = None
    sentiment_score: Optional[Decimal] = None  # -1 to 1

    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Normalize data."""
        if self.ticker:
            self.ticker = self.ticker.upper()

        if isinstance(self.sentiment, str):
            self.sentiment = Sentiment(self.sentiment.lower())

        if self.tags is None:
            self.tags = []

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "ticker": self.ticker,
            "title": self.title,
            "description": self.description,
            "content": self.content,
            "url": self.url,
            "source": self.source,
            "author": self.author,
            "published_date": self.published_date.isoformat(),
            "category": self.category,
            "tags": self.tags,
            "sentiment": self.sentiment.value if self.sentiment else None,
            "sentiment_score": (
                float(self.sentiment_score) if self.sentiment_score else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def get_sentiment_emoji(self) -> str:
        """Get emoji representation of sentiment."""
        if not self.sentiment:
            return "❓"

        emoji_map = {
            Sentiment.POSITIVE: "😊",
            Sentiment.NEUTRAL: "😐",
            Sentiment.NEGATIVE: "😟",
        }
        return emoji_map.get(self.sentiment, "❓")


@dataclass
class SentimentSummary:
    """
    Aggregated sentiment summary for an asset over a time period.
    """

    id: Optional[int]
    asset_id: int
    ticker: str

    # Aggregate sentiment
    avg_sentiment_score: Decimal
    positive_count: int = 0
    neutral_count: int = 0
    negative_count: int = 0
    total_articles: int = 0

    # Time period
    period_start: datetime = None
    period_end: datetime = None
    period_type: str = "daily"  # 'daily', 'weekly', 'monthly'

    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "ticker": self.ticker,
            "avg_sentiment_score": float(self.avg_sentiment_score),
            "sentiment_breakdown": {
                "positive": self.positive_count,
                "neutral": self.neutral_count,
                "negative": self.negative_count,
                "total": self.total_articles,
            },
            "sentiment_percentages": {
                "positive_pct": (
                    (self.positive_count / self.total_articles * 100)
                    if self.total_articles > 0
                    else 0
                ),
                "neutral_pct": (
                    (self.neutral_count / self.total_articles * 100)
                    if self.total_articles > 0
                    else 0
                ),
                "negative_pct": (
                    (self.negative_count / self.total_articles * 100)
                    if self.total_articles > 0
                    else 0
                ),
            },
            "period": {
                "start": self.period_start.isoformat() if self.period_start else None,
                "end": self.period_end.isoformat() if self.period_end else None,
                "type": self.period_type,
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def get_overall_sentiment(self) -> Sentiment:
        """Determine overall sentiment based on average score."""
        score = float(self.avg_sentiment_score)

        if score > 0.1:
            return Sentiment.POSITIVE
        elif score < -0.1:
            return Sentiment.NEGATIVE
        else:
            return Sentiment.NEUTRAL

    def get_sentiment_emoji(self) -> str:
        """Get emoji for overall sentiment."""
        sentiment = self.get_overall_sentiment()
        emoji_map = {
            Sentiment.POSITIVE: "😊",
            Sentiment.NEUTRAL: "😐",
            Sentiment.NEGATIVE: "😟",
        }
        return emoji_map.get(sentiment, "❓")
