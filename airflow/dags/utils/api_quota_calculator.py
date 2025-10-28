"""
API Quota Calculator for EODHD API
Intelligent quota management and batch size adjustment
"""

from typing import Dict, Tuple, Optional
import structlog
from .database_utils import get_db_cursor, execute_query

logger = structlog.get_logger()

# =====================================================
# EODHD API PRICING CONSTANTS
# =====================================================

# API call costs per endpoint (based on EODHD All-World plan pricing)
API_COSTS = {
    'fundamentals': 10,      # Fundamentals API: 10 calls per ticker
    'eod_prices': 1,         # End of Day Prices: 1 call per ticker
    'bulk_exchange': 100,    # Bulk Exchange API: 100 calls (not used currently)
}

# Daily limits (All-World plan: $79.99/month = 100K calls/day)
DAILY_QUOTA_LIMIT = 100000

# Safety buffer (keep 10% as safety margin)
SAFETY_BUFFER_PERCENTAGE = 10.0


# =====================================================
# QUOTA CHECKING FUNCTIONS
# =====================================================

def get_current_quota_status() -> Dict:
    """
    Get current quota status for today.

    Returns:
        dict: {
            'quota_date': date,
            'daily_limit': int,
            'calls_used': int,
            'calls_remaining': int,
            'usage_percentage': float,
            'quota_health': str,  # 'healthy', 'warning', 'critical', 'exhausted'
            'quota_exhausted': bool
        }
    """
    query = """
        SELECT
            quota_date,
            daily_limit,
            calls_used,
            calls_remaining,
            ROUND(100.0 * calls_used / daily_limit, 2) as usage_percentage,
            quota_health,
            quota_exhausted,
            fundamentals_calls,
            eod_prices_calls,
            first_call_at,
            last_call_at
        FROM v_quota_status
        WHERE quota_date = CURRENT_DATE
        LIMIT 1
    """

    try:
        results = execute_query(query, fetch=True)

        if results and len(results) > 0:
            row = results[0]
            return {
                'quota_date': row['quota_date'],
                'daily_limit': row['daily_limit'],
                'calls_used': row['calls_used'],
                'calls_remaining': row['calls_remaining'],
                'usage_percentage': float(row['usage_percentage']),
                'quota_health': row['quota_health'],
                'quota_exhausted': row['quota_exhausted'],
                'fundamentals_calls': row['fundamentals_calls'],
                'eod_prices_calls': row['eod_prices_calls'],
                'first_call_at': row['first_call_at'],
                'last_call_at': row['last_call_at'],
            }
        else:
            # No record for today yet - initialize
            logger.info("no_quota_record_today", action="creating_new_record")
            with get_db_cursor() as cur:
                cur.execute("""
                    INSERT INTO api_daily_quota (quota_date, daily_limit)
                    VALUES (CURRENT_DATE, %s)
                    ON CONFLICT (quota_date) DO NOTHING
                """, (DAILY_QUOTA_LIMIT,))

            return {
                'quota_date': None,
                'daily_limit': DAILY_QUOTA_LIMIT,
                'calls_used': 0,
                'calls_remaining': DAILY_QUOTA_LIMIT,
                'usage_percentage': 0.0,
                'quota_health': 'healthy',
                'quota_exhausted': False,
                'fundamentals_calls': 0,
                'eod_prices_calls': 0,
                'first_call_at': None,
                'last_call_at': None,
            }

    except Exception as e:
        logger.error("quota_status_check_failed", error=str(e))
        raise


def calculate_required_calls(
    tickers_needing_bulk: int,
    tickers_needing_prices: int
) -> Dict:
    """
    Calculate total API calls required for processing.

    Args:
        tickers_needing_bulk: Number of tickers requiring bulk load (fundamentals + prices)
        tickers_needing_prices: Number of tickers requiring price updates only

    Returns:
        dict: {
            'bulk_load_calls': int,
            'price_update_calls': int,
            'total_calls': int,
            'cost_breakdown': dict
        }
    """
    # Bulk load: 10 fundamentals + 1 prices = 11 calls per ticker
    bulk_load_calls = tickers_needing_bulk * (API_COSTS['fundamentals'] + API_COSTS['eod_prices'])

    # Price update: 1 call per ticker
    price_update_calls = tickers_needing_prices * API_COSTS['eod_prices']

    total_calls = bulk_load_calls + price_update_calls

    logger.info(
        "calculated_required_calls",
        bulk_tickers=tickers_needing_bulk,
        price_tickers=tickers_needing_prices,
        bulk_calls=bulk_load_calls,
        price_calls=price_update_calls,
        total_calls=total_calls
    )

    return {
        'bulk_load_calls': bulk_load_calls,
        'price_update_calls': price_update_calls,
        'total_calls': total_calls,
        'cost_breakdown': {
            'bulk_load': {
                'tickers': tickers_needing_bulk,
                'calls_per_ticker': API_COSTS['fundamentals'] + API_COSTS['eod_prices'],
                'total_calls': bulk_load_calls
            },
            'price_update': {
                'tickers': tickers_needing_prices,
                'calls_per_ticker': API_COSTS['eod_prices'],
                'total_calls': price_update_calls
            }
        }
    }


