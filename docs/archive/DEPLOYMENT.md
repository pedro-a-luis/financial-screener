# Deployment Guide - Raspberry Pi K3s Cluster

This guide covers deploying the Financial Screener to your 8-node Raspberry Pi K3s cluster.

## Cluster Overview

- **Master Node**: 192.168.1.240
- **Worker Nodes**: 192.168.1.241-247
- **K3s Version**: v1.32.2+k3s1
- **Storage**: NFS on Synology DS118 (192.168.1.10)
- **Architecture**: ARM64 (aarch64)

## Prerequisites

1. **K3s cluster is running** and accessible via kubectl
2. **NFS storage** is configured and accessible
3. **kubectl** configured to access your cluster
4. **Docker buildx** for building ARM64 images (or build directly on Pi)

## Architecture on Cluster

```
┌─────────────────────────────────────────────────────────┐
│                Raspberry Pi K3s Cluster                  │
│                                                          │
│  Master (192.168.1.240)                                  │
│  ├── PostgreSQL (StatefulSet)                            │
│  ├── Redis (Deployment)                                  │
│  └── API (Deployment)                                    │
│                                                          │
│  Workers (192.168.1.241-247) - 7 nodes                   │
│  ├── Celery Worker (DaemonSet) - 1 pod per node         │
│  ├── Frontend (Deployment)                               │
│  └── CronJobs (data-collector, news-fetcher)            │
│                                                          │
│  Storage (192.168.1.10 - Synology NFS)                   │
│  └── Persistent volumes for PostgreSQL                   │
└─────────────────────────────────────────────────────────┘
```

## Step 1: Prepare the Cluster

### 1.1 Create Namespace

```bash
kubectl create namespace financial-screener
kubectl config set-context --current --namespace=financial-screener
```

### 1.2 Create NFS StorageClass

```bash
# Apply NFS CSI driver (if not already installed)
kubectl apply -f kubernetes/base/storage/nfs-storageclass.yaml
```

### 1.3 Create Secrets

```bash
# Database credentials
kubectl create secret generic postgres-secret \
  --from-literal=POSTGRES_USER=financial \
  --from-literal=POSTGRES_PASSWORD=$(openssl rand -base64 32) \
  --from-literal=POSTGRES_DB=financial_db \
  -n financial-screener

# Redis password (optional but recommended)
kubectl create secret generic redis-secret \
  --from-literal=REDIS_PASSWORD=$(openssl rand -base64 32) \
  -n financial-screener

# API keys for data sources
kubectl create secret generic api-keys \
  --from-literal=ALPHA_VANTAGE_API_KEY=your_key_here \
  --from-literal=NEWS_API_KEY=your_key_here \
  -n financial-screener
```

## Step 2: Build ARM64 Docker Images

You have two options:

### Option A: Build on Development Machine (with buildx)

```bash
# Enable buildx
docker buildx create --name arm-builder --use
docker buildx inspect --bootstrap

# Build all images for ARM64
./scripts/build-arm64.sh

# Images will be pushed to your registry
# Update image references in Kubernetes manifests
```

### Option B: Build Directly on Raspberry Pi (Recommended)

```bash
# SSH to master node
ssh pi@192.168.1.240

# Clone repository
git clone <your-repo-url>
cd financial-screener

# Build images locally (faster, no cross-compilation)
cd services/data-collector
docker build -t financial-data-collector:latest .

cd ../analyzer
docker build -t financial-analyzer:latest .

cd ../api
docker build -t financial-api:latest .

# Tag for local registry or use as-is with imagePullPolicy: Never
```

## Step 3: Deploy PostgreSQL

```bash
# Deploy PostgreSQL with persistence
kubectl apply -f kubernetes/base/postgres/

# Wait for PostgreSQL to be ready
kubectl wait --for=condition=ready pod -l app=postgres --timeout=300s

# Initialize database schema
kubectl exec -it postgres-0 -n financial-screener -- \
  psql -U financial -d financial_db -f /migrations/001_initial_schema.sql
```

## Step 4: Deploy Redis

```bash
# Deploy Redis
kubectl apply -f kubernetes/base/redis/

# Verify Redis is running
kubectl get pods -l app=redis
```

## Step 5: Deploy Celery Workers (Analyzer Service)

