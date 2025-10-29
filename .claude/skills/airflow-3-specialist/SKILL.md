---
name: airflow-3-specialist
description: Expert guidance for Apache Airflow 3.x development including DAG creation, TaskFlow API, dynamic task mapping, task groups, custom operators, XComs, connections, hooks, executors, and best practices. Use for designing data pipelines, orchestration workflows, debugging Airflow issues, migration from Airflow 2.x, and optimizing Airflow performance.
---

# Airflow 3 Specialist

Expert guidance for Apache Airflow 3.x orchestration platform with focus on modern patterns, TaskFlow API, and cloud-native deployments.

## When to Use This Skill

- Creating or refactoring Airflow DAGs
- Implementing dynamic task mapping and task groups
- Building custom operators, sensors, or hooks
- Debugging Airflow issues or performance problems
- Migrating from Airflow 2.x to 3.x
- Designing data pipeline orchestration patterns
- Integrating with cloud services (GCP, AWS, Azure)
- Implementing best practices for production deployments

## Core Airflow 3 Concepts

### TaskFlow API (@task decorator)

Airflow 3 strongly emphasizes the TaskFlow API for cleaner, more Pythonic DAGs:

```python
from airflow.decorators import dag, task
from datetime import datetime

@dag(
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["example"]
)
def my_etl_pipeline():
    
    @task
    def extract() -> dict:
        """Extract data from source"""
        return {"data": [1, 2, 3, 4, 5]}
    
    @task
    def transform(data: dict) -> dict:
        """Transform the data"""
        return {"data": [x * 2 for x in data["data"]]}
    
    @task
    def load(data: dict) -> None:
        """Load data to destination"""
        print(f"Loading: {data}")
    
    # Define task dependencies through function calls
    data = extract()
    transformed = transform(data)
    load(transformed)

my_etl_pipeline()
```

### Dynamic Task Mapping

Use `expand()` for dynamic parallelization (replaces classic SubDAGs):

```python
@task
def process_item(item: dict) -> dict:
    # Process individual item
    return {"result": item["value"] * 2}

@task
def get_items() -> list[dict]:
    return [{"value": i} for i in range(10)]

# Dynamic mapping - creates parallel tasks at runtime
items = get_items()
results = process_item.expand(item=items)
```

### Task Groups

Organize related tasks visually in the UI:

```python
from airflow.utils.task_group import TaskGroup

@dag(schedule="@daily", start_date=datetime(2024, 1, 1))
def grouped_pipeline():
    
    with TaskGroup("ingestion") as ingestion:
        @task
        def fetch_api_1():
            pass
        
        @task
        def fetch_api_2():
            pass
        
        fetch_api_1()
        fetch_api_2()
    
    with TaskGroup("processing") as processing:
        @task
        def clean_data():
            pass
        
        @task  
        def validate_data():
            pass
        
        clean_data() >> validate_data()
    
    ingestion >> processing
```

## Key Airflow 3 Changes from 2.x

### Major Updates

1. **Unified TaskFlow**: All decorators now under `airflow.decorators`
2. **Improved Typing**: Better type hints throughout the codebase
3. **Dataset-Aware Scheduling**: Enhanced dataset-driven scheduling
4. **Params Improvements**: Better parameter validation and UI
5. **Removal of Deprecated Features**: Cleaned up legacy patterns
6. **Better XCom Backend**: More flexible XCom handling

### Migration Checklist

- Replace `PythonOperator` with `@task` decorator
- Update import paths for operators (consolidated modules)
- Review Dataset scheduling if using data-aware scheduling
- Check custom operator compatibility
- Update connection configurations for new formats
- Verify executor configurations for cloud deployments

## Best Practices

### DAG Design

**DO:**
- Use TaskFlow API (@task) for Python tasks
- Implement idempotent tasks
- Set appropriate `retries`, `retry_delay`, and `execution_timeout`
- Use meaningful task_ids and DAG descriptions
- Leverage dynamic task mapping for parallel processing
- Use `catchup=False` unless historical runs are needed
- Implement proper error handling with `on_failure_callback`

**DON'T:**
- Define DAGs inside loops or functions (except @dag decorator)
- Perform heavy computation in DAG definition (parsing)
- Use top-level code that executes at import time
- Create circular dependencies
- Use SubDAGs (use TaskGroups instead)
- Store large data in XComs (use external storage)

### XCom Patterns

**Efficient XCom usage:**

```python
from airflow.decorators import task

@task
def small_metadata() -> dict:
    """Return small metadata - OK for XCom"""
    return {"count": 100, "status": "success"}

@task
def large_data_handler() -> str:
    """Return reference to data location"""
    # Store large data externally
    df.to_parquet("gs://bucket/data.parquet")
    # Return only the path
    return "gs://bucket/data.parquet"

@task
def consumer(path: str):
    """Read data from external location"""
    df = pd.read_parquet(path)
```

### Connection Management

Define connections via environment variables or Airflow UI:

```python
from airflow.providers.google.cloud.hooks.gcs import GCSHook

@task
def use_connection():
    hook = GCSHook(gcp_conn_id="google_cloud_default")
    # Use hook for operations
```

### Error Handling

```python
@task(retries=3, retry_delay=timedelta(minutes=5))
def robust_task():
    try:
        # Task logic
        pass
    except SpecificException as e:
        # Log and potentially skip
        logging.error(f"Expected error: {e}")
        raise AirflowSkipException("Skipping due to expected condition")
    except Exception as e:
        # Log and re-raise for retry
        logging.error(f"Unexpected error: {e}")
        raise

@dag(
    schedule="@daily",
    default_args={
        "on_failure_callback": notify_failure,
        "email": ["alerts@company.com"],
        "email_on_failure": True
    }
)
def monitored_pipeline():
    pass
```

