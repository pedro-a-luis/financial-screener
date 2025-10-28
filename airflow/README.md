# Airflow Orchestration for Financial Screener

Complete Airflow-based orchestration for automated data collection and processing.

## Overview

This system orchestrates daily financial data collection across 21,817 assets from 8 global exchanges, with automatic delta discovery, API quota management, and complete metadata tracking.

### Key Features

✅ **Metadata-Driven Delta Discovery** - Automatically determines what needs processing
✅ **Parallel Processing** - 4 concurrent jobs by exchange
✅ **API Quota Management** - Stays within 100K daily limit
✅ **Idempotent** - Safe to run multiple times, no duplicates
✅ **Complete Audit Trail** - Every operation logged to metadata tables
✅ **Automatic Retry** - Failed tickers retry with exponential backoff
✅ **Technical Indicators** - Auto-calculates 30+ indicators after data loads

---

## Architecture

```
Airflow Scheduler (21:30 UTC daily)
  ↓
DAG: data_collection_equities
  ├─→ initialize_execution (create process record)
  ├─→ discover_delta (query metadata: what needs processing?)
  ├─→ check_api_quota (adjust batch sizes)
  ├─→ [Parallel K8s Jobs]
  │    ├─→ process_us_markets (NYSE, NASDAQ)
  │    ├─→ process_lse (London)
  │    ├─→ process_german_markets (Frankfurt, Xetra)
  │    └─→ process_european_markets (Euronext, BME, SIX)
  ├─→ finalize_execution (update metadata with results)
  └─→ trigger_indicators (start next DAG)
       ↓
DAG: calculate_indicators
  ├─→ initialize_execution
  ├─→ calculate_indicators (K8s Job)
  └─→ finalize_execution
```

---

## Quick Start

### 1. Prerequisites

- ✅ PostgreSQL metadata tables deployed ([005_process_metadata_tables.sql](../database/migrations/005_process_metadata_tables.sql))
- ✅ Airflow 3.0.2 running on cluster
- ✅ Docker images: data-collector, technical-analyzer
- ✅ Secrets: postgres-secret, data-api-secrets

### 2. Deploy

```bash
# Build Docker images
cd /root/gitlab/financial-screener
./scripts/build-and-distribute-data-collector.sh

# Deploy DAGs (git-sync method)
git add airflow/
git commit -m "Add Airflow DAGs"
git push origin main

kubectl apply -f kubernetes/airflow-git-sync-config.yaml
kubectl rollout restart statefulset airflow-scheduler -n airflow

# Verify
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- airflow dags list
```

### 3. Test

```bash
# Manual trigger
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger data_collection_equities

# Monitor
watch kubectl get pods -n financial-screener

# Check results
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
  \"SET search_path TO financial_screener; SELECT * FROM v_recent_executions;\""
```

---

## Documentation

Comprehensive documentation available:

### Architecture & Design
- **[01_ARCHITECTURE_OVERVIEW.md](docs/01_ARCHITECTURE_OVERVIEW.md)** - System architecture, components, data flow
- **[02_METADATA_SCHEMA_DESIGN.md](docs/02_METADATA_SCHEMA_DESIGN.md)** - Database schema, tables, views, indexes
- **[03_DELTA_PROCESSING_STRATEGY.md](docs/03_DELTA_PROCESSING_STRATEGY.md)** - Delta discovery algorithm, idempotency

### Implementation
- **[04_DAG_DATA_COLLECTION.md](docs/04_DAG_DATA_COLLECTION.md)** - Data collection DAG details (TODO)
- **[05_DAG_INDICATORS.md](docs/05_DAG_INDICATORS.md)** - Indicator calculation DAG details (TODO)
- **[06_APPLICATION_INTEGRATION.md](docs/06_APPLICATION_INTEGRATION.md)** - Application changes, metadata logging (TODO)

### Operations
- **[07_DEPLOYMENT_GUIDE.md](docs/07_DEPLOYMENT_GUIDE.md)** - Complete deployment instructions
- **[08_MONITORING_OBSERVABILITY.md](docs/08_MONITORING_OBSERVABILITY.md)** - Monitoring queries, alerts (TODO)
- **[09_TROUBLESHOOTING.md](docs/09_TROUBLESHOOTING.md)** - Common issues, solutions (TODO)

---

## File Structure

