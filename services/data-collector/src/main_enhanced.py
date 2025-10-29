#!/usr/bin/env python3
"""
Enhanced Data Collector - Main Entry Point
Collects complete EODHD data with all 13 API sections

Usage:
    python main_enhanced.py --mode bulk --tickers AAPL,MSFT,GOOGL
"""

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta
from typing import List

import structlog

from config import Settings
from database import DatabaseManager
from database_enhanced import upsert_complete_asset, upsert_news_article, upsert_sentiment_score
from fetchers import EODHDFetcher
from metadata_logger import MetadataLogger

logger = structlog.get_logger()


async def fetch_complete_stock_data(
    ticker: str,
    db: DatabaseManager,
    fetcher: EODHDFetcher,
    mode: str = "incremental",
    metadata_logger: MetadataLogger = None,
    execution_id: str = None,
    skip_existing: bool = False,
    start_date_override: date = None,
    end_date_override: date = None,
) -> bool:
    """
    Fetch COMPLETE data for a stock - prices + all fundamentals + metadata.

    Args:
        ticker: Stock symbol
        db: Database manager
        fetcher: EODHD fetcher
        mode: 'bulk' (2 years) or 'incremental' (from last available date)
        metadata_logger: MetadataLogger instance for Airflow tracking
        execution_id: Airflow DAG run_id
        skip_existing: Skip if already processed in this execution
        start_date_override: Override start date for reprocessing
        end_date_override: Override end date for reprocessing

    Returns:
        bool: Success status
    """
    start_time = datetime.now()
    operation = 'fundamentals_bulk' if mode == 'bulk' else 'prices_incremental'

    # Check if already processed (idempotency)
    if skip_existing and metadata_logger and execution_id:
        already_done = await metadata_logger.check_already_processed(
            ticker, execution_id, operation
        )
        if already_done:
            logger.info("ticker_already_processed_today", ticker=ticker)
            if metadata_logger and execution_id:
                await metadata_logger.log_operation(
                    execution_id, ticker, operation, 'skipped', start_time
                )
            return True
    try:
        # Determine date range for prices
        # IMPORTANT: Never fetch today - only complete/closed trading days
        yesterday = date.today() - timedelta(days=1)

        if start_date_override and end_date_override:
            # Manual reprocessing with explicit dates
            start_date = start_date_override
            end_date = end_date_override
            logger.info("using_override_dates", ticker=ticker, start=start_date, end=end_date)
        elif mode == "bulk":
            # Bulk load: fetch 2 years of historical data up to yesterday
            start_date = yesterday - timedelta(days=2 * 365)
            end_date = yesterday
        else:  # incremental - CORRECTED LOGIC
            # Query metadata for last available date
            if metadata_logger:
                last_date = await metadata_logger.get_last_price_date(ticker)
                if last_date:
                    # Start from day AFTER last available date, up to yesterday
                    start_date = last_date + timedelta(days=1)
                    end_date = yesterday

                    # If already up to date, skip
                    if start_date > end_date:
                        logger.info("already_up_to_date", ticker=ticker, last_date=last_date)
                        return True

                    logger.info("incremental_from_last_date", ticker=ticker, last_date=last_date, start_date=start_date, end_date=end_date)
                else:
                    # No data yet, treat as bulk load
                    start_date = yesterday - timedelta(days=2 * 365)
                    end_date = yesterday
                    logger.warning("no_last_date_using_bulk", ticker=ticker)
            else:
                # Fallback: fetch last 7 days (for standalone mode without metadata)
                start_date = yesterday - timedelta(days=7)
                end_date = yesterday
                logger.warning("no_metadata_logger_using_7day_fallback", ticker=ticker)

        logger.info(
            "fetching_complete_stock_data",
            ticker=ticker,
            mode=mode,
            start_date=str(start_date),
            end_date=str(end_date),
        )

        # Step 1: Fetch complete fundamentals data (all 13 sections)
        complete_data = await fetcher.fetch_complete_asset_data(ticker)

        if not complete_data:
            logger.warning("no_complete_data", ticker=ticker)
            # Still try to get prices
            complete_data = {}

        # Step 2: Extract asset metadata from complete data
        asset_metadata = fetcher.extract_asset_metadata(complete_data, ticker)

        # Step 3: Fetch price data
        prices = await fetcher.fetch_prices(ticker, start_date, end_date)

        if not prices:
            logger.warning("no_price_data", ticker=ticker)
            # If we have fundamentals but no prices, still create asset
            if not complete_data:
                return False

        # Step 4: Store complete asset with all metadata
        async with db.pool.acquire() as conn:
            await conn.execute("SET search_path TO financial_screener")
            asset_id = await upsert_complete_asset(conn, asset_metadata, asset_type="stock")

        logger.info("asset_stored", ticker=ticker, asset_id=asset_id)

        # Step 5: Store prices if we have them
        if prices:
            await db.insert_prices(asset_id, prices)
            logger.info("prices_stored", ticker=ticker, count=len(prices))

        logger.info(
            "complete_stock_data_fetched",
            ticker=ticker,
            prices_count=len(prices) if prices else 0,
            has_fundamentals=bool(complete_data),
            sections=len(complete_data) if complete_data else 0,
        )

        # Update metadata state on success
        if metadata_logger and execution_id:
            if mode == 'bulk':
                await metadata_logger.update_asset_state_bulk(
                    ticker,
                    execution_id,
                    prices_first_date=start_date if prices else None,
                    prices_last_date=end_date if prices else None
                )
            else:  # incremental
                await metadata_logger.update_asset_state_incremental(
                    ticker,
                    execution_id,
                    prices_last_date=end_date if prices else date.today()
                )

            # Log successful operation
            await metadata_logger.log_operation(
                execution_id,
                ticker,
                operation,
                'success',
                start_time,
                records_inserted=1 if prices else 0,
                api_calls_used=11 if mode == 'bulk' else 1
            )

        return True

    except Exception as e:
        logger.error("fetch_complete_stock_data_failed", ticker=ticker, error=str(e), exc_info=True)

        # Update metadata on failure
        if metadata_logger:
            await metadata_logger.increment_failure(ticker, str(e))

            if execution_id:
                await metadata_logger.log_operation(
                    execution_id,
                    ticker,
                    operation,
                    'failed',
                    start_time,
                    error_message=str(e),
                    error_code='api_error' if 'API' in str(e) or '404' in str(e) else 'unknown'
                )

        return False


