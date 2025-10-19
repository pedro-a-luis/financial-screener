# Testing on Raspberry Pi Cluster

Use your Raspberry Pi K3s cluster for both **development** and **production**.

## Two-Namespace Approach

```
financial-screener-dev   # Development/testing namespace
financial-screener-prod  # Production namespace
```

Both run on the same cluster, isolated by Kubernetes namespaces.

## Benefits of Testing on Cluster

- ✅ **Same environment** as production (no "works on my machine")
- ✅ **Test ARM64 compatibility** directly
- ✅ **Test real networking** (service discovery, DNS)
- ✅ **Test resource limits** (memory, CPU constraints)
- ✅ **Fast feedback** (no need to rebuild/redeploy for prod)
- ✅ **Utilize cluster resources** (why not use those 8 Pis!)

## Quick Setup

### 1. Create Development Namespace

```bash
kubectl create namespace financial-screener-dev
kubectl config set-context --current --namespace=financial-screener-dev
```

### 2. Deploy to Development

```bash
# Use development overlays (lighter resource limits, debug logging)
kubectl apply -k kubernetes/overlays/development

# Or deploy individual services for testing
kubectl apply -f kubernetes/base/postgres/
kubectl apply -f kubernetes/base/redis/
kubectl apply -f kubernetes/base/analyzer/
```

### 3. Quick Iteration Workflow

```bash
# Edit code on your machine
vim services/analyzer/src/tasks.py

# Build image on cluster (fast, no cross-compilation)
ssh pi@192.168.1.240
cd financial-screener/services/analyzer
docker build -t financial-analyzer:dev .

# Update pod to use new image
kubectl set image daemonset/celery-worker celery-worker=financial-analyzer:dev -n financial-screener-dev

# Or force restart to pull latest
kubectl rollout restart daemonset/celery-worker -n financial-screener-dev

# Watch logs in real-time
kubectl logs -f daemonset/celery-worker -n financial-screener-dev
```

### 4. Test Specific Features

```bash
# Test Celery task
kubectl exec -it deploy/api -n financial-screener-dev -- \
  python -c "
from tasks import analyze_stock_batch
result = analyze_stock_batch(['AAPL', 'MSFT', 'GOOGL'])
print(result)
"

# Test database connection
kubectl exec -it postgres-0 -n financial-screener-dev -- \
  psql -U financial -d financial_db -c "SELECT ticker, name FROM assets LIMIT 10;"

# Test Redis
kubectl exec -it deploy/redis -n financial-screener-dev -- redis-cli ping
```

## Development Workflow

### Option 1: Remote Development (Recommended)

```bash
# SSH to master node
ssh pi@192.168.1.240

# Clone repo or pull latest
cd financial-screener
git pull

# Edit code directly on Pi using vim/nano
vim services/analyzer/src/calculators/value.py

# Build and test immediately
cd services/analyzer
docker build -t financial-analyzer:dev .
kubectl rollout restart daemonset/celery-worker -n financial-screener-dev

# Test
kubectl logs -f daemonset/celery-worker -n financial-screener-dev --tail=50
```

### Option 2: Local Edit + Remote Deploy

```bash
# Edit on your machine
vim services/analyzer/src/tasks.py

# Sync to cluster
rsync -avz services/analyzer/ pi@192.168.1.240:~/financial-screener/services/analyzer/

# Build on cluster via SSH
ssh pi@192.168.1.240 "cd financial-screener/services/analyzer && docker build -t financial-analyzer:dev ."

# Restart service
kubectl rollout restart daemonset/celery-worker -n financial-screener-dev
```

### Option 3: VS Code Remote-SSH (Best of Both Worlds)

```bash
# Install VS Code Remote-SSH extension
# Connect to pi@192.168.1.240
# Open folder: ~/financial-screener

# Edit code in VS Code (locally), runs on Pi (remotely)
# Terminal in VS Code runs commands directly on Pi
```

## Resource Allocation for Development

Development uses lighter resource limits to allow more testing:

```yaml
# kubernetes/overlays/development/celery-worker.yaml
resources:
  requests:
    memory: "512Mi"  # Half of production
    cpu: "500m"
  limits:
    memory: "1Gi"
    cpu: "2000m"
```

This allows running **both dev and prod** on the same cluster if needed.

## Testing Scenarios

### Test 1: Single Stock Analysis

```bash
kubectl exec -it deploy/api -n financial-screener-dev -- python3 << 'EOF'
from celery_app import app

# Submit task
result = app.send_task('analyzer.tasks.analyze_stock', args=['AAPL'])

# Wait for result
print(result.get(timeout=30))
EOF
```

### Test 2: Batch Analysis (Polars Performance)

```bash
kubectl exec -it deploy/api -n financial-screener-dev -- python3 << 'EOF'
from celery_app import app
import time

tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'] * 20  # 100 stocks

start = time.time()
result = app.send_task('analyzer.tasks.analyze_stock_batch', args=[tickers])
data = result.get(timeout=60)
duration = time.time() - start

print(f"Analyzed {len(tickers)} stocks in {duration:.2f} seconds")
print(f"Speed: {len(tickers)/duration:.2f} stocks/second")
EOF
```

