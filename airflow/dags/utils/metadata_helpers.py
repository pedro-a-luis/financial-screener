"""
Metadata helper functions for Airflow DAGs
Handles process execution tracking and delta discovery
"""

import json
from datetime import datetime, date
from typing import Dict, List, Optional
import structlog

from utils.database_utils import get_db_cursor, execute_query
from utils.api_quota_calculator import validate_quota_for_execution

logger = structlog.get_logger()


def initialize_execution_record(**context) -> str:
    """
    Create process_executions record at DAG start.

    Called by: initialize_execution task (PythonOperator)

    Args:
        context: Airflow task context

    Returns:
        str: execution_id (Airflow run_id)
    """
    execution_id = context['run_id']
    dag_id = context['dag'].dag_id
    logical_date = context.get('logical_date') or context.get('execution_date')

    logger.info(
        "initializing_execution_record",
        execution_id=execution_id,
        dag_id=dag_id
    )

    query = """
        INSERT INTO process_executions (
            process_name,
            execution_id,
            parameters,
            status,
            started_at,
            created_at
        ) VALUES (%s, %s, %s, %s, NOW(), NOW())
        RETURNING id
    """

    parameters = {
        'dag_id': dag_id,
        'execution_date': str(logical_date),
        'triggered_by': context.get('dag_run').run_type,
        'conf': context.get('dag_run').conf or {},
    }

    with get_db_cursor() as cur:
        cur.execute(
            query,
            (dag_id, execution_id, json.dumps(parameters), 'running')
        )
        result = cur.fetchone()

    logger.info(
        "execution_record_created",
        execution_id=execution_id,
        record_id=result['id']
    )

    return execution_id


def discover_processing_delta(**context) -> Dict[str, List[str]]:
    """
    Query metadata to discover what needs processing.

    Uses v_assets_needing_processing view to determine:
    - New tickers (bulk load needed)
    - Existing tickers (price update needed)
    - Tickers needing indicator calculation

    Called by: discover_delta task (PythonOperator)

    Args:
        context: Airflow task context

    Returns:
        dict: Categorized ticker lists
            {
                'bulk_load': ['TICKER1', 'TICKER2', ...],
                'price_update': ['TICKER3', 'TICKER4', ...],
                'indicator_calc': ['TICKER5', ...],
                'up_to_date': ['TICKER6', ...],
                'total_discovered': int
            }
    """
    logger.info("discovering_processing_delta")

    query = """
        SELECT
            processing_need,
            ticker
        FROM v_assets_needing_processing
        ORDER BY processing_need, ticker
    """

    results = {
        'bulk_load': [],
        'price_update': [],
        'indicator_calc': [],
        'up_to_date': [],
        'total_discovered': 0,
    }

    with get_db_cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()

        for row in rows:
            need = row['processing_need']
            ticker = row['ticker']

            if need in results:
                results[need].append(ticker)

            results['total_discovered'] += 1

    logger.info(
        "delta_discovery_complete",
        bulk_load_count=len(results['bulk_load']),
        price_update_count=len(results['price_update']),
        indicator_calc_count=len(results['indicator_calc']),
        up_to_date_count=len(results['up_to_date']),
        total=results['total_discovered']
    )

    # Store in XCom for downstream tasks
    context['ti'].xcom_push(key='delta_discovery', value=results)

    return results


