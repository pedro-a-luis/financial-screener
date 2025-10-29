"""
Historical Data Loading DAG - Equities
Loads historical price data in reverse chronological order (recent to old)

Strategy:
  - Processes data in 1-month chunks
  - Starts from most recent complete month (yesterday's month - 1)
  - Works backward until 2-year target reached
  - Automatically stops when complete

Schedule: Daily at 23:00 UTC (after daily collection)
API Cost: ~16,816 calls per run (1 call per ticker)
Timeline: ~24 days to complete 2 years of history

Features:
  - Reverse chronological loading (most valuable data first)
  - Resumable at month boundaries
  - Idempotent operations
  - Automatic completion detection
  - Progress tracking in metadata
  - Configuration-driven resources and batch sizes
  - Triggers technical indicators after successful load
"""

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from datetime import datetime, timedelta
import sys
import os

# Add utils to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.historical_helpers import (
    initialize_historical_execution,
    determine_next_month_to_load,
    check_completion_status,
    finalize_historical_execution,
)

# =============================================================================
# DAG CONFIGURATION
# =============================================================================

default_args = {
    'owner': 'financial-screener',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
}

dag = DAG(
    dag_id='historical_load_equities',
    default_args=default_args,
    description='Load historical price data in monthly chunks (recent to old)',
    schedule='0 23 * * *',  # 23:00 UTC daily (after daily collection at 21:30)
    start_date=datetime(2025, 10, 27),
    catchup=False,
    max_active_runs=1,
    tags=['data-collection', 'historical', 'equities', 'backfill', 'config-driven'],
    doc_md=__doc__,
)

# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

def load_dag_configuration(**context):
    """
    Load DAG configuration from database (dag_configuration table).

    This replaces hardcoded values with database-driven configuration,
    enabling runtime tuning without code changes.
    """
    import psycopg2
    import os
    from airflow.hooks.base import BaseHook

    # Try Airflow connection first, fall back to DATABASE_URL
    try:
        conn_info = BaseHook.get_connection('postgres_financial_screener')
        conn = psycopg2.connect(conn_info.get_uri())
    except:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("No database connection available. Set DATABASE_URL or create Airflow connection 'postgres_financial_screener'")
        conn = psycopg2.connect(database_url)

    cur = conn.cursor()

    # Get exchange groups
    cur.execute("""
        SET search_path TO financial_screener;
        SELECT group_name, display_name, exchanges, priority
        FROM get_exchange_groups();
    """)
    groups = cur.fetchall()

    # Get configuration for each group
    configs = {}
    for group in groups:
        group_name = group[0]
        cur.execute("""
            SET search_path TO financial_screener;
            SELECT cpu_request, cpu_limit, memory_request, memory_limit,
                   batch_size, timeout_seconds, max_retries, retry_delay_minutes
            FROM get_dag_config(%s, %s);
        """, ('historical_load_equities', group_name))

        config_row = cur.fetchone()
        configs[group_name] = {
            'exchanges': ','.join(group[2]),  # Join array to string
            'cpu_request': config_row[0],
            'cpu_limit': config_row[1],
            'memory_request': config_row[2],
            'memory_limit': config_row[3],
            'batch_size': config_row[4],
            'timeout_seconds': config_row[5],
        }

    conn.close()

    # Push to XCom for downstream tasks
    for group_name, config in configs.items():
        context['ti'].xcom_push(key=f'config_{group_name}', value=config)

    context['ti'].xcom_push(key='exchange_groups', value=[g[0] for g in groups])

    return f"Loaded configuration for {len(configs)} exchange groups"

# =============================================================================
# TASK DEFINITIONS - INITIALIZATION
# =============================================================================

# Task 1: Initialize historical load execution record
initialize_task = PythonOperator(
    task_id='initialize_historical_load',
    python_callable=initialize_historical_execution,
    dag=dag,
    doc_md="""
    Creates execution record and determines processing mode.
    Returns execution_id for tracking.
    """
)

# Task 2: Load configuration from database
load_config_task = PythonOperator(
    task_id='load_configuration',
    python_callable=load_dag_configuration,
    dag=dag,
    doc_md="""
    Loads DAG configuration from dag_configuration table.

    Retrieves:
    - Resource limits (CPU, memory) per exchange group
    - Batch sizes per exchange group
    - Timeout values per exchange group

    Configuration stored in XCom for kubectl commands.
    """
)

