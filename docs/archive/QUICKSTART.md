# Quick Start Guide

Get the Financial Screener running on your Raspberry Pi cluster in **under 30 minutes**.

## Prerequisites

- ✅ K3s cluster running (8× Raspberry Pi 5)
- ✅ kubectl configured
- ✅ NFS storage available

## Step 1: Clone Repository (1 minute)

```bash
# SSH to master node
ssh pi@192.168.1.240

# Clone repo
git clone <your-repo-url> financial-screener
cd financial-screener
```

## Step 2: Create Namespace (30 seconds)

```bash
kubectl create namespace financial-screener-dev
kubectl config set-context --current --namespace=financial-screener-dev
```

## Step 3: Deploy PostgreSQL (5 minutes)

```bash
# Create secret
kubectl create secret generic postgres-secret \
  --from-literal=POSTGRES_USER=financial \
  --from-literal=POSTGRES_PASSWORD=devpassword \
  --from-literal=POSTGRES_DB=financial_db

# Deploy PostgreSQL
kubectl apply -f kubernetes/base/postgres/

# Wait for ready
kubectl wait --for=condition=ready pod -l app=postgres --timeout=300s

# Initialize schema
kubectl exec -it postgres-0 -- \
  psql -U financial -d financial_db < /migrations/001_initial_schema.sql
```

## Step 4: Deploy Redis (2 minutes)

```bash
kubectl apply -f kubernetes/base/redis/

# Verify
kubectl wait --for=condition=ready pod -l app=redis --timeout=60s
```

## Step 5: Build Analyzer Image (5 minutes)

```bash
# Build on Pi (fast, no cross-compilation)
cd services/analyzer
docker build -t financial-analyzer:dev .

# Verify
docker images | grep financial-analyzer
```

## Step 6: Deploy Celery Workers (3 minutes)

```bash
# Deploy to all worker nodes
kubectl apply -f kubernetes/base/analyzer/

# Verify workers (should see 7 pods, one per worker node)
kubectl get pods -l app=celery-worker -o wide

# Check logs
kubectl logs -f daemonset/celery-worker --tail=20
```

## Step 7: Test the System (5 minutes)

### Test Celery Workers

```bash
# Access any worker pod
kubectl exec -it daemonset/celery-worker -- python3

>>> from tasks import analyze_stock_batch
>>> result = analyze_stock_batch(['AAPL', 'MSFT', 'GOOGL'])
>>> print(result)
>>> exit()
```

### Test PostgreSQL

```bash
kubectl exec -it postgres-0 -- psql -U financial -d financial_db

-- Check tables
\dt

-- Exit
\q
```

### Test Redis

```bash
kubectl exec -it deploy/redis -- redis-cli ping
# Should return: PONG
```

## Step 8: Deploy Flower (Optional, 2 minutes)

Monitor your Celery workers:

```bash
kubectl apply -f kubernetes/base/flower/

# Port forward to access
kubectl port-forward svc/flower 5555:5555

# Open browser: http://localhost:5555
```

## Step 9: Run Sample Analysis (5 minutes)

```bash
# Create a test script
cat > test_analysis.py << 'EOF'
from celery_app import app
import time

# Test single stock analysis
print("Testing single stock analysis...")
result = app.send_task('analyzer.tasks.analyze_stock', args=['AAPL'])
data = result.get(timeout=30)
print(f"AAPL Analysis: {data}")

# Test batch analysis (100 stocks)
print("\nTesting batch analysis...")
tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'] * 20
start = time.time()
result = app.send_task('analyzer.tasks.analyze_stock_batch', args=[tickers])
data = result.get(timeout=60)
duration = time.time() - start

print(f"Analyzed {len(tickers)} stocks in {duration:.2f} seconds")
print(f"Speed: {len(tickers)/duration:.2f} stocks/second")
print("Polars is FAST! 🚀")
EOF

# Run test
kubectl exec -it daemonset/celery-worker -- python3 test_analysis.py
```

Expected output:
```
Testing single stock analysis...
AAPL Analysis: {...}

Testing batch analysis...
Analyzed 100 stocks in 5.23 seconds
Speed: 19.12 stocks/second
Polars is FAST! 🚀
```

## Verification Checklist

```bash
# All pods running?
kubectl get pods

# Expected:
# postgres-0          1/1     Running
# redis-xxx           1/1     Running
# celery-worker-xxx   1/1     Running (×7 pods)
# flower-xxx          1/1     Running

# All workers connected?
kubectl exec -it daemonset/celery-worker -- \
  celery -A celery_app inspect active

# Resource usage OK?
kubectl top nodes
kubectl top pods

# Each worker using <2GB RAM? ✅
# Each node using <50% CPU? ✅
```

## Next Steps

Now that the core system is running:

1. **Add data collection**: Deploy the data-collector CronJob
2. **Build the API**: Deploy FastAPI service
3. **Create the frontend**: Deploy React dashboard
4. **Import data**: Fetch historical prices for your watchlist

## Troubleshooting

### Workers not starting?

```bash
# Check logs
kubectl logs -f daemonset/celery-worker --tail=50

# Common issues:
# - Redis not accessible → check service
# - PostgreSQL not ready → check pods
# - Image not found → rebuild image
```

### Can't connect to PostgreSQL?

```bash
# Check PostgreSQL is running
kubectl get pods -l app=postgres

# Test connection
kubectl exec -it postgres-0 -- psql -U financial -d financial_db -c "SELECT 1;"
```

### Out of memory?

```bash
# Check resource usage
kubectl top pods

# Reduce worker concurrency
kubectl set env daemonset/celery-worker CELERY_WORKER_CONCURRENCY=2
```

## Clean Up (Optional)

```bash
# Delete everything in development namespace
kubectl delete namespace financial-screener-dev

# This preserves your production deployment (if any)
```

## Summary

You now have:
- ✅ PostgreSQL with complete schema
- ✅ Redis for caching and queuing
- ✅ 7 Celery workers (one per Pi worker node)
- ✅ 28 concurrent task processors (7 workers × 4 cores)
- ✅ Polars for 2-10x faster data processing
- ✅ Flower dashboard for monitoring

**Total time**: ~30 minutes
**Total cost**: $0 (uses existing cluster)

**Next**: Build the remaining services (API, frontend, data collection) following the same pattern!

🎉 **You're ready to start analyzing stocks at scale!**
