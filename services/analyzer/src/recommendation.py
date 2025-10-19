"""
Recommendation generation module.
Generates buy/sell recommendations based on configurable thresholds.
"""

from typing import Dict, Any
from config_loader import get_config


def generate_recommendation(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate buy/sell recommendation from metrics using configurable weights.

    Args:
        metrics: Dictionary containing:
            - quality_score: float (0-1)
            - growth_score: float (0-1)
            - risk_score: float (0-1)
            - valuation_score: float (0-1)
            - sentiment_score: float (0-1)

    Returns:
        Dictionary with recommendation and confidence
    """
    config = get_config()
    rec_config = config.recommendation

    # Extract scores (default to 0.5 if missing)
    quality = metrics.get("quality_score", 0.5)
    growth = metrics.get("growth_score", 0.5)
    risk = metrics.get("risk_score", 0.5)
    valuation = metrics.get("valuation_score", 0.5)
    sentiment = metrics.get("sentiment_score", 0.5)

    # Calculate weighted score
    weighted_score = (
        quality * rec_config.quality_weight +
        growth * rec_config.growth_weight +
        risk * rec_config.risk_weight +
        valuation * rec_config.valuation_weight +
        sentiment * rec_config.sentiment_weight
    )

    # Determine recommendation based on thresholds
    if weighted_score >= rec_config.strong_buy:
        recommendation = "STRONG_BUY"
    elif weighted_score >= rec_config.buy:
        recommendation = "BUY"
    elif weighted_score >= rec_config.hold:
        recommendation = "HOLD"
    elif weighted_score >= rec_config.sell:
        recommendation = "SELL"
    else:
        recommendation = "STRONG_SELL"

    return {
        "recommendation": recommendation,
        "confidence": weighted_score,
        "scores": {
            "quality": quality,
            "growth": growth,
            "risk": risk,
            "valuation": valuation,
            "sentiment": sentiment,
        },
        "weights": {
            "quality": rec_config.quality_weight,
            "growth": rec_config.growth_weight,
            "risk": rec_config.risk_weight,
            "valuation": rec_config.valuation_weight,
            "sentiment": rec_config.sentiment_weight,
        },
    }