def check_and_adjust_quota(**context) -> Dict:
    """
    Check API quota and adjust processing batch sizes if needed.

    Uses the new API quota management system with real-time tracking.

    Called by: check_api_quota task (PythonOperator)

    API costs (EODHD pricing):
    - Fundamentals: 10 API calls per ticker
    - EOD Prices: 1 API call per ticker
    - Bulk load (new ticker): 11 API calls (10 fundamentals + 1 prices)
    - Price update (existing): 1 API call

    Daily limit: 100,000 API calls (All-World plan)
    Safety buffer: 10% (10,000 calls)

    Args:
        context: Airflow task context

    Returns:
        dict: Quota validation result with adjusted batch sizes
            {
                'can_proceed': bool,
                'recommendation': str,
                'quota_status': dict,
                'required_calls': dict,
                'adjusted_bulk_tickers': int,
                'adjusted_price_tickers': int,
                'original_bulk_tickers': int,
                'original_price_tickers': int
            }
    """
    execution_id = context['run_id']
    delta = context['ti'].xcom_pull(task_ids='discover_delta', key='delta_discovery')

    if not delta:
        logger.warning("no_delta_found_in_xcom", execution_id=execution_id)
        return {'error': 'No delta discovery data'}

    # Get counts from delta discovery
    tickers_needing_bulk = len(delta.get('bulk_load', []))
    tickers_needing_prices = len(delta.get('price_update', []))

    logger.info(
        "checking_api_quota_with_new_system",
        execution_id=execution_id,
        bulk_tickers=tickers_needing_bulk,
        price_tickers=tickers_needing_prices
    )

    # Use new quota validation system
    quota_result = validate_quota_for_execution(
        execution_id=execution_id,
        tickers_needing_bulk=tickers_needing_bulk,
        tickers_needing_prices=tickers_needing_prices
    )

    # Create adjusted delta with new batch sizes
    adjusted_delta = delta.copy()
    adjusted_delta['bulk_load'] = delta['bulk_load'][:quota_result['adjusted_bulk_tickers']]
    adjusted_delta['price_update'] = delta['price_update'][:quota_result['adjusted_price_tickers']]

    # Add comprehensive quota info
    adjusted_delta['quota_info'] = {
        'can_proceed': quota_result['can_proceed'],
        'recommendation': quota_result['recommendation'],
        'quota_health': quota_result['quota_status']['quota_health'],
        'calls_used_today': quota_result['quota_status']['calls_used'],
        'calls_remaining': quota_result['quota_status']['calls_remaining'],
        'usage_percentage': quota_result['quota_status']['usage_percentage'],
        'total_required': quota_result['required_calls']['total_calls'],
        'bulk_load_calls': quota_result['required_calls']['bulk_load_calls'],
        'price_update_calls': quota_result['required_calls']['price_update_calls'],
        'adjusted': (
            quota_result['adjusted_bulk_tickers'] < tickers_needing_bulk or
            quota_result['adjusted_price_tickers'] < tickers_needing_prices
        ),
        'original_bulk_count': tickers_needing_bulk,
        'adjusted_bulk_count': quota_result['adjusted_bulk_tickers'],
        'original_price_count': tickers_needing_prices,
        'adjusted_price_count': quota_result['adjusted_price_tickers'],
    }

    # Log quota decision
    if adjusted_delta['quota_info']['adjusted']:
        logger.warning(
            "quota_batch_adjusted",
            execution_id=execution_id,
            recommendation=quota_result['recommendation'],
            original_bulk=tickers_needing_bulk,
            adjusted_bulk=quota_result['adjusted_bulk_tickers'],
            original_price=tickers_needing_prices,
            adjusted_price=quota_result['adjusted_price_tickers'],
            quota_health=quota_result['quota_status']['quota_health']
        )
    else:
        logger.info(
            "quota_sufficient_no_adjustment",
            execution_id=execution_id,
            recommendation=quota_result['recommendation'],
            bulk_tickers=tickers_needing_bulk,
            price_tickers=tickers_needing_prices,
            quota_health=quota_result['quota_status']['quota_health']
        )

    # Store final delta in XCom
    context['ti'].xcom_push(key='final_delta', value=adjusted_delta)
    context['ti'].xcom_push(key='quota_validation', value=quota_result)

    return adjusted_delta


