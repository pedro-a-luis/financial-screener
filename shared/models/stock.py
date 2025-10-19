"""
Stock-specific models for equity securities.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from .asset import Asset, AssetType


@dataclass
class StockPrice:
    """
    Daily stock price data (OHLCV).

    Simple building block for price information.
    """

    id: Optional[int]
    asset_id: int
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adj_close: Optional[Decimal] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "date": self.date.isoformat(),
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": self.volume,
            "adj_close": float(self.adj_close) if self.adj_close else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class StockFundamentals:
    """
    Stock fundamental data (quarterly or annual).

    Contains all the metrics needed for fundamental analysis.
    Organized into logical groups for easy access.
    """

    id: Optional[int]
    asset_id: int
    period_end_date: date
    period_type: str  # 'quarterly' or 'annual'

    # Valuation metrics
    market_cap: Optional[int] = None
    enterprise_value: Optional[int] = None
    pe_ratio: Optional[Decimal] = None
    pb_ratio: Optional[Decimal] = None
    ps_ratio: Optional[Decimal] = None
    peg_ratio: Optional[Decimal] = None
    ev_ebitda: Optional[Decimal] = None

    # Profitability metrics
    gross_margin: Optional[Decimal] = None
    operating_margin: Optional[Decimal] = None
    profit_margin: Optional[Decimal] = None
    roe: Optional[Decimal] = None
    roa: Optional[Decimal] = None
    roic: Optional[Decimal] = None

    # Financial health
    current_ratio: Optional[Decimal] = None
    quick_ratio: Optional[Decimal] = None
    debt_to_equity: Optional[Decimal] = None
    interest_coverage: Optional[Decimal] = None

    # Cash flow
    operating_cash_flow: Optional[int] = None
    free_cash_flow: Optional[int] = None
    fcf_per_share: Optional[Decimal] = None

    # Income statement
    revenue: Optional[int] = None
    gross_profit: Optional[int] = None
    operating_income: Optional[int] = None
    net_income: Optional[int] = None
    ebitda: Optional[int] = None
    eps: Optional[Decimal] = None

    # Balance sheet
    total_assets: Optional[int] = None
    total_liabilities: Optional[int] = None
    total_debt: Optional[int] = None
    cash_and_equivalents: Optional[int] = None

    # Growth metrics
    revenue_growth: Optional[Decimal] = None
    earnings_growth: Optional[Decimal] = None

    # Dividend info
    dividend_yield: Optional[Decimal] = None
    dividend_per_share: Optional[Decimal] = None
    payout_ratio: Optional[Decimal] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "period_end_date": self.period_end_date.isoformat(),
            "period_type": self.period_type,
            # Valuation
            "valuation": {
                "market_cap": self.market_cap,
                "enterprise_value": self.enterprise_value,
                "pe_ratio": float(self.pe_ratio) if self.pe_ratio else None,
                "pb_ratio": float(self.pb_ratio) if self.pb_ratio else None,
                "ps_ratio": float(self.ps_ratio) if self.ps_ratio else None,
                "peg_ratio": float(self.peg_ratio) if self.peg_ratio else None,
                "ev_ebitda": float(self.ev_ebitda) if self.ev_ebitda else None,
            },
            # Profitability
            "profitability": {
                "gross_margin": float(self.gross_margin) if self.gross_margin else None,
                "operating_margin": (
                    float(self.operating_margin) if self.operating_margin else None
                ),
                "profit_margin": (
                    float(self.profit_margin) if self.profit_margin else None
                ),
                "roe": float(self.roe) if self.roe else None,
                "roa": float(self.roa) if self.roa else None,
                "roic": float(self.roic) if self.roic else None,
            },
            # Financial health
            "financial_health": {
                "current_ratio": (
                    float(self.current_ratio) if self.current_ratio else None
                ),
                "quick_ratio": float(self.quick_ratio) if self.quick_ratio else None,
                "debt_to_equity": (
                    float(self.debt_to_equity) if self.debt_to_equity else None
                ),
                "interest_coverage": (
                    float(self.interest_coverage) if self.interest_coverage else None
                ),
            },
            # Cash flow
            "cash_flow": {
                "operating_cash_flow": self.operating_cash_flow,
                "free_cash_flow": self.free_cash_flow,
                "fcf_per_share": (
                    float(self.fcf_per_share) if self.fcf_per_share else None
                ),
            },
            # Income statement
            "income_statement": {
                "revenue": self.revenue,
                "gross_profit": self.gross_profit,
                "operating_income": self.operating_income,
                "net_income": self.net_income,
                "ebitda": self.ebitda,
                "eps": float(self.eps) if self.eps else None,
            },
            # Balance sheet
            "balance_sheet": {
                "total_assets": self.total_assets,
                "total_liabilities": self.total_liabilities,
                "total_debt": self.total_debt,
                "cash_and_equivalents": self.cash_and_equivalents,
            },
            # Growth
            "growth": {
                "revenue_growth": (
                    float(self.revenue_growth) if self.revenue_growth else None
                ),
                "earnings_growth": (
                    float(self.earnings_growth) if self.earnings_growth else None
                ),
            },
            # Dividend
            "dividend": {
                "dividend_yield": (
                    float(self.dividend_yield) if self.dividend_yield else None
                ),
                "dividend_per_share": (
                    float(self.dividend_per_share) if self.dividend_per_share else None
                ),
                "payout_ratio": (
                    float(self.payout_ratio) if self.payout_ratio else None
                ),
            },
        }


@dataclass
class Stock:
    """
    Complete stock data combining asset info with price and fundamentals.

    This is a composition of smaller building blocks.
    """

    asset: Asset
    price: Optional[StockPrice] = None
    fundamentals: Optional[StockFundamentals] = None

    def __post_init__(self):
        """Ensure asset_type is STOCK."""
        if self.asset.asset_type != AssetType.STOCK:
            raise ValueError(f"Asset type must be STOCK, got {self.asset.asset_type}")

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "asset": self.asset.to_dict(),
            "price": self.price.to_dict() if self.price else None,
            "fundamentals": self.fundamentals.to_dict() if self.fundamentals else None,
        }
