# How to Reprocess Data with Custom Parameters

This guide explains how to trigger the data collection DAG with custom parameters for reprocessing specific tickers or date ranges.

---

## Date Logic - How It Works

### ✅ CORRECTED Logic (Current)

**For Incremental Updates:**
```
1. Query: prices_last_date for AAPL = '2025-10-27'
2. Calculate: start_date = prices_last_date + 1 day = '2025-10-28'
3. Fetch: 2025-10-28 → today
4. Result: Only fetches MISSING dates (no wasted API calls)
```

**For Bulk Loads (new tickers):**
```
1. No prices_last_date exists
2. Calculate: start_date = today - 730 days (2 years)
3. Fetch: 2 years of historical data
```

**Key Points:**
- ✅ Never looks backward - starts from `prices_last_date + 1`
- ✅ Only fetches missing dates
- ✅ Efficient API usage
- ✅ Database merge logic handles any overlaps

---

## Reprocessing Options

###Option 1: Reprocess All Data for Specific Tickers

**Use Case**: A ticker has bad/incomplete data and needs to be reloaded

**Method**: Mark ticker for reprocessing in metadata

```sql
-- Mark AAPL for complete reprocessing
UPDATE financial_screener.asset_processing_state
SET needs_fundamentals_reprocess = TRUE,
    needs_prices_reprocess = TRUE
WHERE ticker = 'AAPL';
```

**Result**: Next DAG run will:
1. Re-fetch all fundamentals
2. Re-fetch 2 years of prices
3. Update all data via `ON CONFLICT DO UPDATE`

---

### Option 2: Reprocess Specific Date Range

**Use Case**: API had issues on specific dates, need to refetch

**Method**: Pass parameters via Airflow DAG configuration

**CLI:**
```bash
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger data_collection_equities \
  --conf '{
    "tickers": ["AAPL", "MSFT", "GOOGL"],
    "start_date": "2025-10-01",
    "end_date": "2025-10-10",
    "force_reprocess": true
  }'
```

**Web UI:**
1. Navigate to: DAGs → data_collection_equities
2. Click "Trigger DAG" button (▶ icon)
3. Click "Trigger DAG w/ config"
4. Enter JSON configuration:
```json
{
  "tickers": ["AAPL", "MSFT", "GOOGL"],
  "start_date": "2025-10-01",
  "end_date": "2025-10-10",
  "force_reprocess": true
}
```
5. Click "Trigger"

**What It Does:**
- Fetches data for specified tickers only
- Fetches specified date range (start_date → end_date)
- Updates existing data via merge logic
- No duplicates created

---

### Option 3: Reprocess All Tickers for Date Range

**Use Case**: API was down for several days, need to backfill

```bash
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags trigger data_collection_equities \
  --conf '{
    "start_date": "2025-10-15",
    "end_date": "2025-10-20",
    "force_reprocess": true
  }'
```

**Result**: Processes all 21,817 tickers for Oct 15-20

---

### Option 4: Reset Single Ticker Completely

**Use Case**: Ticker has corrupted data, start fresh

**Method**: Use database function

```sql
-- Reset AAPL to "never processed" state
SELECT financial_screener.reset_ticker_for_reprocessing('AAPL', 'all');
```

**Options for scope:**
- `'all'` - Reset everything (fundamentals + prices + indicators)
- `'fundamentals'` - Reset fundamentals only
- `'prices'` - Reset prices only
- `'indicators'` - Reset indicators only

**Result**: Next DAG run treats ticker as new (bulk load)

---

## Configuration Parameters

### Available Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `tickers` | Array | List of specific tickers to process | `["AAPL", "MSFT"]` |
| `exchanges` | Array | Process specific exchanges | `["NYSE", "NASDAQ"]` |
| `start_date` | String | Override start date (YYYY-MM-DD) | `"2025-10-01"` |
| `end_date` | String | Override end date (YYYY-MM-DD) | `"2025-10-31"` |
| `force_reprocess` | Boolean | Reprocess even if already done | `true` |
| `mode` | String | Force mode (`bulk` or `incremental`) | `"bulk"` |
| `batch_size` | Integer | Override batch size | `100` |

