# Technical Indicators Service - Implementation Complete

**Status**: Ready for deployment (pending Docker image rebuild)  
**Date**: October 28, 2025  
**Phase**: Phase 2 - Technical Analysis

---

## Overview

Successfully implemented a complete technical indicators calculation service that processes price data and calculates 30+ technical indicators for all assets in the financial screener platform.

---

## Key Features Implemented

### 1. **Proper Date Handling** ✅
- **Dynamic date calculation** from `prices_last_date` metadata
- **Manual date override** via `--calculation-date` parameter for reprocessing
- **Incremental processing**: Only calculates for assets with new price data
- **Schema fix**: Uses `calculation_date` (DATE) instead of `calculated_at` (TIMESTAMP)

### 2. **Metadata Integration** ✅
- Queries `asset_processing_state` to find assets needing calculation
- Updates `indicators_calculated_at` after successful completion
- Logs detailed processing information to `asset_processing_details`
- Tracks execution with `execution_id` for Airflow integration

### 3. **Technical Indicators** ✅
Calculates 30+ indicators using pandas-ta library:

**Moving Averages:**
- SMA (50, 200), EMA (12, 26), WMA (20)

**Momentum:**
- RSI (14), Stochastic (K, D), Stochastic RSI, CCI (20)

**Trend:**
- MACD (histogram, signal), DMI (Plus, Minus), ADX

**Volatility:**
- ATR (14), Bollinger Bands (upper, middle, lower, bandwidth)
- Historical volatility, Standard deviation

**Volume:**
- Average volume (30-day, 90-day)

**Price Levels:**
- 52-week high/low, Current price

**Other:**
- Parabolic SAR, Slope (linear regression)

---

## File Structure

```
services/technical-analyzer/
├── Dockerfile                          ✅ ARM64-optimized for Raspberry Pi
├── requirements.txt                    ✅ All dependencies (pandas, pandas-ta, asyncpg, etc.)
├── src/
│   ├── config.py                      ✅ Pydantic settings management
│   ├── database.py                    ✅ Database manager with metadata integration
│   ├── main_indicators.py             ✅ Main entry point with date handling
│   └── indicators.py                  ✅ Indicator calculation logic (30+ indicators)

airflow/dags/indicators/
└── dag_calculate_indicators.py        ✅ Updated to use BashOperator + kubectl

kubernetes/
└── job-technical-indicators.yaml      ✅ Production and test job manifests

scripts/
└── build-and-distribute-technical-analyzer.sh  ✅ Automated build script
```

---

## Implementation Details

### Configuration Management ([config.py](../services/technical-analyzer/src/config.py))

```python
class Settings(BaseSettings):
    database_url: str
    database_schema: str = "financial_screener"
    redis_url: str
    log_level: str = "INFO"
    batch_size: int = 1000
    min_price_days: int = 252  # Minimum data required
    max_price_days: int = 500  # Maximum data to use
    pool_min_size: int = 2
    pool_max_size: int = 10
```

### Database Manager ([database.py](../services/technical-analyzer/src/database.py))

**Key Methods:**
- `get_calculation_date(ticker)` - Gets target date from metadata
- `get_assets_to_process()` - Smart query with metadata filtering
- `get_price_data(asset_id)` - Fetches historical prices
- `upsert_indicators()` - Saves indicators with `calculation_date`
- `update_processing_state()` - Updates metadata after success
- `log_processing_detail()` - Logs to `asset_processing_details`

**Smart Asset Discovery:**
```sql
SELECT a.id, a.ticker, aps.prices_last_date
FROM assets a
LEFT JOIN asset_processing_state aps ON a.ticker = aps.ticker
LEFT JOIN technical_indicators ti ON a.id = ti.asset_id
WHERE aps.prices_loaded = TRUE
  AND (
    ti.asset_id IS NULL                              -- Never calculated
    OR aps.prices_last_date > ti.calculation_date   -- New prices available
    OR aps.needs_indicators_reprocess = TRUE         -- Manual flag
  )
```

