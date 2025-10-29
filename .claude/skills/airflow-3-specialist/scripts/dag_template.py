"""
Production-Ready DAG Template for Airflow 3

This template includes:
- TaskFlow API best practices
- Error handling and monitoring
- Proper configuration management
- Data quality checks
- Logging and observability
"""

from airflow.decorators import dag, task
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator
from airflow.providers.google.cloud.sensors.gcs import GCSObjectExistenceSensor
from airflow.utils.trigger_rule import TriggerRule
from datetime import datetime, timedelta
from typing import Dict, List
import logging

# DAG Configuration
DAG_ID = "production_etl_pipeline"
SCHEDULE = "@daily"
START_DATE = datetime(2024, 1, 1)
TAGS = ["production", "etl", "bigquery"]

# GCP Configuration
GCP_PROJECT = "your-project-id"
GCS_BUCKET = "your-data-bucket"
BQ_DATASET = "your_dataset"
BQ_TABLE = "your_table"

# Default arguments for all tasks
DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email": ["data-alerts@company.com"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


def send_failure_notification(context):
    """
    Callback function for task failures.
    Customize this to send alerts to Slack, PagerDuty, etc.
    """
    task_instance = context.get("task_instance")
    dag_id = task_instance.dag_id
    task_id = task_instance.task_id
    execution_date = context.get("execution_date")
    log_url = task_instance.log_url
    
    logging.error(
        f"Task Failed - DAG: {dag_id}, Task: {task_id}, "
        f"Date: {execution_date}, Log: {log_url}"
    )
    
    # Add custom notification logic here
    # Example: SlackWebhookOperator, PagerDutyOperator, etc.


