# Manual Deployment Steps Required

## Summary

The deployment is 90% complete. The Docker image has been built and is on the master node at `/tmp/financial-analyzer.tar` (206MB).

## What's Already Done ✅

1. ✅ Docker image built with fixed Celery configuration
2. ✅ Image transferred to master node (`/tmp/financial-analyzer.tar`)
3. ✅ Namespace created (`financial-screener`)
4. ✅ ConfigMap and Secrets created
5. ✅ DaemonSet and Flower deployment created
6. ✅ Redis found and accessible (`redis.redis.svc.cluster.local:6379`)
7. ✅ PostgreSQL found and accessible (`postgresql-primary.databases.svc.cluster.local:5432`)

## What Needs To Be Done Manually

### 1. Distribute Docker Image to Worker Nodes (Required)

SSH to the master node and run these commands:

```bash
# SSH to master
ssh admin@192.168.1.240

# Copy and import image to each worker node
for node in pi-worker-01 pi-worker-02 pi-worker-03 pi-worker-04 pi-worker-05 pi-worker-06 pi-worker-07; do
  echo "Processing $node..."
  scp /tmp/financial-analyzer.tar $node:/tmp/ && \
  ssh $node "sudo k3s ctr images import /tmp/financial-analyzer.tar && sudo rm /tmp/financial-analyzer.tar"
done
```

**Alternative if SSH keys not set up between nodes:**
Manually copy to each worker:
```bash
# From master node, for each worker (01-07):
scp /tmp/financial-analyzer.tar pi-worker-01:/tmp/
ssh pi-worker-01 "sudo k3s ctr images import /tmp/financial-analyzer.tar"

# Repeat for workers 02 through 07
```

### 2. Update Redis URL in ConfigMap

```bash
kubectl patch configmap analyzer-config -n financial-screener \
  --type merge \
  -p '{"data":{"REDIS_URL":"redis://redis.redis.svc.cluster.local:6379/0"}}'
```

### 3. Restart Pods to Use New Image

```bash
# Delete existing pods (DaemonSet will recreate them)
kubectl delete pods --all -n financial-screener

# Or rollout restart
kubectl rollout restart daemonset/celery-worker -n financial-screener
kubectl rollout restart deployment/flower -n financial-screener
```

### 4. Initialize Database Schema

```bash
# Create the schema in PostgreSQL
kubectl exec -n databases postgresql-primary-0 -- \
  psql -U postgres -d postgres <<'EOF'
-- Create dedicated schema for this project
CREATE SCHEMA IF NOT EXISTS financial_screener;

-- Set search path for this migration
SET search_path TO financial_screener, public;

-- Asset types enum
CREATE TYPE financial_screener.asset_type_enum AS ENUM ('stock', 'etf', 'bond');

-- Recommendation enum
CREATE TYPE financial_screener.recommendation_enum AS ENUM (
    'STRONG_BUY',
    'BUY',
    'HOLD',
    'SELL',
    'STRONG_SELL'
);

-- Sentiment enum
CREATE TYPE financial_screener.sentiment_enum AS ENUM ('positive', 'neutral', 'negative');

-- Continue with rest of schema from database/migrations/001_initial_schema.sql...
EOF
```

**Better approach - copy schema file:**
```bash
# From your local machine
scp -i ~/.ssh/pi_cluster database/migrations/001_initial_schema.sql admin@192.168.1.240:/tmp/

# On master node
kubectl cp /tmp/001_initial_schema.sql databases/postgresql-primary-0:/tmp/

# Execute schema
kubectl exec -n databases postgresql-primary-0 -- \
  psql -U postgres -d postgres -f /tmp/001_initial_schema.sql
```

### 5. Verify Deployment

```bash
# Check pod status
kubectl get pods -n financial-screener -o wide

# Expected: 7 celery-worker pods (one per worker node) + 1 flower pod, all Running

# Check logs
kubectl logs -n financial-screener -l app=celery-worker --tail=20

# Check Flower dashboard
kubectl port-forward -n financial-screener svc/flower 5555:5555

# Open browser to http://localhost:5555
```

## Current Issues

### Issue 1: Celery Module Path ✅ FIXED
- **Status**: Fixed in new image
- **Fix**: Changed `app.autodiscover_tasks(["analyzer.tasks"])` to `app.autodiscover_tasks(["tasks"])`

### Issue 2: Redis URL ⚠️ NEEDS UPDATE
- **Status**: ConfigMap has wrong URL
- **Current**: `redis://redis.databases.svc.cluster.local:6379/0`
- **Correct**: `redis://redis.redis.svc.cluster.local:6379/0`
- **Fix**: Run command from step 2 above

### Issue 3: Image Not on Worker Nodes ⚠️ NEEDS MANUAL ACTION
- **Status**: Image only on master node
- **Impact**: 6 of 7 worker pods show `ErrImageNeverPull`
- **Fix**: Run commands from step 1 above

## Expected Final State

After completing the manual steps, you should have:

```
NAMESPACE              NAME                          READY   STATUS
financial-screener     celery-worker-xxxxx (×7)     1/1     Running
financial-screener     flower-xxxxxxxx-xxxxx        1/1     Running
```

All 7 celery workers should be running, one on each worker node.

## Verification Commands

```bash
# 1. Check all pods running
kubectl get pods -n financial-screener

# 2. Check worker distribution
kubectl get pods -n financial-screener -o wide | grep celery-worker

# 3. Test Redis connection
kubectl exec -n financial-screener deployment/flower -- redis-cli -h redis.redis.svc.cluster.local ping

# 4. Test PostgreSQL connection
kubectl exec -n financial-screener deployment/flower -- \
  psql -h postgresql-primary.databases.svc.cluster.local -U postgres -d postgres -c "SELECT 1"

# 5. Check database schema
kubectl exec -n databases postgresql-primary-0 -- \
  psql -U postgres -d postgres -c "\dt financial_screener.*"

# 6. View Celery worker logs
kubectl logs -f -n financial-screener -l app=celery-worker --max-log-requests=1

# 7. Check Flower dashboard
kubectl port-forward -n financial-screener svc/flower 5555:5555
# Then visit: http://localhost:5555
```

##Troubleshooting

### Pods still showing ErrImageNeverPull
- Image not on that specific worker node
- Verify with: `ssh pi-worker-XX "sudo k3s ctr images ls | grep financial-analyzer"`
- Re-import if needed

### Pods in CrashLoopBackOff
- Check logs: `kubectl logs -n financial-screener <pod-name>`
- Common issues:
  - Redis connection failed (check Redis URL)
  - PostgreSQL connection failed (check password)
  - Module import errors (check PYTHONPATH in Dockerfile)

### Can't connect to Flower
- Check service: `kubectl get svc -n financial-screener flower`
- Port forward: `kubectl port-forward -n financial-screener svc/flower 5555:5555`
- Check pod logs: `kubectl logs -n financial-screener -l app=flower`

## Next Steps After Deployment

Once all pods are running successfully:

1. Test Celery task execution
2. Verify database schema is created
3. Run integration tests
4. Deploy remaining services (news-fetcher, sentiment-engine, API, frontend)

---

**Current Status**: Ready for manual image distribution

**Time Required**: ~10-15 minutes

**Risk Level**: Low (can rollback by deleting namespace)
