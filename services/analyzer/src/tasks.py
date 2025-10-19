"""
Celery Tasks for Financial Analysis

These tasks are executed by Celery workers distributed across the Raspberry Pi
cluster. Each task uses Polars for high-performance data processing.

Tasks:
- analyze_stock: Analyze a single stock
- analyze_stock_batch: Analyze batch of stocks (efficient)
- screen_stocks: Screen all stocks by criteria
- calculate_recommendations: Calculate buy/sell recommendations
"""

import polars as pl
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional

import structlog

from celery_app import app
from database import get_stock_data, save_screening_results
from calculators import (
    calculate_value_metrics,
    calculate_quality_metrics,
    calculate_growth_metrics,
    calculate_momentum_metrics,
    calculate_risk_metrics,
)
from recommendation import generate_recommendation

logger = structlog.get_logger()


@app.task(name="analyzer.tasks.analyze_stock")
def analyze_stock(ticker: str) -> Dict:
    """
    Analyze a single stock using Polars.

    This is a building block task - focused on one job.

    Args:
        ticker: Stock symbol

    Returns:
        dict: Analysis results
    """
    logger.info("analyzing_stock", ticker=ticker)

    try:
        # Load stock data from PostgreSQL using Polars
        # connectorx provides zero-copy data transfer
        prices_df = get_stock_data(ticker, table="stock_prices", days=365)
        fundamentals_df = get_stock_data(ticker, table="stock_fundamentals", periods=4)

        if prices_df.is_empty():
            logger.warning("no_price_data", ticker=ticker)
            return {"ticker": ticker, "status": "no_data"}

        # Calculate all metrics using Polars (fast!)
        value_score = calculate_value_metrics(fundamentals_df)
        quality_score = calculate_quality_metrics(fundamentals_df)
        growth_score = calculate_growth_metrics(fundamentals_df)
        momentum_score = calculate_momentum_metrics(prices_df)
        risk_score = calculate_risk_metrics(prices_df)

        # Composite score
        composite_score = (
            value_score * 0.25
            + quality_score * 0.25
            + growth_score * 0.20
            + momentum_score * 0.15
            + risk_score * 0.15
        )

        result = {
            "ticker": ticker,
            "composite_score": float(composite_score),
            "value_score": float(value_score),
            "quality_score": float(quality_score),
            "growth_score": float(growth_score),
            "momentum_score": float(momentum_score),
            "risk_score": float(risk_score),
            "analyzed_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            "stock_analyzed",
            ticker=ticker,
            composite_score=float(composite_score),
        )

        return result

    except Exception as e:
        logger.error("analyze_stock_failed", ticker=ticker, error=str(e))
        return {"ticker": ticker, "status": "error", "error": str(e)}


