# Historical Load DAG - User Guide

## Overview

The **`historical_load_equities`** DAG loads historical price data in **reverse chronological order** - starting from the most recent complete month and working backward toward older data.

### Strategy: Monthly Chunks, Recent to Old

**Why this approach?**
- Most recent data is most valuable (loaded first)
- Usable dataset even if interrupted
- Can stop at any point (1 year, 18 months, 2 years, etc.)
- Easier debugging (recent data more likely to be correct)
- Better user experience (analyze recent trends immediately)

---

## DAG Details

```
DAG ID:       historical_load_equities
Schedule:     Daily at 23:00 UTC (after daily collection at 21:30)
Target Depth: 2 years of historical price data
Status:       Paused by default (manual trigger recommended)
```

### Task Flow

```
initialize_historical_load
    ↓
determine_next_month (finds next month to load)
    ↓
check_completion (2 years reached?)
    ↓
    ├─[YES]→ historical_load_complete → finalize
    │
    └─[NO]→ process_historical_data
              ↓
              ├─→ load_us_markets_historical (NYSE, NASDAQ)
              ├─→ load_lse_historical (LSE)
              ├─→ load_german_markets_historical (Frankfurt, Xetra)
              └─→ load_european_markets_historical (Euronext, BME, SIX)
              ↓
           finalize_historical_load
```

---

## How It Works

### Step 1: Determine Next Month

The DAG queries the `asset_processing_state` table to find:
- Current oldest date (`prices_first_date`) across all tickers
- Calculate the month BEFORE that date
- Return start_date and end_date for that month

**Example:**

```sql
-- Current state
SELECT MIN(prices_first_date) FROM asset_processing_state;
-- Result: 2024-10-01

-- Next month to load: September 2024
start_date = 2024-09-01
end_date = 2024-09-30
```

### Step 2: Process Month

For each exchange in parallel:
```bash
python /app/src/main_enhanced.py \
  --execution-id <airflow_run_id> \
  --exchanges NYSE,NASDAQ \
  --mode historical \
  --start-date 2024-09-01 \
  --end-date 2024-09-30 \
  --skip-existing
```

**API Cost per Run:**
- Tickers needing history: ~16,816
- API calls per ticker: 1 (prices only, fundamentals already loaded)
- Total: ~16,816 API calls per run

### Step 3: Update Metadata

After processing, the DAG updates:
- `prices_first_date` for each ticker
- API calls used
- Progress toward 2-year goal

### Step 4: Check Completion

On next run, the DAG checks:
- Do all tickers have >= 2 years of data?
- If YES: Mark complete, skip processing
- If NO: Load next month (continue backward in time)

---

## Example Run Sequence

```
Day 1:  Load Oct 2024 → 16,816 API calls
        All tickers now have: Oct 20-31, 2024

Day 2:  Load Sep 2024 → 16,816 API calls
        All tickers now have: Sep 1 - Oct 31, 2024

Day 3:  Load Aug 2024 → 16,816 API calls
        All tickers now have: Aug 1 - Oct 31, 2024

...

Day 24: Load Nov 2022 → 16,816 API calls
        All tickers now have: Nov 2022 - Oct 2024 (2 years) ✓

Day 25: Check completion → Already have 2 years → DONE
```

---

## Starting the Historical Load

### Option 1: Manual Trigger (Recommended)

```bash
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags unpause historical_load_equities"

# Trigger first run
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger historical_load_equities"
```

### Option 2: Let Schedule Run Automatically

The DAG is scheduled to run daily at 23:00 UTC. Simply unpause it:

```bash
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags unpause historical_load_equities"
```

---

## Monitoring Progress

### Check Current Progress

```sql
-- Connect to database
kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb

-- Check progress
SET search_path TO financial_screener;

SELECT
    COUNT(*) as total_tickers,
    MIN(prices_first_date) as oldest_data,
    MAX(prices_last_date) as newest_data,
    AVG(EXTRACT(days FROM (CURRENT_DATE - prices_first_date))) as avg_depth_days,
    (AVG(EXTRACT(days FROM (CURRENT_DATE - prices_first_date))) / 730.0 * 100)::numeric(5,1) as progress_pct
FROM asset_processing_state
WHERE prices_first_date IS NOT NULL;
```

**Example Output:**
```
 total_tickers | oldest_data | newest_data | avg_depth_days | progress_pct
---------------+-------------+-------------+----------------+--------------
         5001  | 2024-09-01  | 2025-10-20  |    395.2       |    54.1
```

### Check DAG Runs

```bash
# View recent runs
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list-runs historical_load_equities --limit 10"
```

### Check Running Pods

```bash
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl get pods -n financial-screener -l job-type=historical"
```

---

## API Quota Management

### Daily Quota Usage

```
Daily collection:   ~22,000 calls (all tickers, daily price updates)
Historical load:    ~16,816 calls (one month for all tickers)
-----------------------------------------------------------
Combined:           ~39,000 calls/day (39% of 100K limit)
Remaining:          ~61,000 calls for safety margin
```

**Safe to run both DAGs simultaneously!**

### If Quota Issues Occur

1. **Pause historical load** (let daily collection continue):
   ```bash
   airflow dags pause historical_load_equities
   ```

