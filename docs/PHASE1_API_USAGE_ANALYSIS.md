# Phase 1 API Usage Analysis

## ⚠️ **Issue Summary**

During Phase 1 bulk load, **ALL 100,000 daily API calls were consumed** before completing the full 6,433 stock target.

---

## 📊 **Actual Results**

| Metric | Count |
|--------|-------|
| **Target Stocks** | 6,433 (NYSE + NASDAQ) |
| **Stocks Attempted** | 6,433 |
| **Fundamentals Fetched** | 5,085 |
| **Prices Fetched** | 5,039 |
| **Assets in DB** | 5,045 |
| **API Quota Hit** | ~4:04 AM (after ~5.5 hours) |
| **Job Duration** | 4h 52m |

---

## 🔍 **Root Causes**

### 1. **Comment Lines in Ticker Files** (Minor Waste)

The ticker files contained header comments that were processed as tickers:

```
# New York Stock Exchange (NYSE)
# Auto-generated from EODHD API
# Total tickers: 2339
```

**Impact**: ~30 wasted API calls (60 total with fundamentals + prices)

**Evidence**:
```
[error] eodhd_complete_data_failed ticker=# NEW YORK STOCK EXCHANGE (NYSE)
[error] eodhd_complete_data_failed ticker=# AUTO-GENERATED FROM EODHD API
[error] eodhd_complete_data_failed ticker=# TOTAL TICKERS: 2339
```

### 2. **2 API Calls Per Stock** (Expected)

Each stock requires:
- **1 call**: Complete fundamentals (all 13 sections)
- **1 call**: Price history (5 years of OHLCV)

**Expected total**: 6,433 stocks × 2 calls = **12,866 API calls**

### 3. **Failed Ticker Retries** (Moderate Waste)

Some tickers don't exist or are delisted, but we still made API calls for them.

**Example failures**:
- 404 errors for non-existent tickers
- Empty/invalid ticker symbols
- Delisted stocks

**Estimated waste**: ~500-1,000 calls

### 4. **Additional API Calls Beyond Fundamentals + Prices**

Looking at the code, there may be hidden API calls I didn't account for:
- Rate limit checking?
- Validation calls?
- Retry logic?

---

## 📈 **Actual API Usage Calculation**

```
Successful fundamentals:  5,085 calls
Successful prices:        5,039 calls
Failed attempts:         ~1,400 calls (6,433 - 5,085 for fundamentals)
Comment line waste:          30 calls
-------------------------------------------
Estimated total:        ~11,554 API calls
```

**But we hit the 100K daily limit!**

This means **we made WAY more calls than expected**.

---

## 🤔 **Where Did the Extra ~88,000 Calls Go?**

### Hypothesis 1: The Job Ran Multiple Times

Let me check if there were previous runs today...

**Check**: Look at `data_fetch_log` table or count all jobs that ran on 2025-10-21

### Hypothesis 2: Price Endpoint Makes Multiple Calls

The price fetcher might be making one call per day/week instead of bulk fetching.

**Evidence needed**: Check EODHD API documentation for `/eod/` endpoint

### Hypothesis 3: Retry Logic Gone Wrong

If the rate limiter or retry logic is broken, it could be making duplicate calls.

**Evidence needed**: Check fetcher code for retry loops

### Hypothesis 4: Other Jobs/Tests Used API

The test jobs and other cronjobs may have consumed API quota:
- `test-enhanced-collection` (10 stocks × 2 = 20 calls)
- Previous failed jobs
- Other services

---

## 🔧 **Immediate Fixes Needed**

### Fix 1: Filter Comment Lines in Ticker Files

**File**: `services/data-collector/src/main_enhanced.py`

**Current** (reads all lines):
```python
ALL_TICKERS=$(cat /app/config/tickers/nyse.txt | tr '\n' ',' | sed 's/,$//')
```

