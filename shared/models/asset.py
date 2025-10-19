"""
Asset model - base model for all tradeable assets (stocks, ETFs, bonds).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class AssetType(str, Enum):
    """Asset type enumeration."""

    STOCK = "stock"
    ETF = "etf"
    BOND = "bond"


@dataclass
class Asset:
    """
    Base asset model representing any tradeable financial instrument.

    This is a building block used by all specialized asset types.
    """

    id: Optional[int]
    ticker: str
    name: str
    asset_type: AssetType
    exchange: Optional[str] = None
    currency: str = "USD"
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate and normalize data after initialization."""
        # Normalize ticker to uppercase
        self.ticker = self.ticker.upper()

        # Ensure asset_type is AssetType enum
        if isinstance(self.asset_type, str):
            self.asset_type = AssetType(self.asset_type.lower())

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "ticker": self.ticker,
            "name": self.name,
            "asset_type": self.asset_type.value,
            "exchange": self.exchange,
            "currency": self.currency,
            "sector": self.sector,
            "industry": self.industry,
            "country": self.country,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Asset":
        """Create Asset from dictionary."""
        return cls(
            id=data.get("id"),
            ticker=data["ticker"],
            name=data["name"],
            asset_type=AssetType(data["asset_type"]),
            exchange=data.get("exchange"),
            currency=data.get("currency", "USD"),
            sector=data.get("sector"),
            industry=data.get("industry"),
            country=data.get("country"),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