@app.task(name="analyzer.tasks.analyze_stock_batch")
def analyze_stock_batch(tickers: List[str]) -> Dict:
    """
    Analyze a batch of stocks efficiently using Polars.

    Batch processing is much faster than individual stocks because:
    1. Single database query for all tickers
    2. Polars vectorized operations across all stocks
    3. Reduced overhead

    This is the PREFERRED method for screening.

    Args:
        tickers: List of stock symbols

    Returns:
        dict: Batch analysis results
    """
    logger.info("analyzing_stock_batch", count=len(tickers))

    try:
        # Load data for ALL tickers in one query (efficient!)
        prices_query = f"""
            SELECT sp.*, a.ticker
            FROM stock_prices sp
            JOIN assets a ON a.id = sp.asset_id
            WHERE a.ticker IN {tuple(tickers)}
              AND sp.date >= CURRENT_DATE - INTERVAL '1 year'
            ORDER BY a.ticker, sp.date
        """

        fundamentals_query = f"""
            SELECT sf.*, a.ticker
            FROM stock_fundamentals sf
            JOIN assets a ON a.id = sf.asset_id
            WHERE a.ticker IN {tuple(tickers)}
            ORDER BY a.ticker, sf.period_end_date DESC
        """

        # Use connectorx for fast data loading into Polars
        prices_df = pl.read_database(prices_query, connection_uri=settings.database_url)
        fundamentals_df = pl.read_database(
            fundamentals_query, connection_uri=settings.database_url
        )

        # Process each stock using Polars group_by (very fast!)
        results = (
            prices_df.group_by("ticker")
            .agg(
                [
                    # Calculate metrics for each ticker
                    pl.col("close").last().alias("latest_price"),
                    pl.col("close").mean().alias("avg_price"),
                    pl.col("volume").mean().alias("avg_volume"),
                    # Calculate returns
                    (
                        (pl.col("close").last() - pl.col("close").first())
                        / pl.col("close").first()
                        * 100
                    ).alias("ytd_return"),
                ]
            )
            .collect()
        )

        # Join with fundamentals and calculate scores
        # (This is where Polars really shines - fast joins and aggregations)
        final_results = (
            results.join(
                fundamentals_df.group_by("ticker")
                .agg(
                    [
                        pl.col("pe_ratio").first(),
                        pl.col("roe").first(),
                        pl.col("debt_to_equity").first(),
                        pl.col("revenue_growth").first(),
                    ]
                )
                .collect(),
                on="ticker",
                how="left",
            )
            .with_columns(
                [
                    # Calculate composite scores using Polars expressions
                    (
                        pl.col("pe_ratio").rank() * 0.3
                        + pl.col("roe").rank() * 0.3
                        + pl.col("ytd_return").rank() * 0.4
                    ).alias("composite_score")
                ]
            )
        )

        # Convert to list of dicts for API response
        results_list = final_results.to_dicts()

        logger.info(
            "stock_batch_analyzed",
            count=len(results_list),
        )

        return {
            "status": "success",
            "count": len(results_list),
            "results": results_list,
        }

    except Exception as e:
        logger.error("analyze_stock_batch_failed", error=str(e))
        return {"status": "error", "error": str(e)}


