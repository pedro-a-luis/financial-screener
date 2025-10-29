"""
01 - Historical Prices Load (EODHD API) - ONE-TIME RUN

Loads 2 years of historical OHLCV price data for ALL tickers.
This is a ONE-TIME initial load. After completion, use incremental_prices DAG.

API: EODHD /eod endpoint
Data: 2 years of daily OHLCV (Open, High, Low, Close, Volume)
Mode: bulk
Schedule: None (manual trigger only for initial load)
Run Order: 1st - Run this before any other DAGs

After completion:
- Enable dag_02_incremental_prices for daily delta updates
- Enable dag_04_incremental_fundamentals for quarterly updates
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
    'retry_delay': timedelta(minutes=10),
}

dag = DAG(
    dag_id='01_historical_prices',
    default_args=default_args,
    description='ONE-TIME: Load 2 years of historical prices for all tickers (EODHD API)',
    schedule=None,  # Manual trigger only
    start_date=datetime(2025, 10, 29),
    catchup=False,
    max_active_runs=1,
    tags=['historical', 'prices', 'eodhd', 'one-time', 'step-01'],
    doc_md=__doc__,
)

initialize_task = PythonOperator(
    task_id='initialize_execution',
    python_callable=initialize_execution_record,
    dag=dag,
)

# Process US exchanges
process_us_task = BashOperator(
    task_id='load_us_prices_2years',
    bash_command="""
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"

    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: hist-prices-us-{{ ts_nodash | lower }}
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
          - --exchanges
          - NYSE,NASDAQ
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

    kubectl wait --for=condition=complete --timeout=7200s job/hist-prices-us-{{ ts_nodash | lower }} -n financial-screener
    """,
    dag=dag,
    execution_timeout=timedelta(hours=3),
)

# Process international exchanges
process_intl_task = BashOperator(
    task_id='load_international_prices_2years',
    bash_command="""
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"

    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: hist-prices-intl-{{ ts_nodash | lower }}
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
          - --exchanges
          - LSE,BME,EURONEXT,FRANKFURT,SIX
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

    kubectl wait --for=condition=complete --timeout=7200s job/hist-prices-intl-{{ ts_nodash | lower }} -n financial-screener
    """,
    dag=dag,
    execution_timeout=timedelta(hours=3),
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
    echo "Historical Prices Load Complete"
    echo "================================================"
    kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c "
        SET search_path TO financial_screener;
        SELECT
            COUNT(*) as total_assets,
            COUNT(DISTINCT ticker) as unique_tickers,
            (SELECT COUNT(*) FROM stock_prices) as total_prices,
            (SELECT MAX(date) FROM stock_prices) as latest_price_date,
            (SELECT MIN(date) FROM stock_prices) as earliest_price_date
        FROM assets WHERE is_active = true;
    "
    echo ""
    echo "✅ Historical prices loaded. Next steps:"
    echo "   1. Enable and run dag_03_historical_fundamentals"
    echo "   2. Enable dag_02_incremental_prices for daily updates"
    echo "================================================"
    """,
    dag=dag,
)

initialize_task >> [process_us_task, process_intl_task] >> finalize_task >> summary_task