def finalize_execution_record(**context) -> Dict:
    """
    Update process_executions with final statistics.

    Called by: finalize_execution task (PythonOperator)

    Aggregates results from asset_processing_details and updates
    the process_executions record with final counts and status.

    Args:
        context: Airflow task context

    Returns:
        dict: Execution statistics
    """
    execution_id = context['run_id']

    logger.info("finalizing_execution_record", execution_id=execution_id)

    # Aggregate stats from asset_processing_details
    stats_query = """
        SELECT
            COUNT(*) as total_processed,
            COUNT(*) FILTER (WHERE status = 'success') as succeeded,
            COUNT(*) FILTER (WHERE status = 'failed') as failed,
            COUNT(*) FILTER (WHERE status = 'skipped') as skipped,
            COALESCE(SUM(api_calls_used), 0) as api_calls_used,
            COUNT(DISTINCT operation) as operations_count
        FROM asset_processing_details
        WHERE execution_id = %s
    """

    with get_db_cursor() as cur:
        cur.execute(stats_query, (execution_id,))
        stats = cur.fetchone()

        # Determine final status
        if stats['total_processed'] == 0:
            final_status = 'failed'  # No processing occurred
        elif stats['failed'] == 0:
            final_status = 'success'
        elif stats['total_processed'] > 0 and (stats['failed'] / stats['total_processed']) > 0.1:
            final_status = 'partial'  # More than 10% failed
        else:
            final_status = 'success'  # Less than 10% failures acceptable

        # Update process_executions
        update_query = """
            UPDATE process_executions
            SET status = %s,
                assets_processed = %s,
                assets_succeeded = %s,
                assets_failed = %s,
                api_calls_used = %s,
                completed_at = NOW(),
                duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER
            WHERE execution_id = %s
        """

        cur.execute(
            update_query,
            (
                final_status,
                stats['total_processed'],
                stats['succeeded'],
                stats['failed'],
                stats['api_calls_used'],
                execution_id
            )
        )

    logger.info(
        "execution_finalized",
        execution_id=execution_id,
        status=final_status,
        total_processed=stats['total_processed'],
        succeeded=stats['succeeded'],
        failed=stats['failed'],
        api_calls=stats['api_calls_used']
    )

    result = dict(stats)
    result['final_status'] = final_status

    return result


def get_processing_progress() -> Dict:
    """
    Get current processing progress across all tickers.

    Useful for monitoring and debugging.

    Returns:
        dict: Progress statistics
    """
    query = "SELECT * FROM get_processing_progress()"

    rows = execute_query(query, fetch=True)

    progress = {}
    for row in rows:
        progress[row['metric']] = {
            'value': row['value'],
            'percentage': float(row['percentage'])
        }

    return progress


def get_recent_executions(limit: int = 10) -> List[Dict]:
    """
    Get recent DAG executions from v_recent_executions view.

    Args:
        limit: Number of recent executions to return

    Returns:
        list: Recent execution records
    """
    query = f"""
        SELECT *
        FROM v_recent_executions
        LIMIT {limit}
    """

    return execute_query(query, fetch=True)


def reset_ticker_for_reprocessing(
    ticker: str,
    component: str = 'all'
) -> None:
    """
    Mark a ticker for reprocessing.

    Args:
        ticker: Ticker symbol
        component: What to reprocess ('fundamentals', 'prices', 'indicators', 'all')
    """
    query = "SELECT reset_ticker_for_reprocessing(%s, %s)"

    execute_query(query, params=(ticker, component), fetch=False)

    logger.info(
        "ticker_marked_for_reprocessing",
        ticker=ticker,
        component=component
    )


def get_failed_tickers(min_failures: int = 3) -> List[Dict]:
    """
    Get tickers with consecutive failures.

    Args:
        min_failures: Minimum number of consecutive failures

    Returns:
        list: Failed ticker records
    """
    query = """
        SELECT
            ticker,
            consecutive_failures,
            last_error_at,
            last_error_message
        FROM asset_processing_state
        WHERE consecutive_failures >= %s
        ORDER BY consecutive_failures DESC, last_error_at DESC
    """

    return execute_query(query, params=(min_failures,), fetch=True)


def get_todays_activity() -> List[Dict]:
    """
    Get today's processing activity from v_today_processing_activity view.

    Returns:
        list: Today's activity summary
    """
    query = "SELECT * FROM v_today_processing_activity"

    return execute_query(query, fetch=True)


if __name__ == "__main__":
    # Test functions when run directly
    import pprint

    print("Testing metadata helpers...")
    print("\n1. Processing Progress:")
    pprint.pprint(get_processing_progress())

    print("\n2. Recent Executions:")
    pprint.pprint(get_recent_executions(limit=5))

    print("\n3. Failed Tickers:")
    pprint.pprint(get_failed_tickers(min_failures=3))

    print("\n4. Today's Activity:")
    pprint.pprint(get_todays_activity())
