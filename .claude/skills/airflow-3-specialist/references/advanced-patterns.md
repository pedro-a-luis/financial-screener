# Advanced Airflow 3 Patterns

Complex orchestration patterns and best practices for production Airflow deployments.

## Dynamic Task Generation Patterns

### Dynamic Task Mapping with Multiple Parameters

```python
from airflow.decorators import dag, task
from datetime import datetime
from typing import List, Dict

@dag(schedule="@daily", start_date=datetime(2024, 1, 1))
def multi_param_mapping():
    
    @task
    def get_processing_config() -> List[Dict]:
        """Return list of configurations to process"""
        return [
            {"region": "us-east", "data_type": "sales", "priority": 1},
            {"region": "us-west", "data_type": "sales", "priority": 2},
            {"region": "eu-west", "data_type": "inventory", "priority": 1},
        ]
    
    @task
    def process_region(config: Dict) -> Dict:
        """Process data for specific region and type"""
        print(f"Processing {config['region']} - {config['data_type']}")
        # Processing logic here
        return {"status": "success", "config": config}
    
    @task
    def aggregate_results(results: List[Dict]) -> None:
        """Aggregate all processing results"""
        for result in results:
            print(f"Region {result['config']['region']}: {result['status']}")
    
    configs = get_processing_config()
    processed = process_region.expand(config=configs)
    aggregate_results(processed)

multi_param_mapping()
```

### Conditional Dynamic Mapping

```python
@dag(schedule="@daily", start_date=datetime(2024, 1, 1))
def conditional_mapping():
    
    @task
    def determine_workload(**context) -> List[str]:
        """Decide what to process based on conditions"""
        execution_date = context["execution_date"]
        
        if execution_date.day == 1:
            # Full refresh on first of month
            return ["region_1", "region_2", "region_3", "region_4"]
        else:
            # Incremental daily
            return ["region_1", "region_2"]
    
    @task
    def process_incremental(region: str) -> str:
        print(f"Processing {region}")
        return f"{region}_complete"
    
    regions = determine_workload()
    process_incremental.expand(region=regions)

conditional_mapping()
```

## Advanced Dependency Patterns

### Cross-DAG Dependencies with Datasets

```python
from airflow import Dataset
from airflow.decorators import dag, task
from datetime import datetime

# Producer DAG
raw_data = Dataset("gs://bucket/raw_data/")
processed_data = Dataset("gs://bucket/processed_data/")

@dag(schedule="@hourly", start_date=datetime(2024, 1, 1))
def data_producer():
    
    @task(outlets=[raw_data])
    def extract_raw():
        # Extract and save to GCS
        print("Extracted raw data")
    
    extract_raw()

data_producer()

# Processor DAG - triggers when raw_data updates
@dag(schedule=[raw_data], start_date=datetime(2024, 1, 1))
def data_processor():
    
    @task(outlets=[processed_data])
    def transform_data():
        # Read raw_data, transform, save to processed_data
        print("Transformed data")
    
    transform_data()

data_processor()

# Consumer DAG - triggers when processed_data updates
@dag(schedule=[processed_data], start_date=datetime(2024, 1, 1))
def data_consumer():
    
    @task
    def load_to_warehouse():
        print("Loaded to warehouse")
    
    load_to_warehouse()

data_consumer()
```

### Complex Branching with Multiple Conditions

```python
from airflow.decorators import dag, task
from airflow.operators.empty import EmptyOperator

@dag(schedule="@daily", start_date=datetime(2024, 1, 1))
def complex_branching():
    
    @task.branch
    def determine_processing_path(**context):
        """Determine which processing path to take"""
        execution_date = context["execution_date"]
        
        # Multiple conditions
        if execution_date.weekday() == 0:  # Monday
            return ["weekly_full_refresh"]
        elif execution_date.day == 1:  # First of month
            return ["monthly_aggregate", "compliance_report"]
        else:
            return ["daily_incremental"]
    
    @task
    def weekly_full_refresh():
        print("Running weekly full refresh")
    
    @task
    def monthly_aggregate():
        print("Running monthly aggregate")
    
    @task
    def compliance_report():
        print("Generating compliance report")
    
    @task
    def daily_incremental():
        print("Running daily incremental")
    
    @task(trigger_rule="none_failed_min_one_success")
    def finalize():
        """Runs after any branch completes"""
        print("Finalizing")
    
    branch = determine_processing_path()
    weekly = weekly_full_refresh()
    monthly = monthly_aggregate()
    compliance = compliance_report()
    daily = daily_incremental()
    final = finalize()
    
    branch >> [weekly, monthly, compliance, daily] >> final

complex_branching()
```

