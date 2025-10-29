"""
Unified Prices DAG - EODHD API

Fetches OHLCV price data for all tickers using Airflow's data_interval_start/end.
Handles both historical (via backfill) and incremental (via schedule) loads.

Schedule: Daily at 22:00 UTC (after US market close)
Backfill: airflow dags backfill dag_prices --start-date 2023-10-29 --end-date 2025-10-29

How it works:
- Uses data_interval_start/end from Airflow context for date range
- Backfill: Runs once per day in range (e.g., 2 years = 730 runs)
- Scheduled: Runs daily for yesterday's data
- Mode: Auto-detects bulk vs incremental based on date range
"""

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.metadata_helpers import (
    initialize_execution_record,
    finalize_execution_record,
)

default_args = {
    'owner': 'financial-screener',
    'depends_on_past': False,
    'email_on_failure': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    dag_id='dag_prices',
    default_args=default_args,
    description='Unified prices DAG - handles historical (backfill) and incremental (daily)',
    schedule='0 22 * * *',  # Daily at 22:00 UTC
    start_date=datetime(2023, 10, 29),
    catchup=False,
    max_active_runs=1,
    tags=['unified', 'prices', 'eodhd', 'daily', 'backfill-ready'],
    doc_md=__doc__,
)

initialize_task = PythonOperator(
    task_id='initialize_execution',
    python_callable=initialize_execution_record,
    dag=dag,
)

# Main task - fetches prices for date range from context
fetch_prices_task = BashOperator(
    task_id='fetch_prices',
    bash_command="""
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"
    START_DATE="{{ data_interval_start.strftime('%Y-%m-%d') }}"
    END_DATE="{{ data_interval_end.strftime('%Y-%m-%d') }}"

    echo "Fetching prices for date range: $START_DATE to $END_DATE"

    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: prices-{{ ts_nodash | lower }}
  namespace: financial-screener
spec:
  backoffLimit: 2
  ttlSecondsAfterFinished: 3600
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
          - incremental
          - --exchanges
          - NYSE,NASDAQ,LSE,BME,EURONEXT,FRANKFURT,SIX
          - --start-date
          - ${START_DATE}
          - --end-date
          - ${END_DATE}
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
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
EOF

    kubectl wait --for=condition=complete --timeout=3600s job/prices-{{ ts_nodash | lower }} -n financial-screener || true

    POD_NAME=$(kubectl get pods -n financial-screener -l job-name=prices-{{ ts_nodash | lower }} -o jsonpath='{.items[0].metadata.name}')
    echo "=== Last 20 log lines ==="
    kubectl logs -n financial-screener $POD_NAME --tail=20 2>&1 || echo "Could not retrieve logs"
    """,
    dag=dag,
    execution_timeout=timedelta(hours=1),
)

finalize_task = PythonOperator(
    task_id='finalize_execution',
    python_callable=finalize_execution_record,
    dag=dag,
)

initialize_task >> fetch_prices_task >> finalize_task
