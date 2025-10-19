"""
Database Manager for Data Collector

Handles PostgreSQL operations using asyncpg for async I/O.
"""

import asyncpg
import os
from datetime import datetime
from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger()


class DatabaseManager:
    """Manage PostgreSQL database operations."""

    def __init__(self, database_url: str):
        """Initialize database manager."""
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        self.schema = os.getenv("DATABASE_SCHEMA", "financial_screener")

    async def connect(self):
        """Create connection pool."""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=10,
            command_timeout=60,
            server_settings={'search_path': self.schema},
        )
        logger.info("database_connected", schema=self.schema)

    async def disconnect(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("database_disconnected")

    async def get_or_create_asset(
        self,
        ticker: str,
        name: str,
        asset_type: str,
        exchange: Optional[str] = None,
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        country: Optional[str] = None,
    ) -> int:
        """
        Get existing asset or create new one.

        Returns:
            int: asset_id
        """
        async with self.pool.acquire() as conn:
            # Try to get existing
            row = await conn.fetchrow(
                "SELECT id FROM assets WHERE ticker = $1", ticker.upper()
            )

            if row:
                return row["id"]

            # Create new
            row = await conn.fetchrow(
                """
                INSERT INTO assets (ticker, name, asset_type, exchange, sector, industry, country)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (ticker) DO UPDATE
                SET name = EXCLUDED.name,
                    updated_at = NOW()
                RETURNING id
                """,
                ticker.upper(),
                name,
                asset_type,
                exchange,
                sector,
                industry,
                country,
            )

            logger.info("asset_created", ticker=ticker, asset_id=row["id"])
            return row["id"]

    async def insert_prices(self, asset_id: int, prices: List[Dict]):
        """
        Insert price data in batch.

        Uses INSERT ... ON CONFLICT to handle duplicates.
        """
        if not prices:
            return

        async with self.pool.acquire() as conn:
            # Prepare data
            values = [
                (
                    asset_id,
                    p["date"],
                    p["open"],
                    p["high"],
                    p["low"],
                    p["close"],
                    p["volume"],
                    p.get("adj_close", p["close"]),
                )
                for p in prices
            ]

            # Batch insert
            await conn.executemany(
                """
                INSERT INTO stock_prices (asset_id, date, open, high, low, close, volume, adj_close)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (asset_id, date) DO UPDATE
                SET open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    adj_close = EXCLUDED.adj_close
                """,
                values,
            )

            logger.info("prices_inserted", asset_id=asset_id, count=len(prices))

    async def insert_fundamentals(self, asset_id: int, fundamentals: Dict):
        """Insert or update fundamental data."""
        if not fundamentals:
            return

        async with self.pool.acquire() as conn:
            # Build dynamic SQL based on available fields
            fields = list(fundamentals.keys())
            placeholders = ", ".join(f"${i+2}" for i in range(len(fields)))
            field_names = ", ".join(fields)

            # Update clause
            update_clause = ", ".join(f"{f} = EXCLUDED.{f}" for f in fields)

            query = f"""
                INSERT INTO stock_fundamentals (asset_id, {field_names})
                VALUES ($1, {placeholders})
                ON CONFLICT (asset_id, period_end_date, period_type)
                DO UPDATE SET {update_clause}
            """

            values = [asset_id] + [fundamentals[f] for f in fields]

            await conn.execute(query, *values)

            logger.info("fundamentals_inserted", asset_id=asset_id)

    async def upsert_etf_details(self, asset_id: int, details: Dict):
        """Insert or update ETF details."""
        if not details:
            return

        async with self.pool.acquire() as conn:
            # Build dynamic SQL
            fields = list(details.keys())
            placeholders = ", ".join(f"${i+2}" for i in range(len(fields)))
            field_names = ", ".join(fields)
            update_clause = ", ".join(f"{f} = EXCLUDED.{f}" for f in fields)

            query = f"""
                INSERT INTO etf_details (asset_id, {field_names})
                VALUES ($1, {placeholders})
                ON CONFLICT (asset_id)
                DO UPDATE SET {update_clause}
            """

            values = [asset_id] + [details[f] for f in fields]
            await conn.execute(query, *values)

            logger.info("etf_details_upserted", asset_id=asset_id)

    async def insert_etf_holdings(self, asset_id: int, holdings: List[Dict]):
        """Insert ETF holdings."""
        if not holdings:
            return

        async with self.pool.acquire() as conn:
            values = [
                (
                    asset_id,
                    h.get("ticker"),
                    h.get("name"),
                    h.get("weight"),
                    h.get("shares"),
                    h.get("market_value"),
                    h.get("snapshot_date", datetime.now().date()),
                )
                for h in holdings
            ]

            await conn.executemany(
                """
                INSERT INTO etf_holdings
                (etf_asset_id, holding_ticker, holding_name, weight, shares, market_value, snapshot_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (etf_asset_id, holding_ticker, snapshot_date) DO NOTHING
                """,
                values,
            )

            logger.info("etf_holdings_inserted", asset_id=asset_id, count=len(holdings))

    async def upsert_bond_details(self, asset_id: int, details: Dict):
        """Insert or update bond details."""
        if not details:
            return

        async with self.pool.acquire() as conn:
            fields = list(details.keys())
            placeholders = ", ".join(f"${i+2}" for i in range(len(fields)))
            field_names = ", ".join(fields)
            update_clause = ", ".join(f"{f} = EXCLUDED.{f}" for f in fields)

            query = f"""
                INSERT INTO bond_details (asset_id, {field_names})
                VALUES ($1, {placeholders})
                ON CONFLICT (asset_id)
                DO UPDATE SET {update_clause}
            """

            values = [asset_id] + [details[f] for f in fields]
            await conn.execute(query, *values)

            logger.info("bond_details_upserted", asset_id=asset_id)

    async def get_watchlist_tickers(self, watchlist_name: str) -> List[str]:
        """Get tickers from a watchlist."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT a.ticker
                FROM watchlist_items wi
                JOIN watchlists w ON w.id = wi.watchlist_id
                JOIN assets a ON a.id = wi.asset_id
                WHERE w.name = $1
                """,
                watchlist_name,
            )

            return [row["ticker"] for row in rows]

    async def log_data_fetch(
        self,
        job_type: str,
        status: str,
        records_processed: int = 0,
        ticker: Optional[str] = None,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ):
        """Log data fetch job for tracking."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO data_fetch_log
                (job_type, ticker, status, records_processed, error_message,
                 started_at, completed_at, duration_ms)
                VALUES ($1, $2, $3, $4, $5, NOW(), NOW(), $6)
                """,
                job_type,
                ticker,
                status,
                records_processed,
                error_message,
                duration_ms,
            )