2. **Check quota usage** in EODHD dashboard

3. **Resume when safe** (usage < 50K):
   ```bash
   airflow dags unpause historical_load_equities
   ```

---

## Configuration Options

### Override Target Depth

By default, the DAG loads 2 years of history. To change:

```bash
# Trigger with custom depth (e.g., 3 years)
airflow dags trigger historical_load_equities --conf '{
  "target_years": 3
}'
```

### Load Specific Exchanges Only

```bash
# Load history for US markets only
airflow dags trigger historical_load_equities --conf '{
  "exchanges": ["NYSE", "NASDAQ"]
}'
```

---

## Stopping the Historical Load

### Pause (Resume Later)

```bash
airflow dags pause historical_load_equities
```

The DAG will resume from where it left off when unpaused.

### Complete Stop (if satisfied with current depth)

No action needed - the DAG will automatically stop when it detects all tickers have reached the target depth.

To manually force completion:

```sql
-- Mark all tickers as having sufficient history
UPDATE financial_screener.asset_processing_state
SET prices_first_date = CURRENT_DATE - INTERVAL '2 years'
WHERE prices_first_date > CURRENT_DATE - INTERVAL '2 years';
```

---

## Troubleshooting

### Issue: DAG Not Showing in Airflow

**Solution:**
```bash
# Clear cache
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  rm -rf /opt/airflow/dags/__pycache__"

# Restart dag-processor
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl delete pod -n airflow -l component=dag-processor"

# Wait 30 seconds, then check
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list | grep historical"
```

### Issue: Pods Failing

**Check logs:**
```bash
# Get pod name
kubectl get pods -n financial-screener -l job-type=historical

# View logs
kubectl logs -n financial-screener <pod-name>
```

**Common issues:**
- Database connection: Check `postgres-secret` in namespace
- API key: Check `data-api-secrets` in namespace
- Image not found: Verify image distributed to all nodes

### Issue: Progress Stalled

**Check metadata:**
```sql
-- See which tickers are failing
SELECT ticker, consecutive_failures, last_error_message
FROM financial_screener.asset_processing_state
WHERE consecutive_failures > 0
ORDER BY consecutive_failures DESC
LIMIT 20;
```

**Reset failed tickers:**
```sql
-- Reset failure count for specific ticker
UPDATE financial_screener.asset_processing_state
SET consecutive_failures = 0,
    last_error_message = NULL
WHERE ticker = 'AAPL';
```

---

## Comparison: Historical Load vs Daily Collection

| Aspect | Historical Load | Daily Collection |
|--------|----------------|------------------|
| **Purpose** | Backfill old data | Keep data up-to-date |
| **Direction** | Backward (recent → old) | Forward (last date → yesterday) |
| **Date Range** | 1 month chunks | Delta (missing dates only) |
| **API Cost** | ~16,816 calls/run | ~22,000 calls/day |
| **Schedule** | 23:00 UTC daily | 21:30 UTC daily |
| **Duration** | ~24 days for 2 years | Ongoing (daily) |
| **Completion** | Auto-stops at target | Runs forever |

---

## Expected Timeline

### Current State (Oct 27, 2025)
```
Assets with data:     5,001
Oldest price date:    2024-09-24
Latest price date:    2025-10-20
Current depth:        ~13 months
```

### Target State (Nov 20, 2025)
```
Assets with data:     21,817 (all)
Oldest price date:    2023-10-27 (2 years ago)
Latest price date:    2025-11-20
Target depth:         24 months (2 years) ✓
```

### Timeline
- **Start date**: Oct 27, 2025
- **Completion date**: ~Nov 20, 2025
- **Duration**: 24 days
- **Total API calls**: ~404,000 (24 runs × 16,816 calls)
- **Daily quota used**: 39% (safe margin)

---

## Files Created

| File | Description |
|------|-------------|
| [`airflow/dags/dag_historical_load_equities.py`](dags/dag_historical_load_equities.py) | Main historical load DAG |
| [`airflow/dags/utils/historical_helpers.py`](dags/utils/historical_helpers.py) | Helper functions for month calculation |
| [`services/data-collector/src/main_enhanced.py`](../services/data-collector/src/main_enhanced.py) | Updated with `historical` mode support |
| [`airflow/HISTORICAL_LOAD_GUIDE.md`](HISTORICAL_LOAD_GUIDE.md) | This document |

---

## Summary

✅ **Historical Load DAG Created**
- Loads data in reverse chronological order (most recent first)
- Processes 1 month at a time for all tickers
- Automatically stops when 2-year target reached
- Safe to run alongside daily collection
- Resumable at any point

✅ **Ready to Start**
```bash
# Unpause and trigger
airflow dags unpause historical_load_equities
airflow dags trigger historical_load_equities
```

✅ **Monitor Progress**
```sql
-- Check in database
SELECT AVG(EXTRACT(days FROM (CURRENT_DATE - prices_first_date))) / 730.0 * 100
FROM asset_processing_state
WHERE prices_first_date IS NOT NULL;
```

**Estimated completion: 24 days from start**

---

**Created**: 2025-10-27
**Status**: ✅ Ready to deploy
**Next Step**: Unpause DAG and trigger first run
