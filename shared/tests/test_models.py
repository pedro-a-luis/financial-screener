"""
Test suite for shared data models

Run with: pytest shared/tests/test_models.py -v
"""

import pytest
from datetime import date, datetime
from decimal import Decimal

from models import (
    Asset,
    AssetType,
    Stock,
    StockPrice,
    StockFundamentals,
    ETF,
    ETFDetails,
    Bond,
    BondDetails,
    BondType,
    NewsArticle,
    Sentiment,
    Recommendation,
    RecommendationLevel,
    Portfolio,
    PortfolioHolding,
    Transaction,
    TransactionType,
)


class TestAssetModel:
    """Test Asset model."""

    def test_create_asset(self):
        """Test creating an asset."""
        asset = Asset(
            id=1,
            ticker="AAPL",
            name="Apple Inc.",
            asset_type=AssetType.STOCK,
            exchange="NASDAQ",
            sector="Technology",
        )

        assert asset.ticker == "AAPL"
        assert asset.name == "Apple Inc."
        assert asset.asset_type == AssetType.STOCK
        assert asset.exchange == "NASDAQ"

    def test_ticker_normalization(self):
        """Test ticker is normalized to uppercase."""
        asset = Asset(
            id=1, ticker="aapl", name="Apple", asset_type=AssetType.STOCK
        )

        assert asset.ticker == "AAPL"

    def test_asset_type_enum(self):
        """Test asset type accepts string and converts to enum."""
        asset = Asset(id=1, ticker="AAPL", name="Apple", asset_type="stock")

        assert asset.asset_type == AssetType.STOCK
        assert isinstance(asset.asset_type, AssetType)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        asset = Asset(
            id=1,
            ticker="AAPL",
            name="Apple Inc.",
            asset_type=AssetType.STOCK,
        )

        data = asset.to_dict()

        assert data["ticker"] == "AAPL"
        assert data["name"] == "Apple Inc."
        assert data["asset_type"] == "stock"
        assert data["id"] == 1

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "id": 1,
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "asset_type": "stock",
            "exchange": "NASDAQ",
        }

        asset = Asset.from_dict(data)

        assert asset.ticker == "AAPL"
        assert asset.asset_type == AssetType.STOCK


class TestStockModels:
    """Test Stock-related models."""

    def test_stock_price(self):
        """Test StockPrice model."""
        price = StockPrice(
            id=1,
            asset_id=1,
            date=date(2024, 1, 1),
            open=Decimal("150.00"),
            high=Decimal("155.00"),
            low=Decimal("149.00"),
            close=Decimal("154.00"),
            volume=1000000,
        )

        assert price.close == Decimal("154.00")
        assert price.volume == 1000000

    def test_stock_fundamentals(self):
        """Test StockFundamentals model."""
        fundamentals = StockFundamentals(
            id=1,
            asset_id=1,
            period_end_date=date(2024, 12, 31),
            period_type="annual",
            pe_ratio=Decimal("25.5"),
            pb_ratio=Decimal("8.2"),
            roe=Decimal("0.35"),
            revenue=50000000000,
            net_income=10000000000,
        )

        assert fundamentals.pe_ratio == Decimal("25.5")
        assert fundamentals.roe == Decimal("0.35")

    def test_stock_fundamentals_to_dict(self):
        """Test fundamentals to_dict groups metrics."""
        fundamentals = StockFundamentals(
            id=1,
            asset_id=1,
            period_end_date=date(2024, 12, 31),
            period_type="annual",
            pe_ratio=Decimal("25.5"),
            roe=Decimal("0.35"),
        )

        data = fundamentals.to_dict()

        # Should have grouped sections
        assert "valuation" in data
        assert "profitability" in data
        assert data["valuation"]["pe_ratio"] == 25.5
        assert data["profitability"]["roe"] == 0.35

    def test_stock_composite(self):
        """Test Stock composite model."""
        asset = Asset(id=1, ticker="AAPL", name="Apple", asset_type=AssetType.STOCK)
        price = StockPrice(
            id=1,
            asset_id=1,
            date=date(2024, 1, 1),
            open=Decimal("150.00"),
            high=Decimal("155.00"),
            low=Decimal("149.00"),
            close=Decimal("154.00"),
            volume=1000000,
        )

        stock = Stock(asset=asset, price=price)

        assert stock.asset.ticker == "AAPL"
        assert stock.price.close == Decimal("154.00")

    def test_stock_type_validation(self):
        """Test Stock validates asset_type is STOCK."""
        asset = Asset(id=1, ticker="SPY", name="SPDR S&P 500", asset_type=AssetType.ETF)

        with pytest.raises(ValueError, match="Asset type must be STOCK"):
            Stock(asset=asset)


