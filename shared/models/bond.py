"""
Bond-specific models for fixed income securities.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from .asset import Asset, AssetType


class BondType(str, Enum):
    """Bond type enumeration."""

    GOVERNMENT = "government"
    CORPORATE = "corporate"
    MUNICIPAL = "municipal"
    TIPS = "tips"  # Treasury Inflation-Protected Securities


@dataclass
class BondDetails:
    """
    Bond-specific details and metrics.

    Contains yield, duration, credit, and maturity information.
    """

    id: Optional[int]
    asset_id: int

    # Basic info
    issuer: Optional[str] = None
    bond_type: Optional[str] = None  # Will use BondType enum

    # Yield metrics
    coupon_rate: Optional[Decimal] = None
    yield_to_maturity: Optional[Decimal] = None
    current_yield: Optional[Decimal] = None
    yield_to_call: Optional[Decimal] = None
    yield_to_worst: Optional[Decimal] = None

    # Duration and sensitivity
    macaulay_duration: Optional[Decimal] = None
    modified_duration: Optional[Decimal] = None
    effective_duration: Optional[Decimal] = None
    convexity: Optional[Decimal] = None

    # Credit analysis
    credit_rating_sp: Optional[str] = None  # S&P rating
    credit_rating_moody: Optional[str] = None  # Moody's rating
    credit_rating_fitch: Optional[str] = None  # Fitch rating
    credit_spread: Optional[Decimal] = None

    # Maturity info
    issue_date: Optional[date] = None
    maturity_date: Optional[date] = None
    first_call_date: Optional[date] = None

    # Payment info
    payment_frequency: Optional[str] = None  # 'monthly', 'quarterly', etc.
    last_payment_date: Optional[date] = None
    next_payment_date: Optional[date] = None

    # Pricing
    par_value: Optional[Decimal] = None
    price: Optional[Decimal] = None
    face_value: Optional[int] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate and normalize bond_type."""
        if self.bond_type and isinstance(self.bond_type, str):
            # Normalize to BondType enum if it's a string
            self.bond_type = BondType(self.bond_type.lower()).value

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "basic_info": {
                "issuer": self.issuer,
                "bond_type": self.bond_type,
            },
            "yield": {
                "coupon_rate": (
                    float(self.coupon_rate) if self.coupon_rate else None
                ),
                "yield_to_maturity": (
                    float(self.yield_to_maturity) if self.yield_to_maturity else None
                ),
                "current_yield": (
                    float(self.current_yield) if self.current_yield else None
                ),
                "yield_to_call": (
                    float(self.yield_to_call) if self.yield_to_call else None
                ),
                "yield_to_worst": (
                    float(self.yield_to_worst) if self.yield_to_worst else None
                ),
            },
            "duration": {
                "macaulay_duration": (
                    float(self.macaulay_duration) if self.macaulay_duration else None
                ),
                "modified_duration": (
                    float(self.modified_duration) if self.modified_duration else None
                ),
                "effective_duration": (
                    float(self.effective_duration) if self.effective_duration else None
                ),
                "convexity": float(self.convexity) if self.convexity else None,
            },
            "credit": {
                "credit_rating_sp": self.credit_rating_sp,
                "credit_rating_moody": self.credit_rating_moody,
                "credit_rating_fitch": self.credit_rating_fitch,
                "credit_spread": (
                    float(self.credit_spread) if self.credit_spread else None
                ),
            },
            "maturity": {
                "issue_date": (
                    self.issue_date.isoformat() if self.issue_date else None
                ),
                "maturity_date": (
                    self.maturity_date.isoformat() if self.maturity_date else None
                ),
                "first_call_date": (
                    self.first_call_date.isoformat() if self.first_call_date else None
                ),
            },
            "payment": {
                "payment_frequency": self.payment_frequency,
                "last_payment_date": (
                    self.last_payment_date.isoformat()
                    if self.last_payment_date
                    else None
                ),
                "next_payment_date": (
                    self.next_payment_date.isoformat()
                    if self.next_payment_date
                    else None
                ),
            },
            "pricing": {
                "par_value": float(self.par_value) if self.par_value else None,
                "price": float(self.price) if self.price else None,
                "face_value": self.face_value,
            },
        }


@dataclass
class Bond:
    """
    Complete bond data combining asset info with bond-specific details.

    Composition of building blocks.
    """

    asset: Asset
    details: Optional[BondDetails] = None

    def __post_init__(self):
        """Ensure asset_type is BOND."""
        if self.asset.asset_type != AssetType.BOND:
            raise ValueError(f"Asset type must be BOND, got {self.asset.asset_type}")

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "asset": self.asset.to_dict(),
            "details": self.details.to_dict() if self.details else None,
        }

    def years_to_maturity(self) -> Optional[float]:
        """Calculate years to maturity."""
        if not self.details or not self.details.maturity_date:
            return None

        today = date.today()
        if self.details.maturity_date < today:
            return 0.0

        days_to_maturity = (self.details.maturity_date - today).days
        return round(days_to_maturity / 365.25, 2)

    def is_callable(self) -> bool:
        """Check if bond is callable."""
        return self.details and self.details.first_call_date is not None

    def is_investment_grade(self) -> bool:
        """Check if bond is investment grade (BBB-/Baa3 or higher)."""
        if not self.details:
            return False

        # S&P rating check
        if self.details.credit_rating_sp:
            rating = self.details.credit_rating_sp.upper()
            # Investment grade: AAA, AA, A, BBB
            if any(rating.startswith(r) for r in ["AAA", "AA", "A", "BBB"]):
                return True

        # Moody's rating check
        if self.details.credit_rating_moody:
            rating = self.details.credit_rating_moody.upper()
            # Investment grade: Aaa, Aa, A, Baa
            if any(rating.startswith(r) for r in ["AAA", "AA", "A", "BAA"]):
                return True

        return False
