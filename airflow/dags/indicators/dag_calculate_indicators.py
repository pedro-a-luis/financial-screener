"""
Indicator Calculation DAG
Calculates technical indicators for assets with updated prices

Schedule: Triggered by data_collection_equities DAG after completion
Features:
  - Processes assets with stale indicators
  - Runs main_indicators.py with metadata tracking
  - Idempotent (safe to re-run)
"""

from airflow import DAG
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.providers.cncf.kubernetes.secret import Secret
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from kubernetes.client import models as k8s
import sys
import os

# Add utils to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.metadata_helpers import (
    initialize_execution_record,
    finalize_execution_record,
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
}

dag = DAG(
    dag_id='calculate_indicators',
    default_args=default_args,
    description='Calculate technical indicators for assets with updated prices',
    schedule=None,  # Triggered by data_collection_equities DAG - Airflow 3.0 uses 'schedule' not 'schedule_interval'
    start_date=datetime(2025, 10, 21),
    catchup=False,
    max_active_runs=1,
    tags=['indicators', 'technical-analysis', 'triggered'],
    doc_md=__doc__,
)

# =============================================================================
# KUBERNETES SECRETS
# =============================================================================

db_secret = Secret(
    deploy_type='env',
    deploy_target='DATABASE_URL',
    secret='postgres-secret',
    key='DATABASE_URL'
)

# =============================================================================
# TASK DEFINITIONS
# =============================================================================

# Task 1: Initialize execution record
initialize_task = PythonOperator(
    task_id='initialize_execution',
    python_callable=initialize_execution_record,
    dag=dag,
    doc_md="""
    Creates a record in process_executions table for this indicator calculation run.
    """
)

# Task 2: Calculate indicators
# This runs main_indicators.py which queries asset_processing_state
# to find assets needing indicator calculation
calculate_indicators_task = KubernetesPodOperator(
    task_id='calculate_indicators',
    name='indicator-calculator-{{ ts_nodash | lower }}',
    namespace='financial-screener',
    image='registry.stratdata.org/technical-analyzer:latest',
    image_pull_policy='Always',
    cmds=['python', '/app/src/main_indicators.py'],
    arguments=[
        '--execution-id', '{{ run_id }}',
        '--skip-existing',
        '--batch-size', '1000',  # Indicators are CPU-bound, can batch larger
    ],
    secrets=[db_secret],
    get_logs=True,
    is_delete_operator_pod=True,
    in_cluster=True,
    service_account_name='default',
    labels={
        'app': 'technical-analyzer',
        'dag_id': '{{ dag.dag_id }}',
        'task_id': 'calculate_indicators',
    },
    container_resources=k8s.V1ResourceRequirements(
        requests={"cpu": "1000m", "memory": "2Gi"},
        limits={"cpu": "4000m", "memory": "4Gi"}
    ),
    dag=dag,
    doc_md="""
    Runs main_indicators.py to calculate technical indicators.

    The script:
    1. Queries asset_processing_state for assets needing indicators
    2. Fetches price data from stock_prices table
    3. Calculates 30+ technical indicators (RSI, MACD, etc.)
    4. Stores in technical_indicators table
    5. Updates asset_processing_state metadata

    No API calls required - all data from database.
    """
)

# Task 3: Finalize execution
finalize_task = PythonOperator(
    task_id='finalize_execution',
    python_callable=finalize_execution_record,
    dag=dag,
    doc_md="""
    Updates process_executions with final statistics.
    """
)

# =============================================================================
# TASK DEPENDENCIES
# =============================================================================

initialize_task >> calculate_indicators_task >> finalize_task

# =============================================================================
# TASK FLOW
# =============================================================================

"""
Task Flow:

initialize_execution
    ↓
calculate_indicators (K8s Job)
    ↓
finalize_execution

Expected Duration:
- First run (5,045 assets): ~30-60 minutes
- Steady state (daily updates): ~15-30 minutes

Resource Usage:
- API calls: 0 (reads from database)
- CPU: High (pandas calculations)
- Memory: 2-4 GB (price data in memory)
"""