class TestETFModels:
    """Test ETF-related models."""

    def test_etf_details(self):
        """Test ETFDetails model."""
        details = ETFDetails(
            id=1,
            asset_id=1,
            expense_ratio=Decimal("0.0003"),
            aum=400000000000,
            ytd_return=Decimal("0.15"),
        )

        assert details.expense_ratio == Decimal("0.0003")
        assert details.aum == 400000000000

    def test_etf_composite(self):
        """Test ETF composite model."""
        asset = Asset(id=1, ticker="SPY", name="SPDR S&P 500", asset_type=AssetType.ETF)
        etf = ETF(asset=asset)

        assert etf.asset.ticker == "SPY"
        assert etf.holdings == []

    def test_etf_type_validation(self):
        """Test ETF validates asset_type."""
        asset = Asset(id=1, ticker="AAPL", name="Apple", asset_type=AssetType.STOCK)

        with pytest.raises(ValueError, match="Asset type must be ETF"):
            ETF(asset=asset)


class TestBondModels:
    """Test Bond-related models."""

    def test_bond_details(self):
        """Test BondDetails model."""
        details = BondDetails(
            id=1,
            asset_id=1,
            issuer="US Treasury",
            bond_type="government",
            coupon_rate=Decimal("0.04"),
            yield_to_maturity=Decimal("0.045"),
            maturity_date=date(2030, 12, 31),
        )

        assert details.coupon_rate == Decimal("0.04")
        assert details.bond_type == "government"

    def test_bond_type_normalization(self):
        """Test bond_type normalizes to enum value."""
        details = BondDetails(
            id=1, asset_id=1, bond_type="GOVERNMENT"  # Uppercase
        )

        assert details.bond_type == BondType.GOVERNMENT.value

    def test_bond_years_to_maturity(self):
        """Test calculating years to maturity."""
        asset = Asset(id=1, ticker="TLT", name="Treasury", asset_type=AssetType.BOND)
        details = BondDetails(
            id=1,
            asset_id=1,
            maturity_date=date(2030, 12, 31),
        )

        bond = Bond(asset=asset, details=details)
        years = bond.years_to_maturity()

        assert years is not None
        assert years > 0

    def test_bond_is_investment_grade(self):
        """Test investment grade check."""
        asset = Asset(id=1, ticker="LQD", name="Corp Bond", asset_type=AssetType.BOND)
        details = BondDetails(
            id=1, asset_id=1, credit_rating_sp="AAA"  # Investment grade
        )

        bond = Bond(asset=asset, details=details)

        assert bond.is_investment_grade() is True

    def test_bond_not_investment_grade(self):
        """Test non-investment grade check."""
        asset = Asset(id=1, ticker="HYG", name="High Yield", asset_type=AssetType.BOND)
        details = BondDetails(
            id=1, asset_id=1, credit_rating_sp="BB"  # Junk
        )

        bond = Bond(asset=asset, details=details)

        assert bond.is_investment_grade() is False


class TestNewsModels:
    """Test News and Sentiment models."""

    def test_news_article(self):
        """Test NewsArticle model."""
        article = NewsArticle(
            id=1,
            asset_id=1,
            ticker="AAPL",
            title="Apple announces new product",
            url="https://example.com/article",
            source="Reuters",
            published_date=datetime(2024, 1, 1, 10, 0, 0),
            sentiment=Sentiment.POSITIVE,
            sentiment_score=Decimal("0.75"),
        )

        assert article.ticker == "AAPL"
        assert article.sentiment == Sentiment.POSITIVE
        assert article.get_sentiment_emoji() == "😊"

    def test_ticker_normalization(self):
        """Test ticker is normalized."""
        article = NewsArticle(
            id=1,
            ticker="aapl",
            title="Test",
            url="https://test.com",
            source="Test",
            published_date=datetime.now(),
        )

        assert article.ticker == "AAPL"

    def test_sentiment_emoji(self):
        """Test sentiment emoji mapping."""
        positive = NewsArticle(
            id=1,
            ticker="AAPL",
            title="Good news",
            url="https://test.com",
            source="Test",
            published_date=datetime.now(),
            sentiment=Sentiment.POSITIVE,
        )

        negative = NewsArticle(
            id=2,
            ticker="AAPL",
            title="Bad news",
            url="https://test.com/2",
            source="Test",
            published_date=datetime.now(),
            sentiment=Sentiment.NEGATIVE,
        )

        assert positive.get_sentiment_emoji() == "😊"
        assert negative.get_sentiment_emoji() == "😟"


class TestRecommendationModels:
    """Test Recommendation models."""

    def test_recommendation_level_from_score(self):
        """Test determining recommendation from score."""
        assert RecommendationLevel.from_score(9.0) == RecommendationLevel.STRONG_BUY
        assert RecommendationLevel.from_score(7.5) == RecommendationLevel.BUY
        assert RecommendationLevel.from_score(6.0) == RecommendationLevel.HOLD
        assert RecommendationLevel.from_score(4.0) == RecommendationLevel.SELL
        assert RecommendationLevel.from_score(2.0) == RecommendationLevel.STRONG_SELL

    def test_recommendation_emoji(self):
        """Test recommendation emoji."""
        assert RecommendationLevel.STRONG_BUY.get_emoji() == "🚀"
        assert RecommendationLevel.BUY.get_emoji() == "📈"
        assert RecommendationLevel.HOLD.get_emoji() == "⏸️"
        assert RecommendationLevel.SELL.get_emoji() == "📉"
        assert RecommendationLevel.STRONG_SELL.get_emoji() == "⚠️"