## Common Patterns

### Branching Logic

```python
from airflow.decorators import task

@task.branch
def branch_logic(**context):
    """Decide which path to take"""
    execution_date = context["execution_date"]
    if execution_date.day == 1:
        return "monthly_task"
    return "daily_task"

@task
def monthly_task():
    pass

@task  
def daily_task():
    pass

branch = branch_logic()
branch >> [monthly_task(), daily_task()]
```

### Sensor Pattern

```python
from airflow.providers.google.cloud.sensors.gcs import GCSObjectExistenceSensor

wait_for_file = GCSObjectExistenceSensor(
    task_id="wait_for_file",
    bucket="my-bucket",
    object="path/to/file.csv",
    timeout=600,
    poke_interval=30,
    mode="reschedule"  # Frees worker slot while waiting
)
```

### External Task Dependencies

```python
from airflow.sensors.external_task import ExternalTaskSensor

wait_for_upstream = ExternalTaskSensor(
    task_id="wait_for_upstream_dag",
    external_dag_id="upstream_dag",
    external_task_id="final_task",
    mode="reschedule"
)
```

## Performance Optimization

### Parallelization

```python
# Configure at DAG level
@dag(
    schedule="@daily",
    max_active_runs=1,  # Limit concurrent DAG runs
    max_active_tasks=16  # Limit concurrent tasks per DAG run
)
def optimized_pipeline():
    pass
```

### Pool Management

```python
@task(pool="data_processing", pool_slots=2)
def resource_intensive_task():
    """Uses 2 slots from data_processing pool"""
    pass
```

### Task Priority

```python
@task(priority_weight=10)  # Higher = higher priority
def critical_task():
    pass
```

## Cloud Provider Integration

### GCP (Most Common)

```python
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator

@dag(schedule="@daily", start_date=datetime(2024, 1, 1))
def gcp_pipeline():
    
    load_to_bq = GCSToBigQueryOperator(
        task_id="load_to_bq",
        bucket="my-bucket",
        source_objects=["data/*.parquet"],
        destination_project_dataset_table="project.dataset.table",
        source_format="PARQUET",
        write_disposition="WRITE_TRUNCATE"
    )
    
    @task
    def run_custom_bq_query():
        from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
        hook = BigQueryHook(gcp_conn_id="google_cloud_default")
        # Custom query logic
```

## Debugging Tips

### Enable Debug Logging

```python
import logging

@task
def debug_task():
    logger = logging.getLogger("airflow.task")
    logger.setLevel(logging.DEBUG)
    logger.debug("Detailed debug information")
```

### Test DAGs Locally

```bash
# Test task instance
airflow tasks test dag_id task_id 2024-01-01

# Parse DAG for errors
airflow dags list-import-errors

# Validate DAG structure
python your_dag.py
```

### Common Issues

1. **Import Errors**: Check DAG file parses without errors
2. **Zombie Tasks**: Check executor configuration and worker health
3. **Slow DAG Parsing**: Reduce top-level computation, use lazy imports
4. **XCom Size Limits**: Move large data to external storage
5. **Concurrency Issues**: Review pool configurations and max_active_tasks

## Advanced Features

### Dataset-Aware Scheduling

```python
from airflow import Dataset

# Define datasets
input_dataset = Dataset("gs://bucket/input/")
output_dataset = Dataset("gs://bucket/output/")

@dag(
    schedule=[input_dataset],  # Trigger when input_dataset updates
    start_date=datetime(2024, 1, 1)
)
def consumer_pipeline():
    
    @task(outlets=[output_dataset])  # Mark output dataset
    def process_data():
        pass
```

### Custom Operators

For reusable patterns across DAGs, create custom operators:

```python
from airflow.models.baseoperator import BaseOperator

class CustomProcessOperator(BaseOperator):
    template_fields = ("input_path", "output_path")
    
    def __init__(self, input_path: str, output_path: str, **kwargs):
        super().__init__(**kwargs)
        self.input_path = input_path
        self.output_path = output_path
    
    def execute(self, context):
        # Custom logic here
        pass
```

## Testing DAGs

```python
import pytest
from airflow.models import DagBag

def test_dag_loads():
    """Test DAG loads without errors"""
    dag_bag = DagBag(include_examples=False)
    assert len(dag_bag.import_errors) == 0

def test_dag_structure():
    """Test DAG has expected structure"""
    from my_dags import my_pipeline
    dag = my_pipeline()
    assert len(dag.tasks) == 5
    assert "extract" in dag.task_ids
```

## Additional Resources

For detailed examples and templates:
- See `references/gcp-operators.md` for GCP-specific operator examples
- See `references/advanced-patterns.md` for complex orchestration patterns
- See `scripts/dag_template.py` for production-ready DAG template

## Quick Reference

**Common Decorators:**
- `@dag` - Define DAG
- `@task` - Define Python task
- `@task.branch` - Branching logic
- `@task.short_circuit` - Skip downstream on False
- `@task.virtualenv` - Task in virtual environment
- `@task.docker` - Task in Docker container

**Common Operators:**
- `BashOperator` - Execute bash commands
- `PythonOperator` - Execute Python callable (prefer @task)
- `BranchPythonOperator` - Branching (prefer @task.branch)
- Cloud provider operators (GCS, BigQuery, S3, etc.)

**Scheduling:**
- `@daily` = `0 0 * * *`
- `@hourly` = `0 * * * *`
- `@weekly` = `0 0 * * 0`
- `@monthly` = `0 0 1 * *`
- Custom cron: `"0 12 * * 1-5"` (weekdays at noon)
