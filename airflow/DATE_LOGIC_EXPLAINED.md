# Date Logic - Only Fetch Complete Trading Days

## The Rule: Never Fetch "Today"

**Why?** Trading day is not complete until market closes. Fetching incomplete data causes issues:
- ❌ Partial day data (e.g., only morning prices)
- ❌ Data changes during the day
- ❌ API might not have finalized data yet
- ❌ Have to re-fetch later to get complete day

**Solution**: Always fetch up to **YESTERDAY** only.

---

## How It Works Now ✅

### Example 1: Running on Monday Oct 28, 2025

**Scenario**: AAPL last data is from Friday Oct 25

```python
# Today = Monday Oct 28
yesterday = date.today() - timedelta(days=1)  # Sunday Oct 27

# Query metadata
last_date = get_last_price_date('AAPL')  # Friday Oct 25

# Calculate range
start_date = last_date + timedelta(days=1)  # Saturday Oct 26
end_date = yesterday  # Sunday Oct 27

# Fetch: Oct 26-27 (Sat & Sun)
# Result: API returns nothing (market closed weekends)
# Database: No inserts (no data available)
# Next run: Will try again for Oct 26-28
```

### Example 2: Running on Tuesday Oct 29, 2025

**Scenario**: AAPL last data is still Friday Oct 25 (weekend skipped)

```python
# Today = Tuesday Oct 29
yesterday = date.today() - timedelta(days=1)  # Monday Oct 28

# Query metadata  
last_date = get_last_price_date('AAPL')  # Still Friday Oct 25

# Calculate range
start_date = last_date + timedelta(days=1)  # Saturday Oct 26
end_date = yesterday  # Monday Oct 28

# Fetch: Oct 26-28 (Sat, Sun, Mon)
# Result: API returns Monday Oct 28 only (market open)
# Database: Inserts Oct 28
# Metadata: Updates prices_last_date = Oct 28
```

### Example 3: Already Up to Date

**Scenario**: Running Tuesday night, already processed Monday

```python
# Today = Tuesday Oct 29, 10 PM
yesterday = date.today() - timedelta(days=1)  # Monday Oct 28

# Query metadata
last_date = get_last_price_date('AAPL')  # Monday Oct 28

# Calculate range
start_date = last_date + timedelta(days=1)  # Tuesday Oct 29
end_date = yesterday  # Monday Oct 28

# Check: start_date (Oct 29) > end_date (Oct 28)?
if start_date > end_date:
    logger.info("already_up_to_date")
    return True  # Skip, nothing to fetch

# Result: No API call (efficient!)
```

---

## Complete Logic Flow

```python
def determine_date_range(ticker, mode):
    yesterday = date.today() - timedelta(days=1)
    
    if mode == "bulk":
        # New ticker: 2 years up to yesterday
        start_date = yesterday - timedelta(days=730)
        end_date = yesterday
        
    else:  # incremental
        # Get last available date from metadata
        last_date = get_last_price_date(ticker)
        
        if last_date:
            # Start from day AFTER last date
            start_date = last_date + timedelta(days=1)
            end_date = yesterday
            
            # Already up to date?
            if start_date > end_date:
                return None  # Skip
        else:
            # No history, treat as bulk
            start_date = yesterday - timedelta(days=730)
            end_date = yesterday
    
    return (start_date, end_date)
```

---

## Why This Works

### Handles Weekends/Holidays Automatically

```
Friday Oct 25:
  - last_date = Oct 24
  - Fetch: Oct 25 (gets data)
  - Update: last_date = Oct 25

Saturday Oct 26 (market closed):
  - last_date = Oct 25
  - Fetch: Oct 26 (API returns empty)
  - Update: last_date = unchanged (Oct 25)

Monday Oct 28:
  - last_date = Oct 25
  - Fetch: Oct 26-27 (gets Oct 28 data)
  - Update: last_date = Oct 28
```

### Handles Missing Days

```
If Oct 22 failed to load:
  - last_date = Oct 21
  - Next run fetches: Oct 22 → yesterday
  - Fills the gap automatically
```

### Idempotent

```
Run same day twice:
  First run:
    - Fetch Oct 28
    - Insert Oct 28
    - last_date = Oct 28
  
  Second run:
    - last_date = Oct 28
    - start = Oct 29, end = Oct 28
    - start > end → skip (no API call)
```