async def process_batch(
    tickers: List[str],
    db: DatabaseManager,
    fetcher: EODHDFetcher,
    mode: str = "incremental",
    metadata_logger: MetadataLogger = None,
    execution_id: str = None,
    skip_existing: bool = False,
    start_date_override: date = None,
    end_date_override: date = None,
) -> dict:
    """
    Process a batch of tickers in parallel.

    Args:
        tickers: List of ticker symbols
        db: Database manager
        fetcher: EODHD fetcher
        mode: Fetch mode
        metadata_logger: MetadataLogger instance
        execution_id: Airflow DAG run_id
        skip_existing: Skip already processed tickers
        start_date_override: Override start date for historical mode
        end_date_override: Override end date for historical mode

    Returns:
        dict: Statistics about the batch
    """
    logger.info(
        "processing_batch",
        count=len(tickers),
        mode=mode,
        execution_id=execution_id,
        start_date=str(start_date_override) if start_date_override else None,
        end_date=str(end_date_override) if end_date_override else None,
    )

    # Process in parallel (with concurrency handled by rate limiter)
    tasks = [
        fetch_complete_stock_data(
            ticker, db, fetcher, mode,
            metadata_logger, execution_id, skip_existing,
            start_date_override, end_date_override
        )
        for ticker in tickers
    ]

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


