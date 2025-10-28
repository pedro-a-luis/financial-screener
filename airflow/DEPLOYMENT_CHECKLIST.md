# Airflow Orchestration - Deployment Checklist

**Project**: Financial Screener - Airflow Orchestration
**Status**: Ready for Deployment
**Date**: 2025-10-26

---

## Pre-Deployment Verification

### ✅ Infrastructure
- [x] PostgreSQL metadata tables deployed (005_process_metadata_tables.sql)
- [x] Airflow 3.0.2 running on cluster
- [x] K3s cluster operational (8 nodes)
- [x] Secrets exist: postgres-secret, data-api-secrets

**Verify**:
```bash
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT COUNT(*) as metadata_records FROM asset_processing_state;\""

kubectl get pods -n airflow
kubectl get secrets -n financial-screener postgres-secret data-api-secrets
```

### ✅ Code Files
- [x] DAG files created (2 files)
- [x] DAG utilities created (3 files)
- [x] Metadata logger created
- [x] Enhanced main application
- [x] Documentation complete (9 files)
- [x] Git-sync configuration ready

**Files Created**:
```
airflow/
├── README.md
├── DEPLOYMENT_CHECKLIST.md (this file)
├── dags/
│   ├── data_loading/
│   │   └── dag_data_collection_equities.py
│   ├── indicators/
│   │   └── dag_calculate_indicators.py
│   └── utils/
│       ├── __init__.py
│       ├── database_utils.py
│       └── metadata_helpers.py
├── docs/
│   ├── 01_ARCHITECTURE_OVERVIEW.md
│   ├── 02_METADATA_SCHEMA_DESIGN.md
│   ├── 03_DELTA_PROCESSING_STRATEGY.md
│   ├── 07_DEPLOYMENT_GUIDE.md
│   ├── 08_MONITORING_OBSERVABILITY.md
│   └── 09_TROUBLESHOOTING.md

services/data-collector/src/
├── metadata_logger.py (NEW)
└── main_enhanced.py (MODIFIED)

kubernetes/
└── airflow-git-sync-config.yaml
```

---

## Deployment Steps

### Step 1: Rebuild Data Collector Image

**Includes**: metadata_logger.py, main_enhanced.py with new arguments

```bash
cd /root/gitlab/financial-screener
./scripts/build-and-distribute-data-collector.sh
```

**Expected Duration**: 5-10 minutes

**Verification**:
```bash
# Check image exists on all nodes
for NODE in 192.168.1.{240..247}; do
  echo "Node $NODE:"
  ssh -i ~/.ssh/pi_cluster admin@$NODE \
    "sudo ctr -n k8s.io images ls | grep data-collector:latest"
done
```

### Step 2: Build Technical Analyzer Image

**Required for**: Indicator calculation DAG

```bash
cd /root/gitlab/financial-screener

# Build image
docker build -t registry.stratdata.org/technical-analyzer:latest \
  -f services/technical-analyzer/Dockerfile .

# Distribute to cluster
for NODE in 192.168.1.{240..247}; do
  echo "Distributing to $NODE..."
  docker save registry.stratdata.org/technical-analyzer:latest | \
    ssh -i ~/.ssh/pi_cluster admin@$NODE \
      "sudo ctr -n k8s.io images import -"
done
```

**Expected Duration**: 10-15 minutes

### Step 3: Deploy DAGs to Airflow

**Method**: Git-sync (recommended)

```bash
# 1. Update git-sync config with actual repo URL
# Edit kubernetes/airflow-git-sync-config.yaml and replace:
# GIT_SYNC_REPO: "https://github.com/yourusername/financial-screener.git"
# with your actual repository URL

# 2. Commit all files to git
cd /root/gitlab/financial-screener
git add airflow/ services/data-collector/src/metadata_logger.py \
        services/data-collector/src/main_enhanced.py \
        kubernetes/airflow-git-sync-config.yaml
git commit -m "Add Airflow orchestration with metadata tracking"
git push origin main

# 3. Deploy git-sync configuration
kubectl apply -f kubernetes/airflow-git-sync-config.yaml

# 4. Restart Airflow scheduler
kubectl rollout restart statefulset airflow-scheduler -n airflow
kubectl rollout status statefulset airflow-scheduler -n airflow

# 5. Verify git-sync is working
kubectl logs -n airflow -l app.kubernetes.io/component=scheduler -c git-sync --tail=20
```

**Expected Duration**: 5 minutes

### Step 4: Configure Airflow Variables

**Set via Airflow CLI**:

```bash
# Set quota limits
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow variables set eodhd_daily_quota 100000

kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow variables set eodhd_quota_buffer 10000

# Set batch size limits
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow variables set max_new_assets_per_day 8000

kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow variables set max_price_updates_per_day 25000

kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow variables set bulk_load_batch_size 500

kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow variables set incremental_batch_size 5000
```

**Expected Duration**: 2 minutes

### Step 5: Verify DAGs Loaded

```bash
# List DAGs
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list | grep -E "data_collection|calculate_indicators"

# Expected output:
# data_collection_equities
# calculate_indicators

# Check for import errors
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list-import-errors
```

**Expected**: 0 import errors

---

## Testing

### Test 1: Verify DAG Configuration

```bash
# View DAG details
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags show data_collection_equities

# Check schedule
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags details data_collection_equities
```

### Test 2: Manual Trigger (Small Sample)

**Test with limited tickers first**:

```bash
# Unpause DAG
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags unpause data_collection_equities

# Trigger manually
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger data_collection_equities

# Monitor execution
watch kubectl get pods -n financial-screener

# Check logs
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow tasks logs data_collection_equities discover_delta latest
```