---

## Examples

### Example 1: Reprocess One Ticker for Last Month

```bash
airflow dags trigger data_collection_equities --conf '{
  "tickers": ["AAPL"],
  "start_date": "2025-09-27",
  "end_date": "2025-10-27",
  "force_reprocess": true
}'
```

### Example 2: Bulk Load New Tickers

```bash
# First, add new tickers to metadata
INSERT INTO financial_screener.asset_processing_state (ticker)
VALUES ('NEW_TICKER_1'), ('NEW_TICKER_2'), ('NEW_TICKER_3');

# Then trigger DAG (will auto-detect as bulk_load)
airflow dags trigger data_collection_equities
```

### Example 3: Reprocess All NYSE Tickers for One Day

```bash
airflow dags trigger data_collection_equities --conf '{
  "exchanges": ["NYSE"],
  "start_date": "2025-10-27",
  "end_date": "2025-10-27",
  "force_reprocess": true
}'
```

### Example 4: Fix Weekend Gap (Market was closed)

Market closes Sat-Sun, but API might have issues. Reprocess just Monday:

```bash
airflow dags trigger data_collection_equities --conf '{
  "start_date": "2025-10-28",
  "end_date": "2025-10-28",
  "force_reprocess": true
}'
```

---

## How Parameters are Used

### In the DAG

The DAG reads configuration from `context['params']` or `context['dag_run'].conf`:

```python
def discover_processing_delta(**context):
    # Get DAG run configuration
    dag_conf = context.get('dag_run').conf or {}

    # Override tickers if specified
    if 'tickers' in dag_conf:
        tickers = dag_conf['tickers']
    else:
        # Use metadata view for delta discovery
        tickers = query_metadata_for_tickers()

    # Pass to downstream tasks via XCom
    context['ti'].xcom_push(key='tickers_to_process', value=tickers)
```

### In the Application

The application receives overrides as command-line arguments:

```python
async def fetch_complete_stock_data(
    ticker: str,
    start_date_override: date = None,  # From --start-date
    end_date_override: date = None,    # From --end-date
    ...
):
    if start_date_override and end_date_override:
        # Use provided dates
        start_date = start_date_override
        end_date = end_date_override
    elif mode == "incremental":
        # Use metadata-driven logic
        last_date = await metadata_logger.get_last_price_date(ticker)
        start_date = last_date + timedelta(days=1)
        end_date = date.today()
    ...
```

---

## Safety Features

### Idempotency

All operations are idempotent (safe to run multiple times):

```sql
-- Stock prices merge logic
INSERT INTO stock_prices (asset_id, date, open, high, low, close, volume)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (asset_id, date) DO UPDATE
SET open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume;
```

**Result**:
- New dates: Inserted
- Existing dates: Updated with latest values
- No duplicates ever created

### Duplicate Prevention

Multiple layers of protection:

1. **Database**: UNIQUE constraint on `(asset_id, date)`
2. **Application**: `--skip-existing` flag checks metadata
3. **Airflow**: `max_active_runs=1` prevents concurrent runs

---

## Monitoring Reprocessing

### Check What's Running

```bash
# View current DAG runs
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list-runs data_collection_equities --limit 5

# Check active pods
kubectl get pods -n financial-screener -l app=data-collector
```

### Check Metadata

```sql
-- See recent operations
SELECT * FROM financial_screener.v_today_processing_activity;

-- Check specific ticker
SELECT *
FROM financial_screener.asset_processing_state
WHERE ticker = 'AAPL';

-- See all tickers processed today
SELECT ticker, operation, status, api_calls_used
FROM financial_screener.asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE
ORDER BY created_at DESC;
```

---

## Common Scenarios

### Scenario 1: API Was Down Yesterday

**Problem**: API was unavailable on Oct 26, all tickers missing that date

**Solution**:
```bash
airflow dags trigger data_collection_equities --conf '{
  "start_date": "2025-10-26",
  "end_date": "2025-10-26",
  "force_reprocess": true
}'
```

