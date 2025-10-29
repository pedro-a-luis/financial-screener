# GCP Operators Reference for Airflow 3

Comprehensive guide for Google Cloud Platform operators in Airflow 3.

## BigQuery Operators

### BigQueryInsertJobOperator

Execute any BigQuery job (query, load, extract, copy):

```python
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator

run_query = BigQueryInsertJobOperator(
    task_id="run_query",
    configuration={
        "query": {
            "query": """
                SELECT date, SUM(revenue) as total_revenue
                FROM `project.dataset.sales`
                WHERE date >= '{{ ds }}'
                GROUP BY date
            """,
            "useLegacySql": False,
            "destinationTable": {
                "projectId": "project",
                "datasetId": "dataset", 
                "tableId": "daily_revenue"
            },
            "writeDisposition": "WRITE_TRUNCATE"
        }
    },
    gcp_conn_id="google_cloud_default"
)
```

### BigQueryCheckOperator

Validate data quality with SQL checks:

```python
from airflow.providers.google.cloud.operators.bigquery import BigQueryCheckOperator

check_data = BigQueryCheckOperator(
    task_id="check_revenue",
    sql="""
        SELECT COUNT(*) > 0
        FROM `project.dataset.sales`
        WHERE date = '{{ ds }}'
        AND revenue > 0
    """,
    use_legacy_sql=False
)
```

### BigQueryValueCheckOperator

Check specific value expectations:

```python
from airflow.providers.google.cloud.operators.bigquery import BigQueryValueCheckOperator

check_count = BigQueryValueCheckOperator(
    task_id="check_row_count",
    sql="SELECT COUNT(*) FROM `project.dataset.sales` WHERE date = '{{ ds }}'",
    pass_value=1000,  # Expected minimum count
    tolerance=0.1,  # 10% tolerance
    use_legacy_sql=False
)
```

## GCS (Cloud Storage) Operators

### GCSToGCSOperator

Copy or move objects between GCS buckets:

```python
from airflow.providers.google.cloud.transfers.gcs_to_gcs import GCSToGCSOperator

copy_files = GCSToGCSOperator(
    task_id="copy_files",
    source_bucket="source-bucket",
    source_object="data/*.parquet",
    destination_bucket="dest-bucket",
    destination_object="processed/",
    move_object=False  # Set True to move instead of copy
)
```

### GCSToBigQueryOperator

Load data from GCS to BigQuery:

```python
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator

load_data = GCSToBigQueryOperator(
    task_id="load_to_bq",
    bucket="my-bucket",
    source_objects=["data/{{ ds }}/*.parquet"],
    destination_project_dataset_table="project.dataset.table",
    source_format="PARQUET",
    write_disposition="WRITE_APPEND",  # or WRITE_TRUNCATE, WRITE_EMPTY
    create_disposition="CREATE_IF_NEEDED",
    autodetect=True,  # Auto-detect schema
    time_partitioning={
        "type": "DAY",
        "field": "date"
    },
    cluster_fields=["customer_id", "region"]
)
```

### BigQueryToGCSOperator

Export BigQuery table to GCS:

```python
from airflow.providers.google.cloud.transfers.bigquery_to_gcs import BigQueryToGCSOperator

export_data = BigQueryToGCSOperator(
    task_id="export_to_gcs",
    source_project_dataset_table="project.dataset.table",
    destination_cloud_storage_uris=["gs://bucket/export/*.parquet"],
    export_format="PARQUET",
    compression="SNAPPY",
    print_header=False
)
```

## Cloud Composer Specific

### GCS Sensors

Wait for file existence:

```python
from airflow.providers.google.cloud.sensors.gcs import GCSObjectExistenceSensor

wait_for_file = GCSObjectExistenceSensor(
    task_id="wait_for_landing_file",
    bucket="landing-bucket",
    object="data/{{ ds }}/file.csv",
    timeout=3600,  # 1 hour timeout
    poke_interval=60,  # Check every 60 seconds
    mode="reschedule"  # Free up worker slot while waiting
)
```

Wait for file with updated time:

```python
from airflow.providers.google.cloud.sensors.gcs import GCSObjectUpdateSensor

wait_for_update = GCSObjectUpdateSensor(
    task_id="wait_for_update",
    bucket="bucket",
    object="path/to/file.csv",
    ts_func=lambda context: context["execution_date"]
)
```

## DataProc Operators

Submit Spark jobs on Dataproc:

```python
from airflow.providers.google.cloud.operators.dataproc import (
    DataprocCreateClusterOperator,
    DataprocSubmitJobOperator,
    DataprocDeleteClusterOperator
)

# Create cluster
create_cluster = DataprocCreateClusterOperator(
    task_id="create_cluster",
    cluster_name="ephemeral-cluster-{{ ds_nodash }}",
    region="us-central1",
    cluster_config={
        "master_config": {
            "num_instances": 1,
            "machine_type_uri": "n1-standard-4"
        },
        "worker_config": {
            "num_instances": 2,
            "machine_type_uri": "n1-standard-4"
        }
    }
)

# Submit PySpark job
submit_job = DataprocSubmitJobOperator(
    task_id="submit_pyspark",
    job={
        "reference": {"project_id": "project"},
        "placement": {"cluster_name": "ephemeral-cluster-{{ ds_nodash }}"},
        "pyspark_job": {
            "main_python_file_uri": "gs://bucket/scripts/process.py",
            "args": ["{{ ds }}"],
            "jar_file_uris": ["gs://bucket/jars/bigquery-connector.jar"]
        }
    },
    region="us-central1"
)

# Delete cluster
delete_cluster = DataprocDeleteClusterOperator(
    task_id="delete_cluster",
    cluster_name="ephemeral-cluster-{{ ds_nodash }}",
    region="us-central1",
    trigger_rule="all_done"  # Delete even if job fails
)

create_cluster >> submit_job >> delete_cluster
```

