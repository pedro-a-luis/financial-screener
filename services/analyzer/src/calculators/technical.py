"""
Technical Indicators Calculator

Calculates technical analysis indicators using Polars.
Polars is extremely fast for time-series operations like moving averages.
"""

import polars as pl
from decimal import Decimal
from typing import Optional


def calculate_momentum_metrics(prices_df: pl.DataFrame) -> Decimal:
    """
    Calculate composite momentum/technical score (0-10).

    Includes:
    - RSI (Relative Strength Index)
    - MACD
    - Moving average crossovers
    - Price momentum

    Args:
        prices_df: Polars DataFrame with OHLCV data

    Returns:
        Decimal: Momentum score (0-10)
    """
    if prices_df.is_empty() or len(prices_df) < 50:
        return Decimal("5.0")  # Need at least 50 days for meaningful analysis

    # Sort by date (Polars is very fast at this)
    df = prices_df.sort("date")

    # Calculate technical indicators using Polars expressions (vectorized, fast!)
    df = df.with_columns(
        [
            # Simple Moving Averages
            pl.col("close").rolling_mean(window_size=20).alias("sma_20"),
            pl.col("close").rolling_mean(window_size=50).alias("sma_50"),
            pl.col("close").rolling_mean(window_size=200).alias("sma_200"),
            # RSI components
            pl.col("close").diff().alias("price_change"),
        ]
    )

    # Calculate RSI using Polars (much faster than pandas!)
    df = calculate_rsi_polars(df)

    # Get latest values
    latest = df.tail(1)

    current_price = latest.select("close").item()
    sma_20 = latest.select("sma_20").item()
    sma_50 = latest.select("sma_50").item()
    sma_200 = latest.select("sma_200").item()
    rsi = latest.select("rsi").item() if "rsi" in latest.columns else 50.0

    scores = []

    # RSI score (30-70 is neutral, <30 oversold, >70 overbought)
    if rsi:
        if rsi < 30:
            rsi_score = 8.0 + (30 - rsi) / 10  # Oversold = buying opportunity
        elif rsi > 70:
            rsi_score = 2.0 - (rsi - 70) / 10  # Overbought = selling signal
        else:
            rsi_score = 5.0 + (50 - abs(rsi - 50)) / 10
        scores.append(max(0, min(10, rsi_score)))

    # Moving average position score
    if sma_20 and sma_50 and sma_200:
        ma_score = 0.0
        # Price above all MAs = bullish
        if current_price > sma_20:
            ma_score += 2.5
        if current_price > sma_50:
            ma_score += 2.5
        if current_price > sma_200:
            ma_score += 2.5
        # Golden cross (SMA 50 > SMA 200) = bullish
        if sma_50 > sma_200:
            ma_score += 2.5
        scores.append(ma_score)

    # Price momentum (3-month return)
    if len(df) >= 60:
        price_60d_ago = df.tail(60).head(1).select("close").item()
        momentum_return = (current_price - price_60d_ago) / price_60d_ago * 100

        # Convert to 0-10 score
        # +20% or more = 10, -20% or less = 0
        momentum_score = max(0, min(10, 5 + momentum_return / 4))
        scores.append(momentum_score)

    if not scores:
        return Decimal("5.0")

    avg_score = sum(scores) / len(scores)
    return Decimal(str(round(avg_score, 2)))


def calculate_rsi_polars(df: pl.DataFrame, period: int = 14) -> pl.DataFrame:
    """
    Calculate RSI (Relative Strength Index) using Polars.

    This is MUCH faster than the pandas/ta-lib version!

    Args:
        df: Polars DataFrame with 'price_change' column
        period: RSI period (default 14)

    Returns:
        pl.DataFrame: DataFrame with 'rsi' column added
    """
    df = df.with_columns(
        [
            # Separate gains and losses
            pl.when(pl.col("price_change") > 0)
            .then(pl.col("price_change"))
            .otherwise(0)
            .alias("gain"),
            pl.when(pl.col("price_change") < 0)
            .then(-pl.col("price_change"))
            .otherwise(0)
            .alias("loss"),
        ]
    )

    # Calculate average gain and loss
    df = df.with_columns(
        [
            pl.col("gain").rolling_mean(window_size=period).alias("avg_gain"),
            pl.col("loss").rolling_mean(window_size=period).alias("avg_loss"),
        ]
    )

    # Calculate RS and RSI
    df = df.with_columns(
        [
            (pl.col("avg_gain") / pl.col("avg_loss")).alias("rs"),
        ]
    )

    df = df.with_columns(
        [
            (100 - (100 / (1 + pl.col("rs")))).alias("rsi"),
        ]
    )

    return df