### Test 3: Verify Metadata Logging

**After first run completes**:

```bash
# Check process_executions
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT * FROM v_recent_executions LIMIT 5;\""

# Check processing details
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT operation, status, COUNT(*)
   FROM asset_processing_details
   WHERE DATE(created_at) = CURRENT_DATE
   GROUP BY operation, status;\""

# Check API usage
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT SUM(api_calls_used) as total_api_calls
   FROM asset_processing_details
   WHERE DATE(created_at) = CURRENT_DATE;\""
```

### Test 4: Verify Idempotency

**Run same DAG twice, verify no duplicates**:

```bash
# Run 1
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger data_collection_equities

# Wait for completion (~2-6 hours)

# Run 2
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger data_collection_equities

# Verify no duplicates in stock_prices
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener;
   SELECT ticker, date, COUNT(*) as count
   FROM stock_prices
   WHERE DATE(created_at) = CURRENT_DATE
   GROUP BY ticker, date
   HAVING COUNT(*) > 1;\""

# Expected: 0 rows (no duplicates)
```

---

## Post-Deployment Monitoring

### Daily Checks (First Week)

**1. DAG Run Status**:
```bash
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list-runs -d data_collection_equities --limit 5
```

**2. Processing Progress**:
```sql
SET search_path TO financial_screener;
SELECT * FROM get_processing_progress();
```

**3. API Usage**:
```sql
SELECT
    DATE(created_at) as date,
    SUM(api_calls_used) as total_api_calls,
    COUNT(*) as operations
FROM asset_processing_details
WHERE created_at >= CURRENT_DATE - 7
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

**4. Failed Tickers**:
```sql
SELECT
    ticker,
    consecutive_failures,
    last_error_message,
    last_error_at
FROM asset_processing_state
WHERE consecutive_failures >= 3
ORDER BY consecutive_failures DESC
LIMIT 20;
```

### Expected Timeline

**Day 1 (Initial Catch-Up)**:
- Assets discovered: 21,817
- Already loaded: 5,045 (price updates)
- New assets: 8,000 (API quota limit)
- Remaining: 8,772 (for Day 2+)
- API calls: ~93K (within 100K limit)
- Duration: 4-6 hours

**Day 2-3**:
- New assets: 8,772 remaining
- API calls: ~21K (price updates) + ~66K (new) = ~87K
- Duration: 4-6 hours

**Day 4+ (Steady State)**:
- All assets loaded: 21,817
- Price updates only: 21,817 × 1 = ~22K API calls
- Duration: 2-3 hours
- Quota used: 22%

---

## Rollback Procedures

### If DAGs Fail to Load

```bash
# Check import errors
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list-import-errors

# View git-sync logs
kubectl logs -n airflow airflow-scheduler-0 -c git-sync

# Revert git commit
cd /root/gitlab/financial-screener
git revert HEAD
git push origin main
```

### If Jobs Fail

```bash
# Check pod logs
kubectl get pods -n financial-screener | grep data-collector
kubectl logs -n financial-screener <pod-name>

# Common issues:
# - Image pull error → Rebuild/distribute images
# - Secret not found → Verify secrets exist
# - Database connection → Test DATABASE_URL

# Quick fix: Pause DAG
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags pause data_collection_equities
```

---

## Success Criteria

### ✅ Deployment Successful When:

1. **DAGs Loaded**: Both DAGs appear in Airflow UI without import errors
2. **Variables Set**: All 6 Airflow variables configured
3. **Images Distributed**: data-collector and technical-analyzer on all 8 nodes
4. **First Run Completes**: Manual trigger completes successfully
5. **Metadata Populated**: Records in process_executions and asset_processing_details
6. **No Duplicates**: Idempotency test passes (no duplicate stock_prices)
7. **API Quota OK**: Daily usage stays under 90K calls
8. **Scheduled Runs**: DAG triggers automatically at 21:30 UTC

### ✅ Steady State Operation:

- Daily DAG runs complete within 2-3 hours
- 21,817 tickers updated daily
- ~22K API calls per day (22% quota)
- 0 import errors
- <1% ticker failure rate
- Indicators calculated for all assets

---

## Documentation

**Complete documentation available at**:

- [README.md](README.md) - Project overview
- [01_ARCHITECTURE_OVERVIEW.md](docs/01_ARCHITECTURE_OVERVIEW.md) - System design
- [02_METADATA_SCHEMA_DESIGN.md](docs/02_METADATA_SCHEMA_DESIGN.md) - Database schema
- [03_DELTA_PROCESSING_STRATEGY.md](docs/03_DELTA_PROCESSING_STRATEGY.md) - Delta algorithm
- [07_DEPLOYMENT_GUIDE.md](docs/07_DEPLOYMENT_GUIDE.md) - Detailed deployment
- [08_MONITORING_OBSERVABILITY.md](docs/08_MONITORING_OBSERVABILITY.md) - Monitoring
- [09_TROUBLESHOOTING.md](docs/09_TROUBLESHOOTING.md) - Issue resolution

---

## Support

**For issues**:
1. Check [09_TROUBLESHOOTING.md](docs/09_TROUBLESHOOTING.md) for common problems
2. Review Airflow task logs in UI
3. Check metadata tables for error details
4. Review Kubernetes pod logs

**Useful Commands**:
```bash
# Airflow UI
https://airflow.stratdata.org

# Health check script
/root/gitlab/financial-screener/scripts/health-check.sh

# Database queries
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb"
```

---

**Checklist Version**: 1.0
**Last Updated**: 2025-10-26
**Status**: Ready for Deployment
**Estimated Deployment Time**: 30-45 minutes
**Estimated Testing Time**: 6-8 hours (first full run)