### Test 3: Screening

```bash
kubectl exec -it deploy/api -n financial-screener-dev -- python3 << 'EOF'
from celery_app import app

criteria = {
    "pe_ratio_max": 20,
    "roe_min": 0.15,
    "debt_to_equity_max": 1.5
}

result = app.send_task('analyzer.tasks.screen_stocks',
                       kwargs={'criteria': criteria, 'limit': 50})

results = result.get(timeout=60)
print(f"Found {results['count']} stocks matching criteria")
for stock in results['results'][:5]:
    print(f"{stock['ticker']}: Score {stock['composite_score']:.2f}")
EOF
```

### Test 4: Load Test (All Workers)

```bash
# Submit 1000 tasks to test distribution
kubectl exec -it deploy/api -n financial-screener-dev -- python3 << 'EOF'
from celery_app import app
import time

# Submit 1000 tasks
tasks = []
for i in range(1000):
    ticker = f"TEST{i}"
    task = app.send_task('analyzer.tasks.analyze_stock', args=[ticker])
    tasks.append(task)

# Monitor Flower dashboard to see distribution across workers
print(f"Submitted {len(tasks)} tasks")
print("Check Flower dashboard: kubectl port-forward svc/flower 5555:5555")
EOF
```

## Monitoring During Testing

### Watch All Celery Workers

```bash
# See all workers
kubectl get pods -l app=celery-worker -n financial-screener-dev -o wide

# Watch logs from all workers
kubectl logs -f -l app=celery-worker -n financial-screener-dev --all-containers=true --max-log-requests=7

# Watch specific worker
kubectl logs -f celery-worker-xxxxx -n financial-screener-dev
```

### Resource Usage

```bash
# Node resource usage
kubectl top nodes

# Pod resource usage
kubectl top pods -n financial-screener-dev

# Watch in real-time
watch kubectl top pods -n financial-screener-dev
```

### Flower Dashboard

```bash
# Port forward Flower
kubectl port-forward svc/flower 5555:5555 -n financial-screener-dev

# Open browser to http://localhost:5555
# You'll see:
# - Number of active workers (should be 7, one per worker node)
# - Tasks per worker
# - Success/failure rates
# - Task execution times
```

## Debugging

### Interactive Shell in Pod

```bash
# Python shell in analyzer pod
kubectl exec -it daemonset/celery-worker -n financial-screener-dev -- python3

>>> import polars as pl
>>> pl.__version__
'1.17.1'

>>> # Test database connection
>>> from config import settings
>>> print(settings.database_url)
```

### Check Database

```bash
kubectl exec -it postgres-0 -n financial-screener-dev -- psql -U financial -d financial_db

-- Check tables
\dt

-- Check data
SELECT ticker, name FROM assets LIMIT 10;

-- Check prices
SELECT COUNT(*) FROM stock_prices;
```

### Check Celery Queue

```bash
kubectl exec -it deploy/redis -n financial-screener-dev -- redis-cli

127.0.0.1:6379> KEYS *
127.0.0.1:6379> LLEN celery  # Queue length
127.0.0.1:6379> LRANGE celery 0 10  # Show queued tasks
```

## Common Issues

### Workers Not Picking Up Tasks

```bash
# Check worker status
kubectl exec -it deploy/api -n financial-screener-dev -- \
  celery -A celery_app inspect active

# Restart workers
kubectl rollout restart daemonset/celery-worker -n financial-screener-dev
```

### Out of Memory

```bash
# Check memory usage
kubectl top pods -n financial-screener-dev

# If worker is using too much memory:
kubectl edit daemonset/celery-worker -n financial-screener-dev
# Reduce CELERY_WORKER_CONCURRENCY from 4 to 2
```

### Slow Performance

```bash
# Check Polars is being used (not pandas)
kubectl logs -f daemonset/celery-worker -n financial-screener-dev | grep -i polars

# Check task execution time in Flower dashboard
# Should be <1s for single stock, <5s for 100 stocks
```

## Promotion to Production

Once testing is complete:

```bash
# Tag tested image as production
docker tag financial-analyzer:dev financial-analyzer:v1.0

# Deploy to production namespace
kubectl apply -k kubernetes/overlays/production

# Or deploy specific service
kubectl set image daemonset/celery-worker \
  celery-worker=financial-analyzer:v1.0 \
  -n financial-screener-prod
```

## Cleanup

```bash
# Delete development namespace (keeps production intact)
kubectl delete namespace financial-screener-dev

# Or delete specific resources
kubectl delete -k kubernetes/overlays/development
```

## Summary

**Development/Testing on Cluster:**
- ✅ Same ARM64 environment as production
- ✅ Test with real Kubernetes networking
- ✅ Utilize all 8 Raspberry Pis
- ✅ Fast iteration (build locally, test immediately)
- ✅ No Docker Desktop or cross-compilation needed
- ✅ Easy promotion to production (same images)

**This is the recommended approach** for your setup!
