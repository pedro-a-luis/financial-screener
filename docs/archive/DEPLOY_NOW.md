# Deploy to Cluster - Step-by-Step Guide

Follow these steps to deploy the Financial Screener core services to your Raspberry Pi K3s cluster.

## Prerequisites

- ✅ K3s cluster running (192.168.1.240-247)
- ✅ kubectl configured to access cluster
- ✅ PostgreSQL already running in cluster (shared database)
- ✅ SSH access to master node (pi@192.168.1.240)

**Note:** This project uses a dedicated PostgreSQL schema (`financial_screener`) within your existing shared database, allowing it to coexist with other projects without conflicts.

## Quick Deploy (15 minutes)

```bash
# On your local machine, push code to cluster
rsync -avz /root/gitlab/financial-screener/ pi@192.168.1.240:~/financial-screener/

# SSH to master node
ssh pi@192.168.1.240

# Navigate to project
cd ~/financial-screener

# Build the analyzer image (from project root for shared models)
docker build -f services/analyzer/Dockerfile -t financial-analyzer:latest .

# Run deployment script
./scripts/deploy-to-cluster.sh

# Test deployment
./scripts/test-cluster-deployment.sh
```

## Detailed Step-by-Step

### Step 1: Transfer Code to Cluster (2 minutes)

```bash
# From your development machine
rsync -avz --exclude='node_modules' --exclude='.git' --exclude='__pycache__' \
    /root/gitlab/financial-screener/ \
    pi@192.168.1.240:~/financial-screener/

# Verify transfer
ssh pi@192.168.1.240 "ls -la ~/financial-screener"
```

### Step 2: Build Docker Image (5 minutes)

```bash
# SSH to master node
ssh pi@192.168.1.240

# Navigate to project root (build context needs shared models)
cd ~/financial-screener

# Build image for ARM64 (using project root as build context)
docker build -f services/analyzer/Dockerfile -t financial-analyzer:latest .

# Verify image
docker images | grep financial-analyzer

# Expected output:
# financial-analyzer  latest  <image-id>  X minutes ago  XXX MB
```

### Step 3: Deploy Services (5 minutes)

```bash
# Return to project root
cd ~/financial-screener

# Run deployment script
./scripts/deploy-to-cluster.sh
```

**The script will:**
1. ✅ Check cluster connectivity
2. ✅ Detect existing PostgreSQL
3. ✅ Detect existing Redis (or deploy if needed)
4. ✅ Create namespace `financial-screener`
5. ✅ Create secrets for database connection
6. ✅ Initialize database
7. ✅ Deploy Celery workers (DaemonSet = 1 per node)
8. ✅ Deploy Flower monitoring dashboard

**Follow the prompts:**
- PostgreSQL username: Your existing PostgreSQL username (e.g., `postgres`)
- PostgreSQL password: Your existing password
- Database name: Your shared database name (e.g., `postgres`, `shared_db`)

**Important:** The script will create a dedicated schema `financial_screener` in your database, so this project's tables won't conflict with other projects.

### Step 4: Verify Deployment (2 minutes)

```bash
# Check all resources
kubectl get all -n financial-screener

# Expected output:
# NAME                         READY   STATUS    RESTARTS   AGE
# pod/celery-worker-xxxxx      1/1     Running   0          30s  (×7 pods, one per worker)
# pod/flower-xxxxx             1/1     Running   0          30s
# pod/init-database-xxxxx      0/1     Completed 0          30s

# NAME             TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
# service/flower   LoadBalancer   10.43.xxx.xxx   <pending>     5555:xxxxx/TCP   30s
# service/redis    ClusterIP      10.43.xxx.xxx   <none>        6379/TCP         30s

# NAME                           DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE
# daemonset.apps/celery-worker   7         7         7       7            7

# NAME                     READY   UP-TO-DATE   AVAILABLE   AGE
# deployment.apps/flower   1/1     1            1           30s

# Check worker nodes distribution
kubectl get pods -n financial-screener -l app=celery-worker -o wide

# You should see 7 pods, one on each worker node (192.168.1.241-247)
```

### Step 5: Verify Database Schema (1 minute)

