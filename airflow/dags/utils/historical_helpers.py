"""
Historical Load Helper Functions
Support functions for reverse chronological historical data loading
"""

import asyncio
import asyncpg
import json
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Tuple, Optional
import structlog

logger = structlog.get_logger()

# =============================================================================
# DATABASE CONNECTION
# =============================================================================

async def get_db_connection(database_url: str = None):
    """Get database connection from environment or parameter."""
    import os
    if not database_url:
        database_url = os.getenv('DATABASE_URL')

    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")

    return await asyncpg.connect(database_url)


# =============================================================================
# HISTORICAL LOAD FUNCTIONS
# =============================================================================

def initialize_historical_execution(**context):
    """
    Initialize historical load execution record.

    Creates a process_executions record to track this historical load run.
    Returns execution_id (Airflow run_id) for downstream tasks.
    """
    execution_id = context['run_id']
    dag_id = context['dag'].dag_id
    execution_date = context.get('logical_date') or context.get('execution_date')  # Airflow 3.x uses logical_date

    async def _initialize():
        conn = await get_db_connection()
        try:
            await conn.execute("SET search_path TO financial_screener")

            # Create execution record
            await conn.execute("""
                INSERT INTO process_executions (
                    execution_id,
                    process_name,
                    parameters,
                    status,
                    started_at
                ) VALUES ($1, $2, $3::jsonb, $4, $5)
                ON CONFLICT (execution_id) DO UPDATE
                SET started_at = EXCLUDED.started_at,
                    parameters = EXCLUDED.parameters
            """, execution_id, 'historical_load',
                json.dumps({'execution_date': str(execution_date), 'dag_id': dag_id}),
                'running', datetime.now())

            logger.info("historical_execution_initialized",
                       execution_id=execution_id,
                       dag_id=dag_id)

        finally:
            await conn.close()

    asyncio.run(_initialize())

    # Push execution_id to XCom
    context['ti'].xcom_push(key='execution_id', value=execution_id)

    return execution_id


def determine_next_month_to_load(**context):
    """
    Determine the next month that needs historical data loading.

    Strategy:
    1. Query asset_processing_state for all tickers
    2. Find the earliest prices_first_date (oldest data we have)
    3. Calculate the month BEFORE that date
    4. Return start_date and end_date for that month

    Returns (via XCom):
        start_date: First day of target month (YYYY-MM-DD)
        end_date: Last day of target month (YYYY-MM-DD)
        tickers_count: Number of tickers to process
        target_month: Month being loaded (YYYY-MM)
    """
    dag_run_conf = context.get('dag_run').conf or {}
    target_years = dag_run_conf.get('target_years', 2)  # Default: 2 years

    async def _determine_month():
        conn = await get_db_connection()
        try:
            await conn.execute("SET search_path TO financial_screener")

            # Find the earliest prices_first_date across all tickers
            result = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_tickers,
                    MIN(prices_first_date) as oldest_first_date,
                    MAX(prices_last_date) as newest_last_date,
                    COUNT(*) FILTER (WHERE prices_first_date IS NULL) as tickers_without_data
                FROM asset_processing_state
                WHERE fundamentals_loaded = TRUE
            """)

            total_tickers = result['total_tickers']
            oldest_first_date = result['oldest_first_date']
            newest_last_date = result['newest_last_date']
            tickers_without_data = result['tickers_without_data']

            logger.info("historical_load_status",
                       total_tickers=total_tickers,
                       oldest_first_date=oldest_first_date,
                       newest_last_date=newest_last_date,
                       tickers_without_data=tickers_without_data)

            # Calculate target depth (how far back we want to go)
            target_date = date.today() - timedelta(days=target_years * 365)

            # Determine next month to load
            if oldest_first_date is None:
                # No historical data yet, start from most recent complete month
                today = date.today()
                # Go back to first day of last month
                first_day_last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
                start_date = first_day_last_month
                end_date = (start_date + relativedelta(months=1)) - timedelta(days=1)

            elif oldest_first_date > target_date:
                # Still need to go back further
                # Load the month BEFORE oldest_first_date
                month_before = oldest_first_date - relativedelta(months=1)
                start_date = month_before.replace(day=1)
                end_date = (start_date + relativedelta(months=1)) - timedelta(days=1)

            else:
                # Already reached target depth
                logger.info("historical_load_target_reached",
                           oldest_date=oldest_first_date,
                           target_date=target_date)
                return None, None, 0, None

            # Count tickers that need this month's data
            tickers_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM asset_processing_state
                WHERE fundamentals_loaded = TRUE
                  AND (prices_first_date IS NULL OR prices_first_date > $1)
            """, start_date)

            target_month = start_date.strftime('%Y-%m')

            logger.info("next_month_determined",
                       start_date=start_date,
                       end_date=end_date,
                       target_month=target_month,
                       tickers_count=tickers_count)

            return str(start_date), str(end_date), tickers_count, target_month

        finally:
            await conn.close()

    start_date, end_date, tickers_count, target_month = asyncio.run(_determine_month())

    # Push to XCom for downstream tasks
    ti = context['ti']
    ti.xcom_push(key='start_date', value=start_date)
    ti.xcom_push(key='end_date', value=end_date)
    ti.xcom_push(key='tickers_count', value=tickers_count)
    ti.xcom_push(key='target_month', value=target_month)

    return {
        'start_date': start_date,
        'end_date': end_date,
        'tickers_count': tickers_count,
        'target_month': target_month
    }


