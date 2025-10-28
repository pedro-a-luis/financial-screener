# DAG Configuration Refactoring - Progress Report

**Date**: 2025-10-28
**Status**: Database Foundation Complete, DAG Migration In Progress

---

## Overview

This refactoring removes hardcoded values from all Airflow DAGs, introducing a metadata-driven configuration system that enables runtime tuning without code changes.

---

## ✅ Phase 1: Database Foundation (COMPLETED)

### Created Migration: `008_dag_configuration_tables.sql`

**Tables Created:**

1. **`dag_configuration`** - Runtime DAG settings
   - Resource limits (CPU, memory)
   - Batch sizes
   - Timeouts and retries
   - Per-job configuration (e.g., us_markets, lse, etc.)
   - Enable/disable jobs dynamically

2. **`exchange_groups`** - Market exchange groupings
   - Group definitions (us_markets, lse, german_markets, european_markets)
   - Exchange arrays for each group
   - Market hours and timezone info
   - Priority settings

3. **`dag_configuration_audit`** - Configuration change history
   - Tracks all INSERT/UPDATE/DELETE operations
   - Provides audit trail for compliance

**Functions Created:**

1. **`get_dag_config(dag_name, job_name)`**
   - Retrieves configuration for specific DAG job
   - Returns defaults if no config exists
   - Usage: `SELECT * FROM get_dag_config('data_collection_equities', 'us_markets');`

2. **`get_exchange_groups()`**
   - Returns all enabled exchange groups ordered by priority
   - Usage: `SELECT * FROM get_exchange_groups();`

3. **`update_dag_config(...)`**
   - Safely updates configuration with audit trail
   - Creates new config if doesn't exist
   - Usage: `SELECT update_dag_config('data_collection_equities', 'us_markets', p_cpu_limit => '3000m');`

**Initial Data Populated:**

- 9 DAG configurations (data_collection x4, historical_load x4, calculate_indicators x1)
- 4 exchange groups (US, LSE, German, European)

### Migration Applied Successfully

```sql
-- Verification queries
SELECT * FROM dag_configuration;
SELECT * FROM exchange_groups;
SELECT * FROM get_dag_config('data_collection_equities', 'us_markets');
```

Results:
- ✅ 9 DAG configurations created
- ✅ 4 exchange groups defined
- ✅ All functions working correctly
- ✅ Audit trigger active

---

## 📋 Phase 2: DAG Migration (PENDING)

### Remaining Tasks

#### 1. Migrate Historical Load DAG to BashOperator

**File**: `airflow/dags/data_loading/dag_historical_load_equities.py`

**Current State:**
- ❌ Uses `KubernetesPodOperator` (ARM64 incompatible)
- ❌ Hardcoded resource limits
- ❌ Hardcoded batch sizes
- ❌ Hardcoded exchange groupings
- ❌ No indicators trigger

**Required Changes:**

1. **Convert to BashOperator Pattern**
   - Follow `dag_data_collection_equities.py` approach
   - Create `create_kubectl_historical_command()` function
   - Replace all 4 `KubernetesPodOperator` tasks with `BashOperator`
   - Preserve XCom integration for date ranges

2. **Add Configuration Integration**
   - Create helper function `get_historical_config()` to query database
   - Read resource limits from `dag_configuration` table
   - Read exchange groups from `exchange_groups` table
   - Read batch sizes from configuration

3. **Add Indicators Trigger**
   - Add `TriggerDagRunOperator` after finalization
   - Match pattern from data_collection DAG
   - Trigger `calculate_indicators` DAG

