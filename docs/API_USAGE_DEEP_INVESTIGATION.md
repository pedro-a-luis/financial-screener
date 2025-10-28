# Deep Investigation: API Usage Mystery - 85K Missing Calls

## Executive Summary

**Problem**: Phase 1 job used only ~12,847 API calls but EODHD 100K daily quota was exhausted.
**Missing**: ~85,147 calls UNACCOUNTED FOR
**Status**: ⚠️ **CRITICAL** - Need to identify source before continuing

---

## What We Know FOR CERTAIN

### Confirmed API Usage (from logs)

| Source | Date | API Calls | Evidence |
|--------|------|-----------|----------|
| Phase 1 (phase1-us-markets) | Oct 21 | 12,847 | Job logs analyzed |
| test-enhanced-collection | Oct 20 | 20 | DB log + job |
| price_stock cronjob | Oct 20 | 494 | DB log entry #12 |
| price_stock cronjob | Oct 19 | 1,536 | DB log entries #6,7,8 |
| **TOTAL KNOWN** | | **14,897** | |

### The Mystery

```
100,000 (daily limit)
- 14,897 (confirmed usage)
-----------
 85,103 MISSING API CALLS
```

---

## Investigation Steps Taken

### 1. ✅ Analyzed Complete Phase 1 Logs (53,603 lines)

```bash
Fundamentals fetched (success): 5,085
Prices fetched (success):      5,039
Fundamentals failed (404/etc): 1,348
Price requests:                5,047
402 Payment errors:            1,367
-------------------------------------------
Total Phase 1 calls:          12,847
```

**Breakdown**:
- Each stock = 2 API calls (1 fundamentals + 1 prices)
- Failed calls ALSO consume quota
- 402 errors = quota exhausted attempts

### 2. ✅ Checked All Jobs in Namespace

```
Jobs found:
- bulk-sp500-load (Oct 19, 16:45) - 10m duration
- test-enhanced-collection (Oct 20, 23:42) - 40s duration
- phase1-us-markets (Oct 20, 23:46) - 4h52m duration

Cronjobs (NOW DELETED):
- data-collector-premarket
- data-collector-postmarket
- data-collector-european
- data-collector-psi20
```

### 3. ✅ Checked Database Logs

Found 15 entries in `data_fetch_log` table showing cronjob runs processing stocks.

### 4. ❌ Could NOT Find

- Logs from bulk-sp500-load (pod deleted)
- Logs from older cronjob runs (pods deleted)
- EODHD API quota usage dashboard
- Exact API call counts from missing jobs

---

## Hypotheses (Ranked by Likelihood)

### Hypothesis #1: bulk-sp500-load Job (Oct 19) ⭐⭐⭐⭐⭐

**Evidence**:
- Ran for 10 minutes on Oct 19
- Used ticker file `sp500.txt` (now deleted)
- SP500 has ~500 stocks
- Logs are gone (pod deleted)

**Estimated Impact**:
```
SP500 stocks: ~500
API calls per stock: 2 (fundamentals + prices)
Total: ~1,000 calls
```

**Conclusion**: NOT enough to explain 85K missing

---

### Hypothesis #2: Cronjobs Ran Multiple Times ⭐⭐⭐⭐

**Evidence**:
- 4 cronjobs were scheduled:
  - `data-collector-premarket`: Daily at 00:00
  - `data-collector-postmarket`: Daily at 21:00
  - `data-collector-european`: Daily at 06:00
  - `data-collector-psi20`: Daily at 14:30

- DB log shows runs on Oct 19 and Oct 20
- Pods are deleted, logs unavailable

**Known cronjob runs** (from DB):
```
Oct 19:
  - 3× price_stock jobs processed 768 stocks total

Oct 20:
  - 1× price_stock job processed 247 stocks
```

**Estimated Impact**:
```
(768 + 247) stocks × 2 calls = 2,030 API calls
```

**Conclusion**: Still NOT enough to explain 85K

---

### Hypothesis #3: EODHD Quota is MONTHLY, Not Daily ⭐⭐⭐⭐⭐

**Theory**:
What if the 100K limit is PER MONTH, not per day?

**Math**:
```
Month of October (Oct 1-21):
- 21 days elapsed
- If 100K/month → ~4,762 calls/day budget

Our usage:
- Oct 19: ~2,500 calls (cronjobs + bulk-sp500)
- Oct 20: ~500 calls (cronjobs + test)
- Oct 21: ~12,847 calls (Phase 1)
Total: ~15,847 calls in 3 days

But wait - what about Oct 1-18?
```

**If quota is monthly**:
- We may have used quota on previous days (Oct 1-18)
- Testing, development, other runs
- Would explain hitting limit

**How to verify**:
1. Log into EODHD dashboard
2. Check "API Usage" section
3. Look for "Monthly" vs "Daily" limit label
4. Check usage history for October

---

### Hypothesis #4: Hidden API Calls in Code ⭐⭐⭐