## Error Recovery Patterns

### Retry with Backoff Strategy

```python
from datetime import timedelta
from airflow.exceptions import AirflowException

@task(
    retries=5,
    retry_delay=timedelta(minutes=1),
    retry_exponential_backoff=True,
    max_retry_delay=timedelta(hours=1)
)
def task_with_smart_retry():
    """Task with exponential backoff retry"""
    try:
        # Potentially failing operation
        pass
    except ConnectionError as e:
        # Retryable error
        raise AirflowException(f"Connection failed: {e}")
    except ValueError as e:
        # Non-retryable error - fail immediately
        raise AirflowException(f"Invalid data: {e}") from e
```

### Graceful Degradation Pattern

```python
@dag(schedule="@daily", start_date=datetime(2024, 1, 1))
def graceful_degradation():
    
    @task
    def try_primary_source() -> Dict:
        """Try to fetch from primary source"""
        try:
            # Primary data source
            return {"source": "primary", "data": [...]}
        except Exception as e:
            print(f"Primary source failed: {e}")
            raise AirflowException("Primary unavailable")
    
    @task
    def try_secondary_source() -> Dict:
        """Fallback to secondary source"""
        # Backup data source
        return {"source": "secondary", "data": [...]}
    
    @task(trigger_rule="none_failed_min_one_success")
    def process_data(data: Dict):
        """Process data from whichever source succeeded"""
        print(f"Processing from {data['source']}")
    
    primary = try_primary_source()
    secondary = try_secondary_source()
    
    # If primary fails, use secondary
    primary >> process_data(primary)
    primary >> secondary >> process_data(secondary)

graceful_degradation()
```

### Circuit Breaker Pattern

```python
from airflow.models import Variable

@task
def check_service_health() -> bool:
    """Check if external service is healthy"""
    failure_count = int(Variable.get("service_failure_count", default_var=0))
    
    if failure_count >= 5:
        # Circuit open - don't even try
        raise AirflowException("Circuit breaker open - service unavailable")
    
    try:
        # Health check logic
        Variable.set("service_failure_count", 0)  # Reset on success
        return True
    except Exception:
        Variable.set("service_failure_count", failure_count + 1)
        raise

@task
def call_external_service():
    """Only called if health check passes"""
    # Service call logic
    pass

health_ok = check_service_health()
health_ok >> call_external_service()
```

## Advanced XCom Patterns

### Custom XCom Backend for Large Data

```python
# Custom XCom backend (in plugins/custom_xcom.py)
from airflow.models.xcom import BaseXCom
import json
from google.cloud import storage

class GCSXComBackend(BaseXCom):
    """Store large XComs in GCS"""
    
    PREFIX = "xcom/"
    BUCKET = "airflow-xcom-bucket"
    THRESHOLD_BYTES = 1_000_000  # 1MB
    
    @staticmethod
    def serialize_value(value, key, task_id, dag_id, execution_date, **kwargs):
        serialized = json.dumps(value).encode()
        
        if len(serialized) > GCSXComBackend.THRESHOLD_BYTES:
            # Store in GCS and return reference
            client = storage.Client()
            bucket = client.bucket(GCSXComBackend.BUCKET)
            blob_name = f"{GCSXComBackend.PREFIX}{dag_id}/{task_id}/{execution_date}/{key}"
            blob = bucket.blob(blob_name)
            blob.upload_from_string(serialized)
            
            return json.dumps({"__type": "gcs", "path": blob_name})
        
        return serialized
    
    @staticmethod
    def deserialize_value(result):
        data = json.loads(result.value)
        
        if isinstance(data, dict) and data.get("__type") == "gcs":
            # Fetch from GCS
            client = storage.Client()
            bucket = client.bucket(GCSXComBackend.BUCKET)
            blob = bucket.blob(data["path"])
            return json.loads(blob.download_as_string())
        
        return data

# Usage in DAG
@task
def process_large_dataset() -> dict:
    # Returns large data that will be stored in GCS
    return {"data": [i for i in range(1000000)]}
```

### Typed XCom with Pydantic

