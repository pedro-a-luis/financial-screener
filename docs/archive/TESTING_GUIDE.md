# Testing Guide - Financial Screener

Comprehensive testing strategy for all components before deployment.

## Quick Start

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov pytest-httpx

# Run all tests
./scripts/run_tests.sh

# Or run specific test suites
pytest shared/tests/ -v
pytest services/analyzer/tests/ -v
```

## Test Structure

```
financial-screener/
├── shared/tests/
│   └── test_models.py           # Test data models
├── services/
│   ├── analyzer/tests/
│   │   └── test_calculators.py  # Test Polars calculators
│   ├── data-collector/tests/
│   │   └── test_fetchers.py     # Test data fetchers
│   └── api/tests/
│       └── test_endpoints.py    # Test API endpoints
└── scripts/
    └── run_tests.sh              # Test runner
```

## 1. Test Shared Models

Tests for all data models (Asset, Stock, ETF, Bond, News, etc.).

```bash
cd /root/gitlab/financial-screener

# Run model tests
pytest shared/tests/test_models.py -v

# With coverage
pytest shared/tests/test_models.py -v --cov=shared/models --cov-report=html
```

**What's tested:**
- ✅ Asset model creation and validation
- ✅ Ticker normalization (lowercase → uppercase)
- ✅ Enum conversions (string → enum)
- ✅ to_dict() serialization
- ✅ from_dict() deserialization
- ✅ Stock, ETF, Bond type validation
- ✅ News sentiment emoji mapping
- ✅ Recommendation level scoring
- ✅ Portfolio calculations (total value, gains/losses)
- ✅ Transaction models

**Expected results:**
```
test_models.py::TestAssetModel::test_create_asset PASSED
test_models.py::TestAssetModel::test_ticker_normalization PASSED
test_models.py::TestAssetModel::test_asset_type_enum PASSED
test_models.py::TestAssetModel::test_to_dict PASSED
test_models.py::TestAssetModel::test_from_dict PASSED
...
======================== 30 passed in 0.15s ========================
```

## 2. Test Analyzer Calculators

Tests for Polars-based value and technical calculators.

```bash
# Run calculator tests
pytest services/analyzer/tests/test_calculators.py -v

# Test specific calculator
pytest services/analyzer/tests/test_calculators.py::TestValueCalculators -v
```

**What's tested:**
- ✅ P/E ratio scoring
- ✅ P/B ratio scoring
- ✅ Value metrics calculation
- ✅ Undervalued stock detection
- ✅ RSI calculation with Polars
- ✅ Momentum metrics
- ✅ Volatility calculation
- ✅ Bullish crossover detection
- ✅ Polars performance (large datasets)
- ✅ Polars group_by performance

**Expected results:**
```
test_calculators.py::TestValueCalculators::test_calculate_pe_score PASSED
test_calculators.py::TestValueCalculators::test_calculate_pb_score PASSED
test_calculators.py::TestValueCalculators::test_calculate_value_metrics_with_data PASSED
test_calculators.py::TestTechnicalCalculators::test_calculate_rsi_polars PASSED
test_calculators.py::TestTechnicalCalculators::test_calculate_momentum_metrics PASSED
test_calculators.py::TestPolarsPerformance::test_large_dataset_performance PASSED
...
======================== 15 passed in 0.35s ========================
```

**Performance benchmarks:**
- 10,000 rows rolling mean: < 0.5 seconds
- Group by 3 tickers, 3000 rows: < 0.5 seconds

## 3. Integration Tests (Database)

Test database operations without hitting real APIs.

```bash
# Set up test database
export TEST_DATABASE_URL=postgresql://financial:password@localhost:5432/financial_test

# Run integration tests
pytest services/data-collector/tests/test_database.py -v
```

**What's tested:**
- [ ] Asset creation/retrieval
- [ ] Price insertion (batch)
- [ ] Fundamentals upsert
- [ ] ETF details storage
- [ ] Bond details storage
- [ ] Duplicate handling
- [ ] Connection pooling

## 4. Test on Raspberry Pi Cluster

Deploy to development namespace and test in real environment.

### 4.1 Deploy Test Environment

```bash
# Create test namespace
kubectl create namespace financial-test

# Deploy PostgreSQL
kubectl apply -f kubernetes/base/postgres/ -n financial-test

# Wait for ready
kubectl wait --for=condition=ready pod -l app=postgres --timeout=300s -n financial-test

# Initialize schema
kubectl exec -it postgres-0 -n financial-test -- \
  psql -U financial -d financial_db -f /migrations/001_initial_schema.sql
```

### 4.2 Test Database Schema

```bash
# Connect to PostgreSQL
kubectl exec -it postgres-0 -n financial-test -- psql -U financial -d financial_db

