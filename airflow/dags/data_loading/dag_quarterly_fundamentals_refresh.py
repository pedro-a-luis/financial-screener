"""
Quarterly Fundamentals Refresh DAG

Refreshes comprehensive fundamental data for ALL tickers quarterly.
Fundamental data (company info, financials, earnings) changes less frequently
than price data, so quarterly updates are sufficient.

Schedule: First day of each quarter at 02:00 UTC (Jan 1, Apr 1, Jul 1, Oct 1)
Features:
  - Comprehensive EODHD fundamental data (13 sections, 100+ fields)
  - Parallel processing by exchange groups
  - Full asset metadata update including:
    * General: Company info, officers, sector
    * Financials: 20+ years Balance Sheet, Income, Cash Flow
    * Earnings: Historical + estimates
    * Holders: Institutional/insider ownership
    * SplitsDividends: Complete history
    * AnalystRatings: Consensus ratings
  - API quota management (5,045 API calls for all tickers)
  - Complete execution tracking
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
    'retry_delay': timedelta(minutes=10),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(hours=1),
}

dag = DAG(
    dag_id='quarterly_fundamentals_refresh',
    default_args=default_args,
    description='Quarterly refresh of comprehensive fundamental data for all tickers',
    schedule='0 2 1 1,4,7,10 *',  # 02:00 UTC on Jan 1, Apr 1, Jul 1, Oct 1
    start_date=datetime(2025, 10, 1),
    catchup=False,
    max_active_runs=1,
    tags=['data-collection', 'fundamentals', 'quarterly', 'production'],
    doc_md=__doc__,
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
    Creates execution record in process_executions table.
    Returns execution_id for tracking.
    """
)

# Task 2: Get all active tickers
get_tickers_task = BashOperator(
    task_id='get_active_tickers',
    bash_command="""
    kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -t -c "
        SET search_path TO financial_screener;
        SELECT ticker FROM assets WHERE is_active = true ORDER BY ticker;
    " | grep -v '^$' | wc -l
    """,
    dag=dag,
    doc_md="""
    Query database for count of active tickers.
    This determines the scope of the quarterly refresh.
    """
)

# Task 3: Process US exchanges (largest group)
process_us_task = BashOperator(
    task_id='process_us_exchanges',
    bash_command="""
    # Get execution_id from XCom
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"

    # Create Kubernetes Job for US exchanges
    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: quarterly-fundamentals-us-{{ ts_nodash | lower }}
  namespace: financial-screener
spec:
  backoffLimit: 2
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: data-collector
        image: financial-data-collector:latest
        imagePullPolicy: Never
        command:
          - python3
          - /app/src/main_enhanced.py
          - --mode
          - bulk
          - --exchange-group
          - US
          - --execution-id
          - ${EXECUTION_ID}
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: DATABASE_URL
        - name: EODHD_API_KEY
          valueFrom:
            secretKeyRef:
              name: data-api-secrets
              key: EODHD_API_KEY
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            memory: "2Gi"
            cpu: "500m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
EOF

    # Wait for job completion
    echo "Waiting for US exchanges job to complete..."
    kubectl wait --for=condition=complete --timeout=3600s job/quarterly-fundamentals-us-{{ ts_nodash | lower }} -n financial-screener

    # Get logs
    POD_NAME=$(kubectl get pods -n financial-screener -l job-name=quarterly-fundamentals-us-{{ ts_nodash | lower }} -o jsonpath='{.items[0].metadata.name}')
    kubectl logs -n financial-screener $POD_NAME --tail=50
    """,
    dag=dag,
    execution_timeout=timedelta(hours=2),
    doc_md="""
    Process all US exchange tickers (NASDAQ, NYSE, etc.).
    This is the largest group (~3,500 tickers).
    Uses main_enhanced.py in bulk mode (fetches comprehensive fundamentals).
    """
)

# Task 4: Process international exchanges
process_international_task = BashOperator(
    task_id='process_international_exchanges',
    bash_command="""
    # Get execution_id from XCom
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"

    # Create Kubernetes Job for international exchanges
    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: quarterly-fundamentals-intl-{{ ts_nodash | lower }}
  namespace: financial-screener
spec:
  backoffLimit: 2
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: data-collector
        image: financial-data-collector:latest
        imagePullPolicy: Never
        command:
          - python3
          - /app/src/main_enhanced.py
          - --mode
          - bulk
          - --exchange-group
          - INTERNATIONAL
          - --execution-id
          - ${EXECUTION_ID}
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: DATABASE_URL
        - name: EODHD_API_KEY
          valueFrom:
            secretKeyRef:
              name: data-api-secrets
              key: EODHD_API_KEY
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            memory: "2Gi"
            cpu: "500m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
EOF

    # Wait for job completion
    echo "Waiting for international exchanges job to complete..."
    kubectl wait --for=condition=complete --timeout=3600s job/quarterly-fundamentals-intl-{{ ts_nodash | lower }} -n financial-screener

    # Get logs
    POD_NAME=$(kubectl get pods -n financial-screener -l job-name=quarterly-fundamentals-intl-{{ ts_nodash | lower }} -o jsonpath='{.items[0].metadata.name}')
    kubectl logs -n financial-screener $POD_NAME --tail=50
    """,
    dag=dag,
    execution_timeout=timedelta(hours=2),
    doc_md="""
    Process all international exchange tickers (~1,500 tickers).
    Includes European, Asian, and other non-US markets.
    """
)

# Task 5: Finalize execution record
finalize_task = PythonOperator(
    task_id='finalize_execution',
    python_callable=finalize_execution_record,
    dag=dag,
    doc_md="""
    Updates process_executions record with completion status.
    Logs total API calls used and final statistics.
    """
)

# Task 6: Generate summary report
summary_task = BashOperator(
    task_id='generate_summary',
    bash_command="""
    echo "================================================"
    echo "Quarterly Fundamentals Refresh Summary"
    echo "================================================"
    echo "Execution Date: {{ ds }}"
    echo ""

    # Query database for statistics
    kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c "
        SET search_path TO financial_screener;

        SELECT
            COUNT(*) as total_assets,
            COUNT(DISTINCT ticker) as unique_tickers,
            COUNT(CASE WHEN eodhd_last_update IS NOT NULL THEN 1 END) as with_fundamentals,
            COUNT(CASE WHEN eodhd_last_update > NOW() - INTERVAL '7 days' THEN 1 END) as updated_this_week,
            COUNT(CASE WHEN eodhd_financials IS NOT NULL THEN 1 END) as with_financials,
            COUNT(CASE WHEN eodhd_earnings IS NOT NULL THEN 1 END) as with_earnings,
            COUNT(CASE WHEN eodhd_holders IS NOT NULL THEN 1 END) as with_holders
        FROM assets
        WHERE is_active = true;
    "

    echo ""
    echo "Comprehensive fundamental data updated successfully!"
    echo "================================================"
    """,
    dag=dag,
    doc_md="""
    Query database for updated statistics and generate summary report.
    Shows counts of assets with various fundamental data fields populated.
    """
)

# =============================================================================
# TASK DEPENDENCIES
# =============================================================================

initialize_task >> get_tickers_task >> [process_us_task, process_international_task] >> finalize_task >> summary_task