class TestPortfolioModels:
    """Test Portfolio models."""

    def test_transaction(self):
        """Test Transaction model."""
        transaction = Transaction(
            id=1,
            portfolio_id=1,
            asset_id=1,
            ticker="AAPL",
            transaction_type=TransactionType.BUY,
            quantity=Decimal("10"),
            price=Decimal("150.00"),
            total_amount=Decimal("1500.00"),
            transaction_date=date(2024, 1, 1),
        )

        assert transaction.ticker == "AAPL"
        assert transaction.transaction_type == TransactionType.BUY
        assert transaction.quantity == Decimal("10")

    def test_portfolio_holding(self):
        """Test PortfolioHolding model."""
        holding = PortfolioHolding(
            id=1,
            portfolio_id=1,
            asset_id=1,
            ticker="AAPL",
            quantity=Decimal("10"),
            avg_buy_price=Decimal("150.00"),
            current_price=Decimal("160.00"),
            total_cost=Decimal("1500.00"),
            current_value=Decimal("1600.00"),
            unrealized_gain_loss=Decimal("100.00"),
            unrealized_gain_loss_pct=Decimal("6.67"),
        )

        assert holding.ticker == "AAPL"
        assert holding.unrealized_gain_loss == Decimal("100.00")

    def test_portfolio_holding_update_price(self):
        """Test updating current price recalculates values."""
        holding = PortfolioHolding(
            id=1,
            portfolio_id=1,
            asset_id=1,
            ticker="AAPL",
            quantity=Decimal("10"),
            avg_buy_price=Decimal("150.00"),
            current_price=Decimal("150.00"),
            total_cost=Decimal("1500.00"),
            current_value=Decimal("1500.00"),
            unrealized_gain_loss=Decimal("0.00"),
            unrealized_gain_loss_pct=Decimal("0.00"),
        )

        # Update price
        holding.update_current_price(Decimal("165.00"))

        assert holding.current_price == Decimal("165.00")
        assert holding.current_value == Decimal("1650.00")
        assert holding.unrealized_gain_loss == Decimal("150.00")
        assert holding.unrealized_gain_loss_pct == Decimal("10.00")

    def test_portfolio_summary(self):
        """Test portfolio summary calculations."""
        portfolio = Portfolio(id=1, name="My Portfolio")

        # Add holdings
        holding1 = PortfolioHolding(
            id=1,
            portfolio_id=1,
            asset_id=1,
            ticker="AAPL",
            quantity=Decimal("10"),
            avg_buy_price=Decimal("150.00"),
            current_price=Decimal("160.00"),
            total_cost=Decimal("1500.00"),
            current_value=Decimal("1600.00"),
            unrealized_gain_loss=Decimal("100.00"),
            unrealized_gain_loss_pct=Decimal("6.67"),
        )

        holding2 = PortfolioHolding(
            id=2,
            portfolio_id=1,
            asset_id=2,
            ticker="MSFT",
            quantity=Decimal("5"),
            avg_buy_price=Decimal("300.00"),
            current_price=Decimal("310.00"),
            total_cost=Decimal("1500.00"),
            current_value=Decimal("1550.00"),
            unrealized_gain_loss=Decimal("50.00"),
            unrealized_gain_loss_pct=Decimal("3.33"),
        )

        portfolio.add_holding(holding1)
        portfolio.add_holding(holding2)

        summary = portfolio.get_summary()

        assert summary["num_holdings"] == 2
        assert summary["total_value"] == 3150.0
        assert summary["total_cost"] == 3000.0
        assert summary["total_gain_loss"] == 150.0
        assert summary["total_gain_loss_pct"] == 5.0

    def test_portfolio_get_holding_by_ticker(self):
        """Test finding holding by ticker."""
        portfolio = Portfolio(id=1, name="Test")

        holding = PortfolioHolding(
            id=1,
            portfolio_id=1,
            asset_id=1,
            ticker="AAPL",
            quantity=Decimal("10"),
            avg_buy_price=Decimal("150.00"),
            current_price=Decimal("160.00"),
            total_cost=Decimal("1500.00"),
            current_value=Decimal("1600.00"),
            unrealized_gain_loss=Decimal("100.00"),
            unrealized_gain_loss_pct=Decimal("6.67"),
        )

        portfolio.add_holding(holding)

        found = portfolio.get_holding_by_ticker("AAPL")
        assert found is not None
        assert found.ticker == "AAPL"

        not_found = portfolio.get_holding_by_ticker("MSFT")
        assert not_found is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
