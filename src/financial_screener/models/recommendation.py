"""
Recommendation and screening models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional

from .asset import AssetType


class RecommendationLevel(str, Enum):
    """Buy/Sell recommendation levels."""

    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"

    def get_emoji(self) -> str:
        """Get emoji representation."""
        emoji_map = {
            RecommendationLevel.STRONG_BUY: "🚀",
            RecommendationLevel.BUY: "📈",
            RecommendationLevel.HOLD: "⏸️",
            RecommendationLevel.SELL: "📉",
            RecommendationLevel.STRONG_SELL: "⚠️",
        }
        return emoji_map.get(self, "❓")

    def get_color(self) -> str:
        """Get color code for UI."""
        color_map = {
            RecommendationLevel.STRONG_BUY: "#00C853",  # Green
            RecommendationLevel.BUY: "#64DD17",  # Light green
            RecommendationLevel.HOLD: "#2196F3",  # Blue
            RecommendationLevel.SELL: "#FF6D00",  # Orange
            RecommendationLevel.STRONG_SELL: "#D50000",  # Red
        }
        return color_map.get(self, "#9E9E9E")

    @classmethod
    def from_score(cls, score: float) -> "RecommendationLevel":
        """Determine recommendation level from composite score (0-10)."""
        if score >= 8.5:
            return cls.STRONG_BUY
        elif score >= 7.0:
            return cls.BUY
        elif score >= 5.0:
            return cls.HOLD
        elif score >= 3.0:
            return cls.SELL
        else:
            return cls.STRONG_SELL


@dataclass
class ScoreBreakdown:
    """
    Breakdown of individual scores contributing to recommendation.
    """

    fundamental: Decimal
    sentiment: Decimal
    technical: Decimal
    risk: Decimal

    # Sub-scores for fundamentals
    value: Optional[Decimal] = None
    quality: Optional[Decimal] = None
    growth: Optional[Decimal] = None
    momentum: Optional[Decimal] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "fundamental": float(self.fundamental),
            "sentiment": float(self.sentiment),
            "technical": float(self.technical),
            "risk": float(self.risk),
            "sub_scores": {
                "value": float(self.value) if self.value else None,
                "quality": float(self.quality) if self.quality else None,
                "growth": float(self.growth) if self.growth else None,
                "momentum": float(self.momentum) if self.momentum else None,
            },
        }


@dataclass
class Recommendation:
    """
    Buy/Sell recommendation for an asset.

    Combines scores from multiple analyses into actionable guidance.
    """

    asset_id: int
    ticker: str
    asset_type: AssetType

    # Overall recommendation
    recommendation: RecommendationLevel
    composite_score: Decimal  # 0-10
    confidence: Decimal  # 0-1

    # Score breakdown
    breakdown: ScoreBreakdown

    # Human-readable reasoning
    reasoning: List[str] = field(default_factory=list)

    # Suggested action
    action: Optional[str] = None

    # Timestamp
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Normalize data."""
        if self.ticker:
            self.ticker = self.ticker.upper()

        if isinstance(self.recommendation, str):
            self.recommendation = RecommendationLevel(self.recommendation)

        if isinstance(self.asset_type, str):
            self.asset_type = AssetType(self.asset_type.lower())

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "asset_id": self.asset_id,
            "ticker": self.ticker,
            "asset_type": self.asset_type.value,
            "recommendation": {
                "level": self.recommendation.value,
                "emoji": self.recommendation.get_emoji(),
                "color": self.recommendation.get_color(),
            },
            "composite_score": float(self.composite_score),
            "confidence": float(self.confidence),
            "breakdown": self.breakdown.to_dict(),
            "reasoning": self.reasoning,
            "action": self.action,
            "created_at": self.created_at.isoformat(),
        }

    def add_reasoning(self, reason: str):
        """Add a reasoning point."""
        self.reasoning.append(reason)

    def set_action(self, action: str):
        """Set the suggested action."""
        self.action = action


@dataclass
class ScreeningResult:
    """
    Complete screening result for an asset.

    Used to store and retrieve screening results from cache/database.
    """

    id: Optional[int]
    asset_id: int
    ticker: str
    asset_type: AssetType

    # Composite scores
    composite_score: Decimal
    fundamental_score: Decimal
    sentiment_score: Decimal
    technical_score: Decimal
    risk_score: Decimal

    # Recommendation
    recommendation: RecommendationLevel
    confidence: Decimal

    # Individual metric scores (for filtering)
    value_score: Optional[Decimal] = None
    quality_score: Optional[Decimal] = None
    growth_score: Optional[Decimal] = None
    momentum_score: Optional[Decimal] = None

    # Metadata
    screened_at: datetime = field(default_factory=datetime.now)
    valid_until: Optional[datetime] = None

    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Normalize data."""
        if self.ticker:
            self.ticker = self.ticker.upper()

        if isinstance(self.recommendation, str):
            self.recommendation = RecommendationLevel(self.recommendation)

        if isinstance(self.asset_type, str):
            self.asset_type = AssetType(self.asset_type.lower())

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "ticker": self.ticker,
            "asset_type": self.asset_type.value,
            "scores": {
                "composite": float(self.composite_score),
                "fundamental": float(self.fundamental_score),
                "sentiment": float(self.sentiment_score),
                "technical": float(self.technical_score),
                "risk": float(self.risk_score),
            },
            "recommendation": {
                "level": self.recommendation.value,
                "emoji": self.recommendation.get_emoji(),
                "color": self.recommendation.get_color(),
            },
            "confidence": float(self.confidence),
            "metric_scores": {
                "value": float(self.value_score) if self.value_score else None,
                "quality": float(self.quality_score) if self.quality_score else None,
                "growth": float(self.growth_score) if self.growth_score else None,
                "momentum": float(self.momentum_score) if self.momentum_score else None,
            },
            "metadata": {
                "screened_at": self.screened_at.isoformat(),
                "valid_until": (
                    self.valid_until.isoformat() if self.valid_until else None
                ),
            },
        }

    def is_valid(self) -> bool:
        """Check if screening result is still valid."""
        if not self.valid_until:
            return True

        return datetime.now() < self.valid_until

    def to_recommendation(
        self, reasoning: List[str] = None, action: str = None
    ) -> Recommendation:
        """Convert to a Recommendation object."""
        breakdown = ScoreBreakdown(
            fundamental=self.fundamental_score,
            sentiment=self.sentiment_score,
            technical=self.technical_score,
            risk=self.risk_score,
            value=self.value_score,
            quality=self.quality_score,
            growth=self.growth_score,
            momentum=self.momentum_score,
        )

        return Recommendation(
            asset_id=self.asset_id,
            ticker=self.ticker,
            asset_type=self.asset_type,
            recommendation=self.recommendation,
            composite_score=self.composite_score,
            confidence=self.confidence,
            breakdown=breakdown,
            reasoning=reasoning or [],
            action=action,
            created_at=self.screened_at,
        )
