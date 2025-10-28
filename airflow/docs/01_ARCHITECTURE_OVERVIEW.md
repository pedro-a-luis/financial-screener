# Airflow Orchestration - Architecture Overview

## Table of Contents
1. [System Context](#system-context)
2. [Architecture Diagram](#architecture-diagram)
3. [Component Responsibilities](#component-responsibilities)
4. [Data Flow](#data-flow)
5. [Technology Stack](#technology-stack)
6. [Design Principles](#design-principles)

---

## System Context

The Financial Screener project is a Kubernetes-native application running on an 8-node Raspberry Pi cluster (ARM64 architecture). The system collects, processes, and analyzes financial data for 21,817 assets across 8 global exchanges.

**Current State:**
- **Deployed:** Airflow 3.0.2 (scheduler, webserver, triggerer)
- **Database:** PostgreSQL 16 (financial_screener schema)
- **Message Broker:** Redis (for caching and Celery)
- **Container Runtime:** K3s lightweight Kubernetes
- **Data Loaded:** 5,045 US stocks (NYSE + NASDAQ partial)
- **Missing:** 16,772 assets (remaining US stocks, ETFs, European markets, bonds, funds)

**Challenge:**
- Manual K8s Job execution prone to duplicates
- No orchestration for daily incremental updates
- No centralized tracking of what's loaded/failed
- API quota management manual
- No retry logic for failed assets

**Solution:**
Apache Airflow orchestrating idempotent, metadata-driven data pipelines.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Raspberry Pi K3s Cluster                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      Airflow (namespace: airflow)                  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │  │
│  │  │  Scheduler   │  │  Webserver   │  │  Triggerer   │            │  │
│  │  │  (1 pod)     │  │  (1 pod)     │  │  (1 pod)     │            │  │
│  │  └──────┬───────┘  └──────────────┘  └──────────────┘            │  │
│  │         │                                                          │  │
│  │         │ Reads DAGs from                                         │  │
│  │         ▼                                                          │  │
│  │  ┌──────────────────────────────────────────────────────────┐    │  │
│  │  │   DAGs (Git-Sync or ConfigMap)                           │    │  │
│  │  │   - dag_data_collection_equities.py                      │    │  │
│  │  │   - dag_calculate_indicators.py                          │    │  │
│  │  │   - dag_data_collection_bonds.py                         │    │  │
│  │  └──────────────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │            Worker Namespace (namespace: financial-screener)        │  │
│  │  ┌────────────────────────────────────────────────────────────┐   │  │
│  │  │  Airflow triggers K8s Jobs via KubernetesPodOperator      │   │  │
│  │  │                                                            │   │  │
│  │  │  ┌──────────────────┐      ┌──────────────────┐          │   │  │
│  │  │  │ data-collector   │      │ indicator-calc   │          │   │  │
│  │  │  │ (K8s Job)        │      │ (K8s Job)        │          │   │  │
│  │  │  │                  │      │                  │          │   │  │
│  │  │  │ Runs:            │      │ Runs:            │          │   │  │
│  │  │  │ main_enhanced.py │      │ main_indicators  │          │   │  │
│  │  │  │                  │      │                  │          │   │  │
│  │  │  └────────┬─────────┘      └────────┬─────────┘          │   │  │
│  │  │           │                         │                    │   │  │
│  │  │           │                         │                    │   │  │
│  │  │           ▼                         ▼                    │   │  │
│  │  │  ┌────────────────────────────────────────────────────┐ │   │  │
│  │  │  │      PostgreSQL (namespace: databases)            │ │   │  │
│  │  │  │                                                    │ │   │  │
│  │  │  │  ┌──────────────┐  ┌──────────────────────────┐  │ │   │  │
│  │  │  │  │ Business     │  │ Metadata Tables          │  │ │   │  │
│  │  │  │  │ Tables       │  │ (Process Orchestration)  │  │ │   │  │
│  │  │  │  │              │  │                          │  │ │   │  │
│  │  │  │  │ - assets     │  │ - process_executions     │  │ │   │  │
│  │  │  │  │ - prices     │  │ - asset_processing_state │  │ │   │  │
│  │  │  │  │ - indicators │  │ - asset_processing_log   │  │ │   │  │
│  │  │  │  └──────────────┘  └──────────────────────────┘  │ │   │  │
│  │  │  └────────────────────────────────────────────────────┘ │   │  │
│  │  └────────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │            External Services                                       │  │
│  │  ┌────────────────┐                                               │  │
│  │  │ EODHD API      │ ← Fetches fundamentals + prices               │  │
│  │  │ (100K/day)     │                                               │  │
│  │  └────────────────┘                                               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         Local Development Machine                        │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Git Repository: /root/gitlab/financial-screener                  │  │
│  │  ├── airflow/                                                     │  │
│  │  │   ├── dags/           ← DAG development                        │  │
│  │  │   └── docs/           ← This documentation                     │  │
│  │  ├── services/                                                    │  │
│  │  │   ├── data-collector/ ← Enhanced with metadata logging         │  │
│  │  │   └── technical-analyzer/                                      │  │
│  │  └── database/                                                    │  │
│  │      └── migrations/      ← 005_process_metadata_tables.sql       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### 1. Airflow Scheduler
**Role:** Orchestrator and workflow engine

**Responsibilities:**
- Parse DAGs from `/opt/airflow/dags/`
- Execute tasks on schedule (cron expressions)
- Manage task dependencies and retries
- Trigger K8s Jobs via KubernetesPodOperator
- Store execution state in Airflow metadata DB (PostgreSQL)

**Why Airflow:**
- Built-in retry logic and error handling
- Rich UI for monitoring and manual triggers
- XCom for inter-task communication
- Native Kubernetes integration
- Python-based DAG definition (easy to maintain)

### 2. PostgreSQL Metadata Tables
**Role:** Single source of truth for process state

**Responsibilities:**
- Track every process execution (DAG runs)
- Maintain per-ticker processing state
- Store detailed logs of each asset processed
- Enable delta discovery (what needs processing?)
- Prevent duplicates via constraints
- Provide views for monitoring

**Why Separate Metadata:**
- Decouples process logic from business data
- Fast queries (no scanning 5M+ price records)
- Auditable history of all operations
- Enables idempotent pipelines
- Supports reprocessing workflows

**Key Tables:**
- `process_executions`: DAG run metadata
- `asset_processing_state`: Per-ticker state machine
- `asset_processing_details`: Granular operation logs

### 3. Data Collector Service
**Role:** Fetch and store financial data

**Responsibilities:**
- Fetch data from EODHD API (fundamentals + prices)
- Insert/update data in business tables (assets, stock_prices)
- Log operations to metadata tables
- Update asset processing state
- Handle API errors and rate limits

**Enhancements for Airflow:**
- Accept `--execution-id` parameter (link to DAG run)
- Log to `asset_processing_details` table
- Update `asset_processing_state` after each ticker
- Return metrics (successes, failures, API calls used)

### 4. Technical Analyzer Service
**Role:** Calculate technical indicators

**Responsibilities:**
- Fetch price data from stock_prices table
- Calculate 30+ technical indicators (RSI, MACD, etc.)
- Store in technical_indicators table
- Log to metadata tables

**Enhancements:**
- Query `asset_processing_state` for tickers needing indicators
- Use `--skip-existing` to avoid recalculation
- Log execution_id for traceability

### 5. Kubernetes Jobs
**Role:** Ephemeral compute workloads

**Why Jobs (not CronJobs):**
- Airflow triggers jobs dynamically (better control)
- Jobs are parameterized by DAG (different ticker lists)
- Jobs write execution_id to metadata (traceability)
- Jobs are idempotent (can retry safely)

### 6. Ticker Configuration Files
**Role:** Source of truth for asset universe

**Location:** `config/tickers/`
- `nyse.txt`: 2,339 stocks
- `nasdaq.txt`: 4,086 stocks
- `lse.txt`: 3,145 stocks
- `frankfurt.txt`: 10,209 stocks
- (etc.)

**Usage:**
- DAG reads files at runtime
- Compares with `asset_processing_state` table
- Discovers new tickers to process

---

## Data Flow

### Daily Data Collection Flow

```
1. Schedule Trigger (21:30 UTC)
   ↓
2. DAG: data_collection_equities starts
   ↓
3. Task: discover_assets_delta
   - Read ticker files (21,817 tickers)
   - Query asset_processing_state table
   - Return: {new_assets: [...], needs_update: [...]}
   ↓
4. Task: process_new_assets (if any new tickers)
   - Submit K8s Job with ticker list
   - Job executes: main_enhanced.py --mode bulk --tickers=...
   - Fetches fundamentals (10 API calls) + 2 years prices (1 API call)
   - Writes to assets + stock_prices tables
   - Updates asset_processing_state (fundamentals_loaded=TRUE)
   - Logs to asset_processing_details
   ↓
5. Task: process_existing_assets (daily price updates)
   - Submit K8s Job
   - Job executes: main_enhanced.py --mode incremental
   - Fetches yesterday's price (1 API call per ticker)
   - Inserts into stock_prices (ON CONFLICT DO NOTHING)
   - Updates asset_processing_state (prices_last_date=yesterday)
   ↓
6. Task: update_execution_metadata
   - Query asset_processing_details for counts
   - Update process_executions (status=success, assets_processed=N)
   ↓
7. Trigger: dag_calculate_indicators (separate DAG)
   ↓
8. Calculate indicators for updated assets
   ↓
9. Complete
```

### Metadata Query Pattern

**Before (Manual K8s Jobs):**
```sql
-- How many stocks have prices?
SELECT COUNT(DISTINCT asset_id) FROM stock_prices;

-- Which stocks need prices?
SELECT ticker FROM assets WHERE ticker NOT IN (SELECT DISTINCT ticker FROM stock_prices JOIN assets...);
```
❌ Slow, complex, scans millions of rows

**After (Metadata-Driven):**
```sql
-- Which stocks need processing?
SELECT ticker FROM asset_processing_state
WHERE fundamentals_loaded = FALSE
   OR prices_last_date < CURRENT_DATE - 1;
```
✅ Fast, simple, indexed, single table

---

## Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Orchestration** | Apache Airflow | 3.0.2 | Workflow scheduling |
| **Container Platform** | K3s (Kubernetes) | 1.28+ | Container orchestration |
| **Database** | PostgreSQL | 16 | Data + metadata storage |
| **Message Broker** | Redis | 7.0 | Caching, Airflow backend |
| **Application** | Python | 3.11 | DAGs + data services |
| **Data API** | EODHD | - | Financial data provider |
| **Hardware** | Raspberry Pi 4/5 | ARM64 | 8-node cluster |

**Airflow Providers Used:**
- `apache-airflow-providers-cncf-kubernetes` - K8s integration
- `apache-airflow-providers-postgres` - Database connections

---

## Design Principles

### 1. Idempotency First
**Every component can run multiple times safely:**
- Database constraints prevent duplicate data
- `ON CONFLICT DO UPDATE/NOTHING` in all inserts
- `--skip-existing` flags in applications
- Airflow tasks are stateless

**Example:**
```python
# Running this 10 times produces same result as running once
INSERT INTO assets (ticker, name) VALUES ('AAPL', 'Apple Inc.')
ON CONFLICT (ticker) DO NOTHING;
```

### 2. Metadata-Driven Logic
**Never query business tables for process decisions:**
- ❌ `SELECT COUNT(*) FROM stock_prices WHERE ticker = 'AAPL'`
- ✅ `SELECT prices_last_date FROM asset_processing_state WHERE ticker = 'AAPL'`

**Benefits:**
- Faster queries (small metadata tables)
- Clear separation of concerns
- Auditable state transitions
- Easy to debug

### 3. Single Process for All Modes
**Same DAG handles:**
- Initial bulk load (new tickers)
- Daily incremental updates (existing tickers)
- Reprocessing (flagged tickers)
- Failure retries

**Logic:**
```python
if ticker not in metadata:
    mode = 'bulk'  # 11 API calls
elif ticker.needs_reprocess:
    mode = 'bulk'  # Force reload
else:
    mode = 'incremental'  # 1 API call
```

### 4. Observable Operations
**Every operation logs:**
- What was processed (ticker)
- When (timestamp)
- Result (success/failed)
- Details (records inserted, API calls, errors)
- Traceability (execution_id links to DAG run)

**Monitoring queries:**
```sql
-- Today's progress
SELECT COUNT(*), status FROM asset_processing_details
WHERE DATE(created_at) = CURRENT_DATE
GROUP BY status;
```

### 5. Fail-Safe Defaults
**Protective measures:**
- `max_active_runs=1` prevents concurrent DAG runs
- Consecutive failure tracking (skip after 5 failures)
- API quota checks before processing
- Soft/hard timeouts on K8s Jobs
- Retry with exponential backoff

### 6. Separation of Concerns

| Layer | Responsibility | Example |
|-------|---------------|---------|
| **Airflow DAG** | Orchestration, scheduling, dependencies | "Run data collection daily at 21:30" |
| **Metadata Tables** | State management, delta discovery | "Ticker AAPL needs price update" |
| **Application Code** | Data fetching, transformation, storage | "Fetch AAPL prices from EODHD API" |
| **Database Constraints** | Data integrity, uniqueness | "UNIQUE(ticker) prevents duplicates" |

---

## Next Steps

Proceed to:
- [02_METADATA_SCHEMA_DESIGN.md](./02_METADATA_SCHEMA_DESIGN.md) - Complete database schema
- [03_DELTA_PROCESSING_STRATEGY.md](./03_DELTA_PROCESSING_STRATEGY.md) - How delta detection works

---

**Document Version:** 1.0
**Last Updated:** 2025-10-21
**Author:** Financial Screener Team
**Status:** Draft - Ready for Review