@app.task(name="analyzer.tasks.screen_stocks")
def screen_stocks(
    criteria: Dict,
    limit: int = 100,
    asset_type: str = "stock",
) -> Dict:
    """
    Screen stocks/ETFs/bonds using Polars.

    This is a high-level screening task that filters assets by criteria.

    Args:
        criteria: Screening criteria dict
        limit: Maximum results to return
        asset_type: 'stock', 'etf', or 'bond'

    Returns:
        dict: Screening results

    Example criteria:
        {
            "pe_ratio_max": 20,
            "roe_min": 0.15,
            "debt_to_equity_max": 1.5,
            "dividend_yield_min": 0.03,
            "market_cap_min": 1000000000
        }
    """
    logger.info("screening_stocks", asset_type=asset_type, criteria=criteria)

    try:
        # Build SQL query with filters (let PostgreSQL do initial filtering)
        filters = []

        if "pe_ratio_max" in criteria:
            filters.append(f"sf.pe_ratio <= {criteria['pe_ratio_max']}")
        if "pe_ratio_min" in criteria:
            filters.append(f"sf.pe_ratio >= {criteria['pe_ratio_min']}")
        if "roe_min" in criteria:
            filters.append(f"sf.roe >= {criteria['roe_min']}")
        if "debt_to_equity_max" in criteria:
            filters.append(f"sf.debt_to_equity <= {criteria['debt_to_equity_max']}")
        if "dividend_yield_min" in criteria:
            filters.append(f"sf.dividend_yield >= {criteria['dividend_yield_min']}")
        if "market_cap_min" in criteria:
            filters.append(f"sf.market_cap >= {criteria['market_cap_min']}")

        where_clause = " AND ".join(filters) if filters else "1=1"

        query = f"""
            SELECT
                a.ticker,
                a.name,
                a.sector,
                sf.pe_ratio,
                sf.pb_ratio,
                sf.roe,
                sf.roa,
                sf.debt_to_equity,
                sf.revenue_growth,
                sf.earnings_growth,
                sf.dividend_yield,
                sf.market_cap,
                sp.close as current_price
            FROM assets a
            JOIN stock_fundamentals sf ON a.id = sf.asset_id
            JOIN LATERAL (
                SELECT close
                FROM stock_prices
                WHERE asset_id = a.id
                ORDER BY date DESC
                LIMIT 1
            ) sp ON true
            WHERE a.asset_type = '{asset_type}'
              AND a.is_active = true
              AND {where_clause}
            LIMIT {limit * 2}
        """

        # Load filtered data using Polars
        df = pl.read_database(query, connection_uri=settings.database_url)

        if df.is_empty():
            logger.info("no_results_found", criteria=criteria)
            return {"status": "success", "count": 0, "results": []}

        # Further processing and scoring using Polars
        scored_df = (
            df.with_columns(
                [
                    # Normalize scores to 0-10 scale
                    (
                        (10 - (pl.col("pe_ratio") / pl.col("pe_ratio").max() * 10))
                        .fill_null(5)
                        .alias("pe_score")
                    ),
                    (
                        (pl.col("roe") / pl.col("roe").max() * 10)
                        .fill_null(5)
                        .alias("roe_score")
                    ),
                    (
                        (10 - (pl.col("debt_to_equity") / pl.col("debt_to_equity").max() * 10))
                        .fill_null(5)
                        .alias("debt_score")
                    ),
                    (
                        (pl.col("revenue_growth") / pl.col("revenue_growth").max() * 10)
                        .fill_null(5)
                        .alias("growth_score")
                    ),
                ]
            )
            .with_columns(
                [
                    # Composite score
                    (
                        pl.col("pe_score") * 0.25
                        + pl.col("roe_score") * 0.25
                        + pl.col("debt_score") * 0.25
                        + pl.col("growth_score") * 0.25
                    ).alias("composite_score")
                ]
            )
            .sort("composite_score", descending=True)
            .head(limit)
        )

        results = scored_df.to_dicts()

        logger.info("screening_complete", count=len(results))

        return {"status": "success", "count": len(results), "results": results}

    except Exception as e:
        logger.error("screen_stocks_failed", error=str(e))
        return {"status": "error", "error": str(e)}


@app.task(name="analyzer.tasks.calculate_recommendations")
def calculate_recommendations(ticker: str, sentiment_score: Optional[float] = None) -> Dict:
    """
    Calculate buy/sell recommendation for a stock.

    Combines fundamental analysis, technical analysis, and sentiment.

    Args:
        ticker: Stock symbol
        sentiment_score: Optional sentiment score (-1 to 1)

    Returns:
        dict: Recommendation data
    """
    logger.info("calculating_recommendation", ticker=ticker)

    try:
        # Get analysis scores
        analysis = analyze_stock(ticker)

        if analysis.get("status") == "error":
            return analysis

        # Get sentiment score if not provided
        if sentiment_score is None:
            sentiment_score = get_sentiment_score(ticker)

        # Generate recommendation
        recommendation = generate_recommendation(
            ticker=ticker,
            fundamental_score=analysis["composite_score"],
            sentiment_score=sentiment_score,
            technical_score=analysis["momentum_score"],
            risk_score=analysis["risk_score"],
        )

        logger.info(
            "recommendation_calculated",
            ticker=ticker,
            recommendation=recommendation["recommendation"],
            score=recommendation["composite_score"],
        )

        return recommendation

    except Exception as e:
        logger.error("calculate_recommendation_failed", ticker=ticker, error=str(e))
        return {"ticker": ticker, "status": "error", "error": str(e)}


# Helper function
def get_sentiment_score(ticker: str) -> float:
    """Get average sentiment score for a ticker."""
    # This would query the sentiment_summary table
    # Placeholder for now
    return 0.0
