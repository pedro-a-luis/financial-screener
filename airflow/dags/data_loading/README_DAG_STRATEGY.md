# Data Collection DAG Strategy

## Overview
Structured approach with separate DAGs for historical (one-time) and incremental (recurring) data collection per API source.

## DAG Structure

### 01 - Historical Prices (EODHD API) - ONE-TIME
- **File**: `dag_01_historical_prices.py`
- **Schedule**: Manual trigger only
- **Mode**: bulk (2 years)
- **Run Order**: 1st
- **Purpose**: Initial load of 2 years of OHLCV price data

### 02 - Incremental Prices (EODHD API) - DAILY
- **File**: `dag_02_incremental_prices.py`  
- **Schedule**: Daily at 22:00 UTC (after US market close)
- **Mode**: incremental (deltas only)
- **Run Order**: After dag_01 completes
- **Purpose**: Daily price updates (missing days only)

### 03 - Historical Fundamentals (EODHD API) - ONE-TIME
- **File**: `dag_03_historical_fundamentals.py`
- **Schedule**: Manual trigger only
- **Mode**: bulk (comprehensive)
- **Run Order**: 3rd (after prices loaded)
- **Purpose**: Initial load of comprehensive fundamentals (13 sections, 100+ fields)
- **Currently**: RUNNING via Kubernetes job `comprehensive-fundamentals-refresh`

### 04 - Incremental Fundamentals (EODHD API) - QUARTERLY
- **File**: `dag_04_incremental_fundamentals.py`
- **Schedule**: Quarterly (Jan 1, Apr 1, Jul 1, Oct 1 at 02:00 UTC)
- **Mode**: incremental (delta prices + full fundamentals refresh)
- **Run Order**: After dag_03 completes
- **Purpose**: Quarterly fundamentals refresh after earnings seasons

## Execution Order

**Initial Setup (ONE-TIME)**:
1. Run `dag_01_historical_prices` manually → Loads 2 years prices
2. Run `dag_03_historical_fundamentals` manually → Loads comprehensive fundamentals
3. Enable `dag_02_incremental_prices` → Auto-runs daily
4. Enable `dag_04_incremental_fundamentals` → Auto-runs quarterly

**Ongoing Operations**:
- `dag_02_incremental_prices`: Runs automatically daily at 22:00 UTC
- `dag_04_incremental_fundamentals`: Runs automatically quarterly

## Key Concepts

### Historical vs Incremental
- **Historical** (bulk mode): One-time initial load with 2 years of data
- **Incremental** (incremental mode): Ongoing delta updates (only missing data)

### API Sources
1. **EODHD Prices API** → dag_01 (historical) + dag_02 (incremental daily)
2. **EODHD Fundamentals API** → dag_03 (historical) + dag_04 (incremental quarterly)
3. **Technical Indicators** → Calculated from prices (no API), daily incremental only

### Mode Strategy
- **bulk**: Fetches 2 years prices + fundamentals (for initial load)
- **incremental**: Fetches delta prices + refreshes fundamentals (for updates)

## Current Status (2025-10-29)
- ✅ dag_03 (historical fundamentals) is RUNNING via K8s job
- ⏳ After completion, enable dag_04 for quarterly updates
- ⏳ dag_01 and dag_02 ready to run for price data