# Task 3: Determine which month to load next
determine_month_task = PythonOperator(
    task_id='determine_next_month',
    python_callable=determine_next_month_to_load,
    dag=dag,
    doc_md="""
    Analyzes metadata to find the next month that needs loading.

    Logic:
    - Queries asset_processing_state for tickers needing history
    - Finds earliest prices_first_date across all tickers
    - Calculates next month to load (working backward from that date)
    - Returns: start_date, end_date, tickers_to_process

    Example:
    - Current oldest data: 2024-10-01
    - Next month to load: 2024-09-01 to 2024-09-30

    Pushes to XCom:
    - start_date: First day of target month
    - end_date: Last day of target month
    - tickers_count: Number of tickers to process
    """
)

# Task 4: Check if historical load is complete
check_completion_task = BranchPythonOperator(
    task_id='check_completion',
    python_callable=check_completion_status,
    dag=dag,
    doc_md="""
    Determines if historical load target has been reached.

    Checks:
    - Do all tickers have >= 2 years of price data?
    - Are there any gaps in the historical data?

    Returns:
    - 'historical_load_complete' -> Skip processing
    - 'process_historical_data' -> Continue with data load
    """
)

# Dummy task for completion path
complete_task = EmptyOperator(
    task_id='historical_load_complete',
    dag=dag,
)

# Empty task for processing path (gateway to parallel jobs)
process_task = EmptyOperator(
    task_id='process_historical_data',
    dag=dag,
)

# =============================================================================
# PARALLEL PROCESSING JOBS (BY EXCHANGE) - BASHOPERATOR VERSION
# =============================================================================