def check_quota_available(
    required_calls: int,
    buffer_percentage: float = SAFETY_BUFFER_PERCENTAGE
) -> Dict:
    """
    Check if sufficient API quota available for planned operations.

    Args:
        required_calls: Number of API calls needed
        buffer_percentage: Safety buffer percentage (default: 10%)

    Returns:
        dict: {
            'available': bool,
            'calls_remaining': int,
            'calls_after_buffer': int,
            'can_proceed': bool,
            'recommendation': str,
            'adjusted_batch_size': int  (if reduction needed)
        }
    """
    quota_status = get_current_quota_status()

    calls_remaining = quota_status['calls_remaining']
    buffer_calls = int(quota_status['daily_limit'] * buffer_percentage / 100.0)
    calls_after_buffer = calls_remaining - buffer_calls

    can_proceed = calls_after_buffer >= required_calls

    # Determine recommendation
    if quota_status['quota_exhausted']:
        recommendation = "STOP: Daily quota exhausted"
        adjusted_batch_size = 0
    elif can_proceed:
        recommendation = "PROCEED: Sufficient quota available"
        adjusted_batch_size = required_calls
    elif calls_remaining >= required_calls:
        recommendation = f"CAUTION: Quota tight but available (within {buffer_percentage}% buffer)"
        adjusted_batch_size = required_calls
    else:
        # Need to reduce batch size
        adjusted_batch_size = max(0, calls_after_buffer)
        recommendation = f"REDUCE: Insufficient quota - reduce batch size to {adjusted_batch_size} calls"

    result = {
        'available': calls_remaining > 0,
        'calls_remaining': calls_remaining,
        'calls_after_buffer': calls_after_buffer,
        'can_proceed': can_proceed,
        'recommendation': recommendation,
        'required_calls': required_calls,
        'adjusted_batch_size': adjusted_batch_size,
        'quota_health': quota_status['quota_health'],
        'usage_percentage': quota_status['usage_percentage']
    }

    logger.info(
        "quota_availability_check",
        required=required_calls,
        remaining=calls_remaining,
        can_proceed=can_proceed,
        recommendation=recommendation
    )

    return result