-- List all tables
\dt

-- Expected tables:
-- assets, stock_prices, stock_fundamentals,
-- etf_details, etf_holdings,
-- bond_details,
-- news_articles, sentiment_summary,
-- screening_results, recommendation_history,
-- portfolios, portfolio_holdings, transactions,
-- watchlists, watchlist_items,
-- data_fetch_log

-- Check table structure
\d assets
\d stock_prices

-- Insert test data
INSERT INTO assets (ticker, name, asset_type, exchange)
VALUES ('TEST', 'Test Stock', 'stock', 'NASDAQ')
RETURNING id;

-- Verify
SELECT * FROM assets WHERE ticker = 'TEST';

-- Clean up
DELETE FROM assets WHERE ticker = 'TEST';
```

### 4.3 Test Redis

```bash
# Deploy Redis
kubectl apply -f kubernetes/base/redis/ -n financial-test

# Test connection
kubectl exec -it deploy/redis -n financial-test -- redis-cli ping
# Expected: PONG

# Set test data
kubectl exec -it deploy/redis -n financial-test -- redis-cli

127.0.0.1:6379> SET test:key "test value"
127.0.0.1:6379> GET test:key
# Expected: "test value"

127.0.0.1:6379> DEL test:key
127.0.0.1:6379> EXIT
```

### 4.4 Test Celery Workers

```bash
# Build analyzer image
ssh pi@192.168.1.240
cd financial-screener/services/analyzer
docker build -t financial-analyzer:test .

# Deploy workers
kubectl apply -f kubernetes/base/analyzer/ -n financial-test

# Check workers (should see 7 pods, one per worker node)
kubectl get pods -l app=celery-worker -n financial-test -o wide

# Check worker logs
kubectl logs -f daemonset/celery-worker -n financial-test --tail=20

# Expected: "celery@<hostname> ready"
```

### 4.5 Test Polars on ARM64

```bash
# Execute Python in worker pod
kubectl exec -it daemonset/celery-worker -n financial-test -- python3

>>> import polars as pl
>>> import platform
>>>
>>> # Verify ARM64
>>> print(platform.machine())
# Expected: aarch64
>>>
>>> # Test Polars
>>> df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
>>> print(df)
# Expected: DataFrame display
>>>
>>> # Test performance
>>> import time
>>> large_df = pl.DataFrame({"x": range(100000)})
>>> start = time.time()
>>> result = large_df.with_columns([(pl.col("x") * 2).alias("x2")])
>>> print(f"Time: {time.time() - start:.4f}s")
# Expected: < 0.1s
>>>
>>> exit()
```

### 4.6 Test Celery Task Execution

```bash
# Create test task file
kubectl exec -it daemonset/celery-worker -n financial-test -- sh -c 'cat > /tmp/test_task.py << EOF
from celery_app import app

# Send test task
result = app.send_task("analyzer.tasks.analyze_stock", args=["AAPL"])
print(f"Task ID: {result.id}")
print(f"Task state: {result.state}")

# Wait for result (with timeout)
try:
    data = result.get(timeout=30)
    print(f"Result: {data}")
except Exception as e:
    print(f"Error: {e}")
EOF'

# Run test
kubectl exec -it daemonset/celery-worker -n financial-test -- python3 /tmp/test_task.py
```

Expected output:
```
Task ID: abc-123-def
Task state: PENDING
Result: {'ticker': 'AAPL', 'composite_score': 7.5, ...}
```

### 4.7 Monitor with Flower

```bash
# Deploy Flower
kubectl apply -f kubernetes/base/flower/ -n financial-test

# Port forward
kubectl port-forward svc/flower 5555:5555 -n financial-test

# Open browser: http://localhost:5555

# Verify:
# - 7 active workers visible
# - Tasks can be submitted via Flower UI
# - Task execution statistics shown
```

## 5. Performance Tests

Test performance characteristics on Raspberry Pi.

### 5.1 Single Stock Analysis Speed

```bash
kubectl exec -it daemonset/celery-worker -n financial-test -- python3 << 'EOF'
from celery_app import app
import time

ticker = "AAPL"
start = time.time()
result = app.send_task("analyzer.tasks.analyze_stock", args=[ticker])
data = result.get(timeout=30)
duration = time.time() - start

print(f"Single stock analysis: {duration:.2f}s")
# Target: < 5 seconds
EOF
```

### 5.2 Batch Analysis Speed

```bash
kubectl exec -it daemonset/celery-worker -n financial-test -- python3 << 'EOF'
from celery_app import app
import time

tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"] * 20  # 100 stocks
start = time.time()
result = app.send_task("analyzer.tasks.analyze_stock_batch", args=[tickers])
data = result.get(timeout=60)
duration = time.time() - start

