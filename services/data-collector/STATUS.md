# Data Collector Service

**Status:** ✅ **ACTIVE** (Phase 2 - Production)

## Purpose
Collects fundamental and historical price data for stocks, ETFs, and bonds from EODHD API.

## Current Implementation
- **Primary Script:** `src/main.py` (formerly `main_enhanced.py`)
- **Database Layer:** `src/database.py` (formerly `database_enhanced.py`)
- **API Integration:** `src/fetchers/eodhd.py` (EODHD API v1)
- **Orchestration:** Airflow DAG (`airflow/dags/data_loading/dag_data_collection_equities.py`)
- **Schedule:** Daily at 21:30 UTC
- **Docker Image:** `financial-data-collector:latest`

## Features
- ✅ Metadata-driven delta discovery (only fetch what's needed)
- ✅ Smart fundamental refresh (weekly/monthly/quarterly instead of daily)
- ✅ API quota management (tracks 100K daily limit)
- ✅ Parallel processing (4 jobs by exchange)
- ✅ Comprehensive logging and error handling
- ✅ Automatic retry with exponential backoff

## Coverage
- **Exchanges:** NYSE, NASDAQ, LSE, Frankfurt, Xetra, Euronext, BME, SIX
- **Assets:** 21,817 tickers (stocks, ETFs)
- **Data Points:**
  - Fundamentals: 72 columns per ticker (10 API calls)
  - Prices: OHLCV + adjusted (1 API call per day)
  - History: 2 years on initial load

## API Usage
- **Provider:** EODHD.com (All-World plan: $79.99/month)
- **Daily Quota:** 100,000 API calls
- **Current Usage:** ~27,000 calls/day (73% under limit)
- **Savings:** 88.9% reduction via smart fundamental refresh

## Dependencies
- Python 3.11+
- PostgreSQL 14 + TimescaleDB
- EODHD API key
- Kubernetes cluster (8-node Raspberry Pi 4)

## Monitoring
```sql
-- Check today's activity
SELECT * FROM v_today_processing_activity;

-- Check API quota
SELECT * FROM v_quota_status WHERE quota_date = CURRENT_DATE;

-- Check processing progress
SELECT * FROM get_processing_progress();
```

## Next Improvements
- [ ] Implement async API calls (10-20 concurrent requests)
- [ ] Migrate to Bulk Exchange API for prices (99% reduction)
- [ ] Add Pydantic data validation
- [ ] Implement response caching (Redis)

## Related Documentation
- [.claude.md](../../.claude.md) - Complete project overview
- [PERFORMANCE_AND_STABILITY_ASSESSMENT.md](../../docs/PERFORMANCE_AND_STABILITY_ASSESSMENT.md)
- [006_api_quota_management.sql](../../database/migrations/006_api_quota_management.sql)
- [007_smart_fundamental_refresh.sql](../../database/migrations/007_smart_fundamental_refresh.sql)

**Last Updated:** 2025-10-28