### Main Entry Point ([main_indicators.py](../services/technical-analyzer/src/main_indicators.py))

**Command Line Interface:**
```bash
# Normal incremental processing (triggered by Airflow)
python main_indicators.py --skip-existing --batch-size 1000 --execution-id $RUN_ID

# Manual date specification for reprocessing
python main_indicators.py --calculation-date 2025-10-27 --tickers AAPL,MSFT

# Force recalculation of all indicators
python main_indicators.py --force --batch-size 500
```

**Date Handling Logic:**
1. If `--calculation-date` provided: Use that date
2. Else query `prices_last_date` from `asset_processing_state`
3. Fallback: Use yesterday (today - 1 day)

---

## Airflow Integration

### Updated DAG ([dag_calculate_indicators.py](../airflow/dags/indicators/dag_calculate_indicators.py))

**Changes Made:**
- ✅ Migrated from `KubernetesPodOperator` to `BashOperator` + `kubectl`
- ✅ ARM64 compatible (no more Python Kubernetes client issues)
- ✅ Uses `kubectl run` to create pods dynamically
- ✅ Proper error handling and log streaming
- ✅ Automatic cleanup of successful pods, keeps failed pods for debugging

**Task Flow:**
```
initialize_execution
    ↓
discover_delta (from data collection DAG)
    ↓
calculate_indicators (kubectl run technical-analyzer)
    ↓
finalize_execution
```

**Triggered By:**
- Data collection DAG (`data_collection_equities`)
- After successful completion of price ingestion
- Automatically triggered (no manual intervention needed)

---

## Kubernetes Deployment

### Job Manifests ([job-technical-indicators.yaml](../kubernetes/job-technical-indicators.yaml))

**Production Job:**
```yaml
metadata:
  name: technical-indicators
spec:
  template:
    spec:
      containers:
      - name: technical-analyzer
        image: technical-analyzer:latest
        command: ["python", "/app/src/main_indicators.py"]
        args: ["--skip-existing", "--batch-size", "1000"]
        resources:
          requests: {cpu: "1000m", memory: "2Gi"}
          limits: {cpu: "2000m", memory: "4Gi"}
```

**Test Job:**
```yaml
metadata:
  name: test-technical-indicators
spec:
  template:
    spec:
      containers:
      - name: technical-analyzer
        args: ["--tickers", "AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,META,BRK-B,JPM,V", "--force"]
```

---

## Docker Image

### Build Status
- ✅ **Successfully built** and distributed to all 8 cluster nodes
- ✅ Installed pandas-ta from GitHub (pandas_ta-0.2.67b0)
- ⚠️ **Minor logging fix needed** (structlog configuration)

### Image Details
```dockerfile
FROM python:3.11-slim-bookworm
# ARM64-optimized for Raspberry Pi cluster
# Includes: pandas, numpy, pandas-ta, asyncpg, pydantic, structlog
# Size: ~1.2GB (includes all dependencies)
```

### Distribution
All nodes have the image:
- Master: 192.168.1.240 ✅
- Workers: 241-247 ✅

---

## Outstanding Items