**Template kubectl command** (for historical load):
```python
def create_kubectl_historical_command(pod_name, exchanges, market_label):
    return f"""
POD_NAME="{pod_name}-$(echo "{{{{ run_id }}}}" | tr '[:upper:]_:+.' '[:lower:]----')"
DB_URL=$(kubectl get secret postgres-secret -n financial-screener -o jsonpath='{{.data.DATABASE_URL}}' | base64 -d)
API_KEY=$(kubectl get secret data-api-secrets -n financial-screener -o jsonpath='{{.data.EODHD_API_KEY}}' | base64 -d)

kubectl run $POD_NAME \\
  --namespace=financial-screener \\
  --image=financial-data-collector:latest \\
  --image-pull-policy=Never \\
  --restart=Never \\
  --labels="app=data-collector,job-type=historical,market={market_label}" \\
  --env="DATABASE_URL=$DB_URL" \\
  --env="EODHD_API_KEY=$API_KEY" \\
  --requests="cpu={{{{ ti.xcom_pull(task_ids='get_config', key='cpu_request') }}}},memory={{{{ ti.xcom_pull(task_ids='get_config', key='memory_request') }}}}" \\
  --limits="cpu={{{{ ti.xcom_pull(task_ids='get_config', key='cpu_limit') }}}},memory={{{{ ti.xcom_pull(task_ids='get_config', key='memory_limit') }}}}" \\
  -- python /app/src/main_enhanced.py \\
     --execution-id "{{{{ run_id }}}}" \\
     --exchanges "{exchanges}" \\
     --mode historical \\
     --start-date "{{{{ ti.xcom_pull(task_ids='determine_next_month', key='start_date') }}}}" \\
     --end-date "{{{{ ti.xcom_pull(task_ids='determine_next_month', key='end_date') }}}}" \\
     --skip-existing \\
     --batch-size {{{{ ti.xcom_pull(task_ids='get_config', key='batch_size') }}}}

kubectl wait --for=condition=complete pod/$POD_NAME -n financial-screener --timeout={{{{ ti.xcom_pull(task_ids='get_config', key='timeout_seconds') }}}}s
kubectl logs $POD_NAME -n financial-screener
kubectl delete pod $POD_NAME -n financial-screener
"""
```

#### 2. Refactor Data Collection DAG

**File**: `airflow/dags/data_loading/dag_data_collection_equities.py`

**Changes Needed:**

1. **Add Configuration Task**
   ```python
   get_config_task = PythonOperator(
       task_id='get_config',
       python_callable=load_dag_configuration,
       dag=dag
   )
   ```

2. **Update `create_kubectl_command()` Function**
   - Query configuration from database
   - Use XCom to pass config to kubectl commands
   - Replace hardcoded values

3. **Read Exchange Groups Dynamically**
   - Query `get_exchange_groups()` function
   - Create jobs dynamically based on enabled groups
   - Use group priorities for ordering

**Helper Function to Add:**
```python
def load_dag_configuration(**context):
    """Load DAG configuration from database."""
    import psycopg2
    from airflow.hooks.base import BaseHook

    conn_info = BaseHook.get_connection('postgres_default')
    conn = psycopg2.connect(conn_info.get_uri())
    cur = conn.cursor()

    # Get exchange groups
    cur.execute("""
        SET search_path TO financial_screener;
        SELECT * FROM get_exchange_groups();
    """)
    groups = cur.fetchall()

    # Get config for each group
    configs = {}
    for group in groups:
        cur.execute("""
            SET search_path TO financial_screener;
            SELECT * FROM get_dag_config(%s, %s);
        """, ('data_collection_equities', group[0]))
        config = cur.fetchone()
        configs[group[0]] = {
            'cpu_request': config[0],
            'cpu_limit': config[1],
            'memory_request': config[2],
            'memory_limit': config[3],
            'batch_size': config[4],
            'timeout_seconds': config[5]
        }

    conn.close()

    # Push to XCom
    context['ti'].xcom_push(key='dag_config', value=configs)
    context['ti'].xcom_push(key='exchange_groups', value=groups)
```

#### 3. Refactor Indicators DAG

**File**: `airflow/dags/indicators/dag_calculate_indicators.py`

**Changes Needed:**

1. **Add Configuration Task** (same as data collection)

2. **Update kubectl Command**
   - Read resource limits from configuration
   - Read batch size from configuration
   - Use configuration timeout

