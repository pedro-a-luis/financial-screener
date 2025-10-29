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
    echo "Sentiment collection for {{ data_interval_start }} to {{ data_interval_end }}"
    echo "TODO: Implement sentiment collection in main_enhanced.py with --mode sentiment"
    echo "Will fetch batched sentiment scores (100 tickers/call)"
    """,
    dag=dag,
    execution_timeout=timedelta(minutes=30),
)

finalize_task = PythonOperator(task_id='finalize_execution', python_callable=finalize_execution_record, dag=dag)

initialize_task >> fetch_sentiment_task >> finalize_task
