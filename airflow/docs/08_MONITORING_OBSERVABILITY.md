# Monitoring & Observability

## Table of Contents
1. [Monitoring Overview](#monitoring-overview)
2. [SQL Monitoring Queries](#sql-monitoring-queries)
3. [Airflow UI Monitoring](#airflow-ui-monitoring)
4. [Kubernetes Monitoring](#kubernetes-monitoring)
5. [Alerting](#alerting)
6. [Performance Metrics](#performance-metrics)

---

## Monitoring Overview

The metadata-driven architecture provides complete visibility into:
- **Process execution** - Every DAG run tracked
- **Data quality** - Missing data, failed tickers
- **API usage** - Real-time quota tracking
- **System health** - Resource usage, job duration

### Monitoring Sources

```
┌─────────────────────────────────────────────────────┐
│ Monitoring Data Sources                             │
├─────────────────────────────────────────────────────┤
│                                                      │
│  1. Metadata Tables (PostgreSQL)                    │
│     - process_executions                            │
│     - asset_processing_state                        │
│     - asset_processing_details                      │
│                                                      │
│  2. Airflow Metadata Database                       │
│     - dag_run                                        │
│     - task_instance                                 │
│     - job                                           │
│                                                      │
│  3. Kubernetes Metrics                              │
│     - Pod resource usage                            │
│     - Job completion status                         │
│                                                      │
│  4. Application Logs                                │
│     - Structured logging (JSON)                     │
│     - Error traces                                  │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## SQL Monitoring Queries

### Daily Health Check

Run this query each morning to verify system health:

```sql
SET search_path TO financial_screener;

-- 1. Processing Progress
SELECT * FROM get_processing_progress();

-- 2. Yesterday's Execution Summary
SELECT
    process_name,
    status,
    assets_processed,
    assets_succeeded,
    assets_failed,
    api_calls_used,
    duration_seconds,
    started_at
FROM process_executions
WHERE DATE(started_at) = CURRENT_DATE - 1
ORDER BY started_at DESC;

-- 3. Failed Tickers (need attention)
SELECT
    ticker,
    consecutive_failures,
    last_error_message,
    last_error_at
FROM asset_processing_state
WHERE consecutive_failures >= 3
ORDER BY consecutive_failures DESC
LIMIT 20;

-- 4. API Usage Trend (last 7 days)
SELECT
    DATE(created_at) as date,
    SUM(api_calls_used) as total_api_calls,
    COUNT(DISTINCT ticker) as unique_tickers
FROM asset_processing_details
WHERE created_at > CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### Real-Time Monitoring (During DAG Runs)

```sql
SET search_path TO financial_screener;

-- Current execution status
SELECT
    execution_id,
    status,
    assets_processed,
    assets_succeeded,
    assets_failed,
    started_at,
    EXTRACT(EPOCH FROM (NOW() - started_at))/60 as running_minutes
FROM process_executions
WHERE status = 'running'
ORDER BY started_at DESC;

-- Today's progress (refreshes in real-time)
SELECT
    operation,
    status,
    COUNT(*) as count,
    SUM(api_calls_used) as api_calls,
    ROUND(AVG(duration_ms)::numeric, 0) as avg_duration_ms,
    MIN(started_at) as first_started,
    MAX(completed_at) as last_completed
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE
GROUP BY operation, status
ORDER BY operation, status;

-- Processing rate (tickers per minute)
SELECT
    DATE_TRUNC('minute', created_at) as minute,
    COUNT(*) as tickers_processed,
    COUNT(*) FILTER (WHERE status = 'success') as succeeded,
    COUNT(*) FILTER (WHERE status = 'failed') as failed
FROM asset_processing_details
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY DATE_TRUNC('minute', created_at)
ORDER BY minute DESC
LIMIT 10;
```

### Data Quality Checks

```sql
SET search_path TO financial_screener;

-- 1. Tickers with missing recent prices
SELECT
    a.ticker,
    a.exchange,
    aps.prices_last_date,
    CURRENT_DATE - aps.prices_last_date as days_stale
FROM assets a
JOIN asset_processing_state aps ON a.ticker = aps.ticker
WHERE aps.prices_last_date < CURRENT_DATE - 3
ORDER BY days_stale DESC
LIMIT 50;

-- 2. Tickers with missing indicators
SELECT
    a.ticker,
    a.exchange,
    aps.prices_last_date,
    aps.indicators_calculated_at,
    CASE
        WHEN aps.indicators_calculated_at IS NULL THEN 'Never calculated'
        ELSE CURRENT_DATE - DATE(aps.indicators_calculated_at) || ' days old'
    END as indicator_age
FROM assets a
JOIN asset_processing_state aps ON a.ticker = aps.ticker
WHERE aps.indicators_calculated = FALSE
   OR aps.indicators_calculated_at < CURRENT_DATE - 1
ORDER BY a.ticker
LIMIT 50;

-- 3. Price data gaps (missing dates)
WITH price_counts AS (
    SELECT
        a.ticker,
        COUNT(*) as price_count,
        MIN(sp.date) as first_date,
        MAX(sp.date) as last_date,
        MAX(sp.date) - MIN(sp.date) as date_range_days
    FROM assets a
    JOIN stock_prices sp ON a.id = sp.asset_id
    GROUP BY a.ticker
)
SELECT
    ticker,
    price_count,
    first_date,
    last_date,
    date_range_days,
    date_range_days - price_count as missing_days,
    ROUND(100.0 * price_count / NULLIF(date_range_days, 0), 2) as coverage_pct
FROM price_counts
WHERE date_range_days > 0
  AND (date_range_days - price_count) > 10  -- More than 10 missing days
ORDER BY missing_days DESC
LIMIT 20;
```

### Performance Analysis

```sql
SET search_path TO financial_screener;

-- 1. Slowest operations (identify bottlenecks)
SELECT
    operation,
    ticker,
    duration_ms,
    started_at,
    error_message
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE
  AND duration_ms > 10000  -- Slower than 10 seconds
ORDER BY duration_ms DESC
LIMIT 20;

-- 2. Execution duration trends
SELECT
    process_name,
    DATE(started_at) as date,
    AVG(duration_seconds) as avg_duration,
    MIN(duration_seconds) as min_duration,
    MAX(duration_seconds) as max_duration,
    COUNT(*) as runs
FROM process_executions
WHERE started_at > CURRENT_DATE - INTERVAL '30 days'
GROUP BY process_name, DATE(started_at)
ORDER BY date DESC, process_name;

-- 3. API call efficiency
SELECT
    operation,
    COUNT(*) as total_operations,
    SUM(api_calls_used) as total_api_calls,
    ROUND(AVG(api_calls_used)::numeric, 2) as avg_calls_per_operation,
    ROUND(AVG(duration_ms)::numeric, 0) as avg_duration_ms,
    ROUND(SUM(api_calls_used)::numeric / (SUM(duration_ms)/1000.0), 2) as calls_per_second
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE
  AND api_calls_used > 0
GROUP BY operation;
```

---

## Airflow UI Monitoring

### Accessing Airflow UI

**URL:** https://airflow.stratdata.org

### Key Views

**1. DAGs View**
- Shows all DAGs with recent run status
- Green = Success, Red = Failed, Yellow = Running
- Check: `data_collection_equities` should run daily at 21:30 UTC

**2. DAG Run Timeline**
- Visual timeline of all DAG runs
- Quickly spot failures or long-running tasks
- Filter by date range

**3. Task Duration Graph**
- Shows task execution time trends
- Identify slowdowns over time
- Compare across DAG runs

**4. Task Logs**
- Click any task → View Logs
- Shows stdout/stderr from K8s pods
- Filter by log level

### Useful Airflow CLI Commands

```bash
# List recent DAG runs
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list-runs -d data_collection_equities --state failed

# Get task instance details
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow tasks state data_collection_equities process_us_markets 2025-10-21

# View task logs
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow tasks logs data_collection_equities discover_delta 2025-10-21

# List all running tasks
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow tasks states-for-dag-run data_collection_equities manual__2025-10-21T21:30:00
```

---

## Kubernetes Monitoring

### Pod Resource Usage

```bash
# Current pod resource usage
kubectl top pods -n financial-screener

# Detailed pod metrics
kubectl describe pod -n financial-screener <pod-name> | grep -A5 "Requests:"

# Watch pods in real-time
watch kubectl get pods -n financial-screener -o wide
```

### Job Monitoring

```bash
# List recent jobs
kubectl get jobs -n financial-screener --sort-by=.metadata.creationTimestamp

# Job completion status
kubectl get jobs -n financial-screener -o wide

# Failed pods (for debugging)
kubectl get pods -n financial-screener --field-selector status.phase=Failed

# Pod events (errors, warnings)
kubectl get events -n financial-screener --sort-by='.lastTimestamp' | tail -20
```

### Cluster Health

```bash
# Node resource usage
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl top nodes"

# Cluster capacity
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl describe nodes | grep -A5 'Allocated resources'"

# Pod distribution across nodes
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl get pods -n financial-screener -o wide"
```

---

## Alerting

### Critical Alerts (Manual Monitoring)

**1. DAG Failure**
```sql
-- Check for failed DAG runs in last 24 hours
SELECT
    process_name,
    execution_id,
    error_message,
    started_at
FROM process_executions
WHERE status = 'failed'
  AND started_at > NOW() - INTERVAL '24 hours';
```

**Action:** Review error_message, check Airflow logs, re-run DAG if transient

**2. High Failure Rate**
```sql
-- Check if >10% of tickers failed today
SELECT
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'failed') / COUNT(*), 2) as failure_rate_pct,
    COUNT(*) FILTER (WHERE status = 'failed') as failed_count,
    COUNT(*) as total_count
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE;
```

**Action:** Investigate common error patterns, check API status

**3. API Quota Exceeded**
```sql
-- Check today's API usage
SELECT SUM(api_calls_used) as total_calls
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE;
```

**Action:** If > 95K calls, pause DAG, adjust batch sizes

**4. Stale Data**
```sql
-- Check for tickers with >3 day old prices
SELECT COUNT(*)
FROM asset_processing_state
WHERE prices_last_date < CURRENT_DATE - 3;
```

**Action:** Investigate failed tickers, manually trigger reprocessing

### Automated Alerting (Future)

**Email Alerts:**
```python
# In DAG default_args:
default_args = {
    'email': ['team@example.com'],
    'email_on_failure': True,
    'email_on_retry': False,
}
```

**Slack Alerts:**
```python
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator

send_alert = SlackWebhookOperator(
    task_id='send_slack_alert',
    http_conn_id='slack_webhook',
    message='DAG failed: {{ dag.dag_id }}',
    trigger_rule='one_failed',
)
```

---

## Performance Metrics

### Key Metrics to Track

**1. Processing Throughput**
- **Metric:** Tickers processed per minute
- **Target:** > 5 tickers/minute (steady state)
- **Query:**
  ```sql
  SELECT
      COUNT(*) as tickers,
      EXTRACT(EPOCH FROM (MAX(completed_at) - MIN(started_at)))/60 as duration_minutes,
      ROUND(COUNT(*) / (EXTRACT(EPOCH FROM (MAX(completed_at) - MIN(started_at)))/60), 2) as tickers_per_minute
  FROM asset_processing_details
  WHERE DATE(created_at) = CURRENT_DATE
    AND status = 'success';
  ```

**2. API Efficiency**
- **Metric:** API calls per day
- **Target:** < 90K calls/day (stay within limit)
- **Budget:** 21,817 tickers × 1 call = 21,817 (steady state)

**3. Success Rate**
- **Metric:** Percentage of successful operations
- **Target:** > 95%
- **Query:**
  ```sql
  SELECT
      ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'success') / COUNT(*), 2) as success_rate
  FROM asset_processing_details
  WHERE DATE(created_at) = CURRENT_DATE;
  ```

**4. Data Freshness**
- **Metric:** Percentage of tickers with current data
- **Target:** > 99%
- **Query:**
  ```sql
  SELECT
      COUNT(*) FILTER (WHERE prices_last_date >= CURRENT_DATE - 1) as current,
      COUNT(*) as total,
      ROUND(100.0 * COUNT(*) FILTER (WHERE prices_last_date >= CURRENT_DATE - 1) / COUNT(*), 2) as freshness_pct
  FROM asset_processing_state;
  ```

### Dashboard Template (Manual)

Create a daily monitoring spreadsheet:

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Tickers Processed | 21,750 | 21,817 | ✅ 99.7% |
| API Calls Used | 22,105 | < 90K | ✅ 24.6% |
| Success Rate | 98.2% | > 95% | ✅ |
| Failed Tickers | 67 | < 100 | ✅ |
| Avg Duration | 145 min | < 180 min | ✅ |
| Data Freshness | 99.8% | > 99% | ✅ |

---

## Monitoring Best Practices

### Daily Routine

**Morning Check (5 minutes):**
1. Run daily health check query
2. Check Airflow UI for failed runs
3. Review failed tickers (>3 failures)
4. Verify API usage within limits

**Weekly Review (30 minutes):**
1. Analyze processing trends (duration, failures)
2. Review data quality metrics
3. Check cluster resource usage
4. Update documentation if needed

### Proactive Monitoring

```sql
-- Create view for daily dashboard
CREATE VIEW v_daily_monitoring AS
SELECT
    CURRENT_DATE as date,
    (SELECT COUNT(*) FROM asset_processing_state WHERE prices_last_date >= CURRENT_DATE - 1) as tickers_current,
    (SELECT SUM(api_calls_used) FROM asset_processing_details WHERE DATE(created_at) = CURRENT_DATE) as api_calls_today,
    (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'success') / COUNT(*), 2)
     FROM asset_processing_details WHERE DATE(created_at) = CURRENT_DATE) as success_rate_pct,
    (SELECT COUNT(*) FROM asset_processing_state WHERE consecutive_failures >= 3) as chronic_failures,
    (SELECT MAX(duration_seconds) FROM process_executions WHERE DATE(started_at) = CURRENT_DATE) as longest_run_seconds;

-- Query daily
SELECT * FROM v_daily_monitoring;
```

---

## Next Steps

- [09_TROUBLESHOOTING.md](./09_TROUBLESHOOTING.md) - Common issues and solutions
- [README.md](../README.md) - Project overview

---

**Document Version:** 1.0
**Last Updated:** 2025-10-21
**Author:** Financial Screener Team
**Status:** Production Ready