---

## When DAG Runs at 21:30 UTC

**Why 21:30 UTC?**
- US markets close at 16:00 EST (21:00 UTC)
- Gives API 30 minutes to finalize data
- Fetches yesterday (complete day)

**Example on Oct 28, 21:30 UTC:**
```
US markets closed at 21:00 UTC (today Oct 28)
But we fetch: Oct 27 (yesterday)

Result: 
  - Oct 27 data is complete ✅
  - Oct 28 data will be fetched tomorrow ✅
```

**Next day Oct 29, 21:30 UTC:**
```
Fetch: Oct 28 (yesterday)
Now Oct 28 is a complete trading day ✅
```

---

## Edge Cases Handled

### Case 1: New Ticker Added

```python
# Ticker added on Oct 28
last_date = None  # No history

# Mode: bulk
start = Oct 28 - 730 days  # Oct 28, 2023
end = Oct 27  # Yesterday

# Fetches: 2 years up to yesterday ✅
```

### Case 2: Long Holiday (Market Closed 5 Days)

```python
# Before holiday: last_date = Dec 20
# After holiday (Dec 26): 
start = Dec 21
end = Dec 25

# API returns: Nothing (all holidays)
# last_date: Unchanged (Dec 20)

# Next day (Dec 27):
start = Dec 21
end = Dec 26

# API returns: Dec 26 data (market open)
# last_date: Updated to Dec 26 ✅
```

### Case 3: Reprocessing Specific Dates

```python
# Manual trigger with override
start_date_override = Oct 1
end_date_override = Oct 10

# Uses override dates (ignores yesterday logic)
# Fetches: Oct 1-10 (as specified)
# ON CONFLICT DO UPDATE: Updates existing data ✅
```

---

## What Gets Fetched When

### Monday Morning Run (after weekend)

| Run Date | Yesterday | last_date | Fetches | Result |
|----------|-----------|-----------|---------|--------|
| Mon Oct 28 | Sun Oct 27 | Fri Oct 25 | Sat-Sun | Empty (no data) |
| Tue Oct 29 | Mon Oct 28 | Fri Oct 25 | Sat-Mon | Monday only |
| Wed Oct 30 | Tue Oct 29 | Mon Oct 28 | Tuesday | Tuesday data |

### Daily Steady State

| Run Date | Yesterday | last_date | Fetches | Result |
|----------|-----------|-----------|---------|--------|
| Tue Oct 29 | Mon Oct 28 | Mon Oct 28 | None | Already up to date |
| Wed Oct 30 | Tue Oct 29 | Mon Oct 28 | Tuesday | Tuesday data |
| Thu Oct 31 | Wed Oct 30 | Tue Oct 29 | Wednesday | Wednesday data |

---

## Comparison: Wrong vs Right

### ❌ WRONG (Old Logic)

```python
start_date = date.today() - timedelta(days=7)  # Oct 21
end_date = date.today()  # Oct 28

# Issues:
# - Fetches Oct 21-28 EVERY DAY (wastes API calls)
# - Fetches incomplete Oct 28 (trading day not done)
# - Relies on ON CONFLICT to avoid duplicates
# - 8 days × 21,817 tickers = 174,536 API calls!
```

### ✅ RIGHT (New Logic)

```python
last_date = get_last_price_date(ticker)  # Oct 27
start_date = last_date + timedelta(days=1)  # Oct 28  
end_date = yesterday  # Oct 27

# If start > end: Skip (already up to date)

# Benefits:
# - Fetches only NEW dates (1 day typically)
# - Never fetches incomplete day
# - 1 day × 21,817 tickers = 21,817 API calls
# - 8x more efficient! ✅
```

---

## Summary

✅ **Always fetch up to YESTERDAY**
- Never fetch today (incomplete trading day)
- Ensures complete/closed data only

✅ **Start from last_date + 1**
- Queries metadata for last available date
- Fetches only missing dates
- No wasteful lookback

✅ **Smart skip logic**
- If already up to date: No API call
- Handles weekends/holidays automatically
- Fills gaps on next run

✅ **Efficient API usage**
- Typical: 1 day per ticker
- Old logic: 7-8 days per ticker
- Savings: 85-90% fewer API calls

**Result**: Clean, efficient, predictable data collection! 🎯
