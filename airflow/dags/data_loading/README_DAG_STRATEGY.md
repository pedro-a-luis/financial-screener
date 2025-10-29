# Unified DAG Architecture with Backfill Strategy

## Overview
**4 unified DAGs** - one per API source. Each handles both historical (via Airflow backfill) and incremental (via schedule) using `data_interval_start/end`.

## DAG Structure

| DAG | API | Schedule | Backfill For |
|-----|-----|----------|--------------|
| **dag_prices** | EODHD /eod | Daily 22:00 UTC | 2 years |
| **dag_fundamentals** | EODHD /fundamentals | Quarterly 02:00 UTC | Initial load |
| **dag_news** | EODHD /news | Daily 23:00 UTC | 30 days |
| **dag_sentiment** | EODHD /sentiments | Daily 23:30 UTC | 90 days |

## Initial Setup Commands

```bash
# Run once for historical data
airflow dags backfill dag_prices --start-date 2023-10-29 --end-date 2025-10-29
airflow dags backfill dag_fundamentals --start-date 2025-10-29 --end-date 2025-10-29
airflow dags backfill dag_news --start-date 2025-09-29 --end-date 2025-10-29
airflow dags backfill dag_sentiment --start-date 2025-07-29 --end-date 2025-10-29
```

## Benefits

✅ **4 DAGs instead of 8-10** (simpler)
✅ **Airflow-native backfill** (no custom historical DAGs)
✅ **Idempotent** (safe to rerun dates)
✅ **Flexible** (backfill any date range anytime)

## Status

- ✅ 4 unified DAGs created
- ✅ News/sentiment fetchers added
- ✅ Old historical/incremental DAGs deleted
- ⏳ TODO: Implement news/sentiment in main_enhanced.py

See [UNIFIED_DAG_BACKFILL_IMPLEMENTATION.md](../../../docs/UNIFIED_DAG_BACKFILL_IMPLEMENTATION.md) for details.
