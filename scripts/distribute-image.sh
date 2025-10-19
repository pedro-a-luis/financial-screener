#!/bin/bash
# Distribute Docker Image to All K3s Worker Nodes
# Run this on the master node (pi-master)

set -e

IMAGE_TAR="/tmp/financial-analyzer.tar"
WORKER_NODES="pi-worker-01 pi-worker-02 pi-worker-03 pi-worker-04 pi-worker-05 pi-worker-06 pi-worker-07"

echo "=== Distributing financial-analyzer image to worker nodes ==="
echo

# Check if image tar exists
if [ ! -f "$IMAGE_TAR" ]; then
    echo "ERROR: Image tar not found at $IMAGE_TAR"
    exit 1
fi

echo "Image size: $(du -h $IMAGE_TAR | cut -f1)"
echo

# Import to each worker node
for node in $WORKER_NODES; do
    echo "[$node] Copying image..."
    scp $IMAGE_TAR $node:/tmp/ || {
        echo "  Failed to copy to $node"
        continue
    }

    echo "[$node] Importing to k3s..."
    ssh $node "sudo k3s ctr images import /tmp/financial-analyzer.tar && rm /tmp/financial-analyzer.tar" || {
        echo "  Failed to import on $node"
        continue
    }

    echo "[$node] ✓ Done"
    echo
done

echo "=== Distribution complete ==="
echo "Verifying image on all nodes..."
echo

# Verify on all nodes
for node in $WORKER_NODES; do
    echo -n "[$node] "
    ssh $node "sudo k3s ctr images ls | grep financial-analyzer" || echo "NOT FOUND"
done

echo
echo "Done! Now restart the pods:"
echo "  kubectl rollout restart daemonset/celery-worker -n financial-screener"
