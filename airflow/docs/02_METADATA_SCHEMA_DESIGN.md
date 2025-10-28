# Metadata Schema Design

## Table of Contents
1. [Overview](#overview)
2. [Schema Diagram](#schema-diagram)
3. [Table Specifications](#table-specifications)
4. [State Transitions](#state-transitions)
5. [Indexes and Performance](#indexes-and-performance)
6. [Views and Helper Functions](#views-and-helper-functions)
7. [Complete Migration SQL](#complete-migration-sql)

---

## Overview

The metadata schema provides a **separate layer** for process orchestration, distinct from business data tables. This separation enables:

✅ **Fast delta discovery** - Query metadata, not millions of price records
✅ **Process traceability** - Link every operation to a DAG run
✅ **State management** - Track what's loaded, what failed, what needs reprocessing
✅ **Audit trail** - Complete history of all operations
✅ **Idempotency** - Prevent duplicate processing

### Metadata Tables

| Table | Purpose | Records | Growth Rate |
|-------|---------|---------|-------------|
| `process_executions` | DAG run tracking | ~365/year per DAG | 1 per DAG run |
| `asset_processing_state` | Per-ticker state | 21,817 (fixed) | Static (one per ticker) |
| `asset_processing_details` | Operation logs | ~8M/year | ~21K per day |

**Storage Estimate:**
- Metadata tables: ~2 GB/year
- Business tables (prices): ~50 GB/year
- Ratio: Metadata is 4% of business data

---

## Schema Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       METADATA SCHEMA (financial_screener)               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ process_executions                                              │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ PK  id                    BIGSERIAL                             │    │
│  │     process_name          VARCHAR(100)  'data_collection_...'   │    │
│  │     execution_id          VARCHAR(255)  Airflow run_id (unique) │    │
│  │     parameters            JSONB         {mode, batch_size, ...} │    │
│  │     status                VARCHAR(20)   'running'/'success'/... │    │
│  │     assets_discovered     INTEGER                               │    │
│  │     assets_processed      INTEGER                               │    │
│  │     assets_succeeded      INTEGER                               │    │
│  │     assets_failed         INTEGER                               │    │
│  │     api_calls_used        INTEGER                               │    │
│  │     started_at            TIMESTAMP                             │    │
│  │     completed_at          TIMESTAMP                             │    │
│  │     duration_seconds      INTEGER                               │    │
│  │     error_message         TEXT                                  │    │
│  │     error_details         JSONB                                 │    │
│  │     created_at            TIMESTAMP                             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                               │                                           │
│                               │ 1:N                                       │
│                               ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ asset_processing_details                                        │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ PK  id                    BIGSERIAL                             │    │
│  │ FK  execution_id          VARCHAR(255) → process_executions     │    │
│  │     ticker                VARCHAR(20)                           │    │
│  │     operation             VARCHAR(50)   'fundamentals_bulk'     │    │
│  │     status                VARCHAR(20)   'success'/'failed'      │    │
│  │     records_inserted      INTEGER                               │    │
│  │     records_updated       INTEGER                               │    │
│  │     api_calls_used        INTEGER                               │    │
│  │     error_message         TEXT                                  │    │
│  │     error_code            VARCHAR(50)                           │    │
│  │     started_at            TIMESTAMP                             │    │
│  │     completed_at          TIMESTAMP                             │    │
│  │     duration_ms           INTEGER                               │    │
│  │     created_at            TIMESTAMP                             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ asset_processing_state (State Machine)                          │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ PK  id                           BIGSERIAL                      │    │
│  │ UK  ticker                       VARCHAR(20) UNIQUE             │    │
│  │                                                                  │    │
│  │     -- Data Collection State                                    │    │
│  │     fundamentals_loaded          BOOLEAN                        │    │
│  │     fundamentals_loaded_at       TIMESTAMP                      │    │
│  │     fundamentals_execution_id    VARCHAR(255)                   │    │
│  │                                                                  │    │
│  │     prices_loaded                BOOLEAN                        │    │
│  │     prices_first_date            DATE                           │    │
│  │     prices_last_date             DATE                           │    │
│  │     prices_last_updated_at       TIMESTAMP                      │    │
│  │     prices_execution_id          VARCHAR(255)                   │    │
│  │                                                                  │    │
│  │     -- Indicators State                                         │    │
│  │     indicators_calculated        BOOLEAN                        │    │
│  │     indicators_calculated_at     TIMESTAMP                      │    │
│  │     indicators_execution_id      VARCHAR(255)                   │    │
│  │                                                                  │    │
│  │     -- Reprocessing Flags                                       │    │
│  │     needs_fundamentals_reprocess BOOLEAN                        │    │
│  │     needs_prices_reprocess       BOOLEAN                        │    │
│  │     needs_indicators_reprocess   BOOLEAN                        │    │
│  │                                                                  │    │
│  │     -- Failure Tracking                                         │    │
│  │     last_error_at                TIMESTAMP                      │    │
│  │     last_error_message           TEXT                           │    │
│  │     consecutive_failures         INTEGER                        │    │
│  │                                                                  │    │
│  │     created_at                   TIMESTAMP                      │    │
│  │     updated_at                   TIMESTAMP                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Table Specifications

### 1. process_executions

**Purpose:** Track every DAG run execution with full parameters and results.

**Cardinality:** ~1,000 rows/year (2-3 DAG runs per day)

**Sample Row:**
```json
{
  "id": 1234,
  "process_name": "data_collection_equities",
  "execution_id": "manual__2025-10-21T21:30:00+00:00",
  "parameters": {
    "dag_id": "data_collection_equities",
    "run_id": "manual__2025-10-21T21:30:00+00:00",
    "mode": "daily",
    "new_assets_count": 0,
    "update_count": 5045,
    "batch_size": 500
  },
  "status": "success",
  "assets_discovered": 21817,
  "assets_processed": 5045,
  "assets_succeeded": 5038,
  "assets_failed": 7,
  "api_calls_used": 5045,
  "started_at": "2025-10-21 21:30:00",
  "completed_at": "2025-10-21 22:15:00",
  "duration_seconds": 2700,
  "error_message": null
}
```

**Status Values:**
- `running` - Execution in progress
- `success` - Completed successfully (all or most assets processed)
- `partial` - Completed but with significant failures (>10%)
- `failed` - Critical failure (DAG level error)

**Queries:**

```sql
-- Today's executions
SELECT * FROM process_executions
WHERE DATE(started_at) = CURRENT_DATE
ORDER BY started_at DESC;

-- Execution summary (last 7 days)
SELECT
    process_name,
    COUNT(*) as runs,
    AVG(duration_seconds) as avg_duration_sec,
    SUM(assets_processed) as total_processed,
    SUM(api_calls_used) as total_api_calls
FROM process_executions
WHERE started_at > NOW() - INTERVAL '7 days'
GROUP BY process_name;

-- Failed executions
SELECT execution_id, process_name, error_message, started_at
FROM process_executions
WHERE status IN ('failed', 'partial')
ORDER BY started_at DESC
LIMIT 20;
```

---

### 2. asset_processing_state

**Purpose:** State machine tracking processing status of each ticker.

**Cardinality:** 21,817 rows (one per ticker, static)

**Sample Row:**
```json
{
  "id": 1,
  "ticker": "AAPL",
  "fundamentals_loaded": true,
  "fundamentals_loaded_at": "2025-10-15 22:45:00",
  "fundamentals_execution_id": "scheduled__2025-10-15T21:30:00+00:00",
  "prices_loaded": true,
  "prices_first_date": "2023-10-21",
  "prices_last_date": "2025-10-21",
  "prices_last_updated_at": "2025-10-21 21:45:00",
  "prices_execution_id": "scheduled__2025-10-21T21:30:00+00:00",
  "indicators_calculated": true,
  "indicators_calculated_at": "2025-10-21 23:10:00",
  "indicators_execution_id": "scheduled__2025-10-21T23:00:00+00:00",
  "needs_fundamentals_reprocess": false,
  "needs_prices_reprocess": false,
  "needs_indicators_reprocess": false,
  "last_error_at": null,
  "last_error_message": null,
  "consecutive_failures": 0,
  "created_at": "2025-10-15 22:45:00",
  "updated_at": "2025-10-21 23:10:00"
}
```

**State Transitions:**

```
New Ticker (not in table)
  ↓
fundamentals_loaded = FALSE, prices_loaded = FALSE
  ↓
[Bulk Load Execution]
  ↓
fundamentals_loaded = TRUE, prices_loaded = TRUE
prices_first_date = 2023-10-21, prices_last_date = 2025-10-21
  ↓
[Daily Price Update]
  ↓
prices_last_date = 2025-10-22 (updated)
  ↓
[Indicator Calculation]
  ↓
indicators_calculated = TRUE, indicators_calculated_at = NOW()
  ↓
[Daily Loop: Update prices → Recalculate indicators]
```

**Queries:**

```sql
-- Delta discovery: Assets needing fundamentals (bulk load)
SELECT ticker FROM asset_processing_state
WHERE fundamentals_loaded = FALSE
   OR needs_fundamentals_reprocess = TRUE
ORDER BY ticker;

-- Delta discovery: Assets needing price update
SELECT ticker FROM asset_processing_state
WHERE fundamentals_loaded = TRUE
  AND (prices_last_date < CURRENT_DATE - 1
       OR needs_prices_reprocess = TRUE)
ORDER BY ticker;

-- Delta discovery: Assets needing indicators
SELECT ticker FROM asset_processing_state
WHERE prices_loaded = TRUE
  AND (indicators_calculated = FALSE
       OR indicators_calculated_at < CURRENT_DATE
       OR needs_indicators_reprocess = TRUE)
ORDER BY ticker;

-- Assets with consecutive failures (skip for now)
SELECT ticker, consecutive_failures, last_error_message
FROM asset_processing_state
WHERE consecutive_failures >= 3
ORDER BY consecutive_failures DESC;

-- Processing progress summary
SELECT
    COUNT(*) as total_tickers,
    COUNT(*) FILTER (WHERE fundamentals_loaded) as fundamentals_complete,
    COUNT(*) FILTER (WHERE prices_last_date = CURRENT_DATE - 1) as prices_up_to_date,
    COUNT(*) FILTER (WHERE indicators_calculated_at >= CURRENT_DATE) as indicators_current,
    ROUND(100.0 * COUNT(*) FILTER (WHERE fundamentals_loaded) / COUNT(*), 2) as pct_complete
FROM asset_processing_state;
```

---

### 3. asset_processing_details

**Purpose:** Granular log of each operation on each ticker in each execution.

**Cardinality:** ~8 million rows/year (21K tickers × 365 days)

**Sample Row:**
```json
{
  "id": 50123,
  "execution_id": "scheduled__2025-10-21T21:30:00+00:00",
  "ticker": "AAPL",
  "operation": "prices_incremental",
  "status": "success",
  "records_inserted": 1,
  "records_updated": 0,
  "api_calls_used": 1,
  "error_message": null,
  "error_code": null,
  "started_at": "2025-10-21 21:32:15",
  "completed_at": "2025-10-21 21:32:18",
  "duration_ms": 3200,
  "created_at": "2025-10-21 21:32:18"
}
```

**Operation Values:**
- `fundamentals_bulk` - Initial load (10 API calls)
- `prices_bulk` - 2 years of prices (1 API call)
- `prices_incremental` - Yesterday's price (1 API call)
- `indicators_calc` - Technical indicators (0 API calls)

**Status Values:**
- `success` - Operation completed
- `failed` - API error, network error, data validation error
- `skipped` - Already processed (skip-existing logic)

**Queries:**

```sql
-- Today's processing details
SELECT
    operation,
    status,
    COUNT(*) as count,
    SUM(api_calls_used) as total_api_calls,
    AVG(duration_ms) as avg_duration_ms
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE
GROUP BY operation, status
ORDER BY operation, status;

-- Failed operations today
SELECT ticker, operation, error_message, created_at
FROM asset_processing_details
WHERE status = 'failed'
  AND DATE(created_at) = CURRENT_DATE
ORDER BY created_at DESC;

-- Slowest operations
SELECT ticker, operation, duration_ms, created_at
FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE
ORDER BY duration_ms DESC
LIMIT 20;

-- API usage by execution
SELECT
    execution_id,
    SUM(api_calls_used) as total_api_calls,
    COUNT(*) as operations
FROM asset_processing_details
WHERE execution_id = 'scheduled__2025-10-21T21:30:00+00:00'
GROUP BY execution_id;
```

---

## State Transitions

### Ticker Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TICKER LIFECYCLE                             │
└─────────────────────────────────────────────────────────────────────┘

State 0: NOT IN asset_processing_state
  │
  │ DAG discovers ticker in config files
  │
  ▼
State 1: NEW TICKER
  fundamentals_loaded = FALSE
  prices_loaded = FALSE
  │
  │ bulk load execution
  │
  ▼
State 2: FUNDAMENTALS LOADED
  fundamentals_loaded = TRUE
  fundamentals_loaded_at = timestamp
  prices_loaded = TRUE
  prices_first_date = 2023-10-21
  prices_last_date = 2025-10-21
  │
  │ daily price update
  │
  ▼
State 3: PRICES CURRENT
  prices_last_date = CURRENT_DATE - 1
  prices_last_updated_at = timestamp
  │
  │ indicator calculation
  │
  ▼
State 4: INDICATORS CURRENT
  indicators_calculated = TRUE
  indicators_calculated_at = timestamp
  │
  │
  ▼
State 5: FULLY UP-TO-DATE (steady state)
  fundamentals_loaded = TRUE
  prices_last_date = CURRENT_DATE - 1
  indicators_calculated_at = CURRENT_DATE
  │
  │ [Daily Loop]
  │ - Update prices (State 3)
  │ - Recalculate indicators (State 4)
  │
  └──► Repeat daily

┌─────────────────────────────────────────────────────────────────────┐
│                         ERROR STATES                                 │
└─────────────────────────────────────────────────────────────────────┘

TRANSIENT FAILURE:
  consecutive_failures = 1-2
  → Retry next execution

PERSISTENT FAILURE:
  consecutive_failures >= 3
  → Skip until manual investigation
  → Set needs_*_reprocess = TRUE after fix

REPROCESSING REQUESTED:
  needs_fundamentals_reprocess = TRUE
  → Force bulk reload on next execution
  → Clear flag after successful reload
```

---

## Indexes and Performance

### Index Strategy

```sql
-- =====================================================
-- PROCESS_EXECUTIONS INDEXES
-- =====================================================

-- Query: Recent executions by process name
CREATE INDEX idx_process_exec_name_date
ON process_executions(process_name, started_at DESC);

-- Query: Lookup by execution_id
CREATE INDEX idx_process_exec_id
ON process_executions(execution_id);

-- Query: Failed/partial executions
CREATE INDEX idx_process_exec_status
ON process_executions(status, started_at DESC)
WHERE status IN ('failed', 'partial');

-- =====================================================
-- ASSET_PROCESSING_STATE INDEXES
-- =====================================================

-- Primary key
CREATE UNIQUE INDEX idx_asset_state_ticker
ON asset_processing_state(ticker);

-- Query: Delta discovery (fundamentals)
CREATE INDEX idx_asset_state_needs_fundamentals
ON asset_processing_state(fundamentals_loaded, needs_fundamentals_reprocess)
WHERE fundamentals_loaded = FALSE
   OR needs_fundamentals_reprocess = TRUE;

-- Query: Delta discovery (prices)
CREATE INDEX idx_asset_state_prices_stale
ON asset_processing_state(prices_last_date)
WHERE prices_last_date < CURRENT_DATE - 1;

-- Query: Delta discovery (indicators)
CREATE INDEX idx_asset_state_indicators_stale
ON asset_processing_state(indicators_calculated_at)
WHERE indicators_calculated_at < CURRENT_DATE;

-- Query: Failed assets
CREATE INDEX idx_asset_state_failures
ON asset_processing_state(consecutive_failures)
WHERE consecutive_failures > 0;

-- =====================================================
-- ASSET_PROCESSING_DETAILS INDEXES
-- =====================================================

-- Query: Details by execution
CREATE INDEX idx_asset_details_execution
ON asset_processing_details(execution_id, created_at DESC);

-- Query: History for a ticker
CREATE INDEX idx_asset_details_ticker
ON asset_processing_details(ticker, created_at DESC);

-- Query: Failed operations
CREATE INDEX idx_asset_details_status
ON asset_processing_details(status, created_at DESC)
WHERE status = 'failed';

-- Query: Today's operations (for aggregations)
CREATE INDEX idx_asset_details_date
ON asset_processing_details(DATE(created_at), operation, status);
```

### Performance Estimates

**Query:** Find tickers needing price updates
```sql
SELECT ticker FROM asset_processing_state
WHERE prices_last_date < CURRENT_DATE - 1;
```
**Without Index:** 21,817 row scan (~50ms on Pi)
**With Index:** ~100 rows returned (~5ms)

**Query:** Today's API usage
```sql
SELECT SUM(api_calls_used) FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE;
```
**Without Index:** Full table scan of millions of rows (~5s)
**With Index:** Index-only scan (~50ms)

---

## Views and Helper Functions

### View: v_assets_needing_processing

```sql
CREATE VIEW v_assets_needing_processing AS
SELECT
    ticker,
    CASE
        WHEN fundamentals_loaded = FALSE OR needs_fundamentals_reprocess = TRUE
            THEN 'bulk_load'
        WHEN prices_last_date < CURRENT_DATE - 1 OR needs_prices_reprocess = TRUE
            THEN 'price_update'
        WHEN indicators_calculated = FALSE
             OR indicators_calculated_at < CURRENT_DATE
             OR needs_indicators_reprocess = TRUE
            THEN 'indicator_calc'
        ELSE 'up_to_date'
    END as processing_need,
    prices_last_date,
    indicators_calculated_at,
    consecutive_failures
FROM asset_processing_state
WHERE consecutive_failures < 5  -- Skip permanently broken tickers
ORDER BY
    CASE processing_need
        WHEN 'bulk_load' THEN 1
        WHEN 'price_update' THEN 2
        WHEN 'indicator_calc' THEN 3
        ELSE 4
    END,
    ticker;
```

### View: v_daily_execution_summary

```sql
CREATE VIEW v_daily_execution_summary AS
SELECT
    DATE(started_at) as execution_date,
    process_name,
    COUNT(*) as runs,
    SUM(assets_processed) as total_assets,
    SUM(assets_succeeded) as total_succeeded,
    SUM(assets_failed) as total_failed,
    SUM(api_calls_used) as total_api_calls,
    AVG(duration_seconds) as avg_duration_sec
FROM process_executions
WHERE started_at > CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(started_at), process_name
ORDER BY execution_date DESC, process_name;
```

### View: v_ticker_processing_status

```sql
CREATE VIEW v_ticker_processing_status AS
SELECT
    aps.ticker,
    aps.fundamentals_loaded,
    aps.prices_last_date,
    CURRENT_DATE - aps.prices_last_date as days_since_price_update,
    aps.indicators_calculated_at,
    CURRENT_DATE - DATE(aps.indicators_calculated_at) as days_since_indicator_calc,
    aps.consecutive_failures,
    aps.last_error_message,
    a.name,
    a.exchange,
    a.asset_type
FROM asset_processing_state aps
LEFT JOIN assets a ON a.ticker = aps.ticker
ORDER BY aps.ticker;
```

### Function: reset_ticker_for_reprocessing

```sql
CREATE OR REPLACE FUNCTION reset_ticker_for_reprocessing(
    p_ticker VARCHAR(20),
    p_component VARCHAR(50) DEFAULT 'all'  -- 'fundamentals', 'prices', 'indicators', 'all'
)
RETURNS VOID AS $$
BEGIN
    IF p_component = 'all' THEN
        UPDATE asset_processing_state
        SET needs_fundamentals_reprocess = TRUE,
            needs_prices_reprocess = TRUE,
            needs_indicators_reprocess = TRUE,
            consecutive_failures = 0
        WHERE ticker = p_ticker;
    ELSIF p_component = 'fundamentals' THEN
        UPDATE asset_processing_state
        SET needs_fundamentals_reprocess = TRUE,
            consecutive_failures = 0
        WHERE ticker = p_ticker;
    ELSIF p_component = 'prices' THEN
        UPDATE asset_processing_state
        SET needs_prices_reprocess = TRUE,
            consecutive_failures = 0
        WHERE ticker = p_ticker;
    ELSIF p_component = 'indicators' THEN
        UPDATE asset_processing_state
        SET needs_indicators_reprocess = TRUE,
            consecutive_failures = 0
        WHERE ticker = p_ticker;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Usage:
-- SELECT reset_ticker_for_reprocessing('AAPL', 'fundamentals');
-- SELECT reset_ticker_for_reprocessing('MSFT', 'all');
```

---

## Complete Migration SQL

See: `/root/gitlab/financial-screener/database/migrations/005_process_metadata_tables.sql`

(To be created in next step - this will contain the full DDL)

---

## Next Steps

Proceed to:
- [03_DELTA_PROCESSING_STRATEGY.md](./03_DELTA_PROCESSING_STRATEGY.md) - How delta discovery works
- [04_DAG_DATA_COLLECTION.md](./04_DAG_DATA_COLLECTION.md) - Complete DAG implementation

---

**Document Version:** 1.0
**Last Updated:** 2025-10-21
**Author:** Financial Screener Team
**Status:** Draft - Ready for Review
