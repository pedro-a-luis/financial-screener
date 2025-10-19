#!/usr/bin/env python3
"""
Data Collector Service - Main Entry Point

Fetches stock, ETF, and bond data from yfinance and stores in PostgreSQL.
This is a modular building block that runs as a Kubernetes CronJob.

Usage:
    python main.py --mode bulk --tickers AAPL,MSFT,GOOGL
    python main.py --mode incremental --watchlist sp500
    python main.py --mode single --ticker AAPL
"""

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta
from typing import List

import structlog

from config import Settings
from database import DatabaseManager
from fetchers import StockDataFetcher, ETFDataFetcher, BondDataFetcher
from cache import CacheManager

# Configure structured logging
logger = structlog.get_logger()


async def fetch_stock_data(
    ticker: str,
    db: DatabaseManager,
    cache: CacheManager,
    mode: str = "incremental",
) -> bool:
    """
    Fetch data for a single stock.

    Args:
        ticker: Stock symbol
        db: Database manager
        cache: Cache manager
        mode: 'bulk' (full history) or 'incremental' (recent only)

    Returns:
        bool: Success status
    """
    try:
        fetcher = StockDataFetcher()

        # Determine date range
        if mode == "bulk":
            # Fetch 5 years of history
            start_date = date.today() - timedelta(days=5 * 365)
            end_date = date.today()
        else:  # incremental
            # Fetch last 7 days (to cover weekends)
            start_date = date.today() - timedelta(days=7)
            end_date = date.today()

        logger.info(
            "fetching_stock_data",
            ticker=ticker,
            mode=mode,
            start_date=str(start_date),
            end_date=str(end_date),
        )

        # Fetch price data
        prices = await fetcher.fetch_prices(ticker, start_date, end_date)

        if not prices:
            logger.warning("no_price_data", ticker=ticker)
            return False

        # Get or create asset record
        asset_id = await db.get_or_create_asset(
            ticker=ticker,
            name=prices[0].get("name", ticker),
            asset_type="stock",
            exchange=prices[0].get("exchange"),
        )

        # Store prices in database (batch insert)
        await db.insert_prices(asset_id, prices)

        # Cache latest price
        if prices:
            latest_price = prices[-1]
            await cache.set_latest_price(ticker, latest_price, ttl=3600)

        # Fetch fundamentals (quarterly)
        fundamentals = await fetcher.fetch_fundamentals(ticker)

        if fundamentals:
            await db.insert_fundamentals(asset_id, fundamentals)

        logger.info(
            "stock_data_fetched",
            ticker=ticker,
            prices_count=len(prices),
            has_fundamentals=bool(fundamentals),
        )

        return True

    except Exception as e:
        logger.error("fetch_stock_data_failed", ticker=ticker, error=str(e))
        return False


async def fetch_etf_data(
    ticker: str,
    db: DatabaseManager,
    cache: CacheManager,
    mode: str = "incremental",
) -> bool:
    """
    Fetch data for a single ETF.

    Args:
        ticker: ETF symbol
        db: Database manager
        cache: Cache manager
        mode: 'bulk' or 'incremental'

    Returns:
        bool: Success status
    """
    try:
        fetcher = ETFDataFetcher()

        # Fetch price data (same as stocks)
        if mode == "bulk":
            start_date = date.today() - timedelta(days=5 * 365)
            end_date = date.today()
        else:
            start_date = date.today() - timedelta(days=7)
            end_date = date.today()

        logger.info("fetching_etf_data", ticker=ticker, mode=mode)

        prices = await fetcher.fetch_prices(ticker, start_date, end_date)

        if not prices:
            logger.warning("no_price_data", ticker=ticker)
            return False

        # Get or create asset
        asset_id = await db.get_or_create_asset(
            ticker=ticker,
            name=prices[0].get("name", ticker),
            asset_type="etf",
            exchange=prices[0].get("exchange"),
        )

        # Store prices
        await db.insert_prices(asset_id, prices)

        # Cache latest price
        if prices:
            await cache.set_latest_price(ticker, prices[-1], ttl=3600)

        # Fetch ETF-specific details
        etf_details = await fetcher.fetch_etf_details(ticker)

        if etf_details:
            await db.upsert_etf_details(asset_id, etf_details)

        # Fetch holdings (top 10)
        holdings = await fetcher.fetch_holdings(ticker)

        if holdings:
            await db.insert_etf_holdings(asset_id, holdings)

        logger.info(
            "etf_data_fetched",
            ticker=ticker,
            prices_count=len(prices),
            holdings_count=len(holdings) if holdings else 0,
        )

        return True

    except Exception as e:
        logger.error("fetch_etf_data_failed", ticker=ticker, error=str(e))
        return False


