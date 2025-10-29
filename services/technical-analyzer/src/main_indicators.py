"""
Technical Indicators Calculator - Main Entry Point
Designed to be orchestrated by Airflow

Usage:
    python main_indicators.py --tickers AAPL,MSFT,GOOGL
    python main_indicators.py --batch-size 100 --skip-existing
    python main_indicators.py --calculation-date 2025-10-27  # Reprocess specific date
    python main_indicators.py --all  # Process all assets without indicators
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import structlog

from config import Settings
from database import DatabaseManager
from indicators import TechnicalIndicatorCalculator

logger = structlog.get_logger()


class IndicatorProcessor:
    """Process technical indicators with duplicate prevention."""

    def __init__(
        self,
        settings: Settings,
        skip_existing: bool = True,
        force: bool = False,
        calculation_date: Optional[date] = None,
        execution_id: Optional[str] = None
    ):
        self.settings = settings
        self.db = DatabaseManager(settings.database_url, settings.database_schema)
        self.calculator = TechnicalIndicatorCalculator()
        self.skip_existing = skip_existing
        self.force = force
        self.calculation_date = calculation_date  # For manual date specification
        self.execution_id = execution_id  # For Airflow tracking
        self.stats = {
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "updated": 0,
        }

    async def connect_db(self):
        """Connect to PostgreSQL database."""
        await self.db.connect(
            min_size=self.settings.pool_min_size,
            max_size=self.settings.pool_max_size
        )

    async def close_db(self):
        """Close database connection."""
        await self.db.disconnect()

    def get_target_calculation_date(self, prices_last_date: Optional[date]) -> date:
        """
        Determine which date to calculate indicators for.

        Args:
            prices_last_date: Latest price date from asset_processing_state

        Returns:
            date: The calculation date (either manual override, prices_last_date, or yesterday)
        """
        if self.calculation_date:
            # Manual override for reprocessing
            return self.calculation_date

        if prices_last_date:
            # Use the latest available price date
            return prices_last_date

        # Fallback: yesterday (today - 1 day)
        return date.today() - timedelta(days=1)

    async def process_asset(self, asset: Dict) -> bool:
        """Process single asset: fetch prices, calculate indicators, save."""
        asset_id = asset['id']
        ticker = asset['ticker']
        prices_last_date = asset.get('prices_last_date')
        start_time = datetime.now()

        try:
            # Determine calculation date
            target_date = self.get_target_calculation_date(prices_last_date)

            # Fetch price data (only up to calculation_date to prevent look-ahead bias)
            prices = await self.db.get_price_data(
                asset_id=asset_id,
                limit=self.settings.max_price_days,
                calculation_date=target_date
            )

            if len(prices) < self.settings.min_price_days:
                logger.warning(
                    "insufficient_price_data",
                    ticker=ticker,
                    asset_id=asset_id,
                    data_points=len(prices),
                    required=self.settings.min_price_days
                )
                self.stats["skipped"] += 1

                # Log to metadata if execution_id provided
                if self.execution_id:
                    duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                    await self.db.log_processing_detail(
                        execution_id=self.execution_id,
                        ticker=ticker,
                        operation='indicator_calculation',
                        status='skipped',
                        records_processed=0,
                        error_message=f'Insufficient price data: {len(prices)} < {self.settings.min_price_days}',
                        duration_ms=duration_ms
                    )

                return False

            # Calculate indicators
            indicators = self.calculator.calculate_all_indicators(
                prices=prices,
                ticker=ticker
            )

            if not indicators:
                logger.warning(
                    "no_indicators_calculated",
                    ticker=ticker,
                    asset_id=asset_id
                )
                self.stats["failed"] += 1

                # Log failure to metadata
                if self.execution_id:
                    duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                    await self.db.log_processing_detail(
                        execution_id=self.execution_id,
                        ticker=ticker,
                        operation='indicator_calculation',
                        status='failed',
                        records_processed=0,
                        error_message='No indicators calculated',
                        duration_ms=duration_ms
                    )

                return False

            # Save to database with calculation_date
            await self.db.upsert_indicators(
                asset_id=asset_id,
                ticker=ticker,
                calculation_date=target_date,
                indicators=indicators,
                data_points_used=len(prices)
            )

            # Update processing state
            await self.db.update_processing_state(
                ticker=ticker,
                execution_id=self.execution_id
            )

            # Log success to metadata
            if self.execution_id:
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                await self.db.log_processing_detail(
                    execution_id=self.execution_id,
                    ticker=ticker,
                    operation='indicator_calculation',
                    status='success',
                    records_processed=len(indicators),
                    duration_ms=duration_ms
                )

            logger.info(
                "indicators_calculated",
                ticker=ticker,
                asset_id=asset_id,
                calculation_date=str(target_date),
                indicator_count=len(indicators)
            )

            self.stats["processed"] += 1
            self.stats["updated"] += 1
            return True

        except Exception as e:
            logger.error(
                "process_asset_failed",
                ticker=ticker,
                asset_id=asset_id,
                error=str(e)
            )
            self.stats["failed"] += 1

            # Log error to metadata
            if self.execution_id:
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                await self.db.log_processing_detail(
                    execution_id=self.execution_id,
                    ticker=ticker,
                    operation='indicator_calculation',
                    status='failed',
                    records_processed=0,
                    error_message=str(e),
                    duration_ms=duration_ms
                )

            return False

    async def process_batch(
        self,
        tickers: Optional[List[str]] = None,
        batch_size: Optional[int] = None
    ):
        """
        Process indicators for a batch of assets.

        Args:
            tickers: Specific tickers to process (None = all pending)
            batch_size: Limit number of assets to process
        """
        start_time = datetime.now()

        # Get assets to process using new database manager
        assets = await self.db.get_assets_to_process(
            tickers=tickers,
            skip_existing=self.skip_existing,
            force=self.force,
            limit=batch_size
        )

        if not assets:
            logger.info("no_assets_to_process")
            return

        logger.info(
            "batch_processing_started",
            total_assets=len(assets),
            skip_existing=self.skip_existing,
            force=self.force,
            execution_id=self.execution_id
        )

        # Process each asset
        for i, asset in enumerate(assets, 1):
            await self.process_asset(asset)

            # Progress logging every 50 assets
            if i % 50 == 0:
                logger.info(
                    "batch_progress",
                    processed=i,
                    total=len(assets),
                    success_rate=f"{(self.stats['processed'] / i * 100):.1f}%"
                )

        # Final statistics
        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            "batch_processing_complete",
            total_assets=len(assets),
            processed=self.stats["processed"],
            skipped=self.stats["skipped"],
            failed=self.stats["failed"],
            updated=self.stats["updated"],
            duration_seconds=duration,
            rate_per_second=f"{len(assets) / duration:.2f}" if duration > 0 else "0"
        )


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate technical indicators for financial assets"
    )
    parser.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated list of tickers to process (e.g., AAPL,MSFT,GOOGL)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Maximum number of assets to process"
    )
    parser.add_argument(
        "--calculation-date",
        type=str,
        help="Target date for indicator calculation (YYYY-MM-DD). If not provided, uses prices_last_date from metadata."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all assets (force recalculation)"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip assets with up-to-date indicators (default: True)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recalculation even if indicators are up to date"
    )
    parser.add_argument(
        "--execution-id",
        type=str,
        help="Airflow DAG execution ID for metadata tracking"
    )

    args = parser.parse_args()

    # Load settings from environment
    settings = Settings()

    # Configure structlog (simple configuration without filtering)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Parse tickers
    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]

    # Parse calculation date
    calculation_date = None
    if args.calculation_date:
        try:
            calculation_date = datetime.strptime(args.calculation_date, "%Y-%m-%d").date()
            logger.info("manual_calculation_date", date=str(calculation_date))
        except ValueError:
            logger.error("invalid_date_format", provided=args.calculation_date, expected="YYYY-MM-DD")
            sys.exit(1)

    # Skip existing logic
    skip_existing = args.skip_existing and not args.force
    force = args.force or args.all

    # Override batch size from settings if not provided
    batch_size = args.batch_size if args.batch_size else settings.batch_size

    # Initialize processor
    processor = IndicatorProcessor(
        settings=settings,
        skip_existing=skip_existing,
        force=force,
        calculation_date=calculation_date,
        execution_id=args.execution_id
    )

    try:
        await processor.connect_db()

        # Process batch
        await processor.process_batch(
            tickers=tickers,
            batch_size=batch_size
        )

        # Log final summary
        logger.info(
            "processing_complete",
            stats=processor.stats,
            execution_id=args.execution_id
        )

    except Exception as e:
        logger.error("processing_failed", error=str(e))
        sys.exit(1)

    finally:
        await processor.close_db()


if __name__ == "__main__":
    asyncio.run(main())
