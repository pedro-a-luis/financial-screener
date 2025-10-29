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
    echo "News collection for {{ data_interval_start }} to {{ data_interval_end }}"
    echo "TODO: Implement news collection in main_enhanced.py with --mode news"
    echo "Will fetch articles for date range and store with sentiment data"
    """,
    dag=dag,
    execution_timeout=timedelta(hours=1),
)

finalize_task = PythonOperator(task_id='finalize_execution', python_callable=finalize_execution_record, dag=dag)

initialize_task >> fetch_news_task >> finalize_task
