"""
Portfolio and transaction models.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional


class TransactionType(str, Enum):
    """Transaction type enumeration."""

    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"


@dataclass
class Transaction:
    """
    Investment transaction record.

    Simple building block for tracking buy/sell/dividend activity.
    """

    id: Optional[int]
    portfolio_id: int
    asset_id: int
    ticker: str

    # Transaction details
    transaction_type: TransactionType
    quantity: Decimal
    price: Decimal
    total_amount: Decimal
    fees: Decimal = Decimal("0.00")

    # Source info
    transaction_date: date = None
    source: str = "manual"  # 'manual', 'degiro', 'api'
    external_id: Optional[str] = None

    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Normalize data."""
        if self.ticker:
            self.ticker = self.ticker.upper()

        if isinstance(self.transaction_type, str):
            self.transaction_type = TransactionType(self.transaction_type.lower())

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "portfolio_id": self.portfolio_id,
            "asset_id": self.asset_id,
            "ticker": self.ticker,
            "transaction_type": self.transaction_type.value,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "total_amount": float(self.total_amount),
            "fees": float(self.fees),
            "transaction_date": (
                self.transaction_date.isoformat() if self.transaction_date else None
            ),
            "source": self.source,
            "external_id": self.external_id,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class PortfolioHolding:
    """
    Current position in a portfolio.

    Represents aggregated state from all transactions for an asset.
    """

    id: Optional[int]
    portfolio_id: int
    asset_id: int
    ticker: str

    # Position details
    quantity: Decimal
    avg_buy_price: Decimal
    current_price: Decimal

    # Calculated values
    total_cost: Decimal
    current_value: Decimal
    unrealized_gain_loss: Decimal
    unrealized_gain_loss_pct: Decimal

    # Metadata
    first_purchase_date: Optional[date] = None
    last_updated: datetime = field(default_factory=datetime.now)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Normalize data."""
        if self.ticker:
            self.ticker = self.ticker.upper()

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "portfolio_id": self.portfolio_id,
            "asset_id": self.asset_id,
            "ticker": self.ticker,
            "position": {
                "quantity": float(self.quantity),
                "avg_buy_price": float(self.avg_buy_price),
                "current_price": float(self.current_price),
            },
            "value": {
                "total_cost": float(self.total_cost),
                "current_value": float(self.current_value),
                "unrealized_gain_loss": float(self.unrealized_gain_loss),
                "unrealized_gain_loss_pct": float(self.unrealized_gain_loss_pct),
            },
            "metadata": {
                "first_purchase_date": (
                    self.first_purchase_date.isoformat()
                    if self.first_purchase_date
                    else None
                ),
                "last_updated": self.last_updated.isoformat(),
            },
        }

    def update_current_price(self, new_price: Decimal):
        """
        Update current price and recalculate derived values.

        This is a single-purpose function following KISS principle.
        """
        self.current_price = new_price
        self.current_value = self.quantity * new_price
        self.unrealized_gain_loss = self.current_value - self.total_cost

        if self.total_cost > 0:
            self.unrealized_gain_loss_pct = (
                self.unrealized_gain_loss / self.total_cost * 100
            )
        else:
            self.unrealized_gain_loss_pct = Decimal("0.00")

        self.last_updated = datetime.now()


@dataclass
class Portfolio:
    """
    Investment portfolio.

    Container for holdings and associated metadata.
    """

    id: Optional[int]
    name: str
    description: Optional[str] = None
    user_id: Optional[str] = None
    is_default: bool = False

    # Holdings (populated separately)
    holdings: List[PortfolioHolding] = field(default_factory=list)

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self, include_holdings: bool = True) -> dict:
        """Convert to dictionary."""
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "user_id": self.user_id,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_holdings:
            result["holdings"] = [h.to_dict() for h in self.holdings]
            result["summary"] = self.get_summary()

        return result

    def get_summary(self) -> dict:
        """
        Calculate portfolio summary statistics.

        Composition of small calculations.
        """
        if not self.holdings:
            return {
                "num_holdings": 0,
                "total_value": 0.0,
                "total_cost": 0.0,
                "total_gain_loss": 0.0,
                "total_gain_loss_pct": 0.0,
            }

        total_value = sum(float(h.current_value) for h in self.holdings)
        total_cost = sum(float(h.total_cost) for h in self.holdings)
        total_gain_loss = total_value - total_cost

        gain_loss_pct = (total_gain_loss / total_cost * 100) if total_cost > 0 else 0.0

        return {
            "num_holdings": len(self.holdings),
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_gain_loss": round(total_gain_loss, 2),
            "total_gain_loss_pct": round(gain_loss_pct, 2),
        }

    def add_holding(self, holding: PortfolioHolding):
        """Add a holding to the portfolio."""
        self.holdings.append(holding)

    def get_holding_by_ticker(self, ticker: str) -> Optional[PortfolioHolding]:
        """Find a holding by ticker symbol."""
        ticker_upper = ticker.upper()
        for holding in self.holdings:
            if holding.ticker == ticker_upper:
                return holding
        return None

    def get_allocation(self) -> dict:
        """
        Calculate asset allocation percentages.

        Returns allocation by asset type.
        """
        if not self.holdings:
            return {}

        total_value = sum(float(h.current_value) for h in self.holdings)

        if total_value == 0:
            return {}

        # Group by ticker (you'd need asset_type from Asset model in practice)
        # For now, return ticker-based allocation
        allocation = {}
        for holding in self.holdings:
            pct = (float(holding.current_value) / total_value) * 100
            allocation[holding.ticker] = round(pct, 2)

        return allocation