async def fetch_news_for_ticker(
    ticker: str,
    db: DatabaseManager,
    fetcher: EODHDFetcher,
    start_date: date,
    end_date: date,
    metadata_logger: MetadataLogger = None,
    execution_id: str = None,
) -> bool:
    """
    Fetch news articles for a ticker and store them with sentiment data.

    Args:
        ticker: Stock symbol
        db: Database manager
        fetcher: EODHD fetcher
        start_date: Start date for news fetch
        end_date: End date for news fetch
        metadata_logger: MetadataLogger instance for tracking
        execution_id: Airflow DAG run_id

    Returns:
        bool: Success status
    """
    start_time = datetime.now()
    operation = 'news_collection'

    try:
        logger.info("fetching_news", ticker=ticker, start_date=str(start_date), end_date=str(end_date))

        # Fetch news articles
        articles = await fetcher.fetch_news(ticker, start_date, end_date, limit=100)

        if not articles:
            logger.info("no_news_articles", ticker=ticker)
            return True  # Not a failure, just no news

        # Get asset_id for the ticker
        async with db.pool.acquire() as conn:
            await conn.execute("SET search_path TO financial_screener")

            # Get or create asset
            row = await conn.fetchrow(
                "SELECT id FROM assets WHERE ticker = $1 LIMIT 1",
                ticker
            )

            if not row:
                logger.warning("ticker_not_in_database_skipping_news", ticker=ticker)
                return False

            asset_id = row['id']

            # Store each article
            stored_count = 0
            for article in articles:
                article_id = await upsert_news_article(conn, asset_id, ticker, article)
                if article_id:
                    stored_count += 1

        logger.info("news_stored", ticker=ticker, articles_fetched=len(articles), articles_stored=stored_count)

        # Update metadata on success
        if metadata_logger and execution_id:
            await metadata_logger.log_operation(
                execution_id,
                ticker,
                operation,
                'success',
                start_time,
                records_inserted=stored_count,
                api_calls_used=1
            )

        return True

    except Exception as e:
        logger.error("fetch_news_failed", ticker=ticker, error=str(e), exc_info=True)

        # Update metadata on failure
        if metadata_logger and execution_id:
            await metadata_logger.log_operation(
                execution_id,
                ticker,
                operation,
                'failed',
                start_time,
                error_message=str(e)
            )

        return False


async def fetch_sentiment_for_tickers(
    tickers: List[str],
    db: DatabaseManager,
    fetcher: EODHDFetcher,
    start_date: date,
    end_date: date,
    metadata_logger: MetadataLogger = None,
    execution_id: str = None,
) -> bool:
    """
    Fetch aggregated sentiment scores for multiple tickers (batched API call).

    The EODHD sentiment API supports batching up to 100 tickers per call for efficiency.

    Args:
        tickers: List of stock symbols (up to 100)
        db: Database manager
        fetcher: EODHD fetcher
        start_date: Start date for sentiment fetch
        end_date: End date for sentiment fetch
        metadata_logger: MetadataLogger instance for tracking
        execution_id: Airflow DAG run_id

    Returns:
        bool: Success status
    """
    start_time = datetime.now()
    operation = 'sentiment_collection'

    try:
        logger.info("fetching_sentiment", ticker_count=len(tickers), start_date=str(start_date), end_date=str(end_date))

        # Fetch sentiment data (batched call)
        sentiment_data = await fetcher.fetch_sentiment(tickers, start_date, end_date)

        if not sentiment_data:
            logger.info("no_sentiment_data", ticker_count=len(tickers))
            return True  # Not a failure, just no data

        async with db.pool.acquire() as conn:
            await conn.execute("SET search_path TO financial_screener")

            total_stored = 0

            # Process each ticker's sentiment scores
            for ticker, daily_scores in sentiment_data.items():
                # Get asset_id for the ticker
                row = await conn.fetchrow(
                    "SELECT id FROM assets WHERE ticker = $1 LIMIT 1",
                    ticker
                )

                if not row:
                    logger.warning("ticker_not_in_database_skipping_sentiment", ticker=ticker)
                    continue

                asset_id = row['id']

                # Store each daily sentiment score
                for score_data in daily_scores:
                    sentiment_date = datetime.strptime(score_data['date'], "%Y-%m-%d").date()
                    success = await upsert_sentiment_score(
                        conn,
                        asset_id,
                        ticker,
                        sentiment_date,
                        score_data['normalized'],
                        score_data['count']
                    )
                    if success:
                        total_stored += 1

        logger.info("sentiment_stored", ticker_count=len(tickers), scores_stored=total_stored)

        # Update metadata on success
        if metadata_logger and execution_id:
            # Log one operation per batch (not per ticker)
            await metadata_logger.log_operation(
                execution_id,
                f"batch_{len(tickers)}_tickers",
                operation,
                'success',
                start_time,
                records_inserted=total_stored,
                api_calls_used=1  # Batched call
            )

        return True

    except Exception as e:
        logger.error("fetch_sentiment_failed", ticker_count=len(tickers), error=str(e), exc_info=True)

        # Update metadata on failure
        if metadata_logger and execution_id:
            await metadata_logger.log_operation(
                execution_id,
                f"batch_{len(tickers)}_tickers",
                operation,
                'failed',
                start_time,
                error_message=str(e)
            )

        return False


