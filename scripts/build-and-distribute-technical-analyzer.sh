#!/bin/bash
set -e

echo "=== Building and Distributing Technical Analyzer Image ==="
echo ""

# Build locally
echo "1. Building Docker image locally..."
cd /root/gitlab/financial-screener
docker build --platform linux/arm64 -f services/technical-analyzer/Dockerfile -t technical-analyzer:latest .
echo "✓ Image built"
echo ""

# Save image
echo "2. Saving image to tar file..."
docker save technical-analyzer:latest > /tmp/technical-analyzer.tar
echo "✓ Image saved"
echo ""

# Distribute to all 8 nodes
MASTER="192.168.1.240"
WORKERS="241 242 243 244 245 246 247"

echo "3. Distributing to master node ($MASTER)..."
scp -i ~/.ssh/pi_cluster /tmp/technical-analyzer.tar admin@$MASTER:~/technical-analyzer.tar
ssh -i ~/.ssh/pi_cluster admin@$MASTER 'sudo k3s ctr images import ~/technical-analyzer.tar && rm ~/technical-analyzer.tar'
echo "✓ Master node done"
echo ""

for worker_ip in $WORKERS; do
    echo "4. Distributing to worker 192.168.1.$worker_ip..."
    scp -i ~/.ssh/pi_cluster /tmp/technical-analyzer.tar admin@192.168.1.$worker_ip:~/technical-analyzer.tar
    ssh -i ~/.ssh/pi_cluster admin@192.168.1.$worker_ip 'sudo k3s ctr images import ~/technical-analyzer.tar && rm ~/technical-analyzer.tar'
    echo "✓ Worker $worker_ip done"
done

echo ""
echo "=== Distribution Complete ==="
rm /tmp/technical-analyzer.tar
