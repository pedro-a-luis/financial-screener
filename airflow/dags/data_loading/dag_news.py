"""
Unified News DAG - EODHD API

Fetches financial news articles with sentiment for all tickers.
Handles both historical (via backfill) and daily updates.

Schedule: Daily at 23:00 UTC
Backfill: airflow dags backfill dag_news --start-date 2025-09-29 --end-date 2025-10-29

Uses data_interval_start/end for date range. Deduplicates by article URL.
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
    dag_id='dag_news',
    default_args=default_args,
    description='Unified news DAG - articles with sentiment',
    schedule='0 23 * * *',  # Daily at 23:00 UTC
    start_date=datetime(2025, 9, 29),
    catchup=False,
    max_active_runs=1,
    tags=['unified', 'news', 'eodhd', 'daily', 'backfill-ready'],
    doc_md=__doc__,
)

initialize_task = PythonOperator(task_id='initialize_execution', python_callable=initialize_execution_record, dag=dag)

fetch_news_task = BashOperator(
    task_id='fetch_news',
    bash_command="""
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"
    START_DATE="{{ data_interval_start.strftime('%Y-%m-%d') }}"
    END_DATE="{{ data_interval_end.strftime('%Y-%m-%d') }}"

    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: news-{{ ts_nodash | lower }}
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
        command: [python3, /app/src/main_enhanced.py, --mode, news, --exchanges, NYSE,NASDAQ,LSE,BME,EURONEXT,FRANKFURT,SIX, --start-date, ${START_DATE}, --end-date, ${END_DATE}, --execution-id, ${EXECUTION_ID}]
        env:
        - {name: DATABASE_URL, valueFrom: {secretKeyRef: {name: postgres-secret, key: DATABASE_URL}}}
        - {name: EODHD_API_KEY, valueFrom: {secretKeyRef: {name: data-api-secrets, key: EODHD_API_KEY}}}
        - {name: LOG_LEVEL, value: INFO}
        resources:
          requests: {memory: 2Gi, cpu: 1000m}
          limits: {memory: 4Gi, cpu: 2000m}
EOF
    kubectl wait --for=condition=complete --timeout=3600s job/news-{{ ts_nodash | lower }} -n financial-screener || true
    """,
    dag=dag,
    execution_timeout=timedelta(hours=1),
)

finalize_task = PythonOperator(task_id='finalize_execution', python_callable=finalize_execution_record, dag=dag)

initialize_task >> fetch_news_task >> finalize_task