**Current hardcoded values to replace:**
```python
--requests="cpu=1000m,memory=2Gi"
--limits="cpu=4000m,memory=4Gi"
--batch-size 1000
--timeout=3600s
```

**New approach:**
```python
--requests="cpu={{{{ ti.xcom_pull(task_ids='get_config', key='cpu_request') }}}},memory={{{{ ti.xcom_pull(task_ids='get_config', key='memory_request') }}}}"
--limits="cpu={{{{ ti.xcom_pull(task_ids='get_config', key='cpu_limit') }}}},memory={{{{ ti.xcom_pull(task_ids='get_config', key='memory_limit') }}}}"
--batch-size {{{{ ti.xcom_pull(task_ids='get_config', key='batch_size') }}}}
```

---

## 🧪 Phase 3: Testing (PENDING)

### Test Plan

1. **Configuration Retrieval Tests**
   ```sql
   -- Test getting config for each DAG job
   SELECT * FROM get_dag_config('data_collection_equities', 'us_markets');
   SELECT * FROM get_dag_config('historical_load_equities', 'lse');
   SELECT * FROM get_dag_config('calculate_indicators', 'all');

   -- Test exchange groups
   SELECT * FROM get_exchange_groups();

   -- Test configuration updates
   SELECT update_dag_config('data_collection_equities', 'us_markets', p_cpu_limit => '3000m');
   SELECT * FROM dag_configuration_audit;
   ```

2. **DAG Execution Tests**
   - Trigger `data_collection_equities` DAG
   - Verify configuration loaded from database
   - Verify pods created with correct resources
   - Verify indicators DAG triggered

3. **Historical Load DAG Tests**
   - Trigger `historical_load_equities` DAG
   - Verify BashOperator works correctly
   - Verify XCom date ranges passed correctly
   - Verify indicators triggered after completion

4. **Configuration Change Tests**
   - Update resource limits via `update_dag_config()`
   - Trigger DAG
   - Verify new limits applied
   - Check audit trail

---

## 📚 Phase 4: Documentation (PENDING)

### Documents to Create

1. **DAG Configuration Guide** (`docs/DAG_CONFIGURATION.md`)
   - How to view current configuration
   - How to update configuration
   - Configuration best practices
   - Resource tuning guidelines

2. **Exchange Group Management** (`docs/EXCHANGE_GROUPS.md`)
   - How to add new exchanges
   - How to modify groupings
   - Priority system explanation

3. **Migration Guide** (`docs/DAG_MIGRATION_GUIDE.md`)
   - Changes made in migration 008
   - How to rollback if needed
   - Troubleshooting guide

4. **Operations Runbook** (`docs/DAG_OPERATIONS.md`)
   - Common configuration tasks
   - Emergency procedures
   - Performance tuning
   - Monitoring and alerts

---

## 🎯 Benefits of This Refactoring

### Before (Hardcoded)
```python
# Had to modify code to change resources
container_resources=k8s.V1ResourceRequirements(
    requests={"cpu": "500m", "memory": "1Gi"},
    limits={"cpu": "2000m", "memory": "2Gi"}
)

# Had to modify code to change batch size
'--batch-size', '500',

# Had to modify code to add/change exchanges
exchanges='NYSE,NASDAQ'
```

### After (Configuration-Driven)
```sql
-- Change resources without code changes
SELECT update_dag_config(
    'data_collection_equities',
    'us_markets',
    p_cpu_limit => '3000m',
    p_memory_limit => '4Gi',
    p_batch_size => 750
);

-- Add new exchange group
INSERT INTO exchange_groups (group_name, display_name, exchanges, priority)
VALUES ('asian_markets', 'Asian Markets', ARRAY['TSE', 'HKEX'], 6);

-- Disable a job temporarily
UPDATE dag_configuration
SET enabled = FALSE
WHERE dag_name = 'historical_load_equities' AND job_name = 'european_markets';
```

### Key Improvements

1. **No Code Changes Needed**
   - Tune resources via SQL
   - Adjust batch sizes dynamically
   - Add/remove markets easily

