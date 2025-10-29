"""
Unified Sentiment DAG - EODHD API

Fetches aggregated daily sentiment scores for all tickers.
Handles both historical (via backfill) and daily updates.

Schedule: Daily at 23:30 UTC
Backfill: airflow dags backfill dag_sentiment --start-date 2025-07-29 --end-date 2025-10-29

Batches 100 tickers per API call for efficiency. Uses data_interval_start/end.
"""

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.metadata_helpers import initialize_execution_record, finalize_execution_record

default_args = {
    'owner': 'financial-screener',
    'depends_on_past': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    dag_id='dag_sentiment',
    default_args=default_args,
    description='Unified sentiment DAG - aggregated daily scores',
    schedule='30 23 * * *',  # Daily at 23:30 UTC
    start_date=datetime(2025, 7, 29),
    catchup=False,
    max_active_runs=1,
    tags=['unified', 'sentiment', 'eodhd', 'daily', 'backfill-ready'],
    doc_md=__doc__,
)

initialize_task = PythonOperator(task_id='initialize_execution', python_callable=initialize_execution_record, dag=dag)

fetch_sentiment_task = BashOperator(
    task_id='fetch_sentiment',
    bash_command="""
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"
    START_DATE="{{ data_interval_start.strftime('%Y-%m-%d') }}"
    END_DATE="{{ data_interval_end.strftime('%Y-%m-%d') }}"

    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: sentiment-{{ ts_nodash | lower }}
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
        command: [python3, /app/src/main_enhanced.py, --mode, sentiment, --exchanges, NYSE,NASDAQ,LSE,BME,EURONEXT,FRANKFURT,SIX, --start-date, ${START_DATE}, --end-date, ${END_DATE}, --execution-id, ${EXECUTION_ID}]
        env:
        - {name: DATABASE_URL, valueFrom: {secretKeyRef: {name: postgres-secret, key: DATABASE_URL}}}
        - {name: EODHD_API_KEY, valueFrom: {secretKeyRef: {name: data-api-secrets, key: EODHD_API_KEY}}}
        - {name: LOG_LEVEL, value: INFO}
        resources:
          requests: {memory: 1Gi, cpu: 500m}
          limits: {memory: 2Gi, cpu: 1000m}
EOF
    kubectl wait --for=condition=complete --timeout=1800s job/sentiment-{{ ts_nodash | lower }} -n financial-screener || true
    """,
    dag=dag,
    execution_timeout=timedelta(minutes=30),
)

finalize_task = PythonOperator(task_id='finalize_execution', python_callable=finalize_execution_record, dag=dag)

initialize_task >> fetch_sentiment_task >> finalize_task
