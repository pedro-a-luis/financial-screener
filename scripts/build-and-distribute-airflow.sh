#!/bin/bash
# Build and Distribute Custom Airflow Image
# Builds a custom Airflow image with DAGs baked in and distributes to all worker nodes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_NAME="custom-airflow"
IMAGE_TAG="3.0.2-dags"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Custom Airflow Image Build & Distribution${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Step 1: Build the image locally
echo -e "${YELLOW}Step 1: Building Docker image locally...${NC}"
cd "$PROJECT_ROOT"
docker build -f airflow/Dockerfile -t "$FULL_IMAGE" .

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Image built successfully: ${FULL_IMAGE}${NC}"
else
    echo -e "${RED}✗ Image build failed${NC}"
    exit 1
fi

# Step 2: Save image to tar file
echo ""
echo -e "${YELLOW}Step 2: Saving image to tar file...${NC}"
TAR_FILE="/tmp/${IMAGE_NAME}-${IMAGE_TAG}.tar"
docker save "$FULL_IMAGE" -o "$TAR_FILE"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Image saved to: ${TAR_FILE}${NC}"
    ls -lh "$TAR_FILE"
else
    echo -e "${RED}✗ Failed to save image${NC}"
    exit 1
fi

# Step 3: Get list of worker nodes
echo ""
echo -e "${YELLOW}Step 3: Discovering worker nodes...${NC}"

WORKERS=$(ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
    "kubectl get nodes -l node-role.kubernetes.io/worker=true -o jsonpath='{.items[*].status.addresses[?(@.type==\"InternalIP\")].address}'")

if [ -z "$WORKERS" ]; then
    echo -e "${RED}✗ No worker nodes found${NC}"
    exit 1
fi

echo -e "${GREEN}Found worker nodes: ${WORKERS}${NC}"

# Step 4: Distribute to each worker
echo ""
echo -e "${YELLOW}Step 4: Distributing image to worker nodes...${NC}"

for WORKER_IP in $WORKERS; do
    echo ""
    echo -e "${YELLOW}Deploying to worker: ${WORKER_IP}${NC}"

    # Copy tar file to worker
    scp -i ~/.ssh/pi_cluster "$TAR_FILE" "admin@${WORKER_IP}:/tmp/" 2>&1

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}  ✓ Tar file copied to ${WORKER_IP}${NC}"
    else
        echo -e "${RED}  ✗ Failed to copy to ${WORKER_IP}${NC}"
        continue
    fi

    # Load image on worker
    ssh -i ~/.ssh/pi_cluster "admin@${WORKER_IP}" \
        "sudo docker load -i /tmp/${IMAGE_NAME}-${IMAGE_TAG}.tar && rm /tmp/${IMAGE_NAME}-${IMAGE_TAG}.tar" 2>&1

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}  ✓ Image loaded on ${WORKER_IP}${NC}"
    else
        echo -e "${RED}  ✗ Failed to load image on ${WORKER_IP}${NC}"
    fi
done

# Step 5: Clean up local tar file
echo ""
echo -e "${YELLOW}Step 5: Cleaning up...${NC}"
rm "$TAR_FILE"
echo -e "${GREEN}✓ Temporary files removed${NC}"

# Step 6: Verify distribution
echo ""
echo -e "${YELLOW}Step 6: Verifying image distribution...${NC}"

for WORKER_IP in $WORKERS; do
    IMAGE_EXISTS=$(ssh -i ~/.ssh/pi_cluster "admin@${WORKER_IP}" \
        "sudo docker images ${IMAGE_NAME} --format '{{.Repository}}:{{.Tag}}' | grep ${IMAGE_TAG}" 2>&1)

    if [ -n "$IMAGE_EXISTS" ]; then
        echo -e "${GREEN}  ✓ ${WORKER_IP}: ${IMAGE_EXISTS}${NC}"
    else
        echo -e "${RED}  ✗ ${WORKER_IP}: Image not found${NC}"
    fi
done

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Distribution Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Update Helm values to use image: ${FULL_IMAGE}"
echo "2. Upgrade Airflow: helm upgrade airflow apache-airflow/airflow -n airflow --set images.airflow.repository=${IMAGE_NAME} --set images.airflow.tag=${IMAGE_TAG}"
echo "3. Restart Airflow pods: kubectl rollout restart statefulset airflow-scheduler -n airflow"
echo ""
