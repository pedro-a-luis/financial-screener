"""
ETF-specific models for exchange-traded funds.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from .asset import Asset, AssetType


@dataclass
class ETFDetails:
    """
    ETF-specific details and metrics.
    """

    id: Optional[int]
    asset_id: int

    # Basic info
    expense_ratio: Optional[Decimal] = None
    aum: Optional[int] = None  # Assets under management
    inception_date: Optional[date] = None

    # Performance metrics
    ytd_return: Optional[Decimal] = None
    one_year_return: Optional[Decimal] = None
    three_year_return: Optional[Decimal] = None
    five_year_return: Optional[Decimal] = None

    # Risk metrics
    beta: Optional[Decimal] = None
    sharpe_ratio: Optional[Decimal] = None
    sortino_ratio: Optional[Decimal] = None
    tracking_error: Optional[Decimal] = None

    # ETF structure
    fund_family: Optional[str] = None
    benchmark_index: Optional[str] = None
    replication_method: Optional[str] = None  # 'physical' or 'synthetic'

    # Holdings info
    num_holdings: Optional[int] = None
    top_10_concentration: Optional[Decimal] = None

    # Distributions
    distribution_frequency: Optional[str] = None
    last_distribution_date: Optional[date] = None
    last_distribution_amount: Optional[Decimal] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "basic_info": {
                "expense_ratio": (
                    float(self.expense_ratio) if self.expense_ratio else None
                ),
                "aum": self.aum,
                "inception_date": (
                    self.inception_date.isoformat() if self.inception_date else None
                ),
            },
            "performance": {
                "ytd_return": float(self.ytd_return) if self.ytd_return else None,
                "one_year_return": (
                    float(self.one_year_return) if self.one_year_return else None
                ),
                "three_year_return": (
                    float(self.three_year_return) if self.three_year_return else None
                ),
                "five_year_return": (
                    float(self.five_year_return) if self.five_year_return else None
                ),
            },
            "risk": {
                "beta": float(self.beta) if self.beta else None,
                "sharpe_ratio": (
                    float(self.sharpe_ratio) if self.sharpe_ratio else None
                ),
                "sortino_ratio": (
                    float(self.sortino_ratio) if self.sortino_ratio else None
                ),
                "tracking_error": (
                    float(self.tracking_error) if self.tracking_error else None
                ),
            },
            "structure": {
                "fund_family": self.fund_family,
                "benchmark_index": self.benchmark_index,
                "replication_method": self.replication_method,
                "num_holdings": self.num_holdings,
                "top_10_concentration": (
                    float(self.top_10_concentration)
                    if self.top_10_concentration
                    else None
                ),
            },
            "distributions": {
                "distribution_frequency": self.distribution_frequency,
                "last_distribution_date": (
                    self.last_distribution_date.isoformat()
                    if self.last_distribution_date
                    else None
                ),
                "last_distribution_amount": (
                    float(self.last_distribution_amount)
                    if self.last_distribution_amount
                    else None
                ),
            },
        }


@dataclass
class ETFHolding:
    """
    Individual holding within an ETF.
    """

    id: Optional[int]
    etf_asset_id: int
    holding_ticker: Optional[str]
    holding_name: Optional[str]
    weight: Optional[Decimal]  # Percentage
    shares: Optional[int] = None
    market_value: Optional[int] = None
    snapshot_date: date = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "holding_ticker": self.holding_ticker,
            "holding_name": self.holding_name,
            "weight": float(self.weight) if self.weight else None,
            "shares": self.shares,
            "market_value": self.market_value,
            "snapshot_date": self.snapshot_date.isoformat() if self.snapshot_date else None,
        }


@dataclass
class ETF:
    """
    Complete ETF data combining asset info with ETF-specific details.

    Composition of building blocks.
    """

    asset: Asset
    details: Optional[ETFDetails] = None
    holdings: Optional[List[ETFHolding]] = None

    def __post_init__(self):
        """Ensure asset_type is ETF."""
        if self.asset.asset_type != AssetType.ETF:
            raise ValueError(f"Asset type must be ETF, got {self.asset.asset_type}")

        if self.holdings is None:
            self.holdings = []

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "asset": self.asset.to_dict(),
            "details": self.details.to_dict() if self.details else None,
            "holdings": [h.to_dict() for h in self.holdings] if self.holdings else [],
            "top_holdings_count": len(self.holdings) if self.holdings else 0,
        }
