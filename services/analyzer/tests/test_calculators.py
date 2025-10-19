"""
Test suite for calculator modules (value, technical, etc.)

Run with: pytest services/analyzer/tests/test_calculators.py -v
"""

import pytest
import polars as pl
from datetime import date, timedelta
from decimal import Decimal

import sys
sys.path.insert(0, '../src')

from calculators.value import (
    calculate_value_metrics,
    calculate_pe_score,
    calculate_pb_score,
    is_undervalued,
)
from calculators.technical import (
    calculate_momentum_metrics,
    calculate_rsi_polars,
    is_bullish_crossover,
    calculate_volatility,
)


class TestValueCalculators:
    """Test value metric calculators."""

    def test_calculate_pe_score(self):
        """Test P/E ratio scoring."""
        # Excellent P/E (< 10)
        assert calculate_pe_score(8.0) == 10.0

        # Good P/E (10-15)
        score = calculate_pe_score(12.0)
        assert 7.0 <= score <= 10.0

        # Fair P/E (15-20)
        score = calculate_pe_score(17.0)
        assert 5.0 <= score <= 7.0

        # Poor P/E (> 30)
        score = calculate_pe_score(35.0)
        assert score < 2.0

        # Invalid P/E
        assert calculate_pe_score(0.0) == 5.0
        assert calculate_pe_score(-5.0) == 5.0

    def test_calculate_pb_score(self):
        """Test P/B ratio scoring."""
        # Excellent P/B (< 1)
        assert calculate_pb_score(0.8) == 10.0

        # Good P/B (1-3)
        score = calculate_pb_score(2.0)
        assert 5.0 <= score <= 10.0

        # Poor P/B (> 5)
        score = calculate_pb_score(6.0)
        assert score < 1.0

    def test_calculate_value_metrics_with_data(self):
        """Test value metrics calculation with fundamental data."""
        # Create sample fundamentals DataFrame
        fundamentals_df = pl.DataFrame({
            "period_end_date": [date(2024, 12, 31)],
            "period_type": ["annual"],
            "pe_ratio": [15.0],
            "pb_ratio": [3.0],
            "ps_ratio": [2.0],
            "peg_ratio": [1.5],
            "ev_ebitda": [12.0],
        })

        score = calculate_value_metrics(fundamentals_df)

        # Should return a decimal between 0-10
        assert isinstance(score, Decimal)
        assert Decimal("0.0") <= score <= Decimal("10.0")

    def test_calculate_value_metrics_empty_df(self):
        """Test value metrics with empty DataFrame."""
        empty_df = pl.DataFrame()

        score = calculate_value_metrics(empty_df)

        # Should return neutral score
        assert score == Decimal("5.0")

    def test_is_undervalued(self):
        """Test undervalued check."""
        # Undervalued stock
        undervalued_df = pl.DataFrame({
            "period_end_date": [date(2024, 12, 31)],
            "pe_ratio": [10.0],
            "pb_ratio": [1.5],
            "ps_ratio": [1.0],
        })

        assert is_undervalued(undervalued_df, threshold=7.0)

        # Overvalued stock
        overvalued_df = pl.DataFrame({
            "period_end_date": [date(2024, 12, 31)],
            "pe_ratio": [50.0],
            "pb_ratio": [10.0],
            "ps_ratio": [5.0],
        })

        assert not is_undervalued(overvalued_df, threshold=7.0)


class TestTechnicalCalculators:
    """Test technical indicator calculators."""

    @pytest.fixture
    def sample_price_data(self):
        """Create sample price data for testing."""
        dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(100)]
        closes = [100 + i * 0.5 for i in range(100)]  # Uptrend

        return pl.DataFrame({
            "date": dates,
            "close": closes,
            "open": [c - 1 for c in closes],
            "high": [c + 2 for c in closes],
            "low": [c - 2 for c in closes],
            "volume": [1000000] * 100,
        })

    def test_calculate_rsi_polars(self, sample_price_data):
        """Test RSI calculation using Polars."""
        # Add price change column
        df = sample_price_data.with_columns([
            pl.col("close").diff().alias("price_change")
        ])

        # Calculate RSI
        df_with_rsi = calculate_rsi_polars(df, period=14)

        # Check RSI column exists
        assert "rsi" in df_with_rsi.columns

        # RSI should be between 0-100
        rsi_values = df_with_rsi.select("rsi").drop_nulls()
        if len(rsi_values) > 0:
            for rsi in rsi_values["rsi"]:
                assert 0 <= rsi <= 100

    def test_calculate_momentum_metrics(self, sample_price_data):
        """Test momentum metrics calculation."""
        score = calculate_momentum_metrics(sample_price_data)

        # Should return decimal between 0-10
        assert isinstance(score, Decimal)
        assert Decimal("0.0") <= score <= Decimal("10.0")

    def test_calculate_momentum_metrics_insufficient_data(self):
        """Test momentum with insufficient data."""
        # Only 10 data points (need 50+)
        small_df = pl.DataFrame({
            "date": [date(2024, 1, i + 1) for i in range(10)],
            "close": [100.0] * 10,
        })

        score = calculate_momentum_metrics(small_df)

        # Should return neutral score
        assert score == Decimal("5.0")

    def test_is_bullish_crossover(self, sample_price_data):
        """Test bullish crossover detection."""
        # Modify data to create a crossover
        df = sample_price_data.clone()

        result = is_bullish_crossover(df)

        # Should return boolean
        assert isinstance(result, bool)

    def test_calculate_volatility(self, sample_price_data):
        """Test volatility calculation."""
        volatility = calculate_volatility(sample_price_data, period=30)

        # Should return positive number (annualized %)
        assert isinstance(volatility, float)
        assert volatility >= 0

    def test_calculate_volatility_insufficient_data(self):
        """Test volatility with insufficient data."""
        small_df = pl.DataFrame({
            "date": [date(2024, 1, 1), date(2024, 1, 2)],
            "close": [100.0, 101.0],
        })

        volatility = calculate_volatility(small_df, period=30)

        # Should return 0 for insufficient data
        assert volatility == 0.0


class TestPolarsPerformance:
    """Test Polars performance characteristics."""

    def test_large_dataset_performance(self):
        """Test Polars handles large datasets efficiently."""
        import time

        # Create large dataset (10,000 rows)
        dates = [date(2000, 1, 1) + timedelta(days=i) for i in range(10000)]
        closes = [100 + (i % 100) for i in range(10000)]

        df = pl.DataFrame({
            "date": dates,
            "close": closes,
        })

        # Time a rolling mean calculation
        start = time.time()
        result = df.with_columns([
            pl.col("close").rolling_mean(window_size=50).alias("sma_50")
        ])
        duration = time.time() - start

        # Should complete very quickly (< 0.1 seconds even on Pi)
        assert duration < 0.5  # Generous for testing
        assert len(result) == 10000

    def test_polars_group_by_performance(self):
        """Test Polars group_by performance."""
        import time

        # Multiple tickers
        df = pl.DataFrame({
            "ticker": ["AAPL"] * 1000 + ["MSFT"] * 1000 + ["GOOGL"] * 1000,
            "date": [date(2024, 1, 1) + timedelta(days=i % 365) for i in range(3000)],
            "close": [100 + i * 0.1 for i in range(3000)],
        })

        start = time.time()
        result = df.group_by("ticker").agg([
            pl.col("close").mean().alias("avg_close"),
            pl.col("close").std().alias("std_close"),
        ])
        duration = time.time() - start

        # Should be very fast
        assert duration < 0.5
        assert len(result) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
