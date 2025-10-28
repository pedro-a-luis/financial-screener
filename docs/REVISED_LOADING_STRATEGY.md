# Revised Loading Strategy - 2 Year Historical Window

## Executive Summary

**Updated**: 2025-10-21 07:00 WEST
**Change**: Reduced historical price data from 5 years to 2 years
**API Cost**: Unchanged (11 calls per stock)
**Benefits**: 60% database reduction, faster loading, same API quota usage

---

## Understanding EODHD API Costs

### Per-Request Costs

| Endpoint Type | Cost per Request |
|--------------|------------------|
| Fundamental Data | 10 API calls |
| End-of-Day Prices | 1 API call (regardless of date range!) |
| Live Data | 1 API call per ticker |
| Intraday Data | 5 API calls |
| News | 5 API calls |

### Our Usage Pattern

**Per stock**:
```
Fundamentals:  10 calls  (all 13 sections in one request)
Price history:  1 call   (2 years of daily OHLCV)
-------------------------------------------
Total:         11 calls per stock
```

**Critical insight**: The EOD price endpoint costs **1 call** whether you request 1 day or 10 years of data!

---

## Why 2 Years Instead of 5?

### Benefits

1. **Database Size**: 60% reduction in price records
   - Old: 27.3M price records
   - New: 10.9M price records
   - Saved: 16.4M records

2. **Performance**: Faster queries and smaller backup sizes

3. **Relevance**: 2 years is sufficient for:
   - Technical analysis (52-week highs/lows, moving averages)
   - Trend analysis
   - Volatility calculations
   - Most screening criteria

4. **Same API Cost**: Still 1 call per stock for prices

### Trade-offs

- ❌ Less historical data for long-term backtesting
- ❌ Cannot analyze multi-year trends
- ❌ May need to re-fetch if we want more history later

**Conclusion**: 2 years is the sweet spot for initial load. We can always extend later.

---

## Current Status (After Phase 1)

```
Date: October 21, 2025
Quota used today: ~84,172 / 100,000 calls (84%)
Remaining today: ~15,828 calls

Stocks loaded:
✅ NYSE:   2,329 / 2,343 (99.4%)
✅ NASDAQ: 2,716 / 4,090 (66.4%)
✅ Total:  5,045 / 6,433 Phase 1 stocks (78.4%)

Missing:
❌ ~10 NYSE stocks
❌ ~1,374 NASDAQ stocks
```

---

## Revised 3-Day Loading Plan

### Daily Capacity

```
Daily limit:        100,000 API calls
Safety margin:      90% (to account for failures)
Usable capacity:    90,000 calls/day
Stocks per day:     8,181 stocks max
Safe target:        8,000 stocks/day
```

### Day-by-Day Plan

**Day 1: ✅ COMPLETED (Oct 21)**
```
Loaded: 5,045 stocks
NYSE:   2,329 stocks
NASDAQ: 2,716 stocks
Calls:  ~83,047 calls (successful)
Status: ✅ DONE
```

**Day 2: Phase 1 Completion + European Start (Oct 22)**
```
Target stocks:
  - Phase 1 remaining: 1,388 stocks (NYSE + NASDAQ)
  - European (LSE):    1,900 stocks
  - Total:             3,288 stocks

API calls needed: 3,288 × 11 = 36,168 calls
Status: Within quota ✅
Remaining: ~53,832 calls for future use
```

**Day 3: European Continuation (Oct 23)**
```
Target stocks:
  - Euronext:         1,200 stocks
  - Frankfurt/XETRA:    900 stocks
  - Total:            2,100 stocks

API calls needed: 2,100 × 11 = 23,100 calls
Status: Within quota ✅
```

**Day 4: European Completion + Others (Oct 24)**
```
Target stocks:
  - BME (Spain):       200 stocks
  - SIX (Switzerland): 250 stocks
  - Other remaining: 1,145 stocks
  - Total:           1,595 stocks

API calls needed: 1,595 × 11 = 17,545 calls
Status: Within quota ✅
```

### Total Summary

```
Total stocks:     21,816
Days needed:      4 days
Completion date:  Oct 24, 2025
API efficiency:   ~55,000 calls/day average
```

---

## Per-Exchange Breakdown

| Exchange | Stocks | API Calls | Priority | Day |
|----------|--------|-----------|----------|-----|
| **NYSE** | 2,343 | 25,773 | High | 1 ✅ |
| **NASDAQ** | 4,090 | 44,990 | High | 1-2 |
| **LSE** | 1,900 | 20,900 | Medium | 2 |
| **Euronext** | 1,200 | 13,200 | Medium | 3 |
| **Frankfurt** | 900 | 9,900 | Medium | 3 |
| **XETRA** | 200 | 2,200 | Low | 3 |
| **BME** | 200 | 2,200 | Low | 4 |
| **SIX** | 250 | 2,750 | Low | 4 |
| **Others** | ~10,733 | ~118,063 | As needed | Spread |

