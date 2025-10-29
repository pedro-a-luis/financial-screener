"""
Database Manager for Technical Analyzer Service

Handles PostgreSQL operations using asyncpg for async I/O.
"""

import asyncpg
from datetime import date, datetime
from typing import List, Dict, Optional, Tuple
import structlog

logger = structlog.get_logger()


class DatabaseManager:
    """Manage PostgreSQL database operations for technical indicators."""

    def __init__(self, database_url: str, schema: str = "financial_screener"):
        """Initialize database manager."""
        self.database_url = database_url
        self.schema = schema
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self, min_size: int = 2, max_size: int = 10):
        """Create connection pool."""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=min_size,
            max_size=max_size,
            command_timeout=60,
            server_settings={'search_path': self.schema},
        )
        logger.info("database_connected", schema=self.schema)

    async def disconnect(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("database_disconnected")

    async def get_calculation_date(self, ticker: str) -> Optional[date]:
        """
        Get the date to calculate indicators for (from prices_last_date).

        Returns:
            date: The prices_last_date from asset_processing_state, or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT prices_last_date
                FROM asset_processing_state
                WHERE ticker = $1 AND prices_last_date IS NOT NULL
                ORDER BY prices_last_date DESC
                LIMIT 1
                """,
                ticker
            )
            return row['prices_last_date'] if row else None

    async def get_assets_to_process(
        self,
        tickers: Optional[List[str]] = None,
        skip_existing: bool = True,
        force: bool = False,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get list of assets that need indicator calculation.

        Args:
            tickers: Specific tickers to process (None = all)
            skip_existing: Skip assets with up-to-date indicators
            force: Force recalculation even if up to date
            limit: Maximum number of assets to return

        Returns:
            List of dicts with keys: id, ticker, asset_type, prices_last_date
        """
        async with self.pool.acquire() as conn:
            # Base query
            query = """
                SELECT DISTINCT
                    a.id,
                    a.ticker,
                    a.asset_type,
                    aps.prices_last_date,
                    ti.calculation_date as last_calculation_date,
                    aps.indicators_calculated_at
                FROM assets a
                LEFT JOIN asset_processing_state aps ON a.ticker = aps.ticker
                LEFT JOIN technical_indicators ti ON a.id = ti.asset_id
                WHERE 1=1
            """

            params = []
            param_count = 1

            # Filter by tickers if specified
            if tickers:
                query += f" AND a.ticker = ANY(${param_count})"
                params.append(tickers)
                param_count += 1

            # Filter logic
            if force:
                # Process all assets (no filtering)
                query += " AND aps.prices_loaded = TRUE"
            elif skip_existing:
                # Process only assets that need updates
                query += """
                    AND aps.prices_loaded = TRUE
                    AND (
                        ti.asset_id IS NULL  -- Never calculated
                        OR aps.prices_last_date > ti.calculation_date  -- New prices available
                        OR aps.needs_indicators_reprocess = TRUE  -- Manual flag
                    )
                """
            else:
                # Process all assets with prices
                query += " AND aps.prices_loaded = TRUE"

            query += " ORDER BY a.id"

            if limit:
                query += f" LIMIT ${param_count}"
                params.append(limit)

            rows = await conn.fetch(query, *params)

            results = [
                {
                    'id': row['id'],
                    'ticker': row['ticker'],
                    'asset_type': row['asset_type'],
                    'prices_last_date': row['prices_last_date'],
                    'last_calculation_date': row['last_calculation_date'],
                    'indicators_calculated_at': row['indicators_calculated_at']
                }
                for row in rows
            ]

            logger.info(
                "assets_discovered",
                count=len(results),
                skip_existing=skip_existing,
                force=force
            )

            return results

    async def get_price_data(
        self,
        asset_id: int,
        limit: int = 500,
        calculation_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Fetch historical price data for an asset.

        Args:
            asset_id: Asset ID
            limit: Maximum number of recent records to fetch
            calculation_date: Only fetch data up to this date (prevents look-ahead bias)

        Returns:
            List of price records (ordered by date ASC)
        """
        async with self.pool.acquire() as conn:
            if calculation_date:
                # Prevent look-ahead bias: only use data up to calculation_date
                rows = await conn.fetch(
                    """
                    SELECT date, open, high, low, close, volume, adj_close
                    FROM stock_prices
                    WHERE asset_id = $1 AND date <= $2
                    ORDER BY date DESC
                    LIMIT $3
                    """,
                    asset_id,
                    calculation_date,
                    limit
                )
            else:
                # No date filter - use latest available data
                rows = await conn.fetch(
                    """
                    SELECT date, open, high, low, close, volume, adj_close
                    FROM stock_prices
                    WHERE asset_id = $1
                    ORDER BY date DESC
                    LIMIT $2
                    """,
                    asset_id,
                    limit
                )

            # Return in ascending order (oldest first) for indicator calculation
            return [
                {
                    'date': row['date'],
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': int(row['volume']),
                    'adj_close': float(row['adj_close']) if row['adj_close'] else float(row['close'])
                }
                for row in reversed(rows)  # Reverse to get ascending order
            ]

    async def upsert_indicators(
        self,
        asset_id: int,
        ticker: str,
        calculation_date: date,
        indicators: Dict,
        data_points_used: int
    ):
        """
        Insert or update technical indicators for an asset.

        Args:
            asset_id: Asset ID
            ticker: Ticker symbol
            calculation_date: Date these indicators represent
            indicators: Dict of indicator values
            data_points_used: Number of price records used for calculation
        """
        async with self.pool.acquire() as conn:
            # Build field lists
            fields = ['asset_id', 'ticker', 'calculation_date', 'data_points_used'] + list(indicators.keys())
            placeholders = ', '.join(f'${i+1}' for i in range(len(fields)))

            # Build update clause for ON CONFLICT
            update_fields = [f for f in fields if f not in ['asset_id', 'calculation_date']]
            update_clause = ', '.join(f"{f} = EXCLUDED.{f}" for f in update_fields)

            query = f"""
                INSERT INTO technical_indicators ({', '.join(fields)})
                VALUES ({placeholders})
                ON CONFLICT (asset_id, calculation_date)
                DO UPDATE SET
                    {update_clause},
                    updated_at = NOW()
            """

            values = [asset_id, ticker, calculation_date, data_points_used] + [indicators[k] for k in indicators.keys()]

            await conn.execute(query, *values)

            logger.debug(
                "indicators_upserted",
                ticker=ticker,
                asset_id=asset_id,
                calculation_date=calculation_date,
                indicators_count=len(indicators)
            )

    async def update_processing_state(
        self,
        ticker: str,
        execution_id: Optional[str] = None
    ):
        """
        Update asset_processing_state after successful indicator calculation.

        Args:
            ticker: Ticker symbol
            execution_id: Execution ID from Airflow (optional)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE asset_processing_state
                SET indicators_calculated = TRUE,
                    indicators_calculated_at = NOW(),
                    indicators_execution_id = $2,
                    needs_indicators_reprocess = FALSE,
                    updated_at = NOW()
                WHERE ticker = $1
                """,
                ticker,
                execution_id
            )

            logger.debug("processing_state_updated", ticker=ticker, execution_id=execution_id)

    async def log_processing_detail(
        self,
        execution_id: str,
        ticker: str,
        operation: str,
        status: str,
        records_processed: int = 0,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None
    ):
        """
        Log detailed processing information.

        Args:
            execution_id: Execution ID from process_executions
            ticker: Ticker symbol
            operation: Operation type (e.g., 'indicator_calculation')
            status: Status ('success', 'failed', 'skipped')
            records_processed: Number of indicators calculated
            error_message: Error message if failed
            duration_ms: Processing duration in milliseconds
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO asset_processing_details
                (execution_id, ticker, operation, status, records_processed, error_message, duration_ms)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                execution_id,
                ticker,
                operation,
                status,
                records_processed,
                error_message,
                duration_ms
            )

    async def get_asset_count(self) -> int:
        """Get total number of assets with prices loaded."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM asset_processing_state
                WHERE prices_loaded = TRUE
                """
            )
            return row['count'] if row else 0