def create_kubectl_historical_command(pod_name_prefix, group_name, market_label):
    """
    Creates kubectl command for historical data loading using BashOperator.

    This approach works reliably on ARM64 unlike KubernetesPodOperator.
    Configuration values are loaded from database via XCom.

    Args:
        pod_name_prefix: Prefix for pod name
        group_name: Exchange group name (for config lookup)
        market_label: Market label for pod labels
    """
    return f"""
# Create pod name from Airflow run_id (sanitized for Kubernetes)
POD_NAME="{pod_name_prefix}-$(echo "{{{{ run_id }}}}" | tr '[:upper:]_:+.' '[:lower:]----')"

echo "========================================="
echo "Historical Load Pod: $POD_NAME"
echo "Exchange Group: {group_name}"
echo "========================================="

# Get secrets from Kubernetes
DB_URL=$(kubectl get secret postgres-secret -n financial-screener -o jsonpath='{{.data.DATABASE_URL}}' | base64 -d)
API_KEY=$(kubectl get secret data-api-secrets -n financial-screener -o jsonpath='{{.data.EODHD_API_KEY}}' | base64 -d)

# Get configuration from XCom (loaded from database)
EXCHANGES="{{{{ ti.xcom_pull(task_ids='load_configuration', key='config_{group_name}')['exchanges'] }}}}"
CPU_REQUEST="{{{{ ti.xcom_pull(task_ids='load_configuration', key='config_{group_name}')['cpu_request'] }}}}"
CPU_LIMIT="{{{{ ti.xcom_pull(task_ids='load_configuration', key='config_{group_name}')['cpu_limit'] }}}}"
MEMORY_REQUEST="{{{{ ti.xcom_pull(task_ids='load_configuration', key='config_{group_name}')['memory_request'] }}}}"
MEMORY_LIMIT="{{{{ ti.xcom_pull(task_ids='load_configuration', key='config_{group_name}')['memory_limit'] }}}}"
BATCH_SIZE="{{{{ ti.xcom_pull(task_ids='load_configuration', key='config_{group_name}')['batch_size'] }}}}"
TIMEOUT="{{{{ ti.xcom_pull(task_ids='load_configuration', key='config_{group_name}')['timeout_seconds'] }}}}"

# Get date range from determine_next_month task
START_DATE="{{{{ ti.xcom_pull(task_ids='determine_next_month', key='start_date') }}}}"
END_DATE="{{{{ ti.xcom_pull(task_ids='determine_next_month', key='end_date') }}}}"

echo "Configuration loaded from database:"
echo "  Exchanges: $EXCHANGES"
echo "  CPU: $CPU_REQUEST - $CPU_LIMIT"
echo "  Memory: $MEMORY_REQUEST - $MEMORY_LIMIT"
echo "  Batch Size: $BATCH_SIZE"
echo "  Timeout: $TIMEOUT seconds"
echo "  Date Range: $START_DATE to $END_DATE"
echo "========================================="

# Create pod using kubectl run
kubectl run $POD_NAME \\
  --namespace=financial-screener \\
  --image=financial-data-collector:latest \\
  --image-pull-policy=Never \\
  --restart=Never \\
  --labels="app=data-collector,job-type=historical,market={market_label},dag_id={{{{ dag.dag_id }}}},task_id={{{{ task.task_id }}}},run_id={{{{ run_id }}}}" \\
  --env="DATABASE_URL=$DB_URL" \\
  --env="EODHD_API_KEY=$API_KEY" \\
  --requests="cpu=$CPU_REQUEST,memory=$MEMORY_REQUEST" \\
  --limits="cpu=$CPU_LIMIT,memory=$MEMORY_LIMIT" \\
  -- python /app/src/main_enhanced.py \\
     --execution-id "{{{{ run_id }}}}" \\
     --exchanges "$EXCHANGES" \\
     --mode historical \\
     --start-date "$START_DATE" \\
     --end-date "$END_DATE" \\
     --skip-existing \\
     --batch-size $BATCH_SIZE

echo "Pod created. Waiting for completion (timeout: ${{TIMEOUT}}s)..."

# Wait for pod to complete
if kubectl wait --for=condition=complete pod/$POD_NAME -n financial-screener --timeout=${{TIMEOUT}}s; then
    echo "========================================="
    echo "✓ Pod completed successfully"
    echo "========================================="

    # Get and display logs
    echo ""
    echo "Pod Logs:"
    kubectl logs $POD_NAME -n financial-screener

    # Clean up pod
    kubectl delete pod $POD_NAME -n financial-screener
    echo ""
    echo "✓ Pod cleaned up"
    exit 0
else
    echo "========================================="
    echo "✗ Pod failed or timed out"
    echo "========================================="

    # Get pod status for debugging
    kubectl get pod $POD_NAME -n financial-screener -o yaml

    # Get logs even if failed
    echo ""
    echo "Pod Logs:"
    kubectl logs $POD_NAME -n financial-screener --tail=100

    # Keep failed pod for debugging (don't delete)
    echo ""
    echo "⚠ Failed pod kept for debugging: $POD_NAME"
    exit 1
fi
"""

# Historical Load Job 1: US Markets (NYSE + NASDAQ)
us_markets_historical = BashOperator(
    task_id='load_us_markets_historical',
    bash_command=create_kubectl_historical_command(
        pod_name_prefix='historical-us',
        group_name='us_markets',
        market_label='us'
    ),
    dag=dag,
    doc_md="""
    Loads historical price data for US Markets (NYSE + NASDAQ).

    Uses kubectl-based pod launcher (ARM64 compatible).
    Configuration loaded from dag_configuration table.

    Expected duration: Varies based on month size and ticker count.
    """
)

# Historical Load Job 2: London Stock Exchange
lse_historical = BashOperator(
    task_id='load_lse_historical',
    bash_command=create_kubectl_historical_command(
        pod_name_prefix='historical-lse',
        group_name='lse',
        market_label='uk'
    ),
    dag=dag,
    doc_md="""
    Loads historical price data for London Stock Exchange.

    Configuration loaded from dag_configuration table.
    """
)

# Historical Load Job 3: German Markets (Frankfurt + Xetra)
german_markets_historical = BashOperator(
    task_id='load_german_markets_historical',
    bash_command=create_kubectl_historical_command(
        pod_name_prefix='historical-de',
        group_name='german_markets',
        market_label='germany'
    ),
    dag=dag,
    doc_md="""
    Loads historical price data for German Markets (Frankfurt + XETRA).

    Configuration loaded from dag_configuration table.
    """
)