The Celery workers should run as a **DaemonSet** to utilize all worker nodes.

```bash
# Deploy Celery workers across all worker nodes
kubectl apply -f kubernetes/base/analyzer/

# Verify workers are running on all nodes
kubectl get pods -l app=celery-worker -o wide

# You should see 7 pods (one per worker node)
# Each pod will use all 4 CPU cores of that Pi
```

Expected output:
```
NAME                    READY   STATUS    NODE
celery-worker-xxxxx     1/1     Running   rpi-worker-01
celery-worker-xxxxx     1/1     Running   rpi-worker-02
celery-worker-xxxxx     1/1     Running   rpi-worker-03
celery-worker-xxxxx     1/1     Running   rpi-worker-04
celery-worker-xxxxx     1/1     Running   rpi-worker-05
celery-worker-xxxxx     1/1     Running   rpi-worker-06
celery-worker-xxxxx     1/1     Running   rpi-worker-07
```

This gives you **7 workers × 4 cores = 28 concurrent task processors**!

## Step 6: Deploy API Service

```bash
# Deploy FastAPI service
kubectl apply -f kubernetes/base/api/

# Expose API service
kubectl expose deployment api --type=LoadBalancer --port=8000

# Get API URL
kubectl get svc api
```

## Step 7: Deploy Data Collection CronJobs

```bash
# Deploy CronJobs for data collection
kubectl apply -f kubernetes/base/data-collector/

# Verify CronJobs are created
kubectl get cronjobs

# Manually trigger first data collection (optional)
kubectl create job --from=cronjob/daily-price-update initial-load -n financial-screener

# Check job status
kubectl get jobs
kubectl logs job/initial-load
```

## Step 8: Deploy Frontend

```bash
# Build frontend production bundle
cd frontend
npm run build

# Deploy frontend
kubectl apply -f kubernetes/base/frontend/

# Expose frontend service
kubectl expose deployment frontend --type=LoadBalancer --port=80

# Get frontend URL
kubectl get svc frontend
```

## Step 9: Configure Monitoring (Optional but Recommended)

### Deploy Flower (Celery Monitoring)

```bash
kubectl apply -f kubernetes/base/flower/

# Access Flower dashboard
kubectl port-forward svc/flower 5555:5555

# Open http://localhost:5555 in browser
```

## Step 10: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n financial-screener

# Expected pods:
# - postgres-0 (1 pod)
# - redis-xxx (1 pod)
# - api-xxx (2-3 pods)
# - celery-worker-xxx (7 pods, one per worker node)
# - frontend-xxx (2 pods)
# - flower-xxx (1 pod)

# Check services
kubectl get svc -n financial-screener

# Check resource usage
kubectl top nodes
kubectl top pods -n financial-screener
```

## Resource Allocation

### Per-Service Resources (Tuned for 8GB Pi Nodes)

**PostgreSQL:**
```yaml
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "1000m"
```

**Redis:**
```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

**Celery Worker (per pod):**
```yaml
resources:
  requests:
    memory: "1Gi"
    cpu: "1000m"  # 1 full core, will use all 4 via Polars
  limits:
    memory: "2Gi"
    cpu: "4000m"  # Allow burst to all cores
```

**API:**
```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "1Gi"
    cpu: "1000m"
```

**Frontend:**
```yaml
resources:
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi"
    cpu: "500m"
```

## Total Cluster Resource Usage

- **Master Node** (192.168.1.240):
  - PostgreSQL: ~2GB RAM
  - Redis: ~512MB RAM
  - API: ~1GB RAM (2 replicas × 512MB)
  - **Total: ~3.5GB / 8GB** (plenty of headroom)

- **Worker Nodes** (192.168.1.241-247):
  - Celery Worker: ~2GB RAM per node
  - Frontend: ~256MB RAM (spread across 2 nodes)
  - **Total per worker: ~2GB / 8GB** (very efficient!)

## Accessing Services

### Internal (within cluster)
- PostgreSQL: `postgres.financial-screener.svc.cluster.local:5432`
- Redis: `redis.financial-screener.svc.cluster.local:6379`
- API: `api.financial-screener.svc.cluster.local:8000`

### External (from your network)
- API: `http://192.168.1.240:8000` (via LoadBalancer)
- Frontend: `http://192.168.1.240:3000` (via LoadBalancer)
- Flower: `http://192.168.1.240:5555` (via port-forward)