@dag(
    dag_id=DAG_ID,
    schedule=SCHEDULE,
    start_date=START_DATE,
    catchup=False,
    tags=TAGS,
    default_args=DEFAULT_ARGS,
    on_failure_callback=send_failure_notification,
    description="Production ETL pipeline with error handling and monitoring",
    doc_md="""
    # Production ETL Pipeline
    
    ## Purpose
    Extract data from GCS, transform, and load to BigQuery with data quality checks.
    
    ## Schedule
    Runs daily at midnight UTC
    
    ## Dependencies
    - Requires GCS bucket: {GCS_BUCKET}
    - Writes to BigQuery: {GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}
    
    ## Monitoring
    - Email alerts on failure
    - Metrics logged to monitoring.pipeline_metrics table
    
    ## Contacts
    - Owner: Data Engineering Team
    - Email: data-alerts@company.com
    """,
)
def production_etl_pipeline():
    """
    Production ETL pipeline with comprehensive error handling and monitoring.
    """
    
    # Task 1: Wait for source data
    wait_for_source_data = GCSObjectExistenceSensor(
        task_id="wait_for_source_data",
        bucket=GCS_BUCKET,
        object=f"landing/data_{{{{ ds }}}}.parquet",
        timeout=3600,  # 1 hour timeout
        poke_interval=60,  # Check every minute
        mode="reschedule",  # Free up worker slot
    )
    
    # Task 2: Validate source data
    @task
    def validate_source_data(**context) -> Dict:
        """
        Validate source data before processing.
        Returns validation results.
        """
        from google.cloud import storage
        
        execution_date = context["ds"]
        file_path = f"landing/data_{execution_date}.parquet"
        
        try:
            client = storage.Client()
            bucket = client.bucket(GCS_BUCKET)
            blob = bucket.blob(file_path)
            
            # Check file size
            size_mb = blob.size / (1024 * 1024)
            
            logging.info(f"Source file size: {size_mb:.2f} MB")
            
            if size_mb < 0.1:
                raise ValueError("Source file too small - possible data issue")
            
            if size_mb > 5000:
                raise ValueError("Source file too large - investigate")
            
            return {
                "status": "valid",
                "file_path": file_path,
                "size_mb": size_mb,
                "execution_date": execution_date,
            }
            
        except Exception as e:
            logging.error(f"Validation failed: {e}")
            raise
    
    # Task 3: Load to staging table
    load_to_staging = GCSToBigQueryOperator(
        task_id="load_to_staging",
        bucket=GCS_BUCKET,
        source_objects=["landing/data_{{ ds }}.parquet"],
        destination_project_dataset_table=f"{GCP_PROJECT}.{BQ_DATASET}.staging_{{ ds_nodash }}",
        source_format="PARQUET",
        write_disposition="WRITE_TRUNCATE",
        create_disposition="CREATE_IF_NEEDED",
        autodetect=True,
    )
    
    # Task 4: Data quality checks
    @task.branch
    def run_quality_checks(**context) -> str:
        """
        Run data quality checks on staging data.
        Returns next task ID based on check results.
        """
        from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
        
        execution_date = context["ds_nodash"]
        hook = BigQueryHook(gcp_conn_id="google_cloud_default")
        
        # Check 1: Row count
        count_query = f"""
            SELECT COUNT(*) as row_count
            FROM `{GCP_PROJECT}.{BQ_DATASET}.staging_{execution_date}`
        """
        result = hook.get_pandas_df(sql=count_query)
        row_count = result["row_count"].iloc[0]
        
        logging.info(f"Row count: {row_count}")
        
        if row_count == 0:
            logging.error("No rows in staging table")
            return "handle_quality_failure"
        
        # Check 2: Null values in critical fields
        null_check_query = f"""
            SELECT 
                COUNTIF(id IS NULL) as null_ids,
                COUNTIF(created_at IS NULL) as null_timestamps
            FROM `{GCP_PROJECT}.{BQ_DATASET}.staging_{execution_date}`
        """
        null_result = hook.get_pandas_df(sql=null_check_query)
        
        if null_result["null_ids"].iloc[0] > 0:
            logging.error("Null values found in ID field")
            return "handle_quality_failure"
        
        # Check 3: Data freshness (optional)
        # Add more quality checks as needed
        
        logging.info("All quality checks passed")
        return "transform_and_merge"
    
    # Task 5: Handle quality check failures
    @task
    def handle_quality_failure(**context):
        """
        Handle data quality failures.
        Log issues and alert team.
        """
        logging.error("Data quality checks failed - pipeline stopped")
        # Add custom alerting logic here
        raise ValueError("Data quality checks failed")
    
    # Task 6: Transform and merge to production
    transform_and_merge = BigQueryInsertJobOperator(
        task_id="transform_and_merge",
        configuration={
            "query": {
                "query": f"""
                    -- Transform and merge staging data to production
                    MERGE `{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}` AS target
                    USING (
                        SELECT
                            id,
                            UPPER(name) as name,
                            created_at,
                            updated_at,
                            -- Add transformations here
                            CURRENT_TIMESTAMP() as ingestion_timestamp
                        FROM `{GCP_PROJECT}.{BQ_DATASET}.staging_{{{{ ds_nodash }}}}`
                    ) AS source
                    ON target.id = source.id
                    WHEN MATCHED THEN
                        UPDATE SET
                            name = source.name,
                            updated_at = source.updated_at,
                            ingestion_timestamp = source.ingestion_timestamp
                    WHEN NOT MATCHED THEN
                        INSERT (id, name, created_at, updated_at, ingestion_timestamp)
                        VALUES (id, name, created_at, updated_at, ingestion_timestamp)
                """,
                "useLegacySql": False,
            }
        },
        gcp_conn_id="google_cloud_default",
    )
    
    # Task 7: Cleanup staging table
    cleanup_staging = BigQueryInsertJobOperator(
        task_id="cleanup_staging",
        configuration={
            "query": {
                "query": f"""
                    DROP TABLE IF EXISTS `{GCP_PROJECT}.{BQ_DATASET}.staging_{{{{ ds_nodash }}}}`
                """,
                "useLegacySql": False,
            }
        },
        trigger_rule=TriggerRule.ALL_DONE,  # Run even if upstream fails
    )
    
    # Task 8: Log pipeline metrics
    @task(trigger_rule=TriggerRule.ALL_DONE)
    def log_pipeline_metrics(**context) -> None:
        """
        Log pipeline execution metrics for monitoring.
        """
        from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
        import time
        
        task_instance = context["task_instance"]
        dag_run = context["dag_run"]
        
        # Calculate duration
        if dag_run.start_date and dag_run.end_date:
            duration_seconds = (dag_run.end_date - dag_run.start_date).total_seconds()
        else:
            duration_seconds = None
        
        # Prepare metrics
        metrics = {
            "dag_id": DAG_ID,
            "execution_date": str(context["execution_date"]),
            "dag_run_id": dag_run.run_id,
            "state": str(dag_run.state),
            "duration_seconds": duration_seconds,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        logging.info(f"Pipeline metrics: {metrics}")
        
        # Optional: Write to monitoring table
        try:
            hook = BigQueryHook()
            hook.insert_rows(
                table="monitoring.pipeline_metrics",
                rows=[metrics],
            )
        except Exception as e:
            logging.warning(f"Failed to log metrics to BigQuery: {e}")
    
    # Task 9: Send success notification
    @task(trigger_rule=TriggerRule.ALL_SUCCESS)
    def send_success_notification(**context) -> None:
        """
        Send notification on successful pipeline completion.
        """
        execution_date = context["ds"]
        logging.info(f"Pipeline completed successfully for {execution_date}")
        
        # Add success notification logic here
        # Example: Slack, email, etc.
    
    # Define task dependencies
    validation_result = validate_source_data()
    quality_check = run_quality_checks()
    quality_failure = handle_quality_failure()
    metrics = log_pipeline_metrics()
    success_notif = send_success_notification()
    
    # DAG flow
    (
        wait_for_source_data
        >> validation_result
        >> load_to_staging
        >> quality_check
    )
    
    quality_check >> [transform_and_merge, quality_failure]
    transform_and_merge >> cleanup_staging >> metrics >> success_notif
    quality_failure >> metrics


# Instantiate the DAG
production_etl_pipeline()