# Historical Load Job 4: Other European Markets
european_markets_historical = BashOperator(
    task_id='load_european_markets_historical',
    bash_command=create_kubectl_historical_command(
        pod_name_prefix='historical-eu',
        group_name='european_markets',
        market_label='europe'
    ),
    dag=dag,
    doc_md="""
    Loads historical price data for Other European Markets (Euronext, BME, SIX).

    Configuration loaded from dag_configuration table.
    """
)

# =============================================================================
# FINALIZATION TASKS
# =============================================================================

# Task: Finalize historical load execution
finalize_task = PythonOperator(
    task_id='finalize_historical_load',
    python_callable=finalize_historical_execution,
    dag=dag,
    doc_md="""
    Updates metadata with results of historical load.

    Actions:
    - Updates prices_first_date for processed tickers
    - Records API calls used
    - Updates processing status
    - Logs completion metrics

    Calculates progress:
    - Total months loaded
    - Percentage toward 2-year goal
    - Estimated days remaining
    """
)

# Task: Trigger technical indicators calculation
trigger_indicators_task = TriggerDagRunOperator(
    task_id='trigger_indicators',
    trigger_dag_id='calculate_indicators',
    wait_for_completion=False,
    dag=dag,
    doc_md="""
    Triggers technical indicators calculation after successful historical load.

    This ensures that newly loaded historical data gets technical indicators
    calculated automatically, completing the full data pipeline.

    Runs asynchronously (doesn't wait for completion).
    """
)

# =============================================================================
# TASK DEPENDENCIES
# =============================================================================

# Initialization chain
initialize_task >> load_config_task >> determine_month_task >> check_completion_task

# Branch: Either complete or continue processing
check_completion_task >> [complete_task, process_task]

# If processing needed, run parallel jobs
process_task >> [
    us_markets_historical,
    lse_historical,
    german_markets_historical,
    european_markets_historical
]

# All parallel jobs must complete before finalization
[
    us_markets_historical,
    lse_historical,
    german_markets_historical,
    european_markets_historical
] >> finalize_task

# Complete path also goes to finalize (for cleanup)
complete_task >> finalize_task

# After finalization, trigger indicators calculation
finalize_task >> trigger_indicators_task

# =============================================================================
# TASK FLOW DIAGRAM
# =============================================================================

"""
Task Flow:

initialize_historical_load
    ↓
load_configuration (from database)
    ↓
determine_next_month (query metadata)
    ↓
check_completion (2 years loaded?)
    ↓
    ├─[YES]→ historical_load_complete → finalize → trigger_indicators
    │
    └─[NO]→ process_historical_data
              ↓
              ├─→ load_us_markets_historical (NYSE, NASDAQ)
              ├─→ load_lse_historical (LSE)
              ├─→ load_german_markets_historical (Frankfurt, Xetra)
              └─→ load_european_markets_historical (Euronext, BME, SIX)
              ↓
           finalize_historical_load
              ↓
           trigger_indicators

Key Changes from Previous Version:

1. Migrated from KubernetesPodOperator to BashOperator + kubectl
   - ARM64 compatible
   - Matches data_collection_equities.py pattern
   - More reliable on Raspberry Pi cluster

2. Configuration-Driven Approach
   - Reads resource limits from dag_configuration table
   - Reads exchange groups from exchange_groups table
   - Reads batch sizes from configuration
   - No hardcoded values

3. Indicators Integration
   - Automatically triggers calculate_indicators DAG after completion
   - Ensures full data pipeline (historical load → indicators)
   - Async trigger (doesn't block finalization)

Configuration Management:

To update resources for US markets historical load:
  SELECT update_dag_config(
      'historical_load_equities',
      'us_markets',
      p_cpu_limit => '3000m',
      p_memory_limit => '4Gi',
      p_batch_size => 750
  );

To add new exchange group:
  INSERT INTO exchange_groups (group_name, display_name, exchanges, priority)
  VALUES ('asian_markets', 'Asian Markets', ARRAY['TSE', 'HKEX'], 6);

Benefits:
- No code changes needed for resource tuning
- Easy to add/modify exchange groups
- Full audit trail of configuration changes
- Consistent approach across all DAGs
- Complete pipeline integration
"""
