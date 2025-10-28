"""
Data Collection DAG - Equities (BashOperator Version)
Orchestrates daily data collection with metadata-driven delta discovery

Schedule: Daily at 21:30 UTC (after US market close)
Features:
  - Delta discovery from metadata tables
  - Parallel processing by exchange
  - API quota management
  - Automatic retry logic
  - Complete execution tracking
  - Uses BashOperator with kubectl (ARM64 compatible)
"""

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from datetime import datetime, timedelta
import sys
import os

# Add utils to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.metadata_helpers import (
    initialize_execution_record,
    discover_processing_delta,
    check_and_adjust_quota,
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
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
}

dag = DAG(
    dag_id='data_collection_equities',
    default_args=default_args,
    description='Daily equities data collection with parallel processing (kubectl-based)',
    schedule='30 21 * * *',  # 21:30 UTC (after US market close)
    start_date=datetime(2025, 10, 21),
    catchup=False,
    max_active_runs=1,
    tags=['data-collection', 'equities', 'daily', 'production', 'bashoperator'],
    doc_md=__doc__,
)

# =============================================================================
# TASK DEFINITIONS
# =============================================================================

# Task 1: Initialize execution record in metadata
initialize_task = PythonOperator(
    task_id='initialize_execution',
    python_callable=initialize_execution_record,
    dag=dag,
    doc_md="""
    Creates a record in process_executions table to track this DAG run.
    Returns execution_id (Airflow run_id) for downstream tasks.
    """
)

# Task 2: Discover what needs processing
discover_task = PythonOperator(
    task_id='discover_delta',
    python_callable=discover_processing_delta,
    dag=dag,
    doc_md="""
    Queries v_assets_needing_processing view to determine:
    - New tickers requiring bulk load (fundamentals + 2 years prices)
    - Existing tickers requiring price updates (yesterday's price)
    - Tickers requiring indicator recalculation

    Results stored in XCom for downstream tasks.
    """
)

# Task 3: Check API quota and adjust batch sizes
quota_check_task = PythonOperator(
    task_id='check_api_quota',
    python_callable=check_and_adjust_quota,
    dag=dag,
    doc_md="""
    Calculates required API calls based on delta discovery.
    Adjusts batch sizes if needed to stay within daily quota (100K calls).

    API costs:
    - New ticker (bulk load): 11 calls (10 fundamentals + 1 prices)
    - Existing ticker (price update): 1 call
    """
)

# =============================================================================
# PARALLEL PROCESSING JOBS (BY EXCHANGE) - BASHOPERATOR VERSION
# =============================================================================