def calculate_macd_polars(df: pl.DataFrame) -> pl.DataFrame:
    """
    Calculate MACD (Moving Average Convergence Divergence) using Polars.

    Args:
        df: Polars DataFrame with 'close' column

    Returns:
        pl.DataFrame: DataFrame with MACD columns added
    """
    # Calculate EMAs
    df = df.with_columns(
        [
            pl.col("close").ewm_mean(span=12).alias("ema_12"),
            pl.col("close").ewm_mean(span=26).alias("ema_26"),
        ]
    )

    # MACD line = EMA(12) - EMA(26)
    df = df.with_columns(
        [
            (pl.col("ema_12") - pl.col("ema_26")).alias("macd"),
        ]
    )

    # Signal line = EMA(9) of MACD
    df = df.with_columns(
        [
            pl.col("macd").ewm_mean(span=9).alias("macd_signal"),
        ]
    )

    # MACD histogram
    df = df.with_columns(
        [
            (pl.col("macd") - pl.col("macd_signal")).alias("macd_histogram"),
        ]
    )

    return df


def is_bullish_crossover(prices_df: pl.DataFrame) -> bool:
    """
    Check if there's a bullish moving average crossover.

    Simple boolean check using Polars.

    Args:
        prices_df: Polars DataFrame with price data

    Returns:
        bool: True if bullish crossover detected
    """
    if len(prices_df) < 50:
        return False

    df = prices_df.sort("date").with_columns(
        [
            pl.col("close").rolling_mean(window_size=20).alias("sma_20"),
            pl.col("close").rolling_mean(window_size=50).alias("sma_50"),
        ]
    )

    # Check last 5 days for crossover
    recent = df.tail(5)

    # Get SMA values
    sma_20_today = recent.tail(1).select("sma_20").item()
    sma_50_today = recent.tail(1).select("sma_50").item()
    sma_20_5d_ago = recent.head(1).select("sma_20").item()
    sma_50_5d_ago = recent.head(1).select("sma_50").item()

    # Bullish crossover: SMA 20 crosses above SMA 50
    if sma_20_5d_ago < sma_50_5d_ago and sma_20_today > sma_50_today:
        return True

    return False


def calculate_bollinger_bands(
    df: pl.DataFrame, period: int = 20, std_dev: float = 2.0
) -> pl.DataFrame:
    """
    Calculate Bollinger Bands using Polars.

    Args:
        df: Polars DataFrame with 'close' column
        period: Moving average period
        std_dev: Number of standard deviations

    Returns:
        pl.DataFrame: DataFrame with Bollinger Band columns
    """
    df = df.with_columns(
        [
            pl.col("close").rolling_mean(window_size=period).alias("bb_middle"),
            pl.col("close").rolling_std(window_size=period).alias("bb_std"),
        ]
    )

    df = df.with_columns(
        [
            (pl.col("bb_middle") + std_dev * pl.col("bb_std")).alias("bb_upper"),
            (pl.col("bb_middle") - std_dev * pl.col("bb_std")).alias("bb_lower"),
        ]
    )

    return df


def calculate_volatility(prices_df: pl.DataFrame, period: int = 30) -> float:
    """
    Calculate price volatility (standard deviation of returns).

    Args:
        prices_df: Polars DataFrame with price data
        period: Period for volatility calculation

    Returns:
        float: Annualized volatility percentage
    """
    if len(prices_df) < period:
        return 0.0

    df = prices_df.sort("date").tail(period)

    # Calculate daily returns
    df = df.with_columns(
        [
            (pl.col("close").pct_change()).alias("return"),
        ]
    )

    # Standard deviation of returns
    std_dev = df.select(pl.col("return").std()).item()

    # Annualize (assuming 252 trading days)
    annualized_vol = std_dev * (252**0.5) * 100

    return round(annualized_vol, 2)
