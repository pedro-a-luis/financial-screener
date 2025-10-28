"""
Technical Indicators Calculator - Main Entry Point
Designed to be orchestrated by Airflow

Usage:
    python main_indicators.py --tickers AAPL,MSFT,GOOGL
    python main_indicators.py --batch-size 100 --skip-existing
    python main_indicators.py --all  # Process all assets without indicators
"""

import argparse
import asyncio
import asyncpg
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
import structlog

from indicators import TechnicalIndicatorCalculator

logger = structlog.get_logger()


class IndicatorProcessor:
    """Process technical indicators with duplicate prevention."""

    def __init__(self, skip_existing: bool = True):
        self.db_pool = None
        self.calculator = TechnicalIndicatorCalculator()
        self.skip_existing = skip_existing
        self.stats = {
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "updated": 0,
        }

    async def connect_db(self):
        """Connect to PostgreSQL database."""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is required")

        self.db_pool = await asyncpg.create_pool(
            database_url,
            min_size=2,
            max_size=10,
            command_timeout=60,
            server_settings={'search_path': 'financial_screener'}
        )
        logger.info("database_connected")

    async def close_db(self):
        """Close database connection."""
        if self.db_pool:
            await self.db_pool.close()
            logger.info("database_closed")

    async def get_assets_to_process(
        self,
        tickers: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get list of assets that need indicator calculation.

        Args:
            tickers: Specific tickers to process (None = all)
            limit: Maximum number of assets to process

        Returns:
            List of asset dicts with id, ticker, asset_type
        """
        if tickers:
            # Process specific tickers
            query = """
                SELECT a.id, a.ticker, a.asset_type
                FROM assets a
                WHERE a.ticker = ANY($1::text[])
                ORDER BY a.ticker
            """
            params = [tickers]
        elif self.skip_existing:
            # Process only assets without indicators OR outdated indicators
            query = """
                SELECT a.id, a.ticker, a.asset_type
                FROM assets a
                LEFT JOIN technical_indicators ti ON a.id = ti.asset_id
                WHERE ti.asset_id IS NULL
                   OR ti.calculated_at < NOW() - INTERVAL '1 day'
                ORDER BY a.id
            """
            if limit:
                query += f" LIMIT {limit}"
            params = []
        else:
            # Process all assets (force recalculation)
            query = """
                SELECT a.id, a.ticker, a.asset_type
                FROM assets a
                ORDER BY a.id
            """
            if limit:
                query += f" LIMIT {limit}"
            params = []

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        assets = [dict(row) for row in rows]
        logger.info(
            "assets_to_process",
            total=len(assets),
            skip_existing=self.skip_existing
        )
        return assets

    async def get_price_data(self, asset_id: int) -> List[Dict]:
        """Fetch price data for an asset (last 252 days minimum for indicators)."""
        query = """
            SELECT date, open, high, low, close, volume
            FROM stock_prices
            WHERE asset_id = $1
            ORDER BY date DESC
            LIMIT 500
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, asset_id)

        # Reverse to chronological order (oldest first)
        prices = [dict(row) for row in reversed(rows)]
        return prices

    async def save_indicators(
        self,
        asset_id: int,
        ticker: str,
        indicators: Dict
    ) -> bool:
        """
        Save calculated indicators to database.
        Uses INSERT ... ON CONFLICT to prevent duplicates.
        """
        if not indicators:
            return False

        query = """
            INSERT INTO technical_indicators (
                asset_id, calculated_at,
                sma_50, sma_200, ema_12, ema_26, wma_20,
                rsi_14, stoch_k, stoch_d, stoch_rsi, cci_20,
                macd, macd_signal, macd_histogram,
                dmi_plus, dmi_minus, adx,
                atr_14, volatility, std_dev,
                bb_upper, bb_middle, bb_lower, bb_bandwidth,
                sar, beta, slope,
                avg_volume_30, avg_volume_90,
                week_52_high, week_52_low, current_price
            ) VALUES (
                $1, NOW(),
                $2, $3, $4, $5, $6,
                $7, $8, $9, $10, $11,
                $12, $13, $14,
                $15, $16, $17,
                $18, $19, $20,
                $21, $22, $23, $24,
                $25, $26, $27,
                $28, $29,
                $30, $31, $32
            )
            ON CONFLICT (asset_id)
            DO UPDATE SET
                calculated_at = NOW(),
                sma_50 = EXCLUDED.sma_50,
                sma_200 = EXCLUDED.sma_200,
                ema_12 = EXCLUDED.ema_12,
                ema_26 = EXCLUDED.ema_26,
                wma_20 = EXCLUDED.wma_20,
                rsi_14 = EXCLUDED.rsi_14,
                stoch_k = EXCLUDED.stoch_k,
                stoch_d = EXCLUDED.stoch_d,
                stoch_rsi = EXCLUDED.stoch_rsi,
                cci_20 = EXCLUDED.cci_20,
                macd = EXCLUDED.macd,
                macd_signal = EXCLUDED.macd_signal,
                macd_histogram = EXCLUDED.macd_histogram,
                dmi_plus = EXCLUDED.dmi_plus,
                dmi_minus = EXCLUDED.dmi_minus,
                adx = EXCLUDED.adx,
                atr_14 = EXCLUDED.atr_14,
                volatility = EXCLUDED.volatility,
                std_dev = EXCLUDED.std_dev,
                bb_upper = EXCLUDED.bb_upper,
                bb_middle = EXCLUDED.bb_middle,
                bb_lower = EXCLUDED.bb_lower,
                bb_bandwidth = EXCLUDED.bb_bandwidth,
                sar = EXCLUDED.sar,
                beta = EXCLUDED.beta,
                slope = EXCLUDED.slope,
                avg_volume_30 = EXCLUDED.avg_volume_30,
                avg_volume_90 = EXCLUDED.avg_volume_90,
                week_52_high = EXCLUDED.week_52_high,
                week_52_low = EXCLUDED.week_52_low,
                current_price = EXCLUDED.current_price
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    query,
                    asset_id,
                    indicators.get('sma_50'),
                    indicators.get('sma_200'),
                    indicators.get('ema_12'),
                    indicators.get('ema_26'),
                    indicators.get('wma_20'),
                    indicators.get('rsi_14'),
                    indicators.get('stoch_k'),
                    indicators.get('stoch_d'),
                    indicators.get('stoch_rsi'),
                    indicators.get('cci_20'),
                    indicators.get('macd'),
                    indicators.get('macd_signal'),
                    indicators.get('macd_histogram'),
                    indicators.get('dmi_plus'),
                    indicators.get('dmi_minus'),
                    indicators.get('adx'),
                    indicators.get('atr_14'),
                    indicators.get('volatility'),
                    indicators.get('std_dev'),
                    indicators.get('bb_upper'),
                    indicators.get('bb_middle'),
                    indicators.get('bb_lower'),
                    indicators.get('bb_bandwidth'),
                    indicators.get('sar'),
                    indicators.get('beta'),
                    indicators.get('slope'),
                    indicators.get('avg_volume_30'),
                    indicators.get('avg_volume_90'),
                    indicators.get('week_52_high'),
                    indicators.get('week_52_low'),
                    indicators.get('current_price'),
                )

            logger.info("indicators_saved", ticker=ticker, asset_id=asset_id)
            return True

        except Exception as e:
            logger.error(
                "save_indicators_failed",
                ticker=ticker,
                asset_id=asset_id,
                error=str(e)
            )
            return False

    async def process_asset(self, asset: Dict) -> bool:
        """Process single asset: fetch prices, calculate indicators, save."""
        asset_id = asset['id']
        ticker = asset['ticker']

        try:
            # Fetch price data
            prices = await self.get_price_data(asset_id)

            if len(prices) < 200:
                logger.warning(
                    "insufficient_price_data",
                    ticker=ticker,
                    asset_id=asset_id,
                    data_points=len(prices)
                )
                self.stats["skipped"] += 1
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
                return False

            # Save to database
            success = await self.save_indicators(asset_id, ticker, indicators)

            if success:
                self.stats["processed"] += 1
                self.stats["updated"] += 1
            else:
                self.stats["failed"] += 1

            return success

        except Exception as e:
            logger.error(
                "process_asset_failed",
                ticker=ticker,
                asset_id=asset_id,
                error=str(e)
            )
            self.stats["failed"] += 1
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

        # Get assets to process
        assets = await self.get_assets_to_process(
            tickers=tickers,
            limit=batch_size
        )

        if not assets:
            logger.info("no_assets_to_process")
            return

        logger.info(
            "batch_processing_started",
            total_assets=len(assets),
            skip_existing=self.skip_existing
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
            rate_per_second=f"{len(assets) / duration:.2f}"
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
        "--all",
        action="store_true",
        help="Process all assets (force recalculation)"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip assets with recent indicators (default: True)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force recalculation even if indicators exist"
    )
    parser.add_argument(
        "--execution-id",
        type=str,
        help="Airflow DAG execution ID for metadata tracking"
    )

    args = parser.parse_args()

    # Parse tickers
    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]

    # Skip existing logic
    skip_existing = args.skip_existing and not args.force

    # Initialize processor
    processor = IndicatorProcessor(skip_existing=skip_existing)

    try:
        await processor.connect_db()

        # Process batch
        await processor.process_batch(
            tickers=tickers,
            batch_size=args.batch_size
        )

    finally:
        await processor.close_db()


if __name__ == "__main__":
    asyncio.run(main())
