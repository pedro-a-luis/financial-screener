"""
Financial Calculators Module

Modular building blocks for calculating various financial metrics.
Each calculator is focused on a specific type of analysis.

All calculators use Polars for high-performance data processing.
"""

from .value import (
    calculate_value_metrics,
    calculate_pe_score,
    calculate_pb_score,
    is_undervalued,
)

from .technical import (
    calculate_momentum_metrics,
    calculate_rsi_polars,
    calculate_macd_polars,
    calculate_bollinger_bands,
    calculate_volatility,
    is_bullish_crossover,
)

# Import other calculators
from .quality import calculate_quality_metrics
from .growth import calculate_growth_metrics
from .risk import calculate_risk_metrics

__all__ = [
    # Value metrics
    "calculate_value_metrics",
    "calculate_pe_score",
    "calculate_pb_score",
    "is_undervalued",
    # Technical metrics
    "calculate_momentum_metrics",
    "calculate_rsi_polars",
    "calculate_macd_polars",
    "calculate_bollinger_bands",
    "calculate_volatility",
    "is_bullish_crossover",
    # Quality metrics
    "calculate_quality_metrics",
    # Growth metrics
    "calculate_growth_metrics",
    # Risk metrics
    "calculate_risk_metrics",
]
