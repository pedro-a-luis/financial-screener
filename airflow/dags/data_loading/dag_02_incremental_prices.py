"""
02 - Incremental Prices Update (EODHD API) - DAILY

Fetches delta price data (missing days only) for all tickers.
Runs daily after market close to get the latest prices.

API: EODHD /eod endpoint
Data: Daily OHLCV deltas (from last date to today)
Mode: incremental
Schedule: Daily at 22:00 UTC (after US market close at 21:00 UTC)
Prerequisites: dag_01_historical_prices must be completed first

This DAG:
- Checks last price date per ticker
- Fetches only missing dates
- Minimal API calls (only what's needed)
- Fast execution (~10-30 minutes)
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
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    dag_id='02_incremental_prices',
    default_args=default_args,
    description='DAILY: Fetch incremental price data (deltas only) for all tickers',
    schedule='0 22 * * *',  # 22:00 UTC daily (after US market close)
    start_date=datetime(2025, 10, 29),
    catchup=False,
    max_active_runs=1,
    tags=['incremental', 'prices', 'eodhd', 'daily', 'production', 'step-02'],
    doc_md=__doc__,
)

initialize_task = PythonOperator(
    task_id='initialize_execution',
    python_callable=initialize_execution_record,
    dag=dag,
)

# Process all exchanges
process_all_task = BashOperator(
    task_id='fetch_incremental_prices',
    bash_command="""
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"

    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: incr-prices-{{ ts_nodash | lower }}
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
          - incremental
          - --exchanges
          - NYSE,NASDAQ,LSE,BME,EURONEXT,FRANKFURT,SIX
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

    kubectl wait --for=condition=complete --timeout=3600s job/incr-prices-{{ ts_nodash | lower }} -n financial-screener
    """,
    dag=dag,
    execution_timeout=timedelta(hours=1),
)

finalize_task = PythonOperator(
    task_id='finalize_execution',
    python_callable=finalize_execution_record,
    dag=dag,
)

summary_task = BashOperator(
    task_id='generate_summary',
    bash_command="""
    echo "================================================"
    echo "Incremental Prices Update Complete"
    echo "================================================"
    kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c "
        SET search_path TO financial_screener;
        SELECT
            (SELECT COUNT(*) FROM stock_prices) as total_prices,
            (SELECT MAX(date) FROM stock_prices) as latest_price_date,
            (SELECT COUNT(DISTINCT asset_id) FROM stock_prices WHERE date = (SELECT MAX(date) FROM stock_prices)) as tickers_updated_today
        FROM assets WHERE is_active = true LIMIT 1;
    "
    echo "================================================"
    """,
    dag=dag,
)

initialize_task >> process_all_task >> finalize_task >> summary_task
