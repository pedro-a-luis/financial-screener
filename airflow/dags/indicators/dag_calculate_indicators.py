"""
Indicator Calculation DAG
Calculates technical indicators for assets with updated prices

Schedule: Triggered by data_collection_equities DAG after completion
Features:
  - Processes assets with stale indicators
  - Runs main_indicators.py with metadata tracking
  - Idempotent (safe to re-run)
  - Uses BashOperator + kubectl (ARM64 compatible)
"""

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
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
    schedule=None,  # Triggered by data_collection_equities DAG
    start_date=datetime(2025, 10, 21),
    catchup=False,
    max_active_runs=1,
    tags=['indicators', 'technical-analysis', 'triggered'],
    doc_md=__doc__,
)

# =============================================================================
# BASH COMMAND FOR KUBECTL POD EXECUTION
# =============================================================================

kubectl_indicators_command = """
#!/bin/bash
set -e

echo "========================================="
echo "Technical Indicators Calculation"
echo "========================================="
echo "Execution ID: {{ run_id }}"
echo "Started: $(date)"
echo ""

# Create pod with unique name
POD_NAME="indicators-{{ ts_nodash | lower }}"

echo "Creating pod: $POD_NAME"
kubectl run $POD_NAME \
  --image=technical-analyzer:latest \
  --image-pull-policy=Never \
  --restart=Never \
  --namespace=financial-screener \
  --labels="app=technical-analyzer,dag_id={{ dag.dag_id }},task_id=calculate_indicators" \
  --overrides='{
    "spec": {
      "containers": [{
        "name": "technical-analyzer",
        "image": "technical-analyzer:latest",
        "imagePullPolicy": "Never",
        "command": ["python", "/app/src/main_indicators.py"],
        "args": [
          "--execution-id", "{{ run_id }}",
          "--skip-existing",
          "--batch-size", "1000"
        ],
        "env": [{
          "name": "DATABASE_URL",
          "valueFrom": {
            "secretKeyRef": {
              "name": "postgres-secret",
              "key": "DATABASE_URL"
            }
          }
        }, {
          "name": "DATABASE_SCHEMA",
          "value": "financial_screener"
        }, {
          "name": "LOG_LEVEL",
          "value": "INFO"
        }],
        "resources": {
          "requests": {
            "cpu": "1000m",
            "memory": "2Gi"
          },
          "limits": {
            "cpu": "4000m",
            "memory": "4Gi"
          }
        }
      }],
      "restartPolicy": "Never"
    }
  }'

echo "✓ Pod created"
echo ""

# Wait for pod to complete (max 60 minutes)
echo "Waiting for pod to complete (timeout: 60 minutes)..."
if kubectl wait --for=condition=Ready pod/$POD_NAME -n financial-screener --timeout=5m; then
    # Pod started, now wait for completion
    kubectl wait --for=jsonpath='{.status.phase}'=Succeeded pod/$POD_NAME -n financial-screener --timeout=55m
    POD_STATUS=$?
else
    echo "⚠ Pod failed to start within 5 minutes"
    POD_STATUS=1
fi

# Check result
if [ $POD_STATUS -eq 0 ]; then
    echo ""
    echo "========================================="
    echo "✓ Indicators calculated successfully"
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

# Task 2: Calculate indicators using kubectl
calculate_indicators_task = BashOperator(
    task_id='calculate_indicators',
    bash_command=kubectl_indicators_command,
    dag=dag,
    doc_md="""
    Runs main_indicators.py to calculate technical indicators using kubectl.

    The script:
    1. Queries asset_processing_state for assets needing indicators
    2. Fetches price data from stock_prices table
    3. Calculates 30+ technical indicators (RSI, MACD, etc.)
    4. Stores in technical_indicators table
    5. Updates asset_processing_state metadata

    No API calls required - all data from database.
    Uses BashOperator + kubectl for ARM64 compatibility.
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