**Possible sources**:
1. **Rate limiter validation** - Does `_rate_limit()` call an API endpoint?
2. **Ticker validation** - Does code validate tickers via API before fetching?
3. **Retry logic** - Are failed calls retried multiple times?
4. **Exchange listing calls** - Code might fetch exchange listings

**Need to check**:
- `services/data-collector/src/fetchers/eodhd_fetcher.py`
- `services/data-collector/src/cache.py`
- Any authentication/validation endpoints

---

### Hypothesis #5: Multiple Concurrent Jobs ⭐⭐

**Theory**: Jobs ran in parallel, hitting same stocks

**Evidence against**:
- Only 3 jobs shown in namespace
- Job timestamps don't overlap significantly

**Estimated impact**: Minimal

---

### Hypothesis #6: Test/Development Usage ⭐⭐⭐⭐

**Untracked usage**:
- Manual testing during development
- Previous failed job attempts
- API key used outside cluster

**How to verify**:
- Check EODHD dashboard for complete Oct history
- Look for non-cluster API calls

---

## CRITICAL MISSING INFORMATION

### Need from EODHD Dashboard:

1. **Quota Type**: Daily or Monthly?
2. **Current Usage**: Exact count for Oct 21
3. **Reset Time**: When does quota reset?
4. **Historical Usage**: Oct 1-21 daily breakdown
5. **API Call Log**: If available, detailed call log

### Need from Code Review:

1. **All API endpoints called** - Not just /fundamentals and /eod
2. **Retry logic** - How many times are failed calls retried?
3. **Validation calls** - Any ticker/exchange validation APIs?
4. **Rate limiter** - Does it make API calls?

---

## IMMEDIATE ACTION ITEMS

### 1. Check EODHD Dashboard (URGENT)

```
Log in to: https://eodhd.com/cp/settings
Check:
  - API usage meter
  - Quota type (daily/monthly)
  - Usage history
  - API call breakdown by endpoint
```

### 2. Review Fetcher Code for Hidden Calls

```bash
# Search for all requests.get/post calls
grep -r "requests\.(get|post)" services/data-collector/src/

# Check for API validation endpoints
grep -r "eodhd.com/api" services/data-collector/src/
```

### 3. Add API Call Logging

```python
# Wrap all API calls with logging
def log_api_call(endpoint, ticker=None):
    logger.info("EODHD_API_CALL", endpoint=endpoint, ticker=ticker)
    # Increment counter in Redis
    redis.incr(f"api_calls:{date.today()}")
```

### 4. Check for Previous Month Usage

If quota is monthly, check what happened Oct 1-18.

---

## RECOMMENDATIONS

### Immediate (Before Any More Jobs)

1. ✅ **DONE**: Delete all cronjobs
2. ⏳ **TODO**: Access EODHD dashboard
3. ⏳ **TODO**: Review fetcher code for hidden calls
4. ⏳ **TODO**: Add comprehensive API call logging

### Short-term (Next 24 hours)

1. Implement API call counter in Redis
2. Add quota warnings at 50%, 75%, 90%
3. Create daily usage report
4. Review all Oct activity in EODHD dashboard

### Long-term

1. **If quota is monthly**:
   - Calculate daily budget (100K / 30 days = 3,333/day)
   - Implement strict daily limits
   - Spread Phase 1 across multiple days

2. **If quota is daily**:
   - Find and fix the hidden API usage
   - Implement request deduplication
   - Cache fundamentals longer (they don't change often)

---

## COST ANALYSIS

### If We Need to Upgrade

EODHD pricing tiers (approximate):
- All-In-One Basic: 100K calls/month ($79.99/month)
- All-In-One Plus: 200K calls/month ($149.99/month)
- All-In-One Premium: 500K calls/month ($249.99/month)

### Our Needs

```
Total stocks to load: 21,816
API calls per stock: 2 (fundamentals + prices)
Total calls needed: 43,632

Plus failed attempts: ~8,700 (20% failure rate)
Grand total: ~52,332 API calls for full load

Daily updates (after initial load):
- Only fetch updated fundamentals (quarterly)
- Only fetch new prices (daily)
- Estimated: ~22K calls/day
```

**Conclusion**: 100K/month is NOT ENOUGH for daily operations.
Need at least 200K/month (Plus tier).

---

## NEXT STEPS

**YOU MUST DO**:
1. Log into EODHD dashboard RIGHT NOW
2. Screenshot the usage page
3. Tell me:
   - Is it 100K per day or per month?
   - How many calls have been used?
   - When does it reset?
   - What does the historical usage show?

**THEN I WILL**:
1. Calculate exact budget
2. Create optimized loading strategy
3. Implement API tracking
4. Resume data loading safely

---

**Report Generated**: 2025-10-21 06:30 WEST
**Status**: ⚠️ **BLOCKED** - Need EODHD dashboard access to proceed
**Recommendation**: DO NOT run any more jobs until quota situation is clarified