```
airflow/
├── README.md (this file)
├── docs/
│   ├── 01_ARCHITECTURE_OVERVIEW.md ✅
│   ├── 02_METADATA_SCHEMA_DESIGN.md ✅
│   ├── 03_DELTA_PROCESSING_STRATEGY.md ✅
│   ├── 07_DEPLOYMENT_GUIDE.md ✅
│   └── [04-06, 08-09 TODO]
├── dags/
│   ├── data_loading/
│   │   └── dag_data_collection_equities.py ✅
│   ├── indicators/
│   │   └── dag_calculate_indicators.py ✅
│   └── utils/
│       ├── __init__.py ✅
│       ├── database_utils.py ✅ (DB connections)
│       └── metadata_helpers.py ✅ (DAG helper functions)
└── [plugins/, tests/ - Future]
```

---

## Key Components

### DAGs

| DAG | Schedule | Purpose | Duration |
|-----|----------|---------|----------|
| `data_collection_equities` | Daily 21:30 UTC | Fetch fundamentals & prices | 2-6 hours |
| `calculate_indicators` | Triggered | Calculate technical indicators | 15-60 min |

### Metadata Tables

| Table | Purpose | Rows |
|-------|---------|------|
| `process_executions` | DAG run tracking | ~1K/year |
| `asset_processing_state` | Per-ticker state | 21,817 (static) |
| `asset_processing_details` | Operation logs | ~8M/year |

### Docker Images

| Image | Purpose | Size |
|-------|---------|------|
| `data-collector:latest` | EODHD API fetching | ~500 MB |
| `technical-analyzer:latest` | Indicator calculation | ~800 MB |

---

## Expected Performance

### Day 1 (Initial Catch-Up)

```
Assets Discovered: 21,817
- Already loaded: 5,045 (need price updates)
- New assets: 16,772 (need bulk load)

API Usage:
- Price updates: 5,045 × 1 = 5,045 calls
- New assets (limited): 8,000 × 11 = 88,000 calls
- Total: 93,045 calls (within 100K limit ✅)

Duration: 4-6 hours (parallel processing)
```

### Steady State (Daily)

```
Assets Discovered: 21,817
- All need price updates: 21,817 × 1 = 21,817 API calls
- No new assets: 0 calls

Duration: 2-3 hours
API Quota Used: 22% (78% unused buffer)
```

### Technical Indicators

```
Assets Processed: 21,817
API Calls: 0 (reads from database)
Duration: 30-60 minutes
Resource: CPU-bound (pandas calculations)
```

---

## Monitoring Queries

### Processing Progress

```sql
SET search_path TO financial_screener;

-- Overall progress
SELECT * FROM get_processing_progress();

-- Today's activity
SELECT * FROM v_today_processing_activity;

-- Recent DAG runs
SELECT * FROM v_recent_executions LIMIT 10;

-- Failed tickers
SELECT ticker, consecutive_failures, last_error_message
FROM asset_processing_state
WHERE consecutive_failures >= 3
ORDER BY consecutive_failures DESC;
```

### API Usage Tracking

```sql
-- Today's API usage
SELECT SUM(api_calls_used) as total_calls
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE;

-- API usage by operation
SELECT
    operation,
    COUNT(*) as operations,
    SUM(api_calls_used) as total_api_calls
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE
GROUP BY operation;
```

---

## Maintenance

### Daily Tasks

- Check Airflow UI for failed DAG runs
- Monitor API quota usage
- Review failed tickers

### Weekly Tasks

- Review processing progress (should be 100% after week 2)
- Check cluster resource usage
- Verify data quality (spot-check prices)

### Monthly Tasks

- Review and clean old process_executions records (optional)
- Update documentation for any custom changes
- Review and optimize resource limits

---

## Support

### Issue Reporting

If you encounter issues:

1. Check **[07_DEPLOYMENT_GUIDE.md#troubleshooting](docs/07_DEPLOYMENT_GUIDE.md#troubleshooting)**
2. Review **Airflow task logs** in UI
3. Check **metadata tables** for error details
4. Review **Kubernetes pod logs**

### Useful Commands

```bash
# Airflow
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- airflow dags list
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- airflow tasks list <dag-id>
kubectl logs -n airflow -l app.kubernetes.io/component=scheduler -c scheduler

# Database
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb"

# Kubernetes Jobs
kubectl get pods -n financial-screener
kubectl logs -n financial-screener <pod-name>
kubectl describe pod -n financial-screener <pod-name>
```

---

## Future Enhancements

- [ ] Add email/Slack alerts on DAG failures
- [ ] Create Grafana dashboard for monitoring
- [ ] Add data quality validation tasks
- [ ] Implement data retention policies
- [ ] Add more exchanges (Asia, Australia)
- [ ] Optimize batch sizes based on cluster load

---

**Version:** 1.0
**Status:** Production Ready
**Last Updated:** 2025-10-21
**Maintainer:** Financial Screener Team
