"""
04 - Incremental Fundamentals Update (EODHD API) - QUARTERLY

Refreshes comprehensive fundamental data quarterly (after earnings season).
Uses incremental mode: delta prices + full fundamentals refresh.

API: EODHD /fundamentals endpoint
Data: Comprehensive fundamentals (13 sections, 100+ fields)
Mode: incremental
Schedule: Quarterly at 02:00 UTC (Jan 1, Apr 1, Jul 1, Oct 1)
Prerequisites: dag_03_historical_fundamentals must be completed first
Run Order: 4th - Runs quarterly after dag_03 completes

This refreshes all 13 fundamental sections while only fetching missing price deltas.
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
    'email_on_failure': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=10),
}

dag = DAG(
    dag_id='04_incremental_fundamentals',
    default_args=default_args,
    description='QUARTERLY: Refresh comprehensive fundamentals (incremental mode)',
    schedule='0 2 1 1,4,7,10 *',  # Quarterly: Jan 1, Apr 1, Jul 1, Oct 1
    start_date=datetime(2026, 1, 1),  # Next quarter
    catchup=False,
    max_active_runs=1,
    tags=['incremental', 'fundamentals', 'eodhd', 'quarterly', 'production', 'step-04'],
    doc_md=__doc__,
)

initialize_task = PythonOperator(task_id='initialize_execution', python_callable=initialize_execution_record, dag=dag)

process_all_task = BashOperator(
    task_id='refresh_fundamentals_quarterly',
    bash_command="""
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"
    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: incr-funds-{{ ts_nodash | lower }}
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
    kubectl wait --for=condition=complete --timeout=7200s job/incr-funds-{{ ts_nodash | lower }} -n financial-screener
    """,
    dag=dag,
    execution_timeout=timedelta(hours=3),
)

finalize_task = PythonOperator(task_id='finalize_execution', python_callable=finalize_execution_record, dag=dag)

summary_task = BashOperator(
    task_id='generate_summary',
    bash_command="""
    echo "================================================"
    echo "Quarterly Fundamentals Refresh Complete"
    echo "================================================"
    kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c "
        SET search_path TO financial_screener;
        SELECT COUNT(CASE WHEN eodhd_last_update > NOW() - INTERVAL '7 days' THEN 1 END) as updated_this_week FROM assets WHERE is_active = true;
    "
    """,
    dag=dag,
)

initialize_task >> process_all_task >> finalize_task >> summary_task