def read_exchange_ticker_manifest(exchange_code: str) -> List[str]:
    """
    Read ticker symbols from exchange-specific manifest file.

    Manifest files are located in config/tickers/ directory and named
    by lowercase exchange code (e.g., nyse.txt, nasdaq.txt, lse.txt).

    Args:
        exchange_code: Exchange identifier (e.g., 'NYSE', 'NASDAQ', 'LSE')

    Returns:
        List[str]: Ticker symbols from manifest file, uppercased and stripped

    Raises:
        FileNotFoundError: If manifest file doesn't exist
        Exception: For other file reading errors
    """
    import os

    # Construct manifest file path
    # __file__ is /app/src/main_enhanced.py
    # os.path.dirname(__file__) = /app/src
    # os.path.dirname(os.path.dirname(__file__)) = /app
    base_dir = os.path.dirname(os.path.dirname(__file__))
    manifest_path = os.path.join(base_dir, "config", "tickers", f"{exchange_code.lower()}.txt")

    logger.info("reading_exchange_manifest", exchange=exchange_code, path=manifest_path)

    try:
        tickers = []
        with open(manifest_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    tickers.append(line.upper())

        logger.info("manifest_loaded", exchange=exchange_code, ticker_count=len(tickers))
        return tickers

    except FileNotFoundError:
        logger.error("manifest_file_not_found", exchange=exchange_code, path=manifest_path)
        raise
    except Exception as e:
        logger.error("manifest_read_error", exchange=exchange_code, error=str(e))
        raise


def aggregate_exchange_ticker_manifests(exchange_codes: List[str]) -> List[str]:
    """
    Aggregate ticker symbols from multiple exchange manifests.

    Reads ticker lists from specified exchange manifest files and
    combines them into a single deduplicated list.

    Args:
        exchange_codes: List of exchange identifiers (e.g., ['NYSE', 'NASDAQ'])

    Returns:
        List[str]: Combined ticker symbols from all manifests (deduplicated)

    Raises:
        FileNotFoundError: If any manifest file doesn't exist
    """
    all_tickers = []

    for exchange_code in exchange_codes:
        try:
            exchange_tickers = read_exchange_ticker_manifest(exchange_code)
            all_tickers.extend(exchange_tickers)
        except FileNotFoundError:
            logger.error("skipping_missing_exchange", exchange=exchange_code)
            # Continue with other exchanges instead of failing completely
            continue

    # Deduplicate while preserving order
    seen = set()
    deduplicated = []
    for ticker in all_tickers:
        if ticker not in seen:
            seen.add(ticker)
            deduplicated.append(ticker)

    logger.info("aggregated_exchange_manifests",
                exchanges=exchange_codes,
                total_tickers=len(deduplicated),
                raw_count=len(all_tickers))

    return deduplicated


async def main():
    """Main entry point for enhanced data collection."""
    parser = argparse.ArgumentParser(description="Enhanced Financial Data Collector")
    parser.add_argument(
        "--mode",
        choices=["bulk", "incremental", "single", "auto", "historical", "news", "sentiment"],
        default="incremental",
        help="Fetch mode: bulk (2 years), incremental (delta), auto (detect), single (one ticker), historical (custom date range), news (articles), sentiment (scores)",
    )
    parser.add_argument(
        "--tickers", type=str, help="Comma-separated list of tickers (e.g., AAPL,MSFT)"
    )
    parser.add_argument(
        "--ticker", type=str, help="Single ticker to fetch (for mode=single)"
    )
    parser.add_argument(
        "--exchanges", type=str, help="Comma-separated list of exchanges to filter tickers (e.g., NYSE,NASDAQ)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=50, help="Batch size for processing"
    )
    parser.add_argument(
        "--execution-id", type=str, help="Airflow DAG execution ID for metadata tracking"
    )
    parser.add_argument(
        "--skip-existing", action="store_true", help="Skip tickers already processed in this execution"
    )
    parser.add_argument(
        "--start-date", type=str, help="Start date for historical mode (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date", type=str, help="End date for historical mode (YYYY-MM-DD)"
    )

    args = parser.parse_args()

    # Parse dates if provided
    start_date_override = None
    end_date_override = None
    if args.start_date:
        start_date_override = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    if args.end_date:
        end_date_override = datetime.strptime(args.end_date, "%Y-%m-%d").date()

    # Load configuration
    settings = Settings()

    # Initialize components
    db = DatabaseManager(settings.database_url)
    fetcher = EODHDFetcher(settings.eodhd_api_key)

    # Initialize metadata logger if execution_id provided (Airflow mode)
    metadata_logger = None
    if args.execution_id:
        logger.info("airflow_mode_enabled", execution_id=args.execution_id)

    try:
        await db.connect()

        # Initialize metadata logger after DB connection
        if args.execution_id:
            metadata_logger = MetadataLogger(db.pool)

        # Determine tickers to process
        tickers = []

        if args.mode == "single":
            if not args.ticker:
                logger.error("--ticker required for single mode")
                sys.exit(1)
            tickers = [args.ticker.upper()]

        elif args.tickers:
            tickers = [t.strip().upper() for t in args.tickers.split(",")]

        elif args.exchanges:
            exchange_codes = [e.strip().upper() for e in args.exchanges.split(",")]
            try:
                tickers = aggregate_exchange_ticker_manifests(exchange_codes)
                if not tickers:
                    logger.error("no_tickers_loaded_from_exchanges", exchanges=exchange_codes)
                    sys.exit(1)
            except FileNotFoundError as e:
                logger.error("failed_to_load_exchange_manifests", error=str(e))
                sys.exit(1)

        else:
            logger.error("Must specify --tickers, --ticker, or --exchanges")
            sys.exit(1)

        logger.info(
            "starting_enhanced_data_collection",
            mode=args.mode,
            ticker_count=len(tickers),
        )

        # Determine date range for news/sentiment modes
        if args.mode in ["news", "sentiment"]:
            if not (start_date_override and end_date_override):
                logger.error("--start-date and --end-date required for news/sentiment modes")
                sys.exit(1)

        # Process based on mode
        batch_size = args.batch_size
        total_stats = {"total": 0, "successes": 0, "failures": 0}

        if args.mode == "news":
            # News mode: process each ticker individually
            for i in range(0, len(tickers), batch_size):
                batch = tickers[i : i + batch_size]
                logger.info("processing_news_batch", batch_num=i // batch_size + 1, ticker_count=len(batch))

                # Process tickers in parallel
                tasks = [
                    fetch_news_for_ticker(
                        ticker, db, fetcher,
                        start_date_override, end_date_override,
                        metadata_logger, args.execution_id
                    )
                    for ticker in batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                successes = sum(1 for r in results if r is True)
                total_stats["total"] += len(batch)
                total_stats["successes"] += successes
                total_stats["failures"] += len(batch) - successes

                await asyncio.sleep(2)

        elif args.mode == "sentiment":
            # Sentiment mode: batch API calls (100 tickers per call)
            sentiment_batch_size = 100  # EODHD API limit

            for i in range(0, len(tickers), sentiment_batch_size):
                batch = tickers[i : i + sentiment_batch_size]
                logger.info("processing_sentiment_batch", batch_num=i // sentiment_batch_size + 1, ticker_count=len(batch))

                # Fetch sentiment for batch (single API call)
                success = await fetch_sentiment_for_tickers(
                    batch, db, fetcher,
                    start_date_override, end_date_override,
                    metadata_logger, args.execution_id
                )

                total_stats["total"] += len(batch)
                if success:
                    total_stats["successes"] += len(batch)
                else:
                    total_stats["failures"] += len(batch)

                await asyncio.sleep(2)

        else:
            # Standard modes: bulk, incremental, single, auto, historical
            for i in range(0, len(tickers), batch_size):
                batch = tickers[i : i + batch_size]

                logger.info("processing_batch", batch_num=i // batch_size + 1)

                stats = await process_batch(
                    batch, db, fetcher, args.mode,
                    metadata_logger, args.execution_id, args.skip_existing,
                    start_date_override, end_date_override
                )

                total_stats["total"] += stats["total"]
                total_stats["successes"] += stats["successes"]
                total_stats["failures"] += stats["failures"]

                # Small delay between batches
                await asyncio.sleep(2)

        logger.info("data_collection_complete", stats=total_stats)

        # Log to database
        await db.log_data_fetch(
            job_type="enhanced_collection",
            status="success" if total_stats["failures"] == 0 else "partial",
            records_processed=total_stats["successes"],
        )

    except Exception as e:
        logger.error("data_collection_failed", error=str(e), exc_info=True)
        sys.exit(1)

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
