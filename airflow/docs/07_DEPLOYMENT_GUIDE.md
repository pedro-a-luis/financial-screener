# Deployment Guide

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Deployment Steps](#deployment-steps)
3. [Configuration](#configuration)
4. [Testing](#testing)
5. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### 1. Infrastructure Ready
✅ **PostgreSQL with metadata tables deployed**
```bash
# Verify metadata tables exist
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT table_name FROM information_schema.tables
   WHERE table_schema = 'financial_screener'
     AND table_name IN ('process_executions', 'asset_processing_state', 'asset_processing_details');\""

# Expected output: 3 tables
```

✅ **Airflow deployed and running**
```bash
# Check Airflow pods
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl get pods -n airflow"

# Expected: scheduler, webserver, triggerer all Running
```

✅ **Secrets exist**
```bash
# Verify secrets
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl get secrets -n financial-screener postgres-secret data-api-secrets"

# Expected: Both secrets exist
```

---

## Deployment Steps

### Step 1: Rebuild Data Collector Image

The data-collector image needs to include the new `metadata_logger.py` and modified `main_enhanced.py`.

```bash
cd /root/gitlab/financial-screener

# Build Docker image (ARM64)
./scripts/build-and-distribute-data-collector.sh
```

**What this does:**
1. Builds `registry.stratdata.org/data-collector:latest` with:
   - Updated `main_enhanced.py` (metadata logging)
   - New `metadata_logger.py`
   - New arguments: `--execution-id`, `--exchanges`, `--skip-existing`
2. Distributes to all 8 cluster nodes

**Expected output:**
```
✓ Image built: registry.stratdata.org/data-collector:latest
✓ Pushed to nodes: 192.168.1.240-247
✓ All nodes ready
```

### Step 2: Build Technical Analyzer Image

Create Dockerfile for technical-analyzer if it doesn't exist:

```bash
# Check if Dockerfile exists
ls -la services/technical-analyzer/Dockerfile

# If missing, create it:
cat > services/technical-analyzer/Dockerfile <<'EOF'
FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies for pandas
RUN apt-get update && apt-get install -y \
    gcc g++ gfortran \
    libopenblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/technical-analyzer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/technical-analyzer/src/ /app/src/

ENV PYTHONPATH=/app

CMD ["python", "/app/src/main_indicators.py", "--help"]
EOF

# Build and distribute
docker build -t registry.stratdata.org/technical-analyzer:latest \
  -f services/technical-analyzer/Dockerfile .

# Distribute to cluster nodes
for NODE in 192.168.1.{240..247}; do
  echo "Distributing to $NODE..."
  docker save registry.stratdata.org/technical-analyzer:latest | \
    ssh -i ~/.ssh/pi_cluster admin@$NODE \
    "sudo ctr -n k8s.io images import -"
done
```

### Step 3: Deploy DAGs to Airflow

**Option A: Direct ConfigMap (Quick Start)**

```bash
# Create ConfigMap with DAG files
kubectl create configmap airflow-dags \
  --from-file=airflow/dags/ \
  --namespace=airflow \
  --dry-run=client -o yaml | kubectl apply -f -

# Mount ConfigMap to scheduler
kubectl patch statefulset airflow-scheduler -n airflow --type='json' -p='[
  {
    "op": "add",
    "path": "/spec/template/spec/volumes/-",
    "value": {
      "name": "dags-configmap",
      "configMap": {"name": "airflow-dags"}
    }
  },
  {
    "op": "add",
    "path": "/spec/template/spec/containers/0/volumeMounts/-",
    "value": {
      "name": "dags-configmap",
      "mountPath": "/opt/airflow/dags"
    }
  }
]'

# Restart scheduler to pick up DAGs
kubectl rollout restart statefulset airflow-scheduler -n airflow
kubectl rollout status statefulset airflow-scheduler -n airflow
```

**Option B: Git-Sync (Recommended for Production)**

```bash
# 1. Commit DAGs to git
cd /root/gitlab/financial-screener
git add airflow/
git commit -m "Add Airflow DAGs for data orchestration"
git push origin main

# 2. Update git-sync config with your repo URL
sed -i 's|https://github.com/yourusername/financial-screener.git|YOUR_REPO_URL|' \
  kubernetes/airflow-git-sync-config.yaml

# 3. Deploy git-sync configuration
kubectl apply -f kubernetes/airflow-git-sync-config.yaml

# 4. Restart scheduler
kubectl rollout restart statefulset airflow-scheduler -n airflow

# 5. Verify git-sync is running
kubectl logs -n airflow -l app.kubernetes.io/component=scheduler -c git-sync --tail=20
```

### Step 4: Configure Airflow Variables

Access Airflow UI and set variables:

**Airflow UI:** https://airflow.stratdata.org

**Variables to set:**
```python
# Admin → Variables → Create
eodhd_daily_quota = 100000
eodhd_quota_buffer = 10000
max_new_assets_per_day = 8000
max_price_updates_per_day = 25000
bulk_load_batch_size = 500
incremental_batch_size = 5000
```

**Alternative (CLI):**
```bash
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow variables set eodhd_daily_quota 100000

kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow variables set eodhd_quota_buffer 10000
```

### Step 5: Create Airflow Connection (Optional)

If you want to use Airflow connections instead of env vars:

```bash
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow connections add postgres_financial_screener \
  --conn-type postgres \
  --conn-host postgresql-primary.databases.svc.cluster.local \
  --conn-port 5432 \
  --conn-login appuser \
  --conn-password AppUser123 \
  --conn-schema appdb
```

---

## Configuration

### DAG Configuration

**Data Collection DAG:**
- **File:** `airflow/dags/data_loading/dag_data_collection_equities.py`
- **Schedule:** `30 21 * * *` (21:30 UTC daily)
- **Parallel Jobs:** 4 (US, LSE, German, European)
- **Auto-triggered:** No

**Indicator Calculation DAG:**
- **File:** `airflow/dags/indicators/dag_calculate_indicators.py`
- **Schedule:** `None` (triggered by data collection DAG)
- **Parallel Jobs:** 1
- **Auto-triggered:** Yes (after data collection completes)

### Modify Schedules (if needed)

```python
# In dag_data_collection_equities.py, change:
schedule_interval='30 21 * * *',  # Current: 21:30 UTC
# To:
schedule_interval='0 22 * * *',   # 22:00 UTC
schedule_interval='0 6 * * *',    # 06:00 UTC (after European close)
schedule_interval=None,           # Disable automatic schedule (manual only)
```

### Resource Limits

Current settings (in DAG files):

```yaml
Data Collector Jobs:
  requests: {cpu: 500m, memory: 1Gi}
  limits: {cpu: 2000m, memory: 2Gi}

Indicator Calculator:
  requests: {cpu: 1000m, memory: 2Gi}
  limits: {cpu: 4000m, memory: 4Gi}
```

**Adjust if needed** based on cluster capacity:
- 8 Raspberry Pi nodes
- Total capacity: ~16-24 GB RAM, ~32 cores
- Recommended: Don't exceed 50% of total capacity for data jobs

---

## Testing

### Test 1: Verify DAGs Loaded

```bash
# Check if DAGs appear in Airflow
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list

# Expected output should include:
# - data_collection_equities
# - calculate_indicators
```

### Test 2: Manual Trigger with Small Sample

**Via Airflow UI:**
1. Navigate to https://airflow.stratdata.org
2. Find `data_collection_equities` DAG
3. Click "Trigger DAG with config"
4. Add configuration:
   ```json
   {
     "test_mode": true,
     "ticker_limit": 10
   }
   ```
5. Click "Trigger"

**Via CLI:**
```bash
# Trigger manually
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger data_collection_equities

# Monitor execution
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags state data_collection_equities

# View logs
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow tasks logs data_collection_equities discover_delta latest
```

### Test 3: Verify Metadata Logging

After a DAG run completes:

```bash
# Check process_executions table
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT * FROM process_executions ORDER BY started_at DESC LIMIT 1;\""

# Check asset_processing_details
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT operation, status, COUNT(*)
   FROM asset_processing_details
   WHERE DATE(created_at) = CURRENT_DATE
   GROUP BY operation, status;\""
```

### Test 4: Verify Data Idempotency

Run the same DAG twice:

```bash
# Run 1
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger data_collection_equities

# Wait for completion, then Run 2
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger data_collection_equities

# Verify no duplicates in database
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT ticker, COUNT(*) as count
   FROM stock_prices
   WHERE DATE(created_at) = CURRENT_DATE
   GROUP BY ticker
   HAVING COUNT(*) > 1;\""

# Expected: 0 rows (no duplicates)
```

---

## Troubleshooting

### Issue 1: DAGs Not Appearing

**Symptoms:** DAGs don't show up in Airflow UI

**Solutions:**
```bash
# Check DAG directory
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  ls -la /opt/airflow/dags/

# Check for Python errors
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list-import-errors

# Check git-sync logs (if using git-sync)
kubectl logs -n airflow -l app.kubernetes.io/component=scheduler -c git-sync
```

### Issue 2: Kubernetes Jobs Failing

**Symptoms:** "process_us_markets" task fails

**Solutions:**
```bash
# Check pod logs
kubectl get pods -n financial-screener | grep data-collector
kubectl logs -n financial-screener <pod-name>

# Common issues:
# - Image pull error: Verify image exists on all nodes
# - Secret not found: Verify secrets exist in namespace
# - Database connection error: Check DATABASE_URL secret

# Verify secrets
kubectl describe secret postgres-secret -n financial-screener
kubectl describe secret data-api-secrets -n financial-screener
```

### Issue 3: Metadata Tables Not Updating

**Symptoms:** process_executions table empty after DAG run

**Solutions:**
```bash
# Check if execution_id is being passed
kubectl logs -n financial-screener <data-collector-pod> | grep execution-id

# Verify database connection from pod
kubectl exec -n financial-screener <pod-name> -- env | grep DATABASE_URL

# Test metadata logger manually
kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  "SET search_path TO financial_screener;
   SELECT * FROM get_processing_progress();"
```

### Issue 4: Git-Sync Not Working

**Symptoms:** DAGs not updating automatically

**Solutions:**
```bash
# Check git-sync logs
kubectl logs -n airflow airflow-scheduler-0 -c git-sync --tail=50

# Common issues:
# - Repository URL incorrect
# - Branch doesn't exist
# - Path incorrect (should be airflow/dags/)

# Verify ConfigMap
kubectl get configmap airflow-git-sync-config -n airflow -o yaml

# Restart with one-time sync to debug
kubectl exec -n airflow airflow-scheduler-0 -c git-sync -- \
  git-sync --one-time
```

### Issue 5: API Quota Exceeded

**Symptoms:** "check_api_quota" task shows quota exceeded

**Solutions:**
```bash
# Check current API usage
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT
     DATE(created_at) as date,
     SUM(api_calls_used) as total_api_calls
   FROM asset_processing_details
   WHERE created_at > CURRENT_DATE
   GROUP BY DATE(created_at);\""

# Reduce batch sizes in Airflow variables
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow variables set max_new_assets_per_day 5000

# Or pause DAG until quota resets
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags pause data_collection_equities
```

---

## Rollback Procedures

### Rollback DAGs

```bash
# Option A: Revert git commit
cd /root/gitlab/financial-screener
git revert <commit-hash>
git push

# Option B: Delete DAGs
kubectl delete configmap airflow-dags -n airflow
kubectl rollout restart statefulset airflow-scheduler -n airflow
```

### Rollback Docker Images

```bash
# Tag and use previous version
docker tag registry.stratdata.org/data-collector:latest \
  registry.stratdata.org/data-collector:backup

# Revert to old code
git checkout <previous-commit> services/data-collector/

# Rebuild
./scripts/build-and-distribute-data-collector.sh
```

---

## Next Steps

After successful deployment:

1. **Monitor first runs** (check metadata tables, logs)
2. **Verify data quality** (spot-check prices, indicators)
3. **Tune resource limits** (adjust based on actual usage)
4. **Set up alerts** (if desired - email, Slack)
5. **Document custom changes** (if you modified schedules, etc.)

Proceed to:
- [08_MONITORING_OBSERVABILITY.md](./08_MONITORING_OBSERVABILITY.md) - Monitoring queries and dashboards
- [09_TROUBLESHOOTING.md](./09_TROUBLESHOOTING.md) - Common issues and solutions

---

**Document Version:** 1.0
**Last Updated:** 2025-10-21
**Author:** Financial Screener Team
**Status:** Ready for Production
