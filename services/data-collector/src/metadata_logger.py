"""
Metadata Logger for Airflow Orchestration
Logs processing operations to metadata tables for tracking and monitoring
"""

import asyncpg
from datetime import datetime, date
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger()


class MetadataLogger:
    """
    Handles logging to metadata tables for Airflow orchestration.

    Logs operations to:
    - asset_processing_details: Granular operation logs
    - asset_processing_state: Per-ticker state tracking
    """

    def __init__(self, db_pool: asyncpg.Pool):
        """
        Initialize metadata logger.

        Args:
            db_pool: asyncpg connection pool
        """
        self.db_pool = db_pool

    async def log_operation(
        self,
        execution_id: str,
        ticker: str,
        operation: str,
        status: str,
        started_at: datetime,
        **kwargs
    ) -> None:
        """
        Log individual ticker processing operation to asset_processing_details.

        Args:
            execution_id: Airflow DAG run_id
            ticker: Stock ticker symbol
            operation: Operation type ('fundamentals_bulk', 'prices_incremental', 'indicators_calc')
            status: Operation status ('success', 'failed', 'skipped')
            started_at: Operation start timestamp
            **kwargs: Additional fields:
                - records_inserted: int
                - records_updated: int
                - api_calls_used: int
                - error_message: str
                - error_code: str

        Example:
            await logger.log_operation(
                execution_id='scheduled__2025-10-21T21:30:00',
                ticker='AAPL',
                operation='prices_incremental',
                status='success',
                started_at=datetime.now(),
                records_inserted=1,
                api_calls_used=1
            )
        """
        query = """
            INSERT INTO asset_processing_details (
                execution_id, ticker, operation, status,
                records_inserted, records_updated, api_calls_used,
                error_message, error_code,
                started_at, completed_at, duration_ms, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
        """

        completed_at = datetime.now()
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("SET search_path TO financial_screener")
                await conn.execute(
                    query,
                    execution_id,
                    ticker,
                    operation,
                    status,
                    kwargs.get('records_inserted', 0),
                    kwargs.get('records_updated', 0),
                    kwargs.get('api_calls_used', 0),
                    kwargs.get('error_message'),
                    kwargs.get('error_code'),
                    started_at,
                    completed_at,
                    duration_ms
                )

            logger.debug(
                "operation_logged",
                ticker=ticker,
                operation=operation,
                status=status,
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.error(
                "failed_to_log_operation",
                ticker=ticker,
                operation=operation,
                error=str(e)
            )
            # Don't raise - logging failure shouldn't stop processing

    async def update_asset_state_bulk(
        self,
        ticker: str,
        execution_id: str,
        prices_first_date: Optional[date],
        prices_last_date: Optional[date]
    ) -> None:
        """
        Update asset_processing_state after successful bulk load.

        Sets:
        - fundamentals_loaded = TRUE
        - prices_loaded = TRUE
        - prices_first_date, prices_last_date
        - Resets consecutive_failures to 0

        Args:
            ticker: Stock ticker
            execution_id: Airflow run_id
            prices_first_date: Earliest price date loaded
            prices_last_date: Most recent price date loaded
        """
        query = """
            INSERT INTO asset_processing_state (
                ticker,
                fundamentals_loaded,
                fundamentals_loaded_at,
                fundamentals_execution_id,
                prices_loaded,
                prices_first_date,
                prices_last_date,
                prices_last_updated_at,
                prices_execution_id,
                consecutive_failures,
                created_at,
                updated_at
            ) VALUES (
                $1, TRUE, NOW(), $2, TRUE, $3, $4, NOW(), $2, 0, NOW(), NOW()
            )
            ON CONFLICT (ticker)
            DO UPDATE SET
                fundamentals_loaded = TRUE,
                fundamentals_loaded_at = NOW(),
                fundamentals_execution_id = $2,
                prices_loaded = TRUE,
                prices_first_date = COALESCE($3, asset_processing_state.prices_first_date),
                prices_last_date = $4,
                prices_last_updated_at = NOW(),
                prices_execution_id = $2,
                consecutive_failures = 0,
                updated_at = NOW()
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("SET search_path TO financial_screener")
                await conn.execute(
                    query,
                    ticker,
                    execution_id,
                    prices_first_date,
                    prices_last_date
                )

            logger.debug(
                "asset_state_updated_bulk",
                ticker=ticker,
                prices_first=prices_first_date,
                prices_last=prices_last_date
            )

        except Exception as e:
            logger.error(
                "failed_to_update_asset_state",
                ticker=ticker,
                operation='bulk',
                error=str(e)
            )

    async def update_asset_state_incremental(
        self,
        ticker: str,
        execution_id: str,
        prices_last_date: date
    ) -> None:
        """
        Update asset_processing_state after successful price update.

        Sets:
        - prices_last_date (most recent price)
        - prices_last_updated_at
        - Resets consecutive_failures to 0

        Args:
            ticker: Stock ticker
            execution_id: Airflow run_id
            prices_last_date: Most recent price date
        """
        query = """
            UPDATE asset_processing_state
            SET prices_last_date = $1,
                prices_last_updated_at = NOW(),
                prices_execution_id = $2,
                consecutive_failures = 0,
                updated_at = NOW()
            WHERE ticker = $3
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("SET search_path TO financial_screener")
                result = await conn.execute(query, prices_last_date, execution_id, ticker)

                # If ticker doesn't exist in state table, insert it
                if result == "UPDATE 0":
                    logger.warning(
                        "ticker_not_in_state_table",
                        ticker=ticker,
                        action="inserting"
                    )
                    await self.ensure_ticker_in_state(ticker)
                    await conn.execute(query, prices_last_date, execution_id, ticker)

            logger.debug(
                "asset_state_updated_incremental",
                ticker=ticker,
                prices_last=prices_last_date
            )

        except Exception as e:
            logger.error(
                "failed_to_update_asset_state",
                ticker=ticker,
                operation='incremental',
                error=str(e)
            )

    async def update_asset_state_indicators(
        self,
        ticker: str,
        execution_id: str
    ) -> None:
        """
        Update asset_processing_state after successful indicator calculation.

        Sets:
        - indicators_calculated = TRUE
        - indicators_calculated_at
        - Resets needs_indicators_reprocess flag

        Args:
            ticker: Stock ticker
            execution_id: Airflow run_id
        """
        query = """
            UPDATE asset_processing_state
            SET indicators_calculated = TRUE,
                indicators_calculated_at = NOW(),
                indicators_execution_id = $1,
                needs_indicators_reprocess = FALSE,
                updated_at = NOW()
            WHERE ticker = $2
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("SET search_path TO financial_screener")
                await conn.execute(query, execution_id, ticker)

            logger.debug("asset_state_updated_indicators", ticker=ticker)

        except Exception as e:
            logger.error(
                "failed_to_update_asset_state",
                ticker=ticker,
                operation='indicators',
                error=str(e)
            )

    async def increment_failure(
        self,
        ticker: str,
        error_message: str
    ) -> None:
        """
        Increment consecutive_failures counter for a ticker.

        Called when processing fails. After 5+ consecutive failures,
        the ticker will be skipped by delta discovery queries.

        Args:
            ticker: Stock ticker
            error_message: Error description
        """
        query = """
            INSERT INTO asset_processing_state (
                ticker,
                consecutive_failures,
                last_error_at,
                last_error_message,
                created_at,
                updated_at
            ) VALUES ($1, 1, NOW(), $2, NOW(), NOW())
            ON CONFLICT (ticker)
            DO UPDATE SET
                consecutive_failures = asset_processing_state.consecutive_failures + 1,
                last_error_at = NOW(),
                last_error_message = $2,
                updated_at = NOW()
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("SET search_path TO financial_screener")
                await conn.execute(query, ticker, error_message)

            logger.warning(
                "failure_count_incremented",
                ticker=ticker,
                error=error_message[:100]  # Truncate long errors
            )

        except Exception as e:
            logger.error(
                "failed_to_increment_failure",
                ticker=ticker,
                error=str(e)
            )

    async def check_already_processed(
        self,
        ticker: str,
        execution_id: str,
        operation: str
    ) -> bool:
        """
        Check if ticker already processed successfully in this execution.

        Used for idempotency - skips reprocessing if already done.

        Args:
            ticker: Stock ticker
            execution_id: Airflow run_id
            operation: Operation type

        Returns:
            bool: True if already processed successfully
        """
        query = """
            SELECT 1
            FROM asset_processing_details
            WHERE ticker = $1
              AND execution_id = $2
              AND operation = $3
              AND status = 'success'
            LIMIT 1
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("SET search_path TO financial_screener")
                result = await conn.fetchrow(query, ticker, execution_id, operation)
                return result is not None

        except Exception as e:
            logger.error(
                "failed_to_check_already_processed",
                ticker=ticker,
                error=str(e)
            )
            return False

    async def ensure_ticker_in_state(self, ticker: str) -> None:
        """
        Ensure ticker exists in asset_processing_state table.

        Inserts with default values if not exists.

        Args:
            ticker: Stock ticker
        """
        query = """
            INSERT INTO asset_processing_state (ticker, created_at, updated_at)
            VALUES ($1, NOW(), NOW())
            ON CONFLICT (ticker) DO NOTHING
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("SET search_path TO financial_screener")
                await conn.execute(query, ticker)

        except Exception as e:
            logger.error(
                "failed_to_ensure_ticker_in_state",
                ticker=ticker,
                error=str(e)
            )

    async def get_ticker_state(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get current processing state for a ticker.

        Useful for debugging and status checks.

        Args:
            ticker: Stock ticker

        Returns:
            dict: Ticker state or None if not found
        """
        query = """
            SELECT *
            FROM asset_processing_state
            WHERE ticker = $1
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("SET search_path TO financial_screener")
                result = await conn.fetchrow(query, ticker)
                return dict(result) if result else None

        except Exception as e:
            logger.error(
                "failed_to_get_ticker_state",
                ticker=ticker,
                error=str(e)
            )
            return None

    async def get_last_price_date(self, ticker: str):
        """
        Get the last available price date for a ticker from metadata.

        Args:
            ticker: Stock symbol

        Returns:
            date: Last price date, or None if not found
        """
        query = """
            SELECT prices_last_date
            FROM asset_processing_state
            WHERE ticker = $1
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("SET search_path TO financial_screener")
                result = await conn.fetchval(query, ticker)
                return result

        except Exception as e:
            logger.error(
                "failed_to_get_last_price_date",
                ticker=ticker,
                error=str(e)
            )
            return None