def check_completion_status(**context):
    """
    Check if historical load has reached target depth (2 years).

    Returns:
        'historical_load_complete': If target reached
        'process_historical_data': If more data needed
    """
    dag_run_conf = context.get('dag_run').conf or {}
    target_years = dag_run_conf.get('target_years', 2)

    # Get data from previous task
    ti = context['ti']
    start_date = ti.xcom_pull(task_ids='determine_next_month', key='start_date')
    tickers_count = ti.xcom_pull(task_ids='determine_next_month', key='tickers_count')

    # If determine_next_month returned None, we're complete
    if start_date is None or tickers_count == 0:
        logger.info("historical_load_complete", reason="target_depth_reached")
        return 'historical_load_complete'

    async def _check_completion():
        conn = await get_db_connection()
        try:
            await conn.execute("SET search_path TO financial_screener")

            # Check how many tickers have reached target depth
            target_date = date.today() - timedelta(days=target_years * 365)

            result = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_tickers,
                    COUNT(*) FILTER (WHERE prices_first_date <= $1) as complete_tickers,
                    COUNT(*) FILTER (WHERE prices_first_date IS NULL OR prices_first_date > $1) as incomplete_tickers
                FROM asset_processing_state
                WHERE fundamentals_loaded = TRUE
            """, target_date)

            total = result['total_tickers']
            complete = result['complete_tickers']
            incomplete = result['incomplete_tickers']

            completion_pct = (complete / total * 100) if total > 0 else 0

            logger.info("completion_check",
                       total_tickers=total,
                       complete=complete,
                       incomplete=incomplete,
                       completion_pct=f"{completion_pct:.1f}%",
                       target_years=target_years)

            # Consider complete if 95%+ of tickers have target depth
            # (Some tickers may be delisted/invalid)
            return incomplete > 0

        finally:
            await conn.close()

    needs_processing = asyncio.run(_check_completion())

    if needs_processing:
        logger.info("historical_load_continuing", tickers_remaining=tickers_count)
        return 'process_historical_data'
    else:
        logger.info("historical_load_complete", reason="all_tickers_complete")
        return 'historical_load_complete'


def finalize_historical_execution(**context):
    """
    Finalize historical load execution record.

    Updates metadata with:
    - Total tickers processed
    - API calls used
    - Month loaded
    - Completion status
    - Progress toward target
    """
    execution_id = context['run_id']
    ti = context['ti']

    # Get data from XCom
    start_date = ti.xcom_pull(task_ids='determine_next_month', key='start_date')
    end_date = ti.xcom_pull(task_ids='determine_next_month', key='end_date')
    tickers_count = ti.xcom_pull(task_ids='determine_next_month', key='tickers_count')
    target_month = ti.xcom_pull(task_ids='determine_next_month', key='target_month')

    async def _finalize():
        conn = await get_db_connection()
        try:
            await conn.execute("SET search_path TO financial_screener")

            # Query actual results from asset_processing_details
            results = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_processed,
                    COUNT(*) FILTER (WHERE status = 'success') as successful,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    COALESCE(SUM(api_calls_used), 0) as total_api_calls
                FROM asset_processing_details
                WHERE execution_id = $1
                  AND operation IN ('prices_incremental', 'prices_historical')
            """, execution_id)

            total_processed = results['total_processed']
            successful = results['successful']
            failed = results['failed']
            total_api_calls = results['total_api_calls']

            # Calculate progress
            progress_result = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_tickers,
                    AVG(EXTRACT(days FROM (CURRENT_DATE - prices_first_date))) as avg_depth_days,
                    MIN(prices_first_date) as oldest_date
                FROM asset_processing_state
                WHERE fundamentals_loaded = TRUE
                  AND prices_first_date IS NOT NULL
            """)

            avg_depth_days = float(progress_result['avg_depth_days'] or 0)
            target_days = 2 * 365  # 2 years
            progress_pct = min((avg_depth_days / target_days * 100), 100)

            # Determine final status
            if total_processed == 0:
                final_status = 'complete'  # Nothing to process
            elif failed == 0:
                final_status = 'success'
            elif successful > 0:
                final_status = 'partial'
            else:
                final_status = 'failed'

            # Update process_executions
            await conn.execute("""
                UPDATE process_executions
                SET
                    status = $2,
                    completed_at = $3,
                    assets_processed = $4,
                    assets_succeeded = $5,
                    assets_failed = $6,
                    api_calls_used = $7,
                    parameters = parameters || jsonb_build_object(
                        'month_loaded', $8,
                        'start_date', $9,
                        'end_date', $10,
                        'progress_pct', $11,
                        'avg_depth_days', $12
                    )
                WHERE execution_id = $1
            """, execution_id, final_status, datetime.now(),
                total_processed, successful, failed, total_api_calls,
                target_month, start_date, end_date, progress_pct, avg_depth_days)

            logger.info("historical_execution_finalized",
                       execution_id=execution_id,
                       status=final_status,
                       month_loaded=target_month,
                       processed=total_processed,
                       successful=successful,
                       failed=failed,
                       api_calls=total_api_calls,
                       progress_pct=f"{progress_pct:.1f}%")

            return {
                'status': final_status,
                'processed': total_processed,
                'successful': successful,
                'failed': failed,
                'api_calls': total_api_calls,
                'progress_pct': progress_pct
            }

        finally:
            await conn.close()

    result = asyncio.run(_finalize())

    # Push results to XCom
    ti.xcom_push(key='finalization_results', value=result)

    return result


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_historical_progress_report(**context):
    """
    Generate a progress report for historical loading.

    Returns summary of:
    - Total months loaded
    - Percentage complete
    - Estimated days remaining
    - API calls used so far
    """
    async def _get_report():
        conn = await get_db_connection()
        try:
            await conn.execute("SET search_path TO financial_screener")

            report = await conn.fetchrow("""
                WITH ticker_stats AS (
                    SELECT
                        COUNT(*) as total_tickers,
                        AVG(EXTRACT(days FROM (CURRENT_DATE - prices_first_date))) as avg_depth_days,
                        MIN(prices_first_date) as oldest_date,
                        MAX(prices_last_date) as newest_date,
                        COUNT(*) FILTER (WHERE prices_first_date IS NOT NULL) as tickers_with_history
                    FROM asset_processing_state
                    WHERE fundamentals_loaded = TRUE
                ),
                execution_stats AS (
                    SELECT
                        COUNT(*) as total_runs,
                        SUM(api_calls_used) as total_api_calls,
                        MIN(started_at) as first_run,
                        MAX(completed_at) as last_run
                    FROM process_executions
                    WHERE process_name = 'historical_load'
                      AND status != 'failed'
                )
                SELECT
                    ts.*,
                    es.total_runs,
                    es.total_api_calls,
                    es.first_run,
                    es.last_run
                FROM ticker_stats ts
                CROSS JOIN execution_stats es
            """)

            target_days = 2 * 365
            avg_depth = float(report['avg_depth_days'] or 0)
            progress_pct = min((avg_depth / target_days * 100), 100)
            days_remaining = max(0, int((target_days - avg_depth) / 30))  # Approximate months remaining

            return {
                'total_tickers': report['total_tickers'],
                'tickers_with_history': report['tickers_with_history'],
                'avg_depth_days': int(avg_depth),
                'progress_pct': f"{progress_pct:.1f}%",
                'oldest_date': str(report['oldest_date']),
                'newest_date': str(report['newest_date']),
                'total_runs': report['total_runs'],
                'total_api_calls': report['total_api_calls'],
                'estimated_months_remaining': days_remaining,
                'first_run': str(report['first_run']),
                'last_run': str(report['last_run'])
            }

        finally:
            await conn.close()

    report = asyncio.run(_get_report())

    logger.info("historical_progress_report", **report)

    return report