```python
from pydantic import BaseModel
from typing import List

class ProcessingResult(BaseModel):
    records_processed: int
    errors: List[str]
    execution_time: float
    status: str

@task
def process_data() -> ProcessingResult:
    """Return typed result"""
    return ProcessingResult(
        records_processed=10000,
        errors=[],
        execution_time=45.2,
        status="success"
    )

@task
def validate_result(result: ProcessingResult):
    """Consume typed result with validation"""
    if result.status != "success":
        raise AirflowException(f"Processing failed: {result.errors}")
    
    if result.records_processed < 5000:
        raise AirflowException("Insufficient records processed")
```

## Monitoring and Observability

### Custom Metrics Collection

```python
from airflow.decorators import task
from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
import time

@task
def monitored_task(**context):
    """Task with custom metrics"""
    start_time = time.time()
    records_processed = 0
    
    try:
        # Processing logic
        records_processed = 10000
        
    finally:
        # Log metrics to BigQuery
        execution_time = time.time() - start_time
        
        hook = BigQueryHook()
        metrics = {
            "dag_id": context["dag"].dag_id,
            "task_id": context["task"].task_id,
            "execution_date": str(context["execution_date"]),
            "records_processed": records_processed,
            "execution_time": execution_time,
            "timestamp": time.time()
        }
        
        hook.insert_rows(
            table="monitoring.task_metrics",
            rows=[metrics]
        )
```

### Alerting Pattern

```python
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

def create_failure_alert(context):
    """Alert on task failure"""
    slack_msg = f"""
    :red_circle: Task Failed
    *DAG*: {context.get('task_instance').dag_id}
    *Task*: {context.get('task_instance').task_id}
    *Execution Time*: {context.get('execution_date')}
    *Log*: {context.get('task_instance').log_url}
    """
    
    return SlackWebhookOperator(
        task_id="slack_alert",
        http_conn_id="slack_webhook",
        message=slack_msg
    ).execute(context=context)

@dag(
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    default_args={"on_failure_callback": create_failure_alert}
)
def monitored_pipeline():
    pass
```

## Testing Patterns

### Integration Testing DAGs

```python
import pytest
from airflow.models import DagBag
from airflow.utils.state import DagRunState
from datetime import datetime

def test_dag_run():
    """Test full DAG execution"""
    from my_dags.etl_pipeline import etl_pipeline
    
    dag = etl_pipeline()
    
    # Create test DAG run
    dag.test(
        execution_date=datetime(2024, 1, 1),
        conn_file_path="/path/to/test_connections.json"
    )

def test_task_dependencies():
    """Test task dependency structure"""
    from my_dags.etl_pipeline import etl_pipeline
    
    dag = etl_pipeline()
    
    # Verify task exists
    assert "extract" in dag.task_ids
    assert "transform" in dag.task_ids
    
    # Verify dependencies
    extract_task = dag.get_task("extract")
    transform_task = dag.get_task("transform")
    
    assert transform_task in extract_task.downstream_list
```

### Mocking External Services

```python
from unittest.mock import Mock, patch

@task
def task_with_external_call():
    from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
    
    hook = BigQueryHook()
    result = hook.get_records(sql="SELECT COUNT(*) FROM table")
    return result[0][0]

# Test
@patch('airflow.providers.google.cloud.hooks.bigquery.BigQueryHook')
def test_task_with_mock(mock_hook):
    mock_hook.return_value.get_records.return_value = [[1000]]
    
    result = task_with_external_call.function()
    assert result == 1000
```

## Performance Optimization Patterns

### Parallel Processing with Pools

```python
# Define custom pools in Airflow UI:
# - Pool: "bigquery_slots" with 10 slots
# - Pool: "api_calls" with 5 slots

@dag(schedule="@hourly", start_date=datetime(2024, 1, 1))
def optimized_parallel():
    
    @task(pool="bigquery_slots", pool_slots=2)
    def heavy_query():
        """Uses 2 BQ slots"""
        pass
    
    @task(pool="api_calls", pool_slots=1)
    def api_call():
        """Uses 1 API call slot"""
        pass
    
    # Create 10 query tasks - only 5 run concurrently (10 slots / 2 slots each)
    queries = [heavy_query.override(task_id=f"query_{i}")() for i in range(10)]
```

### Batch Processing Pattern

```python
@task
def batch_processor(batch_size: int = 1000):
    """Process data in batches to avoid memory issues"""
    from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
    
    hook = BigQueryHook()
    offset = 0
    
    while True:
        query = f"""
            SELECT * FROM large_table
            LIMIT {batch_size} OFFSET {offset}
        """
        
        batch = hook.get_pandas_df(sql=query)
        
        if batch.empty:
            break
        
        # Process batch
        process_batch(batch)
        offset += batch_size
```
