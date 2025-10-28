# Troubleshooting Guide

## Table of Contents
1. [Common Issues](#common-issues)
2. [Diagnostic Commands](#diagnostic-commands)
3. [Recovery Procedures](#recovery-procedures)
4. [FAQ](#faq)

---

## Common Issues

### Issue 1: DAG Not Running on Schedule

**Symptoms:**
- DAG shows as active but doesn't trigger at scheduled time
- Manual triggers work, but scheduled runs don't appear

**Diagnosis:**
```bash
# Check if DAG is paused
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list | grep data_collection_equities

# Check scheduler logs
kubectl logs -n airflow -l app.kubernetes.io/component=scheduler -c scheduler --tail=50
```

**Causes & Solutions:**

1. **DAG is paused**
   ```bash
   # Unpause DAG
   kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
     airflow dags unpause data_collection_equities
   ```

2. **Schedule timezone mismatch**
   - Check: DAG uses UTC (`schedule_interval='30 21 * * *'` = 21:30 UTC)
   - Verify current UTC time: `date -u`

3. **Catchup is disabled preventing backfill**
   - This is intentional (`catchup=False`)
   - Manual trigger needed for missed runs

4. **max_active_runs=1 blocking**
   - If previous run still active, new run won't start
   - Check running DAGs:
     ```bash
     kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
       airflow dags list-runs -d data_collection_equities --state running
     ```

---

### Issue 2: Kubernetes Job Fails Immediately

**Symptoms:**
- Airflow task "process_us_markets" fails
- K8s pod shows `Error` or `CrashLoopBackOff`

**Diagnosis:**
```bash
# Get recent pods
kubectl get pods -n financial-screener --sort-by=.metadata.creationTimestamp | tail -5

# Check pod status
kubectl describe pod -n financial-screener <pod-name>

# View logs
kubectl logs -n financial-screener <pod-name>
```

**Common Causes:**

**1. Image Pull Error**
```
Error: ErrImagePull or ImagePullBackOff
```

**Solution:**
```bash
# Verify image exists on node
ssh -i ~/.ssh/pi_cluster admin@192.168.1.241 "sudo ctr -n k8s.io images ls | grep data-collector"

# Rebuild and distribute
cd /root/gitlab/financial-screener
./scripts/build-and-distribute-data-collector.sh
```

**2. Secret Not Found**
```
Error: secret "postgres-secret" not found
```

**Solution:**
```bash
# Check secret exists
kubectl get secret postgres-secret -n financial-screener

# Create if missing
kubectl create secret generic postgres-secret -n financial-screener \
  --from-literal=DATABASE_URL='postgresql://appuser:AppUser123@postgresql-primary.databases.svc.cluster.local:5432/appdb'
```

**3. Python Import Error**
```
ModuleNotFoundError: No module named 'metadata_logger'
```

**Solution:**
- Rebuild Docker image (metadata_logger.py missing)
- Verify PYTHONPATH in Dockerfile: `ENV PYTHONPATH=/app/src:/app`

**4. Database Connection Error**
```
asyncpg.exceptions.ConnectionDoesNotExistError
```

**Solution:**
```bash
# Test database connectivity from pod
kubectl run -it --rm debug --image=postgres:16 --restart=Never -n financial-screener -- \
  psql postgresql://appuser:AppUser123@postgresql-primary.databases.svc.cluster.local:5432/appdb -c "SELECT 1;"

# Check PostgreSQL pod
kubectl get pods -n databases | grep postgresql
```

---

### Issue 3: Metadata Tables Not Updating

**Symptoms:**
- DAG runs successfully
- `process_executions` table empty
- No records in `asset_processing_details`

**Diagnosis:**
```sql
SET search_path TO financial_screener;

-- Check if tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'financial_screener'
  AND table_name LIKE '%process%';

-- Check recent inserts
SELECT COUNT(*), MAX(created_at)
FROM asset_processing_details;
```

**Causes & Solutions:**

**1. Execution ID not passed to jobs**

Check K8s Job manifest:
```bash
kubectl get job -n financial-screener -o yaml | grep execution-id
```

Expected: `--execution-id {{ run_id }}`

**2. DATABASE_URL points to wrong schema**

Verify search_path:
```bash
kubectl logs -n financial-screener <pod-name> | grep "SET search_path"
```

Expected: `SET search_path TO financial_screener`

**3. Permissions issue**

```sql
-- Check if appuser can insert
SET search_path TO financial_screener;
INSERT INTO process_executions (process_name, execution_id, parameters, status)
VALUES ('test', 'test_123', '{}', 'running');
```

---

### Issue 4: High API Usage / Quota Exceeded

**Symptoms:**
- Error: "API quota exceeded"
- DAG task `check_api_quota` fails
- EODHD API returns 429 Too Many Requests

**Diagnosis:**
```sql
-- Check today's API usage
SELECT
    SUM(api_calls_used) as total_calls,
    COUNT(*) as operations
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE;

-- Usage by operation
SELECT
    operation,
    COUNT(*) as ops,
    SUM(api_calls_used) as calls
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE
GROUP BY operation;
```

**Solutions:**

**1. Reduce batch size (temporary)**
```bash
# Set Airflow variable
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow variables set max_new_assets_per_day 5000
```

**2. Pause DAG until quota resets**
```bash
# Pause DAG
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags pause data_collection_equities

# Resume after midnight UTC
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags unpause data_collection_equities
```

**3. Identify rogue processes**
```sql
-- Check for duplicate operations
SELECT
    ticker,
    operation,
    COUNT(*) as times_processed,
    SUM(api_calls_used) as total_calls
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE
GROUP BY ticker, operation
HAVING COUNT(*) > 1
ORDER BY total_calls DESC;
```

---

### Issue 5: Data Not Up-to-Date

**Symptoms:**
- Prices last updated several days ago
- `prices_last_date` is old
- Indicators not calculated

**Diagnosis:**
```sql
SET search_path TO financial_screener;

-- Check data freshness
SELECT
    COUNT(*) as total_tickers,
    COUNT(*) FILTER (WHERE prices_last_date >= CURRENT_DATE - 1) as current,
    COUNT(*) FILTER (WHERE prices_last_date < CURRENT_DATE - 3) as stale
FROM asset_processing_state;

-- Find specific stale tickers
SELECT
    ticker,
    prices_last_date,
    CURRENT_DATE - prices_last_date as days_old,
    consecutive_failures,
    last_error_message
FROM asset_processing_state
WHERE prices_last_date < CURRENT_DATE - 2
ORDER BY days_old DESC
LIMIT 20;
```

**Solutions:**

**1. Manual reprocessing**
```sql
-- Mark ticker for reprocessing
SELECT reset_ticker_for_reprocessing('AAPL', 'prices');

-- Or mark all stale tickers
UPDATE asset_processing_state
SET needs_prices_reprocess = TRUE
WHERE prices_last_date < CURRENT_DATE - 3;
```

**2. Trigger DAG manually**
```bash
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger data_collection_equities
```

**3. Check for chronic failures**
```sql
-- Tickers failing repeatedly
SELECT
    ticker,
    consecutive_failures,
    last_error_message,
    last_error_at
FROM asset_processing_state
WHERE consecutive_failures >= 5
ORDER BY consecutive_failures DESC;
```

**Action:** Investigate error messages, may need ticker symbol correction

---

## Diagnostic Commands

### Full System Health Check

Run this comprehensive health check:

```bash
#!/bin/bash
echo "=== Airflow Health ==="
kubectl get pods -n airflow

echo -e "\n=== DAG Status ==="
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list | grep -E "data_collection|calculate_indicators"

echo -e "\n=== Recent DAG Runs ==="
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list-runs -d data_collection_equities --limit 5

echo -e "\n=== Active Jobs ==="
kubectl get jobs -n financial-screener

echo -e "\n=== Recent Pods ==="
kubectl get pods -n financial-screener --sort-by=.metadata.creationTimestamp | tail -5

echo -e "\n=== Database Metadata ==="
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT * FROM get_processing_progress();\""

echo -e "\n=== Today's API Usage ==="
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT SUM(api_calls_used) as api_calls FROM asset_processing_details WHERE DATE(created_at) = CURRENT_DATE;\""
```

Save as `/root/gitlab/financial-screener/scripts/health-check.sh` and run:
```bash
chmod +x scripts/health-check.sh
./scripts/health-check.sh
```

---

## Recovery Procedures

### Recover from Failed DAG Run

**Scenario:** DAG run failed mid-execution, some tickers processed, some not

**Steps:**

1. **Check what was processed**
   ```sql
   SELECT
       COUNT(*) FILTER (WHERE status = 'success') as succeeded,
       COUNT(*) FILTER (WHERE status = 'failed') as failed,
       COUNT(*) FILTER (WHERE status = 'skipped') as skipped
   FROM asset_processing_details
   WHERE execution_id = '<failed-run-id>';
   ```

2. **Clear failed execution** (optional)
   ```bash
   # Mark as failed in Airflow
   kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
     airflow dags state data_collection_equities <execution_date>
   ```

3. **Retry failed run**
   ```bash
   # Option A: Clear and retry
   kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
     airflow tasks clear data_collection_equities --start-date <date> --end-date <date>

   # Option B: New manual trigger (recommended)
   kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
     airflow dags trigger data_collection_equities
   ```

4. **Verify idempotency**
   - Successful tickers will be skipped (--skip-existing)
   - Only failed/missing tickers will be reprocessed

---

### Reset Ticker State

**Scenario:** Ticker has bad data, needs complete reload

```sql
-- Option 1: Reset specific ticker
UPDATE asset_processing_state
SET fundamentals_loaded = FALSE,
    prices_loaded = FALSE,
    prices_first_date = NULL,
    prices_last_date = NULL,
    indicators_calculated = FALSE,
    consecutive_failures = 0,
    needs_fundamentals_reprocess = TRUE
WHERE ticker = 'AAPL';

-- Option 2: Use helper function
SELECT reset_ticker_for_reprocessing('AAPL', 'all');

-- Option 3: Delete and reload
DELETE FROM assets WHERE ticker = 'AAPL';
DELETE FROM asset_processing_state WHERE ticker = 'AAPL';
-- Next DAG run will reload as new ticker
```

---

### Clean Up Old Metadata

**Scenario:** Metadata tables growing too large

```sql
-- Delete old execution records (keep 90 days)
DELETE FROM process_executions
WHERE started_at < CURRENT_DATE - INTERVAL '90 days';

-- Delete old processing details (keep 30 days)
DELETE FROM asset_processing_details
WHERE created_at < CURRENT_DATE - INTERVAL '30 days';

-- Vacuum tables
VACUUM ANALYZE process_executions;
VACUUM ANALYZE asset_processing_details;
```

**Add to monthly maintenance:**
```bash
# Schedule with cron or Airflow maintenance DAG
0 0 1 * * /path/to/cleanup-metadata.sh
```

---

## FAQ

### Q1: Can I run the DAG more frequently than daily?

**A:** Yes, but consider API limits:
- Daily schedule uses ~22K API calls/day
- Hourly would use ~22K × 24 = 528K calls/day (exceeds limit)
- Recommendation: Keep daily schedule, use manual triggers for ad-hoc updates

### Q2: How do I process a specific ticker immediately?

**A:** Two options:

**Option 1: Mark for reprocessing (picked up next DAG run)**
```sql
SELECT reset_ticker_for_reprocessing('AAPL', 'all');
```

**Option 2: Manual run (immediate)**
```bash
# SSH to a worker node
ssh -i ~/.ssh/pi_cluster admin@192.168.1.241

# Run directly
kubectl run -it --rm manual-fetch \
  --image=registry.stratdata.org/data-collector:latest \
  --restart=Never \
  -n financial-screener \
  -- python /app/src/main_enhanced.py --mode bulk --tickers AAPL
```

### Q3: What happens if the cluster reboots during a DAG run?

**A:** System is resilient:
1. Airflow scheduler restarts automatically
2. Running K8s Jobs are terminated
3. Airflow marks tasks as failed
4. Next scheduled run processes missing tickers
5. Metadata prevents duplicates

**Manual recovery:** Trigger DAG manually after reboot

### Q4: Can I disable certain exchanges?

**A:** Yes, comment out tasks in DAG:

```python
# In dag_data_collection_equities.py
# quota_check_task >> [
#     us_markets_job,
#     lse_job,
#     # german_markets_job,  # DISABLED
#     european_markets_job
# ]
```

### Q5: How do I add a new exchange?

**A:**
1. Add ticker file: `config/tickers/new_exchange.txt`
2. Add K8s Job task in DAG:
   ```python
   new_exchange_job = KubernetesPodOperator(
       task_id='process_new_exchange',
       arguments=['--exchanges', 'NEW_EXCHANGE', ...],
       ...
   )
   ```
3. Update dependencies: `quota_check_task >> new_exchange_job`

### Q6: Why are some tickers always failing?

**Common reasons:**
- Ticker delisted (404 from API)
- Symbol changed (needs mapping)
- Data not available from EODHD
- Typo in ticker file

**Check:**
```sql
SELECT ticker, last_error_message
FROM asset_processing_state
WHERE consecutive_failures >= 5;
```

**Solutions:**
- Remove from ticker file if delisted
- Update ticker symbol if changed
- Accept limitation if data unavailable

---

## Emergency Contacts

**Critical Issues:**
1. Check documentation: `/root/gitlab/financial-screener/airflow/docs/`
2. Review logs: Airflow UI, kubectl logs
3. Check metadata: SQL queries in docs
4. Escalate if unresolved

**Useful Links:**
- Airflow UI: https://airflow.stratdata.org
- Airflow Docs: https://airflow.apache.org/docs/
- Project Docs: `/root/gitlab/financial-screener/airflow/`

---

**Document Version:** 1.0
**Last Updated:** 2025-10-21
**Author:** Financial Screener Team
**Status:** Production Ready
