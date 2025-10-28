"""
Database connection management

Consolidates all database connection logic from across services into
a single, well-tested module with connection pooling and proper error handling.
"""

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator, Optional
import asyncpg
import psycopg2
from psycopg2.extras import RealDictCursor
import structlog

from financial_screener.config import get_settings

logger = structlog.get_logger(__name__)

# Global connection pool (initialized once per process)
_async_pool: Optional[asyncpg.Pool] = None


# =============================================================================
# ASYNC DATABASE CONNECTIONS (asyncpg - for data-collector, technical-analyzer)
# =============================================================================


async def init_async_pool() -> asyncpg.Pool:
    """
    Initialize async connection pool.

    Should be called once at application startup.

    Returns:
        asyncpg.Pool: Connection pool

    Example:
        # At app startup
        await init_async_pool()

        # Later in code
        async with get_async_connection() as conn:
            result = await conn.fetch("SELECT * FROM assets LIMIT 10")
    """
    global _async_pool

    if _async_pool is not None:
        logger.warning("async_pool_already_initialized")
        return _async_pool

    settings = get_settings()
    db_config = settings.database

    try:
        _async_pool = await asyncpg.create_pool(
            host=db_config.host,
            port=db_config.port,
            user=db_config.user,
            password=db_config.password,
            database=db_config.database,
            min_size=db_config.pool_min_size,
            max_size=db_config.pool_max_size,
            timeout=db_config.pool_timeout,
            command_timeout=60,  # 60 seconds for long queries
        )

        logger.info(
            "async_pool_initialized",
            host=db_config.host,
            database=db_config.database,
            pool_min=db_config.pool_min_size,
            pool_max=db_config.pool_max_size,
        )

        return _async_pool

    except Exception as e:
        logger.error("async_pool_init_failed", error=str(e), exc_info=True)
        raise


async def close_async_pool() -> None:
    """
    Close async connection pool.

    Should be called at application shutdown.

    Example:
        # At app shutdown
        await close_async_pool()
    """
    global _async_pool

    if _async_pool is None:
        return

    try:
        await _async_pool.close()
        _async_pool = None
        logger.info("async_pool_closed")
    except Exception as e:
        logger.error("async_pool_close_failed", error=str(e))


def get_async_pool() -> asyncpg.Pool:
    """
    Get the existing async connection pool.

    Raises:
        RuntimeError: If pool not initialized

    Returns:
        asyncpg.Pool: Connection pool
    """
    if _async_pool is None:
        raise RuntimeError("Async pool not initialized. Call init_async_pool() first.")
    return _async_pool


@asynccontextmanager
async def get_async_connection() -> AsyncIterator[asyncpg.Connection]:
    """
    Get async database connection from pool (context manager).

    Automatically handles connection acquisition and release.

    Yields:
        asyncpg.Connection: Database connection

    Example:
        async with get_async_connection() as conn:
            result = await conn.fetch("SELECT * FROM assets WHERE ticker = $1", "AAPL")
            for row in result:
                print(row['name'])
    """
    pool = get_async_pool()

    conn = await pool.acquire()
    try:
        # Set search_path for convenience
        await conn.execute("SET search_path TO financial_screener, public")
        yield conn
    finally:
        await pool.release(conn)


# =============================================================================
# SYNC DATABASE CONNECTIONS (psycopg2 - for Airflow DAGs)
# =============================================================================


@contextmanager
def get_sync_connection() -> Iterator[psycopg2.extensions.connection]:
    """
    Get synchronous database connection (context manager).

    Used primarily by Airflow DAGs where async is not available.

    Yields:
        psycopg2.connection: Database connection

    Example:
        with get_sync_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM assets LIMIT 10")
                rows = cur.fetchall()
    """
    settings = get_settings()
    db_config = settings.database

    conn = None
    try:
        conn = psycopg2.connect(
            host=db_config.host,
            port=db_config.port,
            user=db_config.user,
            password=db_config.password,
            dbname=db_config.database,
            connect_timeout=db_config.pool_timeout,
        )
        conn.autocommit = False  # Explicit transaction control

        # Set search_path
        with conn.cursor() as cur:
            cur.execute("SET search_path TO financial_screener, public")

        yield conn

        # Commit if no exception
        conn.commit()

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("sync_connection_failed", error=str(e))
        raise

    finally:
        if conn:
            conn.close()


@contextmanager
def get_db_cursor(dict_cursor: bool = True) -> Iterator[psycopg2.extensions.cursor]:
    """
    Get database cursor (context manager).

    Convenience function for Airflow DAGs that need quick queries.

    Args:
        dict_cursor: If True, return RealDictCursor (rows as dicts)

    Yields:
        psycopg2.cursor: Database cursor

    Example:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM assets WHERE exchange = %s", ("NYSE",))
            rows = cur.fetchall()
            for row in rows:
                print(row['ticker'], row['name'])
    """
    with get_sync_connection() as conn:
        cursor_factory = RealDictCursor if dict_cursor else None
        with conn.cursor(cursor_factory=cursor_factory) as cur:
            yield cur


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def execute_query(
    query: str,
    params: Optional[tuple] = None,
    fetch: bool = True,
) -> list:
    """
    Execute a query and return results (synchronous).

    Convenience function for simple queries in Airflow DAGs.

    Args:
        query: SQL query with placeholders (%s)
        params: Query parameters
        fetch: If True, fetch and return results

    Returns:
        list: Query results (empty if fetch=False)

    Example:
        # Fetch results
        results = execute_query(
            "SELECT * FROM assets WHERE exchange = %s",
            params=("NYSE",),
            fetch=True
        )

        # Execute without fetch (INSERT/UPDATE/DELETE)
        execute_query(
            "UPDATE assets SET is_active = %s WHERE ticker = %s",
            params=(False, "TSLA.US"),
            fetch=False
        )
    """
    with get_db_cursor() as cur:
        cur.execute(query, params or ())

        if fetch:
            return cur.fetchall()

    return []


async def execute_query_async(
    query: str,
    *args,
    fetch_one: bool = False,
) -> list:
    """
    Execute a query and return results (asynchronous).

    Args:
        query: SQL query with placeholders ($1, $2, ...)
        *args: Query parameters
        fetch_one: If True, return single row instead of list

    Returns:
        list or dict: Query results

    Example:
        # Fetch multiple rows
        results = await execute_query_async(
            "SELECT * FROM assets WHERE exchange = $1",
            "NYSE"
        )

        # Fetch single row
        asset = await execute_query_async(
            "SELECT * FROM assets WHERE ticker = $1",
            "AAPL.US",
            fetch_one=True
        )
    """
    async with get_async_connection() as conn:
        if fetch_one:
            return await conn.fetchrow(query, *args)
        else:
            return await conn.fetch(query, *args)


# =============================================================================
# DATABASE URL PARSING (for DATABASE_URL environment variable)
# =============================================================================


def parse_database_url(url: str) -> dict:
    """
    Parse DATABASE_URL into components.

    Supports the common postgres:// and postgresql:// URL formats.

    Args:
        url: Database URL (e.g., postgresql://user:pass@host:port/dbname)

    Returns:
        dict: Database connection parameters

    Example:
        url = "postgresql://appuser:pass@localhost:5432/appdb"
        config = parse_database_url(url)
        # {'host': 'localhost', 'port': 5432, 'user': 'appuser', ...}
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)

    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": parsed.username,
        "password": parsed.password,
        "database": parsed.path.lstrip("/"),
    }