async def fetch_bond_data(
    ticker: str,
    db: DatabaseManager,
    cache: CacheManager,
    mode: str = "incremental",
) -> bool:
    """
    Fetch data for a single bond or bond ETF.

    Args:
        ticker: Bond symbol
        db: Database manager
        cache: Cache manager
        mode: 'bulk' or 'incremental'

    Returns:
        bool: Success status
    """
    try:
        fetcher = BondDataFetcher()

        logger.info("fetching_bond_data", ticker=ticker, mode=mode)

        # Bonds may have limited price data availability
        if mode == "bulk":
            start_date = date.today() - timedelta(days=2 * 365)
            end_date = date.today()
        else:
            start_date = date.today() - timedelta(days=7)
            end_date = date.today()

        prices = await fetcher.fetch_prices(ticker, start_date, end_date)

        if not prices:
            logger.warning("no_price_data", ticker=ticker)
            # Bond data might not be available via yfinance
            # Could require manual entry or other sources
            return False

        # Get or create asset
        asset_id = await db.get_or_create_asset(
            ticker=ticker,
            name=prices[0].get("name", ticker),
            asset_type="bond",
            exchange=prices[0].get("exchange"),
        )

        # Store prices
        await db.insert_prices(asset_id, prices)

        # Fetch bond details
        bond_details = await fetcher.fetch_bond_details(ticker)

        if bond_details:
            await db.upsert_bond_details(asset_id, bond_details)

        logger.info(
            "bond_data_fetched",
            ticker=ticker,
            prices_count=len(prices),
            has_details=bool(bond_details),
        )

        return True

    except Exception as e:
        logger.error("fetch_bond_data_failed", ticker=ticker, error=str(e))
        return False


async def process_batch(
    tickers: List[str],
    asset_type: str,
    db: DatabaseManager,
    cache: CacheManager,
    mode: str = "incremental",
) -> dict:
    """
    Process a batch of tickers in parallel.

    Args:
        tickers: List of ticker symbols
        asset_type: 'stock', 'etf', or 'bond'
        db: Database manager
        cache: Cache manager
        mode: Fetch mode

    Returns:
        dict: Statistics about the batch
    """
    logger.info(
        "processing_batch",
        count=len(tickers),
        asset_type=asset_type,
        mode=mode,
    )

    # Choose appropriate fetch function
    fetch_func = {
        "stock": fetch_stock_data,
        "etf": fetch_etf_data,
        "bond": fetch_bond_data,
    }.get(asset_type)

    if not fetch_func:
        raise ValueError(f"Unknown asset type: {asset_type}")

    # Process in parallel (with concurrency limit)
    tasks = [fetch_func(ticker, db, cache, mode) for ticker in tickers]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Count successes and failures
    successes = sum(1 for r in results if r is True)
    failures = len(results) - successes

    logger.info(
        "batch_complete",
        total=len(tickers),
        successes=successes,
        failures=failures,
    )

    return {"total": len(tickers), "successes": successes, "failures": failures}


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Financial Data Collector")
    parser.add_argument(
        "--mode",
        choices=["bulk", "incremental", "single"],
        default="incremental",
        help="Fetch mode: bulk (full history), incremental (recent), single (one ticker)",
    )
    parser.add_argument(
        "--asset-type",
        choices=["stock", "etf", "bond", "all"],
        default="stock",
        help="Asset type to fetch",
    )
    parser.add_argument(
        "--tickers", type=str, help="Comma-separated list of tickers (e.g., AAPL,MSFT)"
    )
    parser.add_argument(
        "--watchlist",
        type=str,
        help="Watchlist name (e.g., sp500, nasdaq100)",
    )
    parser.add_argument(
        "--ticker", type=str, help="Single ticker to fetch (for mode=single)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=100, help="Batch size for processing"
    )

    args = parser.parse_args()

    # Load configuration
    settings = Settings()

    # Initialize database and cache
    db = DatabaseManager(settings.database_url)
    cache = CacheManager(settings.redis_url)

    try:
        await db.connect()
        await cache.connect()

        # Determine tickers to process
        tickers = []

        if args.mode == "single":
            if not args.ticker:
                logger.error("--ticker required for single mode")
                sys.exit(1)
            tickers = [args.ticker.upper()]

        elif args.tickers:
            tickers = [t.strip().upper() for t in args.tickers.split(",")]

        elif args.watchlist:
            # Load tickers from watchlist (from database)
            tickers = await db.get_watchlist_tickers(args.watchlist)

            if not tickers:
                logger.error("watchlist_not_found", watchlist=args.watchlist)
                sys.exit(1)

        else:
            logger.error("Must specify --tickers, --watchlist, or --ticker")
            sys.exit(1)

        logger.info(
            "starting_data_collection",
            mode=args.mode,
            asset_type=args.asset_type,
            ticker_count=len(tickers),
        )

        # Process in batches
        batch_size = args.batch_size
        total_stats = {"total": 0, "successes": 0, "failures": 0}

        for i in range(0, len(tickers), batch_size):
            batch = tickers[i : i + batch_size]

            logger.info("processing_batch", batch_num=i // batch_size + 1)

            stats = await process_batch(
                batch,
                args.asset_type,
                db,
                cache,
                args.mode,
            )

            total_stats["total"] += stats["total"]
            total_stats["successes"] += stats["successes"]
            total_stats["failures"] += stats["failures"]

            # Small delay between batches to avoid rate limiting
            await asyncio.sleep(2)

        logger.info("data_collection_complete", stats=total_stats)

        # Log to database (for tracking)
        await db.log_data_fetch(
            job_type=f"price_{args.asset_type}",
            status="success" if total_stats["failures"] == 0 else "partial",
            records_processed=total_stats["successes"],
        )

    except Exception as e:
        logger.error("data_collection_failed", error=str(e))
        sys.exit(1)

    finally:
        await db.disconnect()
        await cache.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