The deployment script automatically initialized the database schema in the `financial_screener` schema.

```bash
# Verify schema and tables were created
kubectl exec -n financial-screener daemonset/celery-worker -- \
    psql -h postgres.default.svc.cluster.local \
    -U <your-username> \
    -d <your-database> \
    -c "\dt financial_screener.*"

# Expected: List of 14 tables in financial_screener schema
# Example output:
#              List of relations
#     Schema          |       Name        | Type  |  Owner
# --------------------+-------------------+-------+----------
#  financial_screener | assets            | table | postgres
#  financial_screener | bond_details      | table | postgres
#  financial_screener | etf_details       | table | postgres
#  ... (11 more tables)

# Check schema exists
kubectl exec -n financial-screener daemonset/celery-worker -- \
    psql -h postgres.default.svc.cluster.local \
    -U <your-username> \
    -d <your-database> \
    -c "\dn financial_screener"

# Check custom types
kubectl exec -n financial-screener daemonset/celery-worker -- \
    psql -h postgres.default.svc.cluster.local \
    -U <your-username> \
    -d <your-database> \
    -c "\dT financial_screener.*"
```

## Step 6: Run Tests

```bash
# Run automated cluster tests
./scripts/test-cluster-deployment.sh
```

**Expected test results:**
```
Testing: Namespace exists
✓ PASS: Namespace exists

Testing: Redis is accessible
✓ PASS: Redis is accessible

Testing: PostgreSQL is accessible
✓ PASS: PostgreSQL is accessible

Testing: Celery workers running
✓ PASS: 7 Celery workers running

Testing: Polars installed in workers
✓ PASS: Polars installed in workers

Testing: Celery broker connection
✓ PASS: Celery broker connection

Testing: Flower dashboard accessible
✓ PASS: Flower dashboard accessible

Testing: Polars performance on ARM64
Architecture: aarch64
Polars 10K rows: 0.0234s
PASS
✓ PASS: Polars performance test

=== Test Summary ===
Passed: 8
Failed: 0
Total: 8

All tests passed! ✓
```

## Step 7: Access Flower Dashboard

```bash
# Port forward Flower to your local machine
kubectl port-forward svc/flower 5555:5555 -n financial-screener

# Open browser to: http://localhost:5555
```

**In Flower, you should see:**
- 7 active workers (one per Raspberry Pi worker node)
- Worker names: celery@rpi-worker-01, celery@rpi-worker-02, etc.
- Each worker: 4 processes (matching 4 CPU cores)
- Broker: Connected
- Tasks: Ready to accept

## Step 8: Manual Testing

### Test 1: Redis Connectivity

```bash
kubectl exec -n financial-screener daemonset/celery-worker -- redis-cli -h redis.default.svc.cluster.local ping

# Expected: PONG
```

### Test 2: PostgreSQL Connectivity

```bash
kubectl exec -n financial-screener daemonset/celery-worker -- \
    psql -h postgres.default.svc.cluster.local -U <your-username> -d <your-database> -c "SELECT 1"

# Expected:
#  ?column?
# ----------
#         1
# (1 row)
```

### Test 3: Polars Performance

```bash
kubectl exec -n financial-screener daemonset/celery-worker -- python3 << 'EOF'
import polars as pl
import time
import platform

print(f"Architecture: {platform.machine()}")
print(f"Polars version: {pl.__version__}")

# Performance test
df = pl.DataFrame({"x": range(100000)})

start = time.time()
result = df.with_columns([
    (pl.col("x") * 2).alias("x2"),
    (pl.col("x") ** 2).alias("x_squared")
])
duration = time.time() - start

print(f"Processed 100K rows in {duration:.4f} seconds")
print(f"Throughput: {100000/duration:.0f} rows/second")
EOF

# Expected:
# Architecture: aarch64
# Polars version: 1.17.1
# Processed 100K rows in 0.0456 seconds
# Throughput: 2192982 rows/second
```

### Test 4: Celery Task (When Tasks Are Implemented)