2. **Audit Trail**
   - All changes logged
   - Who changed what, when
   - Rollback capability

3. **Consistency**
   - All 3 DAGs use same pattern
   - Single source of truth
   - Easier maintenance

4. **ARM64 Compatibility**
   - All DAGs use BashOperator
   - No KubernetesPodOperator issues
   - Proven reliability

5. **Better Pipeline Integration**
   - Historical load triggers indicators
   - Complete end-to-end flow
   - No manual intervention needed

---

## 📊 Configuration Schema Reference

### dag_configuration Table

| Column | Type | Description |
|--------|------|-------------|
| dag_name | VARCHAR(100) | Airflow DAG ID |
| job_name | VARCHAR(100) | Specific job within DAG |
| cpu_request | VARCHAR(20) | CPU request (e.g., '500m', '2') |
| cpu_limit | VARCHAR(20) | CPU limit |
| memory_request | VARCHAR(20) | Memory request (e.g., '1Gi') |
| memory_limit | VARCHAR(20) | Memory limit |
| batch_size | INTEGER | Assets per batch |
| timeout_seconds | INTEGER | Pod completion timeout |
| max_retries | INTEGER | Airflow task retries |
| retry_delay_minutes | INTEGER | Initial retry delay |
| enabled | BOOLEAN | Enable/disable job |
| priority | INTEGER | Job priority (1-10) |

### exchange_groups Table

| Column | Type | Description |
|--------|------|-------------|
| group_name | VARCHAR(50) | Group identifier |
| display_name | VARCHAR(100) | Human-readable name |
| exchanges | TEXT[] | Array of exchange codes |
| primary_timezone | VARCHAR(50) | Market timezone |
| enabled | BOOLEAN | Enable/disable group |
| priority | INTEGER | Processing priority |

---

## 🚀 Next Steps

To complete this refactoring:

1. **Immediate**: Migrate historical load DAG to BashOperator
2. **Next**: Refactor data collection DAG to read from configuration
3. **Then**: Refactor indicators DAG to read from configuration
4. **Finally**: Test all DAGs with configuration changes
5. **Last**: Create comprehensive documentation

---

## 🔧 Quick Reference Commands

### View Current Configuration
```sql
SET search_path TO financial_screener;

-- All configurations
SELECT * FROM dag_configuration ORDER BY dag_name, priority DESC;

-- Specific DAG config
SELECT * FROM get_dag_config('data_collection_equities', 'us_markets');

-- All exchange groups
SELECT * FROM get_exchange_groups();

-- Audit history
SELECT * FROM dag_configuration_audit ORDER BY changed_at DESC LIMIT 10;
```

### Update Configuration
```sql
SET search_path TO financial_screener;

-- Update resources
SELECT update_dag_config(
    'data_collection_equities',
    'us_markets',
    p_cpu_request => '1000m',
    p_cpu_limit => '3000m',
    p_memory_request => '2Gi',
    p_memory_limit => '4Gi',
    p_updated_by => 'admin'
);

-- Update batch size
SELECT update_dag_config(
    'calculate_indicators',
    'all',
    p_batch_size => 1500,
    p_timeout_seconds => 4800,
    p_updated_by => 'admin'
);

-- Disable a job
UPDATE dag_configuration
SET enabled = FALSE, updated_at = NOW()
WHERE dag_name = 'historical_load_equities' AND job_name = 'european_markets';
```

---

## ✅ Completion Checklist

- [x] Create database migration
- [x] Apply migration to cluster
- [x] Verify configuration retrieval
- [ ] Migrate historical load DAG
- [ ] Add indicators trigger to historical load
- [ ] Refactor data collection DAG
- [ ] Refactor indicators DAG
- [ ] Test configuration changes
- [ ] Test all DAGs end-to-end
- [ ] Create configuration guide
- [ ] Create operations runbook
- [ ] Update README with configuration info

---

**Last Updated**: 2025-10-28
**Status**: Phase 1 Complete, Phase 2 Ready to Begin