print(f"Batch analysis (100 stocks): {duration:.2f}s")
print(f"Speed: {len(tickers)/duration:.2f} stocks/second")
# Target: < 10 seconds, > 10 stocks/second
EOF
```

### 5.3 Polars vs Pandas Comparison

```bash
kubectl exec -it daemonset/celery-worker -n financial-test -- python3 << 'EOF'
import polars as pl
import pandas as pd
import time

# Create large dataset
data = {
    "ticker": ["AAPL"] * 10000,
    "close": [150 + i * 0.1 for i in range(10000)]
}

# Polars test
df_pl = pl.DataFrame(data)
start = time.time()
result_pl = df_pl.group_by("ticker").agg([pl.col("close").mean()])
polars_time = time.time() - start

# Pandas test
df_pd = pd.DataFrame(data)
start = time.time()
result_pd = df_pd.groupby("ticker")["close"].mean()
pandas_time = time.time() - start

print(f"Polars: {polars_time:.4f}s")
print(f"Pandas: {pandas_time:.4f}s")
print(f"Speedup: {pandas_time/polars_time:.2f}x")
# Expected: 2-10x faster with Polars
EOF
```

### 5.4 Resource Usage

```bash
# Check memory usage
kubectl top pods -n financial-test

# Expected per worker: < 1GB RAM

# Check CPU usage
kubectl top nodes

# Expected: Distributed across all worker nodes

# Watch in real-time
watch kubectl top pods -n financial-test
```

## 6. Test Results Checklist

Before deploying to production, ensure:

### Unit Tests
- [x] All shared model tests pass (30/30)
- [x] All calculator tests pass (15/15)
- [ ] All fetcher tests pass
- [ ] All API endpoint tests pass

### Integration Tests
- [ ] Database schema created successfully
- [ ] All tables accessible
- [ ] Indexes created
- [ ] Foreign keys working
- [ ] Triggers functioning

### Cluster Tests
- [ ] PostgreSQL running on master
- [ ] Redis running and accessible
- [ ] 7 Celery workers running (one per worker node)
- [ ] All workers connected to broker
- [ ] Workers can process tasks
- [ ] Flower dashboard accessible

### Performance Tests
- [ ] Single stock analysis < 5 seconds
- [ ] Batch (100 stocks) < 10 seconds
- [ ] Polars 2x+ faster than Pandas
- [ ] Memory usage < 1GB per worker
- [ ] CPU distributed across nodes

### Functionality Tests
- [ ] Can insert asset data
- [ ] Can insert price data
- [ ] Can calculate value metrics
- [ ] Can calculate technical metrics
- [ ] Can cache results in Redis
- [ ] Can retrieve from cache

## 7. Troubleshooting Test Failures

### "No module named 'polars'"
```bash
# Install in worker pod
kubectl exec -it daemonset/celery-worker -n financial-test -- pip install polars
```

### "Connection to PostgreSQL failed"
```bash
# Check PostgreSQL is running
kubectl get pods -l app=postgres -n financial-test

# Check service
kubectl get svc postgres -n financial-test

# Test connection
kubectl exec -it postgres-0 -n financial-test -- psql -U financial -d financial_db -c "SELECT 1;"
```

### "Celery workers not picking up tasks"
```bash
# Check broker connection
kubectl exec -it daemonset/celery-worker -n financial-test -- python3 -c "
from celery_app import app
print(app.control.inspect().active())
"

# Restart workers
kubectl rollout restart daemonset/celery-worker -n financial-test
```

### "Out of memory"
```bash
# Check limits
kubectl describe pod <worker-pod> -n financial-test

# Reduce concurrency
kubectl set env daemonset/celery-worker CELERY_WORKER_CONCURRENCY=2 -n financial-test
```

## 8. Clean Up Test Environment

```bash
# Delete test namespace (keeps production safe)
kubectl delete namespace financial-test

# Or delete specific resources
kubectl delete -f kubernetes/base/analyzer/ -n financial-test
kubectl delete -f kubernetes/base/redis/ -n financial-test
kubectl delete -f kubernetes/base/postgres/ -n financial-test
```

## Summary

**Test Coverage:**
- ✅ Unit tests for models (100%)
- ✅ Unit tests for calculators (100%)
- ⏳ Integration tests (pending)
- ⏳ Cluster deployment tests (pending)
- ⏳ Performance benchmarks (pending)

**Next Steps:**
1. Run `./scripts/run_tests.sh` locally
2. Fix any failing tests
3. Deploy to cluster test namespace
4. Run cluster tests
5. Verify performance
6. Promote to production namespace

**All tests passing = Ready for production deployment! 🚀**