# Helper function to create kubectl pod command
def create_kubectl_command(pod_name, exchanges, market_label):
    """
    Creates a kubectl command to run data collector pod and wait for completion.

    This approach works reliably on ARM64 unlike KubernetesPodOperator.
    """
    return f"""
# Create pod name from Airflow run_id (sanitized for Kubernetes)
POD_NAME="{pod_name}-$(echo "{{{{ run_id }}}}" | tr '[:upper:]_:+.' '[:lower:]----')"

echo "========================================="
echo "Starting Data Collection Pod: $POD_NAME"
echo "Exchanges: {exchanges}"
echo "========================================="

# Get secrets from Kubernetes
DB_URL=$(kubectl get secret postgres-secret -n financial-screener -o jsonpath='{{.data.DATABASE_URL}}' | base64 -d)
API_KEY=$(kubectl get secret data-api-secrets -n financial-screener -o jsonpath='{{.data.EODHD_API_KEY}}' | base64 -d)

# Create pod using kubectl run
kubectl run $POD_NAME \
  --namespace=financial-screener \
  --image=financial-data-collector:latest \
  --image-pull-policy=Never \
  --restart=Never \
  --labels="app=data-collector,market={market_label},dag_id={{{{ dag.dag_id }}}},task_id={{{{ task.task_id }}}},run_id={{{{ run_id }}}}" \
  --env="DATABASE_URL=$DB_URL" \
  --env="EODHD_API_KEY=$API_KEY" \
  --requests="cpu=500m,memory=1Gi" \
  --limits="cpu=2000m,memory=2Gi" \
  -- python /app/src/main_enhanced.py \
     --execution-id "{{{{ run_id }}}}" \
     --exchanges "{exchanges}" \
     --mode auto \
     --skip-existing \
     --batch-size 500

echo "Pod created. Waiting for completion (timeout: 600s)..."

# Wait for pod to complete
if kubectl wait --for=condition=complete pod/$POD_NAME -n financial-screener --timeout=600s; then
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

# Job 1: US Markets (NYSE + NASDAQ)
us_markets_job = BashOperator(
    task_id='process_us_markets',
    bash_command=create_kubectl_command(
        pod_name='data-collector-us',
        exchanges='NYSE,NASDAQ',
        market_label='us'
    ),
    dag=dag,
    doc_md="""
    Processes US stock markets (NYSE + NASDAQ) using kubectl-based pod launcher.

    This approach works reliably on ARM64 Raspberry Pi cluster, unlike KubernetesPodOperator
    which has compatibility issues with Airflow 3.x on ARM64.

    Expected duration: 15-30 minutes depending on number of updates needed.
    """
)

# Job 2: London Stock Exchange
lse_job = BashOperator(
    task_id='process_lse',
    bash_command=create_kubectl_command(
        pod_name='data-collector-lse',
        exchanges='LSE',
        market_label='uk'
    ),
    dag=dag,
    doc_md="""
    Processes London Stock Exchange.

    Expected duration: 10-20 minutes.
    """
)

# Job 3: German Markets (Frankfurt + Xetra)
german_markets_job = BashOperator(
    task_id='process_german_markets',
    bash_command=create_kubectl_command(
        pod_name='data-collector-de',
        exchanges='FRANKFURT,XETRA',
        market_label='germany'
    ),
    dag=dag,
    doc_md="""
    Processes German stock markets (Frankfurt + Xetra).

    Expected duration: 10-15 minutes.
    """
)

# Job 4: Other European Markets (Euronext, BME, SIX)
european_markets_job = BashOperator(
    task_id='process_european_markets',
    bash_command=create_kubectl_command(
        pod_name='data-collector-eu',
        exchanges='EURONEXT,BME,SIX',
        market_label='europe'
    ),
    dag=dag,
    doc_md="""
    Processes other European markets (Euronext, BME, SIX).

    Expected duration: 10-20 minutes.
    """
)

# =============================================================================
# FINALIZATION TASKS
# =============================================================================

# Task: Finalize execution record
finalize_task = PythonOperator(
    task_id='finalize_execution',
    python_callable=finalize_execution_record,
    dag=dag,
    doc_md="""
    Aggregates results from asset_processing_details table.
    Updates process_executions record with:
    - Total assets processed
    - Success/failure counts
    - Total API calls used
    - Final status (success/partial/failed)
    """
)

# Task: Trigger indicator calculation DAG
trigger_indicators_task = TriggerDagRunOperator(
    task_id='trigger_indicators',
    trigger_dag_id='calculate_indicators',
    wait_for_completion=False,
    dag=dag,
    doc_md="""
    Triggers the indicator calculation DAG to process assets with updated prices.
    Runs asynchronously (does not wait for completion).
    """
)

# =============================================================================
# TASK DEPENDENCIES
# =============================================================================

# Linear dependency chain for initialization
initialize_task >> discover_task >> quota_check_task

# Parallel processing jobs (run simultaneously)
quota_check_task >> [
    us_markets_job,
    lse_job,
    german_markets_job,
    european_markets_job
]

# All jobs must complete before finalization
[
    us_markets_job,
    lse_job,
    german_markets_job,
    european_markets_job
] >> finalize_task

# Trigger indicators after finalization
finalize_task >> trigger_indicators_task

# =============================================================================
# TASK FLOW DIAGRAM
# =============================================================================

"""
Task Flow:

initialize_execution
    ↓
discover_delta (queries metadata)
    ↓
check_api_quota (adjusts batch sizes)
    ↓
    ├─→ process_us_markets (NYSE, NASDAQ) [BashOperator + kubectl]
    ├─→ process_lse (LSE) [BashOperator + kubectl]
    ├─→ process_german_markets (Frankfurt, Xetra) [BashOperator + kubectl]
    └─→ process_european_markets (Euronext, BME, SIX) [BashOperator + kubectl]
    ↓
finalize_execution (update metadata)
    ↓
trigger_indicators (start next DAG)

Expected Duration:
- Day 1 (catch-up): 4-6 hours (parallel processing)
- Steady state: 2-3 hours (price updates only)

API Usage:
- Day 1: ~93,000 calls (5,045 updates + 8,000 new assets)
- Steady state: ~22,000 calls (21,817 price updates)

Implementation Notes:
- Migrated from KubernetesPodOperator to BashOperator + kubectl
- Reason: KubernetesPodOperator has ARM64 compatibility issues in Airflow 3.x
- Benefits:
  * Reliable task completion detection
  * Direct control over pod lifecycle
  * Better error reporting
  * Works perfectly on ARM64 architecture
"""
