# Delta Processing Strategy

## Table of Contents
1. [Overview](#overview)
2. [Delta Discovery Algorithm](#delta-discovery-algorithm)
3. [Processing Modes](#processing-modes)
4. [Idempotency Guarantees](#idempotency-guarantees)
5. [Duplicate Prevention](#duplicate-prevention)
6. [Reprocessing Workflows](#reprocessing-workflows)
7. [Error Handling](#error-handling)
8. [Examples](#examples)

---

## Overview

**Core Principle:** The same daily DAG run automatically determines what needs processing based on metadata state, eliminating the need for separate "bulk load" vs "incremental update" workflows.

### Delta Processing Flow

```
Daily DAG Trigger (21:30 UTC)
  ↓
Query metadata: asset_processing_state
  ↓
Classify each ticker:
  - New ticker → Bulk load (fundamentals + 2 years prices)
  - Existing, stale prices → Incremental (yesterday's price only)
  - Up-to-date → Skip
  - Failed recently → Retry
  - Reprocess flag set → Force reload
  ↓
Submit K8s Jobs with appropriate parameters
  ↓
Jobs update metadata after processing
  ↓
Next day: Process only what changed
```

**Benefits:**
- **No manual intervention** - Automatic catch-up for missing data
- **Optimal API usage** - Only fetch what's needed (1 call vs 11 calls)
- **Self-healing** - Automatically retries failed tickers
- **Resumable** - Crash recovery without duplicates

---

## Delta Discovery Algorithm

### Step 1: Load Ticker Universe

```python
def load_ticker_universe():
    """
    Read all ticker files from config/tickers/
    Returns: Set of 21,817 tickers
    """
    ticker_files = [
        'config/tickers/nyse.txt',      # 2,339 tickers
        'config/tickers/nasdaq.txt',    # 4,086 tickers
        'config/tickers/lse.txt',       # 3,145 tickers
        'config/tickers/frankfurt.txt', # 10,209 tickers
        # ... etc
    ]

    all_tickers = set()
    for file_path in ticker_files:
        with open(file_path) as f:
            tickers = {line.strip() for line in f if line.strip()}
            all_tickers.update(tickers)

    return all_tickers  # 21,817 total
```

### Step 2: Ensure All Tickers in Metadata

```python
def ensure_tickers_in_metadata(conn, all_tickers):
    """
    Insert any new tickers into asset_processing_state.
    Uses ON CONFLICT DO NOTHING for idempotency.
    """
    query = """
        INSERT INTO asset_processing_state (ticker)
        VALUES (%s)
        ON CONFLICT (ticker) DO NOTHING
    """

    # Batch insert
    cur = conn.cursor()
    cur.executemany(query, [(t,) for t in all_tickers])
    conn.commit()

    # Log results
    print(f"Inserted {cur.rowcount} new tickers into metadata")
```

**Why This Works:**
- First run: Inserts all 21,817 tickers
- Subsequent runs: Insert count = 0 (all already exist)
- New ticker added to config file: Automatically inserted
- **Idempotent** - Safe to run every day

### Step 3: Classify Each Ticker

```python
def discover_assets_delta(conn):
    """
    Query metadata to determine what each ticker needs.
    Returns dict with categorized ticker lists.
    """
    query = """
        SELECT
            ticker,
            fundamentals_loaded,
            prices_last_date,
            indicators_calculated_at,
            needs_fundamentals_reprocess,
            needs_prices_reprocess,
            needs_indicators_reprocess,
            consecutive_failures
        FROM asset_processing_state
        WHERE consecutive_failures < 5  -- Skip permanently failed
        ORDER BY ticker
    """

    cur = conn.cursor()
    cur.execute(query)

    results = {
        'bulk_load': [],           # New tickers or forced reprocess
        'price_update': [],        # Existing tickers needing daily update
        'indicator_calc': [],      # Tickers with stale indicators
        'up_to_date': [],          # No action needed
        'skipped_failed': []       # Too many failures
    }

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    for row in cur.fetchall():
        ticker = row['ticker']

        # Check for bulk load need
        if not row['fundamentals_loaded'] or row['needs_fundamentals_reprocess']:
            results['bulk_load'].append(ticker)
            continue

        # Check for price update need
        if row['prices_last_date'] is None or \
           row['prices_last_date'] < yesterday or \
           row['needs_prices_reprocess']:
            results['price_update'].append(ticker)

        # Check for indicator calculation need
        if not row['indicators_calculated_at'] or \
           row['indicators_calculated_at'].date() < today or \
           row['needs_indicators_reprocess']:
            results['indicator_calc'].append(ticker)

        # If all up-to-date
        if row['prices_last_date'] == yesterday and \
           row['indicators_calculated_at'] and \
           row['indicators_calculated_at'].date() == today:
            results['up_to_date'].append(ticker)

    return results
```

**Query Performance:**
- **Without metadata:** Query stock_prices table (5M+ rows, ~10 seconds on Pi)
- **With metadata:** Query asset_processing_state (21,817 rows, ~50ms on Pi)
- **200x faster** ✅

### Step 4: Decision Logic

```
For each ticker:

┌────────────────────────────────────────────────────────────┐
│ Decision Tree                                               │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  fundamentals_loaded = FALSE?                              │
│    ├─ YES → bulk_load (11 API calls)                       │
│    └─ NO  → Continue                                        │
│                                                             │
│  needs_fundamentals_reprocess = TRUE?                      │
│    ├─ YES → bulk_load (11 API calls)                       │
│    └─ NO  → Continue                                        │
│                                                             │
│  prices_last_date < CURRENT_DATE - 1?                      │
│    ├─ YES → price_update (1 API call)                      │
│    └─ NO  → Continue                                        │
│                                                             │
│  needs_prices_reprocess = TRUE?                            │
│    ├─ YES → price_update (1 API call)                      │
│    └─ NO  → Continue                                        │
│                                                             │
│  indicators_calculated_at < CURRENT_DATE?                  │
│    ├─ YES → indicator_calc (0 API calls)                   │
│    └─ NO  → Continue                                        │
│                                                             │
│  needs_indicators_reprocess = TRUE?                        │
│    ├─ YES → indicator_calc (0 API calls)                   │
│    └─ NO  → up_to_date (skip)                              │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

---

## Processing Modes

### Mode 1: Bulk Load (New Assets)

**Trigger Conditions:**
- `fundamentals_loaded = FALSE` (never loaded before)
- `needs_fundamentals_reprocess = TRUE` (manual flag)

**Operations:**
1. Fetch fundamentals from EODHD API (10 API calls)
2. Fetch 2 years of historical prices (1 API call)
3. Insert into `assets` table (with all 13 JSONB sections)
4. Insert into `stock_prices` table (~500 rows)
5. Update metadata:
   ```sql
   UPDATE asset_processing_state
   SET fundamentals_loaded = TRUE,
       fundamentals_loaded_at = NOW(),
       prices_loaded = TRUE,
       prices_first_date = '2023-10-21',
       prices_last_date = '2025-10-21',
       consecutive_failures = 0
   WHERE ticker = 'AAPL';
   ```

**API Cost:** 11 calls per ticker
**Time:** ~5 seconds per ticker (network I/O bound)

### Mode 2: Price Update (Existing Assets)

**Trigger Conditions:**
- `fundamentals_loaded = TRUE` (already loaded)
- `prices_last_date < CURRENT_DATE - 1` (missing yesterday's price)
- `needs_prices_reprocess = TRUE` (manual flag)

**Operations:**
1. Fetch yesterday's price only (1 API call)
2. Insert into `stock_prices` table (1 row)
   ```sql
   INSERT INTO stock_prices (asset_id, date, open, high, low, close, volume)
   VALUES (123, '2025-10-21', 150.0, 152.0, 149.0, 151.5, 50000000)
   ON CONFLICT (asset_id, date) DO NOTHING;  -- Idempotency
   ```
3. Update metadata:
   ```sql
   UPDATE asset_processing_state
   SET prices_last_date = '2025-10-21',
       prices_last_updated_at = NOW(),
       consecutive_failures = 0
   WHERE ticker = 'AAPL';
   ```

**API Cost:** 1 call per ticker
**Time:** ~1 second per ticker

### Mode 3: Indicator Calculation

**Trigger Conditions:**
- `indicators_calculated_at < CURRENT_DATE` (stale indicators)
- `needs_indicators_reprocess = TRUE` (manual flag)

**Operations:**
1. Fetch price data from `stock_prices` table (local, no API)
2. Calculate 30+ technical indicators (pandas-ta)
3. Upsert into `technical_indicators` table:
   ```sql
   INSERT INTO technical_indicators (asset_id, calculation_date, rsi_14, macd, ...)
   VALUES (123, '2025-10-21', 55.3, 2.1, ...)
   ON CONFLICT (asset_id, calculation_date)
   DO UPDATE SET rsi_14 = EXCLUDED.rsi_14, ...;  -- Idempotency
   ```
4. Update metadata:
   ```sql
   UPDATE asset_processing_state
   SET indicators_calculated = TRUE,
       indicators_calculated_at = NOW()
   WHERE ticker = 'AAPL';
   ```

**API Cost:** 0 calls (local computation)
**Time:** ~2 seconds per ticker (pandas calculations)

### Mode 4: Skip (Up-to-Date)

**Conditions:**
- `prices_last_date = CURRENT_DATE - 1`
- `indicators_calculated_at >= CURRENT_DATE`
- No reprocess flags set

**Operations:** None (skip processing)

---

## Idempotency Guarantees

### Database Layer

Every insert operation uses `ON CONFLICT` clauses:

```sql
-- Assets table: Prevent duplicate tickers
INSERT INTO assets (ticker, name, exchange, ...)
VALUES ('AAPL', 'Apple Inc.', 'NASDAQ', ...)
ON CONFLICT (ticker)
DO UPDATE SET name = EXCLUDED.name, ...;  -- Update if already exists

-- Stock prices: Prevent duplicate dates
INSERT INTO stock_prices (asset_id, date, open, high, low, close, volume)
VALUES (123, '2025-10-21', 150.0, 152.0, 149.0, 151.5, 50000000)
ON CONFLICT (asset_id, date)
DO NOTHING;  -- Silently skip if already exists

-- Technical indicators: Update if recalculated same day
INSERT INTO technical_indicators (asset_id, calculation_date, rsi_14, ...)
VALUES (123, '2025-10-21', 55.3, ...)
ON CONFLICT (asset_id, calculation_date)
DO UPDATE SET rsi_14 = EXCLUDED.rsi_14, ...;  -- Allow recalculation
```

### Application Layer

**Skip-Existing Flag:**
```python
# In main_enhanced.py
if args.skip_existing:
    # Check if ticker already processed today
    result = await db.fetch_one("""
        SELECT 1 FROM asset_processing_details
        WHERE ticker = $1
          AND operation = $2
          AND DATE(created_at) = CURRENT_DATE
          AND status = 'success'
    """, ticker, operation)

    if result:
        logger.info("ticker_already_processed", ticker=ticker)
        return True  # Skip
```

### Airflow Layer

**Prevent Concurrent Runs:**
```python
dag = DAG(
    'data_collection_equities',
    max_active_runs=1,  # Only one run at a time
    catchup=False,      # Don't backfill missed runs
)
```

**Result:** Running the same DAG 10 times produces the same result as running once ✅

---

## Duplicate Prevention

### Three-Layer Protection

```
Layer 1: Database Constraints (Primary)
  ↓
UNIQUE constraints on (ticker), (asset_id, date), (asset_id, calculation_date)
  ↓
Cannot insert duplicate rows - PostgreSQL prevents it
  ↓

Layer 2: Application Logic (Secondary)
  ↓
ON CONFLICT clauses in all INSERT statements
  ↓
Silently skip or update if duplicate detected
  ↓

Layer 3: Metadata Tracking (Tertiary)
  ↓
Check asset_processing_details before processing
  ↓
Skip if already processed today with success status
```

### Example Scenarios

**Scenario 1: DAG runs twice on same day**
```
Run 1 (21:30): Processes AAPL → prices_last_date = 2025-10-21
Run 2 (23:00): Checks metadata → prices_last_date = 2025-10-21 (current) → SKIP

Result: AAPL processed once ✅
API calls: 1 (not 2) ✅
```

**Scenario 2: Manual K8s Job + DAG both run**
```
Manual Job: Inserts price for AAPL on 2025-10-21
DAG Run: Attempts insert → ON CONFLICT DO NOTHING → No duplicate ✅

Result: One price record ✅
```

**Scenario 3: DAG crashes mid-execution, restarts**
```
First run: Processes 500 tickers, crashes
Restart: Checks metadata, sees 500 already have prices_last_date = today
→ Skips those 500, processes remaining 4,545 ✅

Result: All 5,045 processed exactly once ✅
```

---

## Reprocessing Workflows

### Use Case 1: Fix Bad Fundamentals Data

**Problem:** EODHD API returned incorrect data for AAPL

**Solution:**
```sql
-- Mark ticker for reprocessing
SELECT reset_ticker_for_reprocessing('AAPL', 'fundamentals');

-- Verify flag set
SELECT ticker, needs_fundamentals_reprocess
FROM asset_processing_state
WHERE ticker = 'AAPL';
-- Result: needs_fundamentals_reprocess = TRUE
```

**Next DAG Run:**
1. Delta discovery finds `needs_fundamentals_reprocess = TRUE`
2. Classifies AAPL as `bulk_load`
3. Fetches fresh fundamentals (10 API calls)
4. Updates assets table with new data
5. Clears flag: `needs_fundamentals_reprocess = FALSE`

### Use Case 2: Backfill Missing Prices

**Problem:** API was down 2024-12-15, all tickers missing that date

**Solution:**
```sql
-- Mark all tickers for price reprocessing
UPDATE asset_processing_state
SET needs_prices_reprocess = TRUE
WHERE prices_last_date < '2024-12-15';

-- Or use function for specific tickers
SELECT reset_ticker_for_reprocessing('AAPL', 'prices');
SELECT reset_ticker_for_reprocessing('MSFT', 'prices');
```

**Next DAG Run:**
1. Fetches prices for flagged tickers
2. Fills gap in stock_prices table
3. Clears flags

### Use Case 3: Recalculate All Indicators

**Problem:** Updated indicator calculation formula

**Solution:**
```sql
-- Mark all tickers for indicator reprocessing
UPDATE asset_processing_state
SET needs_indicators_reprocess = TRUE;
```

**Next DAG Run:**
1. Recalculates indicators for all 21,817 tickers
2. Updates technical_indicators table
3. Clears flags

**Alternative (via Airflow):**
```python
# Trigger DAG with config
airflow dags trigger calculate_indicators \
  --conf '{"force_recalculate": true}'
```

---

## Error Handling

### Transient Errors (Retry)

**Examples:**
- Network timeout
- API rate limit (429)
- Database connection lost

**Strategy:**
```python
# In application code
try:
    data = await fetch_fundamentals(ticker)
except (NetworkError, APIRateLimitError) as e:
    # Don't increment failure counter (transient)
    raise  # Let Airflow retry
```

**Airflow Retry:**
```python
default_args = {
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
}
```

### Persistent Errors (Track and Skip)

**Examples:**
- Ticker delisted (404)
- Invalid ticker symbol
- Data validation failure

**Strategy:**
```python
try:
    data = await fetch_fundamentals(ticker)
except TickerNotFoundError as e:
    # Increment failure counter
    await db.execute("""
        UPDATE asset_processing_state
        SET consecutive_failures = consecutive_failures + 1,
            last_error_at = NOW(),
            last_error_message = $1
        WHERE ticker = $2
    """, str(e), ticker)

    # Log to details table
    await log_processing_detail(
        execution_id, ticker, 'fundamentals_bulk',
        status='failed', error_message=str(e)
    )
```

**Skip After 5 Failures:**
```sql
-- Delta discovery query excludes chronic failures
SELECT ticker FROM asset_processing_state
WHERE fundamentals_loaded = FALSE
  AND consecutive_failures < 5  -- Skip after 5 attempts
```

### Failure Recovery

**Manual Investigation:**
```sql
-- Find failed tickers
SELECT ticker, consecutive_failures, last_error_message, last_error_at
FROM asset_processing_state
WHERE consecutive_failures >= 3
ORDER BY consecutive_failures DESC;

-- After fixing issue (e.g., correcting ticker symbol)
SELECT reset_ticker_for_reprocessing('OLD_TICKER', 'all');
```

---

## Examples

### Example 1: Initial Deployment (Day 1)

```
DAG Run 1 (Day 1, 21:30 UTC)

1. Load ticker universe: 21,817 tickers from config files
2. Ensure in metadata: 21,817 inserted into asset_processing_state
3. Delta discovery:
   - bulk_load: 21,817 (all new)
   - price_update: 0
   - up_to_date: 0

4. API quota check: 21,817 × 11 = 239,987 calls needed
   Daily limit: 100,000 → Can process ~9,090 tickers

5. Submit K8s Job: Process 9,000 tickers (batch-size=500)
   API calls used: 9,000 × 11 = 99,000

6. Update metadata: 9,000 tickers now have fundamentals_loaded=TRUE

Result: 9,000 / 21,817 complete (41%)
Remaining: 12,817 tickers
```

### Example 2: Catch-Up (Day 2)

```
DAG Run 2 (Day 2, 21:30 UTC)

1. Delta discovery:
   - bulk_load: 12,817 (yesterday's remainder)
   - price_update: 9,000 (yesterday's processed tickers need today's price)
   - up_to_date: 0

2. API quota: Fresh 100,000 calls available

3. Process priorities:
   a. Price updates: 9,000 × 1 = 9,000 API calls (quick)
   b. Bulk load: 9,000 × 11 = 99,000 API calls

   Total: 108,000 calls needed → Process 9,000 price updates + 8,000 bulk loads

Result: 17,000 / 21,817 complete (78%)
Remaining: 4,817 tickers
```

### Example 3: Steady State (Day 5)

```
DAG Run 5 (Day 5, 21:30 UTC)

All 21,817 tickers loaded.

1. Delta discovery:
   - bulk_load: 0
   - price_update: 21,817 (all need yesterday's price)
   - up_to_date: 0

2. API quota: 21,817 × 1 = 21,817 calls (well within limit)

3. Submit K8s Job: Process all tickers in incremental mode

4. Update metadata: All prices_last_date = 2025-10-25

5. Trigger indicator DAG: Calculate indicators for 21,817 tickers

Result: All tickers up-to-date ✅
API calls: 21,817 (not 239,987) ✅
Duration: ~6 hours (not 60 hours) ✅
```

### Example 4: Weekend Catch-Up (Monday)

```
Friday run: Completed successfully
Saturday: No DAG run (market closed)
Sunday: No DAG run (market closed)
Monday DAG Run (21:30 UTC)

1. Delta discovery:
   - price_update: 21,817 (prices_last_date = Friday, need Friday's close)
   - Note: Weekend dates have no trading data, so still need Friday

2. Process: Fetch Friday's prices for all tickers

Result: Automatically caught up after weekend ✅
```

---

## Next Steps

Proceed to:
- [04_DAG_DATA_COLLECTION.md](./04_DAG_DATA_COLLECTION.md) - Complete DAG implementation with code
- [05_DAG_INDICATORS.md](./05_DAG_INDICATORS.md) - Indicator calculation DAG

---

**Document Version:** 1.0
**Last Updated:** 2025-10-21
**Author:** Financial Screener Team
**Status:** Draft - Ready for Review
