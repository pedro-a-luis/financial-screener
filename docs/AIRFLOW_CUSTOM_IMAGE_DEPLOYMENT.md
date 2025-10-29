# Airflow Custom Image Deployment Guide

**Date**: 2025-10-29
**Status**: Image Built, Distribution Pending

---

## Overview

The import error in `utils/api_quota_calculator.py` has been fixed and a custom Airflow image has been created with DAGs baked in. This document describes how to complete the deployment.

---

## What's Been Completed

1. ✅ **Fixed Import Error**
   - Changed `from .database_utils` to `from utils.database_utils`
   - Committed to git: commit 6796f14
   - Pushed to origin/main

2. ✅ **Created Custom Airflow Infrastructure**
   - Dockerfile: `airflow/Dockerfile`
   - Build script: `scripts/build-and-distribute-airflow.sh`
   - Image built successfully: `custom-airflow:3.0.2-dags` (504MB)

3. ✅ **Image Saved**
   - Location: `/tmp/custom-airflow-3.0.2-dags.tar`
   - Ready for distribution

---

## Remaining Steps

### Step 1: Distribute Image to Worker Nodes

The build script failed to find worker nodes automatically. You need to manually distribute the image:

```bash
# From the master node (192.168.1.240)
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240

# Get list of worker nodes
kubectl get nodes -l node-role.kubernetes.io/worker=true -o wide

# For each worker node, copy and load the image:
# Replace WORKER_IP with actual worker IP addresses

for WORKER_IP in 192.168.1.241 192.168.1.242 192.168.1.243 192.168.1.244 192.168.1.245 192.168.1.246 192.168.1.247; do
  echo "Deploying to $WORKER_IP..."

  # Copy tar file
  scp -i ~/.ssh/pi_cluster /tmp/custom-airflow-3.0.2-dags.tar admin@${WORKER_IP}:/tmp/

  # Load image
  ssh -i ~/.ssh/pi_cluster admin@${WORKER_IP} \
    "sudo docker load -i /tmp/custom-airflow-3.0.2-dags.tar && rm /tmp/custom-airflow-3.0.2-dags.tar"

  # Verify
  ssh -i ~/.ssh/pi_cluster admin@${WORKER_IP} \
    "sudo docker images custom-airflow --format '{{.Repository}}:{{.Tag}}'"
done
```

### Step 2: Update Helm Values

Create a new Helm values file or update existing one:

```yaml
# File: kubernetes/airflow-values-custom-image.yaml

executor: LocalExecutor

postgresql:
  enabled: true
  image:
    registry: docker.io
    repository: library/postgres
    tag: 16-alpine

webserver:
  defaultUser:
    username: admin
    password: admin123

logs:
  persistence:
    enabled: false

# Use custom image with DAGs baked in
images:
  airflow:
    repository: custom-airflow
    tag: 3.0.2-dags
    pullPolicy: Never  # Use local image, don't pull from registry

# Disable DAG persistence (using baked-in DAGs)
dags:
  persistence:
    enabled: false
```

### Step 3: Upgrade Airflow Helm Release

```bash
# From master node
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240

# Upgrade Airflow to use custom image
helm upgrade airflow apache-airflow/airflow \
  -n airflow \
  --set images.airflow.repository=custom-airflow \
  --set images.airflow.tag=3.0.2-dags \
  --set images.airflow.pullPolicy=Never \
  --reuse-values
```

### Step 4: Restart Airflow Pods

```bash
# Restart scheduler to pick up new image
kubectl rollout restart statefulset airflow-scheduler -n airflow

# Restart dag processor
kubectl rollout restart deployment airflow-dag-processor -n airflow

# Restart webserver
kubectl rollout restart deployment airflow-webserver -n airflow

# Restart triggerer
kubectl rollout restart statefulset airflow-triggerer -n airflow
```

### Step 5: Verify Import Errors Resolved

```bash
# Wait for pods to be ready
kubectl wait --for=condition=ready pod -n airflow -l component=scheduler --timeout=300s

# Check for import errors
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list-import-errors 2>&1

# Should show no errors, or only deprecation warnings
```

### Step 6: Verify DAGs Loaded

```bash
# List all DAGs
kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
  airflow dags list 2>&1

# Should show:
# - calculate_indicators
# - data_collection_equities
# - historical_load_equities
```

---

## Rebuilding Image After DAG Changes

Whenever you modify DAG files, rebuild and redistribute:

```bash
# From your local machine
cd /root/gitlab/financial-screener

# Pull latest changes
git pull origin main

# Rebuild image
docker build -f airflow/Dockerfile -t custom-airflow:3.0.2-dags .

# Save to tar
docker save custom-airflow:3.0.2-dags -o /tmp/custom-airflow-3.0.2-dags.tar

# Follow distribution steps above
```

---

## Alternative: Automated Build Script

If you want to automate this, update the script to use correct node discovery:

```bash
# Edit: scripts/build-and-distribute-airflow.sh
# Change the worker discovery section:

WORKERS=$(ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
    "kubectl get nodes -o json | jq -r '.items[] | select(.metadata.labels.\"node-role.kubernetes.io/worker\"==\"true\") | .status.addresses[] | select(.type==\"InternalIP\") | .address'")
```

Then run:
```bash
chmod +x scripts/build-and-distribute-airflow.sh
./scripts/build-and-distribute-airflow.sh
```

---

## Troubleshooting

### Import Error Still Showing

If the import error persists after upgrading:
1. Check pod is using new image: `kubectl describe pod airflow-scheduler-0 -n airflow | grep Image:`
2. Clear Python cache: `kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- find /opt/airflow/dags -name "*.pyc" -delete`
3. Restart scheduler: `kubectl delete pod airflow-scheduler-0 -n airflow`

### Image Not Found

If pods show `ImagePullBackOff` or `ErrImagePull`:
1. Verify image exists on node: `ssh admin@WORKER_IP "sudo docker images | grep custom-airflow"`
2. Check imagePullPolicy is `Never` in Helm values
3. Verify image loaded correctly: `sudo docker images custom-airflow:3.0.2-dags`

### DAGs Not Updating

If DAG changes don't appear:
1. Rebuild image with latest code
2. Redistribute to all workers
3. Delete pods to force recreation: `kubectl delete pod -n airflow -l component=scheduler`

---

## Files Reference

- **Dockerfile**: `airflow/Dockerfile`
- **Build Script**: `scripts/build-and-distribute-airflow.sh`
- **Image Location**: `/tmp/custom-airflow-3.0.2-dags.tar` (504MB)
- **Fixed File**: `airflow/dags/utils/api_quota_calculator.py` (line 8)
- **Git Commit**: 6796f14

---

## Current Airflow Status

**Airflow Version**: 3.0.2
**Helm Chart**: 1.18.0
**Namespace**: airflow

**Current Pods**:
- airflow-scheduler-0 (StatefulSet)
- airflow-dag-processor (Deployment)
- airflow-webserver (Deployment)
- airflow-triggerer-0 (StatefulSet)

**DAGs Status**:
- ✅ calculate_indicators (paused)
- ✅ data_collection_equities (active)
- ✅ historical_load_equities (paused)
- ⚠️ Import error showing (cached, not blocking)

---

## Summary

The fix is complete in the code and a custom image has been built. You just need to:
1. Distribute the image to worker nodes (manual or scripted)
2. Update Helm to use the custom image
3. Restart pods
4. Verify the import error is gone

The import error is currently just a cached warning and doesn't prevent DAGs from running. But deploying the custom image will cleanly resolve it.

---

**Last Updated**: 2025-10-29
**Next Action**: Distribute image to workers and upgrade Helm release