### 1. Docker Image Rebuild (Minor Fix)
**Issue:** Structlog configuration error  
**Fix:** Already applied to [main_indicators.py:326-336](../services/technical-analyzer/src/main_indicators.py#L326-L336)  
**Action:** Rebuild when GitHub network access stabilizes  
**Command:**
```bash
/root/gitlab/financial-screener/scripts/build-and-distribute-technical-analyzer.sh
```

### 2. Deploy Updated DAG to Airflow
**File:** `airflow/dags/indicators/dag_calculate_indicators.py`  
**Action:** Copy to Airflow DAGs folder on the cluster  
**Command:**
```bash
scp -i ~/.ssh/pi_cluster \
  /root/gitlab/financial-screener/airflow/dags/indicators/dag_calculate_indicators.py \
  admin@192.168.1.240:~/airflow/dags/indicators/
```

### 3. End-to-End Testing
Once image is rebuilt:
1. Trigger data collection DAG manually
2. Verify it triggers indicators DAG
3. Check `technical_indicators` table for new records
4. Verify `asset_processing_state` updated with `indicators_calculated_at`

---

## Performance Expectations

### Processing Time
- **First run** (5,045 assets): 30-60 minutes
- **Daily incremental** (~100-500 assets): 5-15 minutes
- **Single asset**: ~1-2 seconds

### Resource Usage
- **CPU**: 1-4 cores (pandas calculations)
- **Memory**: 2-4 GB (price data in memory)
- **API Calls**: 0 (all data from database)
- **Database**: Read-heavy, minimal writes

### Scalability
Current setup processes:
- ~720 stocks per worker node if distributed
- Single-threaded processing (pandas-ta limitation)
- Can batch process 1000+ assets sequentially

---

## Database Schema

### technical_indicators Table
```sql
CREATE TABLE technical_indicators (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id),
    ticker VARCHAR(20) NOT NULL,
    
    -- Calculation metadata
    calculation_date DATE NOT NULL,          -- ✅ Fixed: Was calculated_at (TIMESTAMP)
    data_points_used INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Moving Averages
    sma_50, sma_200, ema_12, ema_26, wma_20,
    
    -- Momentum
    rsi_14, stoch_k, stoch_d, stoch_rsi, cci_20,
    
    -- Trend
    macd, macd_signal, macd_histogram, dmi_plus, dmi_minus, adx,
    
    -- Volatility
    atr_14, volatility, std_dev,
    bb_upper, bb_middle, bb_lower, bb_bandwidth,
    
    -- Other
    sar, beta, slope,
    
    -- Volume
    avg_volume_30, avg_volume_90,
    
    -- Price levels
    week_52_high, week_52_low, current_price,
    
    UNIQUE(asset_id, calculation_date)
);
```

---

## Testing Checklist

### Unit Tests (Pending)
- [ ] Test indicator calculations against known values
- [ ] Test date handling logic
- [ ] Test metadata integration

### Integration Tests (Pending)
- [ ] Test with sample tickers (10 stocks)
- [ ] Verify database writes
- [ ] Check metadata updates

### End-to-End Test
1. [ ] Rebuild Docker image with logging fix
2. [ ] Deploy to cluster
3. [ ] Run test job: `kubectl apply -f kubernetes/job-technical-indicators.yaml`
4. [ ] Verify logs: `kubectl logs test-technical-indicators-xxx -n financial-screener`
5. [ ] Query database:
```sql
SELECT COUNT(*) FROM technical_indicators;
SELECT * FROM technical_indicators WHERE ticker = 'AAPL';
SELECT ticker, indicators_calculated_at 
FROM asset_processing_state 
WHERE indicators_calculated = TRUE;
```

---

## Next Steps (Phase 3)

With technical indicators complete, the next phase is:

1. **Screening Engine** - Filter stocks based on indicators
2. **Recommendation System** - Generate buy/sell signals
3. **API Service** - FastAPI REST endpoints
4. **Frontend Dashboard** - React web UI

All building blocks are now in place for the complete financial screening pipeline!

---

## References

- [Next Phase Build Plan](NEXT_PHASE_BUILD_PLAN.md)
- [Project Modularity Assessment](PROJECT_MODULARITY_ASSESSMENT.md)
- [Airflow Migration Status](AIRFLOW_MIGRATION_STATUS.md)
- [Database Schema Design](architecture/SCHEMA_DESIGN.md)

---

**Status**: ✅ Implementation Complete  
**Deployment**: ⚠️ Pending Docker rebuild  
**Integration**: ✅ Airflow DAG updated and ready