```bash
kubectl exec -n financial-screener daemonset/celery-worker -- python3 << 'EOF'
from celery_app import app

# Check Celery connection
inspector = app.control.inspect()
print("Active workers:", inspector.active())
print("Registered tasks:", inspector.registered())
EOF
```

## Step 9: View Logs

```bash
# View logs from all workers
kubectl logs -f daemonset/celery-worker -n financial-screener

# View logs from specific worker
kubectl logs -f daemonset/celery-worker-xxxxx -n financial-screener

# View Flower logs
kubectl logs -f deployment/flower -n financial-screener

# View init job logs
kubectl logs job/init-database-xxxxx -n financial-screener
```

## Step 10: Check Resource Usage

```bash
# Node resource usage
kubectl top nodes

# Pod resource usage
kubectl top pods -n financial-screener

# Expected per worker:
# NAME                    CPU(cores)   MEMORY(bytes)
# celery-worker-xxxxx     50m          500Mi

# All 7 workers should use < 4GB total RAM
```

## Troubleshooting

### Workers Not Starting

```bash
# Check events
kubectl get events -n financial-screener --sort-by='.lastTimestamp'

# Describe worker pod
kubectl describe daemonset/celery-worker -n financial-screener

# Check if image exists
docker images | grep financial-analyzer
```

### Can't Connect to PostgreSQL

```bash
# Test from worker pod
kubectl exec -it daemonset/celery-worker -n financial-screener -- bash

# Inside pod:
psql -h postgres.default.svc.cluster.local -U <your-username> -l

# If fails, check:
# 1. PostgreSQL is running: kubectl get pods -n default | grep postgres
# 2. Service exists: kubectl get svc postgres -n default
# 3. Credentials are correct
```

### Can't Connect to Redis

```bash
# Test from worker pod
kubectl exec -it daemonset/celery-worker -n financial-screener -- \
    redis-cli -h redis.default.svc.cluster.local ping

# If fails:
# Check if Redis pod is running
kubectl get pods -n financial-screener | grep redis

# Check service
kubectl get svc redis -n financial-screener
```

### Celery Workers Can't Connect to Broker

```bash
# Check Redis is accessible
kubectl exec -it daemonset/celery-worker -n financial-screener -- \
    redis-cli -h redis.default.svc.cluster.local ping

# Check Celery configuration
kubectl exec -it daemonset/celery-worker -n financial-screener -- \
    celery -A celery_app inspect ping

# Check environment variables
kubectl exec -it daemonset/celery-worker -n financial-screener -- env | grep -E 'REDIS|CELERY'
```

## Clean Up (If Needed)

```bash
# Delete everything in namespace
kubectl delete namespace financial-screener

# Or delete specific resources
kubectl delete daemonset/celery-worker -n financial-screener
kubectl delete deployment/flower -n financial-screener
kubectl delete svc/flower -n financial-screener
```

## Next Steps After Successful Deployment

1. **Run Unit Tests on Cluster**
   ```bash
   kubectl exec -it daemonset/celery-worker -n financial-screener -- \
       pytest /app/tests/ -v
   ```

2. **Initialize Sample Data** (when data collector is ready)
   ```bash
   # Will fetch data for sample tickers
   ```

3. **Deploy Data Collector CronJob** (next phase)

4. **Deploy API Service** (next phase)

5. **Deploy Frontend** (next phase)

## Success Criteria

✅ **Deployment successful if:**
- 7 Celery worker pods running (one per worker node)
- 1 Flower pod running
- All pods in `Running` status
- Redis accessible from workers
- PostgreSQL accessible from workers
- Database schema initialized (14 tables)
- Flower dashboard accessible
- All tests passing (./scripts/test-cluster-deployment.sh)
- Polars performance test < 0.1s for 10K rows

## Performance Expectations

On Raspberry Pi 5 cluster:
- **Celery workers**: 7 pods × 4 cores = 28 concurrent task processors
- **Memory per worker**: ~500MB
- **Total cluster memory used**: ~4GB (out of 56GB available)
- **Polars throughput**: > 1M rows/second on ARM64
- **Task latency**: < 100ms broker overhead

---

**You're now ready to process financial data at scale on your Raspberry Pi cluster!** 🚀