## Cloud Functions

Invoke Cloud Functions:

```python
from airflow.providers.google.cloud.operators.functions import CloudFunctionInvokeFunctionOperator

invoke_function = CloudFunctionInvokeFunctionOperator(
    task_id="trigger_processing",
    function_id="process-data",
    location="us-central1",
    input_data={"date": "{{ ds }}", "mode": "full"},
    gcp_conn_id="google_cloud_default"
)
```

## Dataflow Operators

Run Dataflow jobs:

```python
from airflow.providers.google.cloud.operators.dataflow import DataflowTemplatedJobStartOperator

run_dataflow = DataflowTemplatedJobStartOperator(
    task_id="run_dataflow_job",
    template="gs://dataflow-templates/latest/GCS_Text_to_BigQuery",
    parameters={
        "inputFilePattern": "gs://bucket/input/*.csv",
        "outputTable": "project:dataset.table",
        "bigQueryLoadingTemporaryDirectory": "gs://bucket/temp/"
    },
    location="us-central1"
)
```

## Best Practices for GCP Operators

### Templating

Use Airflow macros for dynamic values:

```python
# Good - templated values
load_data = GCSToBigQueryOperator(
    source_objects=["data/{{ ds }}/*.parquet"],  # Uses execution date
    destination_project_dataset_table="project.dataset.table_{{ ds_nodash }}"
)
```

### Connection Management

Configure GCP connection with JSON key or Workload Identity:

```python
# Using specific connection
hook = GCSHook(gcp_conn_id="gcp_data_eng")

# Using default connection (configured in environment)
hook = GCSHook(gcp_conn_id="google_cloud_default")
```

### Error Handling

```python
from airflow.exceptions import AirflowException

@task
def process_with_retry():
    try:
        hook = BigQueryHook(gcp_conn_id="google_cloud_default")
        # Process data
    except Exception as e:
        if "quotaExceeded" in str(e):
            raise AirflowException("Quota exceeded - adjust rate")
        raise
```

### Cost Optimization

```python
# Use partitioned tables
load_data = GCSToBigQueryOperator(
    task_id="load",
    time_partitioning={"type": "DAY", "field": "date"},
    cluster_fields=["user_id"],  # Clustering for better query performance
)

# Use ephemeral Dataproc clusters
create_cluster = DataprocCreateClusterOperator(
    cluster_config={
        "gce_cluster_config": {
            "metadata": {"PIP_PACKAGES": "pandas spark-bigquery-connector"}
        },
        "lifecycle_config": {
            "idle_delete_ttl": {"seconds": 600}  # Auto-delete after idle
        }
    }
)
```

## Common Patterns

### Incremental Load Pattern

```python
@dag(schedule="@daily", start_date=datetime(2024, 1, 1))
def incremental_load():
    
    # Extract from source
    extract = GCSToBigQueryOperator(
        task_id="extract_incremental",
        bucket="landing",
        source_objects=["data/{{ ds }}/*.parquet"],
        destination_project_dataset_table="project.staging.raw_{{ ds_nodash }}",
        write_disposition="WRITE_TRUNCATE"
    )
    
    # Transform and merge
    merge = BigQueryInsertJobOperator(
        task_id="merge_to_prod",
        configuration={
            "query": {
                "query": """
                    MERGE project.prod.table AS target
                    USING project.staging.raw_{{ ds_nodash }} AS source
                    ON target.id = source.id
                    WHEN MATCHED THEN UPDATE SET *
                    WHEN NOT MATCHED THEN INSERT *
                """,
                "useLegacySql": False
            }
        }
    )
    
    extract >> merge
```

### Data Quality Pattern

```python
@dag(schedule="@daily", start_date=datetime(2024, 1, 1))
def quality_checks():
    
    load = GCSToBigQueryOperator(task_id="load", ...)
    
    # Check 1: Row count
    check_count = BigQueryCheckOperator(
        task_id="check_count",
        sql="SELECT COUNT(*) > 1000 FROM `project.dataset.table` WHERE date = '{{ ds }}'"
    )
    
    # Check 2: No nulls in key fields  
    check_nulls = BigQueryCheckOperator(
        task_id="check_nulls",
        sql="SELECT COUNT(*) = 0 FROM `project.dataset.table` WHERE date = '{{ ds }}' AND id IS NULL"
    )
    
    # Check 3: Value ranges
    check_ranges = BigQueryCheckOperator(
        task_id="check_ranges",
        sql="SELECT MIN(amount) >= 0 AND MAX(amount) < 1000000 FROM `project.dataset.table` WHERE date = '{{ ds }}'"
    )
    
    load >> [check_count, check_nulls, check_ranges]
```