def adjust_batch_sizes(
    bulk_tickers: int,
    price_tickers: int,
    available_calls: int
) -> Tuple[int, int]:
    """
    Adjust batch sizes to fit within available quota.

    Priority:
    1. Always process price updates (cheap: 1 call each)
    2. Process bulk loads if quota allows (expensive: 11 calls each)

    Args:
        bulk_tickers: Number of tickers needing bulk load
        price_tickers: Number of tickers needing price updates
        available_calls: Available API calls after buffer

    Returns:
        tuple: (adjusted_bulk_tickers, adjusted_price_tickers)
    """
    # Cost per operation
    bulk_cost = API_COSTS['fundamentals'] + API_COSTS['eod_prices']  # 11 calls
    price_cost = API_COSTS['eod_prices']  # 1 call

    # Priority 1: Price updates (cheap and important)
    price_calls_needed = price_tickers * price_cost
    remaining_after_prices = available_calls - price_calls_needed

    if remaining_after_prices < 0:
        # Not enough quota even for all price updates
        adjusted_price_tickers = available_calls // price_cost
        adjusted_bulk_tickers = 0

        logger.warning(
            "insufficient_quota_for_all_prices",
            requested_price_tickers=price_tickers,
            adjusted_price_tickers=adjusted_price_tickers,
            available_calls=available_calls
        )
    else:
        # All price updates fit - use remainder for bulk loads
        adjusted_price_tickers = price_tickers
        adjusted_bulk_tickers = min(bulk_tickers, remaining_after_prices // bulk_cost)

        logger.info(
            "batch_size_adjustment",
            original_bulk=bulk_tickers,
            original_price=price_tickers,
            adjusted_bulk=adjusted_bulk_tickers,
            adjusted_price=adjusted_price_tickers,
            available_calls=available_calls
        )

    return (adjusted_bulk_tickers, adjusted_price_tickers)


def get_priority_tickers(max_count: int = 1000, min_priority: int = 1) -> list:
    """
    Get list of priority tickers to process when quota is limited.

    Args:
        max_count: Maximum number of tickers to return
        min_priority: Minimum priority level (1=highest, 5=lowest)

    Returns:
        list: List of ticker symbols in priority order
    """
    query = """
        SELECT ticker, priority_level, priority_reason
        FROM api_ticker_priority
        WHERE priority_level >= %s
        ORDER BY priority_level ASC, ticker
        LIMIT %s
    """

    try:
        results = execute_query(query, params=(min_priority, max_count), fetch=True)
        tickers = [row['ticker'] for row in results]

        logger.info(
            "retrieved_priority_tickers",
            count=len(tickers),
            min_priority=min_priority,
            max_count=max_count
        )

        return tickers

    except Exception as e:
        logger.error("priority_ticker_retrieval_failed", error=str(e))
        return []


def log_api_call(
    execution_id: str,
    ticker: Optional[str],
    api_endpoint: str,
    api_calls_count: int,
    http_status_code: int = 200,
    response_time_ms: Optional[int] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None
) -> None:
    """
    Log an API call to the database and update quota counters.

    This function should be called from the data collector after each API call.

    Args:
        execution_id: Airflow execution ID
        ticker: Ticker symbol (or None for bulk operations)
        api_endpoint: 'fundamentals', 'eod_prices', or 'bulk_exchange'
        api_calls_count: Number of API calls consumed
        http_status_code: HTTP response code (200, 402, 404, etc.)
        response_time_ms: API response time in milliseconds
        error_code: Error code if failed
        error_message: Error message if failed
    """
    query = """
        SELECT log_api_call(
            %s, %s, %s, %s, %s, %s, %s, %s
        )
    """

    params = (
        execution_id,
        ticker,
        api_endpoint,
        api_calls_count,
        http_status_code,
        response_time_ms,
        error_code,
        error_message
    )

    try:
        execute_query(query, params=params, fetch=False)

        logger.debug(
            "api_call_logged",
            execution_id=execution_id,
            ticker=ticker,
            endpoint=api_endpoint,
            calls=api_calls_count,
            status=http_status_code
        )

    except Exception as e:
        # Don't fail the main operation if logging fails
        logger.error(
            "api_call_logging_failed",
            execution_id=execution_id,
            ticker=ticker,
            endpoint=api_endpoint,
            error=str(e)
        )


def get_todays_api_usage() -> Dict:
    """
    Get today's API usage summary.

    Returns:
        dict: API usage breakdown by endpoint
    """
    query = """
        SELECT
            api_endpoint,
            total_requests,
            total_api_calls,
            successful_requests,
            failed_requests,
            avg_response_ms,
            first_call,
            last_call
        FROM v_api_usage_today
        ORDER BY total_api_calls DESC
    """

    try:
        results = execute_query(query, fetch=True)

        usage_summary = {
            'total_calls': 0,
            'by_endpoint': {},
            'total_requests': 0,
            'failed_requests': 0
        }

        for row in results:
            endpoint = row['api_endpoint']
            usage_summary['by_endpoint'][endpoint] = {
                'requests': row['total_requests'],
                'api_calls': row['total_api_calls'],
                'successful': row['successful_requests'],
                'failed': row['failed_requests'],
                'avg_response_ms': row['avg_response_ms'],
                'first_call': row['first_call'],
                'last_call': row['last_call']
            }
            usage_summary['total_calls'] += row['total_api_calls']
            usage_summary['total_requests'] += row['total_requests']
            usage_summary['failed_requests'] += row['failed_requests']

        return usage_summary

    except Exception as e:
        logger.error("api_usage_retrieval_failed", error=str(e))
        return {'total_calls': 0, 'by_endpoint': {}, 'total_requests': 0, 'failed_requests': 0}


# =====================================================
# HELPER FUNCTIONS FOR AIRFLOW DAG
# =====================================================

def validate_quota_for_execution(
    execution_id: str,
    tickers_needing_bulk: int,
    tickers_needing_prices: int
) -> Dict:
    """
    Complete quota validation workflow for DAG execution.

    This is the main function called by Airflow DAG's check_api_quota task.

    Args:
        execution_id: Airflow run_id
        tickers_needing_bulk: Number of tickers requiring bulk load
        tickers_needing_prices: Number of tickers requiring price updates

    Returns:
        dict: {
            'can_proceed': bool,
            'recommendation': str,
            'quota_status': dict,
            'required_calls': dict,
            'quota_check': dict,
            'adjusted_bulk_tickers': int,
            'adjusted_price_tickers': int
        }
    """
    logger.info(
        "validating_quota_for_execution",
        execution_id=execution_id,
        bulk_tickers=tickers_needing_bulk,
        price_tickers=tickers_needing_prices
    )

    # Step 1: Get current quota status
    quota_status = get_current_quota_status()

    # Step 2: Calculate required calls
    required_calls = calculate_required_calls(tickers_needing_bulk, tickers_needing_prices)

    # Step 3: Check if quota available
    quota_check = check_quota_available(required_calls['total_calls'])

    # Step 4: Adjust batch sizes if needed
    if not quota_check['can_proceed']:
        adjusted_bulk, adjusted_price = adjust_batch_sizes(
            tickers_needing_bulk,
            tickers_needing_prices,
            quota_check['calls_after_buffer']
        )
    else:
        adjusted_bulk = tickers_needing_bulk
        adjusted_price = tickers_needing_prices

    result = {
        'can_proceed': quota_check['can_proceed'],
        'recommendation': quota_check['recommendation'],
        'quota_status': quota_status,
        'required_calls': required_calls,
        'quota_check': quota_check,
        'adjusted_bulk_tickers': adjusted_bulk,
        'adjusted_price_tickers': adjusted_price,
        'original_bulk_tickers': tickers_needing_bulk,
        'original_price_tickers': tickers_needing_prices
    }

    logger.info(
        "quota_validation_complete",
        execution_id=execution_id,
        can_proceed=result['can_proceed'],
        recommendation=result['recommendation'],
        original_bulk=tickers_needing_bulk,
        adjusted_bulk=adjusted_bulk,
        original_price=tickers_needing_prices,
        adjusted_price=adjusted_price
    )

    return result


# =====================================================
# QUOTA MONITORING
# =====================================================

def get_quota_health_report() -> Dict:
    """
    Get comprehensive quota health report for monitoring.

    Returns:
        dict: Complete quota health report
    """
    quota_status = get_current_quota_status()
    api_usage = get_todays_api_usage()

    report = {
        'quota_status': quota_status,
        'api_usage': api_usage,
        'health_indicators': {
            'quota_health': quota_status['quota_health'],
            'usage_percentage': quota_status['usage_percentage'],
            'calls_remaining': quota_status['calls_remaining'],
            'quota_exhausted': quota_status['quota_exhausted']
        },
        'recommendations': []
    }

    # Add recommendations based on health
    if quota_status['quota_health'] == 'exhausted':
        report['recommendations'].append("STOP all non-critical processing")
    elif quota_status['quota_health'] == 'critical':
        report['recommendations'].append("Process only priority tickers")
        report['recommendations'].append("Skip fundamental data collection (switch to prices-only mode)")
    elif quota_status['quota_health'] == 'warning':
        report['recommendations'].append("Monitor quota closely")
        report['recommendations'].append("Consider reducing batch sizes")

    return report


if __name__ == "__main__":
    """
    Test quota calculator functions
    """
    import json

    print("=== Quota Calculator Test ===\n")

    # Test 1: Current quota status
    print("1. Current Quota Status:")
    status = get_current_quota_status()
    print(json.dumps(status, indent=2, default=str))

    # Test 2: Calculate required calls
    print("\n2. Calculate Required Calls (5000 bulk, 15000 prices):")
    required = calculate_required_calls(5000, 15000)
    print(json.dumps(required, indent=2))

    # Test 3: Check quota availability
    print("\n3. Check Quota Availability:")
    check = check_quota_available(required['total_calls'])
    print(json.dumps(check, indent=2, default=str))

    # Test 4: Health report
    print("\n4. Quota Health Report:")
    report = get_quota_health_report()
    print(json.dumps(report, indent=2, default=str))
