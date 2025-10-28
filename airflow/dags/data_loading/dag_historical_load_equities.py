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
"""

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.providers.cncf.kubernetes.secret import Secret
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from datetime import datetime, timedelta
from kubernetes.client import models as k8s
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
    tags=['data-collection', 'historical', 'equities', 'backfill'],
    doc_md=__doc__,
)

# =============================================================================
# KUBERNETES SECRETS
# =============================================================================

# PostgreSQL connection
db_secret = Secret(
    deploy_type='env',
    deploy_target='DATABASE_URL',
    secret='postgres-secret',
    key='DATABASE_URL'
)

# EODHD API key
api_secret = Secret(
    deploy_type='env',
    deploy_target='EODHD_API_KEY',
    secret='data-api-secrets',
    key='EODHD_API_KEY'
)

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

# Task 2: Determine which month to load next
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

# Task 3: Check if historical load is complete
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
# PARALLEL PROCESSING JOBS (BY EXCHANGE)
# =============================================================================

# Common Kubernetes pod configuration
common_pod_config = {
    'namespace': 'financial-screener',
    'image': 'financial-data-collector:latest',
    'image_pull_policy': 'Never',  # Use local images distributed via tar
    'cmds': ['python', '/app/src/main_enhanced.py'],
    'secrets': [db_secret, api_secret],
    'get_logs': True,
    'is_delete_operator_pod': True,
    'in_cluster': True,
    'service_account_name': 'default',
    'container_resources': k8s.V1ResourceRequirements(
        requests={"cpu": "500m", "memory": "1Gi"},
        limits={"cpu": "2000m", "memory": "2Gi"}
    ),
}

# Historical Load Job 1: US Markets (NYSE + NASDAQ)
us_markets_historical = KubernetesPodOperator(
    task_id='load_us_markets_historical',
    name='historical-us-{{ run_id | replace("_", "-") | replace(":", "-") | replace("+", "-") | replace(".", "-") | lower }}',
    arguments=[
        '--execution-id', '{{ run_id }}',
        '--exchanges', 'NYSE,NASDAQ',
        '--mode', 'historical',
        '--start-date', '{{ ti.xcom_pull(task_ids="determine_next_month", key="start_date") }}',
        '--end-date', '{{ ti.xcom_pull(task_ids="determine_next_month", key="end_date") }}',
        '--skip-existing',
        '--batch-size', '500',
    ],
    labels={
        'app': 'data-collector',
        'job-type': 'historical',
        'market': 'us',
        'dag_id': '{{ dag.dag_id }}',
        'task_id': 'load_us_markets_historical',
    },
    dag=dag,
    **common_pod_config
)

# Historical Load Job 2: London Stock Exchange
lse_historical = KubernetesPodOperator(
    task_id='load_lse_historical',
    name='historical-lse-{{ run_id | replace("_", "-") | replace(":", "-") | replace("+", "-") | replace(".", "-") | lower }}',
    arguments=[
        '--execution-id', '{{ run_id }}',
        '--exchanges', 'LSE',
        '--mode', 'historical',
        '--start-date', '{{ ti.xcom_pull(task_ids="determine_next_month", key="start_date") }}',
        '--end-date', '{{ ti.xcom_pull(task_ids="determine_next_month", key="end_date") }}',
        '--skip-existing',
        '--batch-size', '500',
    ],
    labels={
        'app': 'data-collector',
        'job-type': 'historical',
        'market': 'uk',
        'dag_id': '{{ dag.dag_id }}',
        'task_id': 'load_lse_historical',
    },
    dag=dag,
    **common_pod_config
)

# Historical Load Job 3: German Markets (Frankfurt + Xetra)
german_markets_historical = KubernetesPodOperator(
    task_id='load_german_markets_historical',
    name='historical-de-{{ run_id | replace("_", "-") | replace(":", "-") | replace("+", "-") | replace(".", "-") | lower }}',
    arguments=[
        '--execution-id', '{{ run_id }}',
        '--exchanges', 'FRANKFURT,XETRA',
        '--mode', 'historical',
        '--start-date', '{{ ti.xcom_pull(task_ids="determine_next_month", key="start_date") }}',
        '--end-date', '{{ ti.xcom_pull(task_ids="determine_next_month", key="end_date") }}',
        '--skip-existing',
        '--batch-size', '500',
    ],
    labels={
        'app': 'data-collector',
        'job-type': 'historical',
        'market': 'germany',
        'dag_id': '{{ dag.dag_id }}',
        'task_id': 'load_german_markets_historical',
    },
    dag=dag,
    **common_pod_config
)

# Historical Load Job 4: Other European Markets
european_markets_historical = KubernetesPodOperator(
    task_id='load_european_markets_historical',
    name='historical-eu-{{ run_id | replace("_", "-") | replace(":", "-") | replace("+", "-") | replace(".", "-") | lower }}',
    arguments=[
        '--execution-id', '{{ run_id }}',
        '--exchanges', 'EURONEXT,BME,SIX',
        '--mode', 'historical',
        '--start-date', '{{ ti.xcom_pull(task_ids="determine_next_month", key="start_date") }}',
        '--end-date', '{{ ti.xcom_pull(task_ids="determine_next_month", key="end_date") }}',
        '--skip-existing',
        '--batch-size', '500',
    ],
    labels={
        'app': 'data-collector',
        'job-type': 'historical',
        'market': 'europe',
        'dag_id': '{{ dag.dag_id }}',
        'task_id': 'load_european_markets_historical',
    },
    dag=dag,
    **common_pod_config
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

# =============================================================================
# TASK DEPENDENCIES
# =============================================================================

# Initialization chain
initialize_task >> determine_month_task >> check_completion_task

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

# =============================================================================
# TASK FLOW DIAGRAM
# =============================================================================

"""
Task Flow:

initialize_historical_load
    ↓
determine_next_month (query metadata)
    ↓
check_completion (2 years loaded?)
    ↓
    ├─[YES]→ historical_load_complete → finalize
    │
    └─[NO]→ process_historical_data
              ↓
              ├─→ load_us_markets_historical (NYSE, NASDAQ)
              ├─→ load_lse_historical (LSE)
              ├─→ load_german_markets_historical (Frankfurt, Xetra)
              └─→ load_european_markets_historical (Euronext, BME, SIX)
              ↓
           finalize_historical_load

Example Run Sequence:

Day 1:  Load Oct 2024 for all tickers  → 16,816 API calls
Day 2:  Load Sep 2024 for all tickers  → 16,816 API calls
Day 3:  Load Aug 2024 for all tickers  → 16,816 API calls
...
Day 24: Load Nov 2022 for all tickers  → 16,816 API calls
Day 25: Check completion → Already have 2 years → DONE

Progress Tracking:

Query current status:
SELECT
    COUNT(*) as total_tickers,
    MIN(prices_first_date) as oldest_data,
    MAX(prices_first_date) as newest_first_date,
    AVG(CURRENT_DATE - prices_first_date) as avg_depth_days
FROM asset_processing_state
WHERE prices_last_date IS NOT NULL;

API Usage per Run:
- Tickers needing history: ~16,816
- Calls per ticker: 1 (prices only, no fundamentals)
- Total per run: ~16,816 calls
- Daily collection: ~22,000 calls
- Combined: ~39,000 calls/day (39% of quota)

Benefits of Reverse Chronological Loading:
1. Most recent data loaded first (highest value)
2. Usable dataset even if interrupted
3. Can stop at any point (1 year, 18 months, etc.)
4. Easier debugging (recent data more likely to be correct)
5. Better user experience (can analyze recent trends immediately)
"""