---

## API Quota Management

### Daily Monitoring

```bash
# Before starting any job, check current usage
echo "Date: $(date)"
echo "Quota status: Check EODHD dashboard"
echo "Safe to proceed if usage < 10,000 calls"
```

### Safety Thresholds

| Usage | Action |
|-------|--------|
| 0-50,000 | ✅ Safe - Full speed ahead |
| 50,000-75,000 | ⚠️ Caution - Reduce batch size |
| 75,000-90,000 | 🔶 Warning - Small batches only |
| 90,000-100,000 | 🔴 STOP - Wait for reset |

### Failure Handling

Failed API calls still consume quota:
- 404 Not Found: 10 calls wasted (fundamentals)
- Invalid ticker: 10 calls wasted
- Network error: May consume calls

**Strategy**: Pre-validate tickers when possible to minimize failures.

---

## Database Impact

### Price Records (2 years)

```
Per stock: ~500 trading days
Total stocks: 21,816
Total records: 10,908,000

Estimated size:
- Uncompressed: ~1.5 GB
- PostgreSQL compressed: ~800 MB
```

### Assets Table

```
Records: 21,816
Columns: 72 + 13 JSONB
Estimated size: ~2 GB (with JSONB fundamentals)
```

### Total Database Size (Complete)

```
Assets:              ~2 GB
Prices (2 years):    ~800 MB
Technical indicators: ~50 MB
Other tables:        ~150 MB
-----------------------------------
Total:               ~3 GB
```

---

## Job Configuration

### Updated Settings (2-year window)

```yaml
# kubernetes/job-phase1-us-markets.yaml
env:
  - name: HISTORICAL_WINDOW_DAYS
    value: "730"  # 2 years
```

**Note**: The code now uses `2 * 365` days in [main_enhanced.py:50](../services/data-collector/src/main_enhanced.py#L50)

---

## Cost Projections

### One-Time Initial Load

```
21,816 stocks × 11 calls = 239,976 API calls
At 100K/day limit = 3 days minimum
With failures/retries = 4 days realistic
```

### Daily Maintenance (After Initial Load)

**Fundamentals**: Only update quarterly
```
21,816 stocks / 90 days = ~242 stocks/day
242 × 10 calls = 2,420 calls/day
```

**Prices**: Update daily for all stocks
```
21,816 stocks × 1 call = 21,816 calls/day
```

**Total daily maintenance**: ~24,236 calls/day
**Quota remaining**: ~75,764 calls/day for new stocks/analysis

---

## Optimization Opportunities

### Future Improvements

1. **Batch Fundamentals Updates**
   - Only fetch for stocks with quarterly earnings
   - Use bulk API endpoints where available
   - Cache fundamentals for 90 days

2. **Incremental Price Updates**
   - Only fetch prices for changed dates
   - Use "from=last_date" parameter

3. **Smart Retry Logic**
   - Don't retry invalid tickers
   - Exponential backoff for rate limits
   - Skip delisted stocks

4. **Exchange-Level Bulk APIs**
   - Some exchanges support bulk endpoints (100 calls for entire exchange)
   - Worth investigating for large exchanges

---

## Monitoring & Alerts

### Implement in Airflow (Future)

```python
# Check quota before DAG run
if api_usage_today > 80000:
    raise AirflowSkipException("API quota too high")

# Log usage after each task
log_api_usage(task_name, calls_used)

# Send alert at thresholds
if api_usage_today > 90000:
    send_alert("API quota critical!")
```

---

## Rollback Plan

### If 2 Years Isn't Enough

To extend back to 5 years (or any period):

1. **Update code**:
   ```python
   # main_enhanced.py line 50
   start_date = date.today() - timedelta(days=5 * 365)
   ```

2. **Rebuild image**:
   ```bash
   ./scripts/build-and-distribute-data-collector.sh
   ```

3. **Re-fetch prices only**:
   ```bash
   # Create job that only fetches additional price history
   # Cost: 1 call per stock = 21,816 calls
   ```

**Note**: Fundamentals don't need re-fetching, just prices!

---

## Recommendations

### Immediate

1. ✅ Use 2-year window for all new loads
2. ✅ Monitor daily API usage in EODHD dashboard
3. ✅ Set alerts at 50K, 75K, 90K thresholds

### Short-term

1. Implement API usage tracking in Redis
2. Add pre-flight quota checks to all jobs
3. Create Airflow DAGs for scheduled loads

### Long-term

1. Evaluate if 100K/day is sufficient for operations
2. Consider upgrading to 200K/day plan if needed
3. Implement intelligent caching strategies

---

**Updated**: 2025-10-21 07:00 WEST
**Next Review**: After Day 2 completion (Oct 22)
**Status**: ✅ Ready to proceed with optimized strategy
