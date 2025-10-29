"""
Unified Fundamentals DAG - EODHD API

Fetches comprehensive fundamentals (13 sections, 100+ fields) for all tickers.
Handles both historical (via backfill) and quarterly updates.

Schedule: Quarterly at 02:00 UTC (Jan 1, Apr 1, Jul 1, Oct 1)
Backfill: airflow dags backfill dag_fundamentals --start-date 2025-10-29 --end-date 2025-10-29

Note: Fundamentals are always comprehensive (not delta). Uses data_interval for tracking only.
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
    'retry_delay': timedelta(minutes=10),
}

dag = DAG(
    dag_id='dag_fundamentals',
    default_args=default_args,
    description='Unified fundamentals DAG - comprehensive refresh quarterly',
    schedule='0 2 1 1,4,7,10 *',  # Quarterly
    start_date=datetime(2025, 10, 29),
    catchup=False,
    max_active_runs=1,
    tags=['unified', 'fundamentals', 'eodhd', 'quarterly', 'backfill-ready'],
    doc_md=__doc__,
)

initialize_task = PythonOperator(task_id='initialize_execution', python_callable=initialize_execution_record, dag=dag)

fetch_fundamentals_task = BashOperator(
    task_id='fetch_fundamentals',
    bash_command="""
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"
    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: fundamentals-{{ ts_nodash | lower }}
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
        command: [python3, /app/src/main_enhanced.py, --mode, incremental, --exchanges, NYSE,NASDAQ,LSE,BME,EURONEXT,FRANKFURT,SIX, --execution-id, ${EXECUTION_ID}]
        env:
        - {name: DATABASE_URL, valueFrom: {secretKeyRef: {name: postgres-secret, key: DATABASE_URL}}}
        - {name: EODHD_API_KEY, valueFrom: {secretKeyRef: {name: data-api-secrets, key: EODHD_API_KEY}}}
        - {name: LOG_LEVEL, value: INFO}
        resources:
          requests: {memory: 2Gi, cpu: 1000m}
          limits: {memory: 4Gi, cpu: 2000m}
EOF
    kubectl wait --for=condition=complete --timeout=7200s job/fundamentals-{{ ts_nodash | lower }} -n financial-screener || true
    """,
    dag=dag,
    execution_timeout=timedelta(hours=3),
)

finalize_task = PythonOperator(task_id='finalize_execution', python_callable=finalize_execution_record, dag=dag)

initialize_task >> fetch_fundamentals_task >> finalize_task
