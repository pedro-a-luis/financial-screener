# Unified DAG + Backfill Implementation - Status & Next Steps

## Overview
Implementation of unified DAG architecture where each API has ONE DAG that handles both historical (via backfill) and incremental (via schedule) data collection.

## Completed ✅

### Phase 1: News/Sentiment Fetchers
- ✅ Added `fetch_news()` to eodhd_fetcher.py
  - Fetches news articles with sentiment per ticker
  - Params: ticker, from_date, to_date, limit
  - Returns: List of articles with title, content, sentiment, tags, symbols
  
- ✅ Added `fetch_sentiment()` to eodhd_fetcher.py
  - Fetches aggregated daily sentiment scores
  - Batches up to 100 tickers per call
  - Returns: Dict of ticker → daily sentiment scores (-1 to +1)

### Phase 2: Database Methods
- ✅ Added `upsert_news_article()` to database_enhanced.py
  - Deduplicates by URL
  - Stores: title, content, published_date, tags[], sentiment_score
  
- ✅ Added `upsert_sentiment_score()` to database_enhanced.py
  - Stores daily aggregated sentiment
  - Fields: date, normalized_score, article_count

## Next Steps ⏳

### Phase 3: Create 4 Unified DAGs
Need to create backfill-ready DAGs:

**1. dag_prices.py** (EODHD prices API)
- Schedule: Daily 22:00 UTC
- Uses: `data_interval_start/end` from Airflow context
- Mode: Auto-detect (bulk for large ranges, incremental for daily)
- Backfill: 2 years historical

**2. dag_fundamentals.py** (EODHD fundamentals API)
- Schedule: Quarterly (Jan/Apr/Jul/Oct 1st at 02:00 UTC)
- Uses: `data_interval_start/end`
- Mode: Always comprehensive (13 sections, 100+ fields)
- Backfill: One-time initial load

**3. dag_news.py** (EODHD news API)
- Schedule: Daily 23:00 UTC
- Uses: `data_interval_start/end`
- Fetches articles for date range
- Backfill: 30 days historical

**4. dag_sentiment.py** (EODHD sentiment API)
- Schedule: Daily 23:30 UTC
- Uses: `data_interval_start/end`
- Batches 100 tickers per call
- Backfill: 90 days historical

### Phase 4: Remove Old DAGs
Delete the historical/incremental split approach:
- ❌ dag_01_historical_prices.py
- ❌ dag_02_incremental_prices.py
- ❌ dag_03_historical_fundamentals.py
- ❌ dag_04_incremental_prices.py
- ❌ dag_quarterly_fundamentals_refresh.py (old)

### Phase 5: Update Documentation
- Update README_DAG_STRATEGY.md with backfill approach
- Document backfill commands for each DAG
- Add troubleshooting guide

### Phase 6: Initial Backfill Execution
Run historical loads using Airflow backfill:
```bash
# Prices: 2 years
airflow dags backfill dag_prices \\
  --start-date 2023-10-29 --end-date 2025-10-29

# Fundamentals: Initial load
airflow dags backfill dag_fundamentals \\
  --start-date 2025-10-29 --end-date 2025-10-29

# News: 30 days
airflow dags backfill dag_news \\
  --start-date 2025-09-29 --end-date 2025-10-29

# Sentiment: 90 days
airflow dags backfill dag_sentiment \\
  --start-date 2025-07-29 --end-date 2025-10-29
```

## Current Status

**Running Jobs:**
- ✅ comprehensive-fundamentals-refresh K8s job (started ~2 hours ago)
  - Processing tickers with comprehensive fundamentals
  - Will complete current run, then use new unified dag_fundamentals

**Code Ready:**
- ✅ News/sentiment fetchers added to eodhd_fetcher.py
- ✅ Database upsert methods added to database_enhanced.py
- ⏳ Need to create 4 unified DAGs
- ⏳ Need to rebuild data-collector image

## Benefits of Unified Approach

✅ **Simpler**: 4 DAGs instead of 8-10
✅ **Maintainable**: One DAG per API
✅ **Airflow-Native**: Uses built-in backfill
✅ **Flexible**: Can backfill any date range
✅ **Idempotent**: Safe to rerun dates
✅ **Cleaner**: No "one-time" DAGs to disable

## API Call Estimates

**One-Time Backfills:**
- Prices (2 years): ~10,000 calls
- Fundamentals: ~5,000 calls
- News (30 days): ~5,000 calls
- Sentiment (90 days): ~50 calls (batched)

**Daily Operations:**
- Prices: ~5,000 calls
- News: ~5,000 calls
- Sentiment: ~50 calls
- **Total**: ~10,050 calls/day

**Quarterly:**
- Fundamentals: ~5,000 calls

## Database Schema Status

**Existing Tables (Ready):**
- ✅ `assets` - 72 columns + 13 JSONB for comprehensive fundamentals
- ✅ `stock_prices` - OHLCV daily prices
- ✅ `news_articles` - News with sentiment (may need URL column for dedup)
- ✅ `sentiment_summary` - Daily aggregated sentiment scores

**Schema Updates Needed:**
- ⚠️  Add UNIQUE constraint on `news_articles.url` (if missing)
- ⚠️  Add `symbols` TEXT[] to news_articles (if missing)
- ⚠️  Add UNIQUE constraint on `sentiment_summary(ticker, period_start, period_type)`

## Next Immediate Actions

1. **Create 4 unified DAGs** (priority)
2. **Test with sample backfill** (1-2 tickers, 7 days)
3. **Rebuild data-collector image** (with news/sentiment fetchers)
4. **Delete old DAG files**
5. **Run full backfills** (after testing)
6. **Enable scheduled runs**

## Notes

- Current K8s job `comprehensive-fundamentals-refresh` will complete its run
- After completion, use new `dag_fundamentals` for quarterly updates
- Old DAGs (01-04) were committed but not yet deployed/used in production
- Safe to delete and replace with unified approach