## Testing the Deployment

### 1. Test Database Connection
```bash
kubectl exec -it postgres-0 -n financial-screener -- \
  psql -U financial -d financial_db -c "SELECT COUNT(*) FROM assets;"
```

### 2. Test Redis
```bash
kubectl exec -it redis-xxx -n financial-screener -- redis-cli ping
# Should return: PONG
```

### 3. Test Celery Workers
```bash
# Submit a test task
kubectl exec -it api-xxx -n financial-screener -- \
  python -c "from celery_app import app; result = app.send_task('analyzer.tasks.analyze_stock', args=['AAPL']); print(result.get(timeout=30))"
```

### 4. Test API
```bash
curl http://192.168.1.240:8000/api/health
# Should return: {"status": "healthy"}
```

### 5. Trigger Data Collection
```bash
# Manually trigger data collection for a test
kubectl create job --from=cronjob/daily-price-update test-run -n financial-screener

# Watch logs
kubectl logs -f job/test-run
```

## Maintenance

### View Logs
```bash
# API logs
kubectl logs -f deployment/api --tail=100

# Celery worker logs (specific node)
kubectl logs -f daemonset/celery-worker --tail=100

# All Celery worker logs
kubectl logs -l app=celery-worker --tail=20 --all-containers=true
```

### Scale Services
```bash
# Scale API (not needed unless high traffic)
kubectl scale deployment api --replicas=3

# Note: Celery workers are DaemonSet, one per node automatically
```

### Update Services
```bash
# Rebuild image
cd services/api
docker build -t financial-api:v2 .

# Update deployment
kubectl set image deployment/api api=financial-api:v2

# Rollback if needed
kubectl rollout undo deployment/api
```

### Database Backup
```bash
# Backup PostgreSQL
kubectl exec postgres-0 -n financial-screener -- \
  pg_dump -U financial financial_db > backup-$(date +%Y%m%d).sql

# Restore
kubectl exec -i postgres-0 -n financial-screener -- \
  psql -U financial financial_db < backup-20241019.sql
```

## Troubleshooting

### Celery Workers Not Connecting
```bash
# Check Redis connectivity
kubectl exec -it celery-worker-xxx -- redis-cli -h redis ping

# Check logs
kubectl logs celery-worker-xxx --tail=50
```

### High Memory Usage
```bash
# Check resource usage
kubectl top pods

# If worker memory is high, restart workers
kubectl rollout restart daemonset/celery-worker
```

### PostgreSQL Issues
```bash
# Check PostgreSQL logs
kubectl logs postgres-0 --tail=100

# Connect to PostgreSQL
kubectl exec -it postgres-0 -- psql -U financial -d financial_db
```

## Performance Tuning

### Celery Worker Concurrency
Adjust based on workload:
```yaml
# In deployment manifest
env:
  - name: CELERY_WORKER_CONCURRENCY
    value: "4"  # Match CPU cores on Pi 5
```

### PostgreSQL Tuning
```bash
# Edit PostgreSQL config
kubectl edit configmap postgres-config

# Add:
shared_buffers = 512MB
effective_cache_size = 2GB
max_connections = 100
```

### Polars Performance
```python
# Already configured in code, but can tune:
import polars as pl
pl.Config.set_streaming_chunk_size(10000)  # Adjust for memory
```

## Next Steps

1. **Monitor the cluster** with Flower and kubectl top
2. **Set up ingress** for external access (optional)
3. **Configure backups** (PostgreSQL + Redis)
4. **Implement alerting** (Prometheus + Grafana - optional)
5. **Test failover** (kill pods, ensure recovery)

## Cluster Advantages

With this setup on your Raspberry Pi cluster:

- ✅ **28 concurrent task processors** (7 workers × 4 cores)
- ✅ **Automatic failover** (Kubernetes restarts failed pods)
- ✅ **Load distribution** (Celery distributes tasks evenly)
- ✅ **Polars efficiency** (processes data 2-10x faster than Pandas)
- ✅ **Low overhead** (no JVM, no Spark complexity)
- ✅ **Easy monitoring** (Flower dashboard)
- ✅ **Scalable** (add more Pis, get more workers automatically)

This is a **production-ready** setup optimized for your hardware!
