# Technical Analyzer Service

**Status:** 🔜 **PLANNED** (Phase 3 - Q1 2025)

## Purpose
Calculate technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands) from historical price data using Polars for high-performance computation.

## Planned Implementation

### Architecture
- **Processing Engine:** Polars (Rust-based DataFrame library)
- **Orchestration:** Airflow DAG (scheduled after price updates)
- **Data Source:** `historical_prices` table (TimescaleDB hypertable)
- **Data Target:** `technical_indicators` table
- **Deployment:** Kubernetes Job (parallel processing by exchange)

### Technical Indicators
1. **Moving Averages:**
   - SMA (Simple Moving Average): 20, 50, 200-day
   - EMA (Exponential Moving Average): 12, 26-day

2. **Momentum Indicators:**
   - RSI (Relative Strength Index): 14-day
   - MACD (Moving Average Convergence Divergence)
   - Stochastic Oscillator

3. **Volatility Indicators:**
   - Bollinger Bands (20-day, 2σ)
   - ATR (Average True Range)

4. **Volume Indicators:**
   - OBV (On-Balance Volume)
   - Volume SMA

### Performance Targets
- **Processing Speed:** 21,817 tickers in <15 minutes
- **Parallelization:** 8 workers (one per Pi node)
- **Memory Usage:** <1GB per worker
- **Why Polars:** 2-10x faster than Pandas on ARM64

### Database Schema
Table already exists: `technical_indicators`
```sql
CREATE TABLE technical_indicators (
    ticker VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    sma_20 DECIMAL(12,2),
    sma_50 DECIMAL(12,2),
    sma_200 DECIMAL(12,2),
    ema_12 DECIMAL(12,2),
    ema_26 DECIMAL(12,2),
    rsi_14 DECIMAL(5,2),
    macd DECIMAL(12,2),
    macd_signal DECIMAL(12,2),
    macd_histogram DECIMAL(12,2),
    bollinger_upper DECIMAL(12,2),
    bollinger_middle DECIMAL(12,2),
    bollinger_lower DECIMAL(12,2),
    PRIMARY KEY (ticker, date)
);
```

## Dependencies
**Prerequisites:**
- ✅ Phase 2 complete (data-collector operational)
- ✅ Historical prices loaded (2 years minimum)
- ✅ TimescaleDB hypertable working

**Technology Stack:**
- Python 3.11+
- Polars 0.19+ (with lazy evaluation)
- PostgreSQL connector (asyncpg or psycopg3)
- Kubernetes for orchestration

## Implementation Plan

### Step 1: Core Engine (Week 1)
```python
# src/calculator.py
import polars as pl

def calculate_sma(df: pl.DataFrame, window: int) -> pl.Series:
    return df['close'].rolling_mean(window)

def calculate_rsi(df: pl.DataFrame, period: int = 14) -> pl.Series:
    # RSI calculation using Polars
    pass

# Batch processing for efficiency
def process_ticker(ticker: str, lazy: bool = True):
    # Load from database using Polars lazy scan
    df = pl.scan_csv(...)  # or read from database

    # Calculate all indicators in one pass
    result = df.with_columns([
        pl.col('close').rolling_mean(20).alias('sma_20'),
        pl.col('close').rolling_mean(50).alias('sma_50'),
        # ... other indicators
    ])

    return result.collect()  # Execute lazy query
```

### Step 2: Airflow Integration (Week 2)
- Create `dag_calculate_indicators.py`
- Trigger after `data_collection_equities` completes
- Parallel processing by exchange (4-8 jobs)

### Step 3: Testing & Validation (Week 3)
- Unit tests for indicator calculations
- Compare against TA-Lib for accuracy
- Performance benchmarking

### Step 4: Production Deployment (Week 4)
- Build Docker image
- Deploy to Kubernetes
- Schedule daily execution

## Timeline
- **Start Date:** After Phase 2 testing complete (early Q1 2025)
- **Duration:** 4 weeks
- **Go-Live:** Late Q1 2025

## Success Metrics
- [ ] All 21,817 tickers processed successfully
- [ ] Processing time <15 minutes
- [ ] 99.9% accuracy vs TA-Lib
- [ ] Zero memory leaks
- [ ] Automatic recovery from failures

## Related Documentation
- [003_technical_indicators_table.sql](../../database/migrations/003_technical_indicators_table.sql)
- [Polars Documentation](https://pola-rs.github.io/polars/)

## Notes
- Consider using Polars' lazy API for memory efficiency
- Implement incremental calculation (only new dates)
- Add validation against known-good values (TA-Lib)
- Monitor memory usage per worker

**Last Updated:** 2025-10-28
