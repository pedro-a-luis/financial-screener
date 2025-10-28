"""
Database connection utilities for Airflow DAGs
Provides PostgreSQL connections with proper error handling
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import structlog

logger = structlog.get_logger()


def get_db_connection():
    """
    Get PostgreSQL connection for financial_screener schema.

    Tries multiple methods in order:
    1. Airflow connection (if available)
    2. Environment variable DATABASE_URL
    3. Constructed from individual env vars

    Returns:
        psycopg2.connection: Active database connection

    Raises:
        Exception: If no valid connection method available
    """
    # Method 1: Try Airflow connection
    try:
        from airflow.hooks.base import BaseHook
        conn_params = BaseHook.get_connection('postgres_financial_screener')

        connection = psycopg2.connect(
            host=conn_params.host,
            port=conn_params.port or 5432,
            user=conn_params.login,
            password=conn_params.password,
            dbname=conn_params.schema or 'appdb',
        )

        logger.info("database_connection_via_airflow_hook")
        return connection

    except Exception as e:
        logger.debug("airflow_hook_not_available", error=str(e))

    # Method 2: DATABASE_URL environment variable
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        connection = psycopg2.connect(database_url)
        logger.info("database_connection_via_env_url")
        return connection

    # Method 3: Individual environment variables
    db_host = os.getenv('DB_HOST', 'postgresql-primary.databases.svc.cluster.local')
    db_port = os.getenv('DB_PORT', '5432')
    db_user = os.getenv('DB_USER', 'appuser')
    db_password = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME', 'appdb')

    if db_password:
        connection = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            dbname=db_name,
        )
        logger.info("database_connection_via_env_vars")
        return connection

    raise Exception("No valid database connection method available")


@contextmanager
def get_db_cursor(dict_cursor=True):
    """
    Context manager for database cursor with automatic cleanup.

    Usage:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM assets")
            rows = cur.fetchall()

    Args:
        dict_cursor: If True, return RealDictCursor for dict-like rows

    Yields:
        psycopg2.cursor: Database cursor
    """
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor if dict_cursor else None)

        # Set search path to financial_screener schema
        cursor.execute("SET search_path TO financial_screener, public")

        yield cursor

        # Commit on successful completion
        conn.commit()

    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("database_operation_failed", error=str(e))
        raise

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def execute_query(query, params=None, fetch=True):
    """
    Execute a SQL query with automatic connection management.

    Args:
        query: SQL query string
        params: Query parameters (tuple or list)
        fetch: If True, return fetchall() results

    Returns:
        list: Query results if fetch=True, else None
    """
    with get_db_cursor() as cur:
        cur.execute(query, params or ())

        if fetch:
            return cur.fetchall()

        return None


def execute_many(query, params_list):
    """
    Execute a SQL query multiple times with different parameters.

    Args:
        query: SQL query string
        params_list: List of parameter tuples

    Returns:
        int: Number of rows affected
    """
    with get_db_cursor(dict_cursor=False) as cur:
        cur.executemany(query, params_list)
        return cur.rowcount


def test_connection():
    """
    Test database connection and schema access.

    Returns:
        dict: Connection test results
    """
    try:
        with get_db_cursor() as cur:
            # Test basic query
            cur.execute("SELECT 1 as test")
            result = cur.fetchone()

            # Test metadata tables exist
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'financial_screener'
                  AND table_name IN ('process_executions', 'asset_processing_state', 'asset_processing_details')
                ORDER BY table_name
            """)
            tables = [row['table_name'] for row in cur.fetchall()]

            return {
                'success': True,
                'connection_test': result['test'] == 1,
                'metadata_tables': tables,
                'all_tables_present': len(tables) == 3
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


if __name__ == "__main__":
    # Test when run directly
    import json
    result = test_connection()
    print(json.dumps(result, indent=2))