### Scenario 2: Wrong Data Loaded for AAPL

**Problem**: AAPL has incorrect prices for last week

**Solution**:
```sql
-- Option A: Mark for reprocess (will refetch 2 years)
UPDATE financial_screener.asset_processing_state
SET needs_prices_reprocess = TRUE
WHERE ticker = 'AAPL';

-- Option B: Targeted reprocess (just last week)
airflow dags trigger data_collection_equities --conf '{
  "tickers": ["AAPL"],
  "start_date": "2025-10-20",
  "end_date": "2025-10-27",
  "force_reprocess": true
}'
```

### Scenario 3: Added 1000 New Tickers

**Problem**: Just added 1000 new tickers to metadata, need historical data

**Solution**:
```sql
-- Insert new tickers
INSERT INTO financial_screener.asset_processing_state (ticker)
SELECT ticker FROM new_tickers_list;

-- Trigger normal DAG run
airflow dags trigger data_collection_equities

-- Delta discovery will see fundamentals_loaded = FALSE
-- Automatically treats as bulk_load (2 years of data)
```

---

## Best Practices

### 1. Use Targeted Reprocessing

❌ **Don't**: Reprocess all 21,817 tickers when only 10 have issues
✅ **Do**: Target specific tickers via configuration

### 2. Monitor API Quota

```sql
-- Check today's API usage
SELECT SUM(api_calls_used) as total_calls
FROM financial_screener.asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE;

-- Daily limit: 100,000 calls
-- If close to limit, batch reprocessing across multiple days
```

### 3. Use Metadata Flags for Ongoing Issues

If a ticker consistently fails:
```sql
-- Check failures
SELECT ticker, consecutive_failures, last_error_message
FROM financial_screener.asset_processing_state
WHERE consecutive_failures >= 3;

-- After 5 failures, automatically excluded from processing
```

### 4. Verify Before Large Reprocess

```sql
-- Count how many tickers would be affected
SELECT COUNT(*)
FROM financial_screener.asset_processing_state
WHERE prices_last_date < '2025-10-25';

-- Estimate API calls (each ticker = 1 call for price update)
```

---

## Troubleshooting

### Issue: Reprocessing Not Working

**Check**:
1. DAG run triggered? `airflow dags list-runs data_collection_equities`
2. Configuration passed? Check DAG run conf in UI
3. Pods created? `kubectl get pods -n financial-screener`
4. Logs? `kubectl logs <pod-name> -n financial-screener`

### Issue: Duplicates Created

**Should never happen** (ON CONFLICT prevents this)

If it does:
```sql
-- Find duplicates
SELECT asset_id, date, COUNT(*)
FROM financial_screener.stock_prices
GROUP BY asset_id, date
HAVING COUNT(*) > 1;

-- Remove duplicates (keep latest)
DELETE FROM financial_screener.stock_prices
WHERE id NOT IN (
    SELECT MAX(id)
    FROM financial_screener.stock_prices
    GROUP BY asset_id, date
);
```

### Issue: API Quota Exceeded

**Solution**: Batch reprocessing across multiple days

```bash
# Day 1: First 5000 tickers
airflow dags trigger data_collection_equities --conf '{
  "start_date": "2025-10-01",
  "end_date": "2025-10-10",
  "batch_size": 5000
}'

# Day 2: Next 5000 tickers
# (Automatically continues from where Day 1 left off)
```

---

## Summary

✅ **Date Logic Fixed**: Now uses `prices_last_date + 1` (no lookback)
✅ **Reprocessing Supported**: Via DAG configuration parameters
✅ **Idempotent**: Safe to run multiple times
✅ **Flexible**: Target specific tickers, dates, or exchanges
✅ **Monitored**: Complete audit trail in metadata tables

**Most Common Use Case**:
```bash
# Reprocess specific tickers for specific dates
airflow dags trigger data_collection_equities --conf '{
  "tickers": ["AAPL", "MSFT"],
  "start_date": "2025-10-01",
  "end_date": "2025-10-27",
  "force_reprocess": true
}'
```
