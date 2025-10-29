"""
03 - Historical Fundamentals Load (EODHD API) - ONE-TIME RUN

Loads comprehensive fundamental data for ALL tickers (initial/historical load).
This is currently RUNNING and should complete first. After completion, use dag_04_incremental_fundamentals.

API: EODHD /fundamentals endpoint
Data: Comprehensive fundamentals (13 sections, 100+ fields per ticker)
Mode: bulk
Schedule: None (manual trigger only - ONE-TIME initial load)
Prerequisites: dag_01_historical_prices should be completed first
Run Order: 3rd - After prices are loaded

Comprehensive data includes:
- General: Company info, officers, sector, description
- Highlights & Valuation: Key metrics and ratios
- SharesStats: Outstanding shares, float, ownership %
- Technicals: 52-week ranges, moving averages, beta
- SplitsDividends: Complete dividend/split history
- AnalystRatings: Consensus ratings and targets
- Holders: Top institutional/fund holders
- InsiderTransactions: Form 4 filings
- ESGScores: Environmental, social, governance metrics
- Earnings: Historical earnings + estimates
- Financials: 20+ years Balance Sheet, Income Statement, Cash Flow (quarterly + yearly)

After completion:
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
    dag_id='03_historical_fundamentals',
    default_args=default_args,
    description='ONE-TIME: Load comprehensive fundamentals for all tickers (EODHD API)',
    schedule=None,  # Manual trigger only
    start_date=datetime(2025, 10, 29),
    catchup=False,
    max_active_runs=1,
    tags=['historical', 'fundamentals', 'eodhd', 'one-time', 'step-03'],
    doc_md=__doc__,
)

initialize_task = PythonOperator(
    task_id='initialize_execution',
    python_callable=initialize_execution_record,
    dag=dag,
)

# Process US exchanges
process_us_task = BashOperator(
    task_id='load_us_fundamentals',
    bash_command="""
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"

    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: hist-funds-us-{{ ts_nodash | lower }}
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

    kubectl wait --for=condition=complete --timeout=7200s job/hist-funds-us-{{ ts_nodash | lower }} -n financial-screener
    """,
    dag=dag,
    execution_timeout=timedelta(hours=3),
)

# Process international exchanges
process_intl_task = BashOperator(
    task_id='load_international_fundamentals',
    bash_command="""
    EXECUTION_ID="{{ ti.xcom_pull(task_ids='initialize_execution', key='execution_id') }}"

    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: hist-funds-intl-{{ ts_nodash | lower }}
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

    kubectl wait --for=condition=complete --timeout=7200s job/hist-funds-intl-{{ ts_nodash | lower }} -n financial-screener
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
    echo "Historical Fundamentals Load Complete"
    echo "================================================"
    kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c "
        SET search_path TO financial_screener;
        SELECT
            COUNT(*) as total_assets,
            COUNT(CASE WHEN eodhd_last_update IS NOT NULL THEN 1 END) as with_fundamentals,
            COUNT(CASE WHEN eodhd_financials IS NOT NULL THEN 1 END) as with_financials,
            COUNT(CASE WHEN eodhd_earnings IS NOT NULL THEN 1 END) as with_earnings,
            COUNT(CASE WHEN eodhd_holders IS NOT NULL THEN 1 END) as with_holders
        FROM assets WHERE is_active = true;
    "
    echo ""
    echo "✅ Historical fundamentals loaded. Next steps:"
    echo "   1. Enable dag_04_incremental_fundamentals for quarterly updates"
    echo "   2. Enable dag_05_incremental_technical_indicators for daily calcs"
    echo "================================================"
    """,
    dag=dag,
)

initialize_task >> [process_us_task, process_intl_task] >> finalize_task >> summary_task