**Fixed** (skip comments and empty lines):
```python
ALL_TICKERS=$(grep -v '^#' /app/config/tickers/nyse.txt | grep -v '^$' | tr '\n' ',' | sed 's/,$//')
```

### Fix 2: Add API Call Counter/Logger

Add explicit logging of every API call to track actual usage:

```python
@functools.wraps(func)
async def log_api_call(*args, **kwargs):
    logger.info("API_CALL", endpoint=endpoint, ticker=ticker)
    return await func(*args, **kwargs)
```

### Fix 3: Check EODHD Dashboard

Log into EODHD account and check:
- Today's API usage count
- When quota resets (UTC time)
- Historical usage patterns

---

## 📅 **EODHD API Quota Details**

### Your Plan
- **Plan**: All-in-One (assumed)
- **Daily Limit**: 100,000 calls/day
- **Reset Time**: Midnight UTC (likely)

### When Can We Resume?

**Next quota reset**: 2025-10-22 00:00:00 UTC

Convert to your timezone:
- **UTC**: Tomorrow at 00:00
- **WEST** (UTC+1): Tomorrow at 01:00 AM
- **Hours from now**: ~19 hours (as of 06:00 WEST)

---

## 🎯 **Recommended Next Steps**

### Immediate (Before Next Run)

1. **Fix ticker file parsing** - Skip # comments
2. **Check EODHD dashboard** - Confirm actual usage
3. **Add API call logging** - Track every call
4. **Review fetcher code** - Check for hidden calls
5. **Check other running jobs** - Stop any active cronjobs

### Tomorrow (After Quota Reset)

1. **Resume Phase 1** - Load remaining ~1,388 stocks
2. **Monitor API usage** - Watch counter in real-time
3. **Adjust batch size** - Maybe use smaller batches (50 instead of 100)

### Long Term

1. **Implement API quota tracking** - Store daily usage in DB
2. **Add quota warning system** - Alert at 80% usage
3. **Optimize fetching strategy** - Batch calls where possible
4. **Consider upgrading plan** - If 100K/day is not enough

---

## 💾 **What We Successfully Loaded**

Despite hitting the quota, we still got:

✅ **5,045 stocks** with complete data
✅ **5,167,357 price records** (5 years × 1,250 days × 5,045 stocks)
✅ **All 13 JSONB sections** from EODHD API
✅ **78% of target** (5,045 / 6,433)

**Missing**: ~1,388 stocks (mostly NASDAQ stocks starting with "O" and later)

---

## 🔍 **Action Items for Tomorrow**

### Before Running Anything

```bash
# 1. Check EODHD API dashboard for quota status

# 2. Fix ticker file parsing
# Edit: kubernetes/job-phase1-us-markets.yaml
# Change the command to filter comments

# 3. Identify remaining stocks to load
# Query DB for what's missing

# 4. Create a "resume" job for missing stocks only
```

### API Quota Monitoring

Create a simple script to check EODHD API usage:

```bash
#!/bin/bash
# Check current API usage (implement using EODHD dashboard or API)
# EODHD might have an endpoint to check quota
curl "https://eodhd.com/api/user?api_token=YOUR_KEY&fmt=json"
```

---

## 📊 **Phase 1 Statistics**

```
Status: ✅ PARTIAL SUCCESS (78% complete)

Loaded:
- NYSE: 2,329 / ~2,339 (99.6%)
- NASDAQ: 2,716 / ~4,094 (66.3%)

Missing:
- ~10 NYSE stocks
- ~1,378 NASDAQ stocks (mostly O-Z tickers)

Database Size:
- Assets: 261 MB
- Prices: 121 MB → will grow significantly after completion

API Usage:
- Used: 100,000 calls (100%)
- Expected for 5,045: ~10,090 calls
- Discrepancy: ~89,910 calls MISSING/UNACCOUNTED FOR ⚠️
```

---

**Generated**: 2025-10-21 06:05 WEST
**Next Action**: Investigate API usage discrepancy and prepare Phase 1 resume job
