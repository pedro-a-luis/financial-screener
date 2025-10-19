#!/bin/bash
# Pre-Deployment Verification Script
# Run this before deploying to ensure everything is ready

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

echo -e "${YELLOW}=== Pre-Deployment Verification ===${NC}\n"

# Function to check command exists
check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "${GREEN}✓ $1 is installed${NC}"
        return 0
    else
        echo -e "${RED}✗ $1 is not installed${NC}"
        ((ERRORS++))
        return 1
    fi
}

# Function to check file exists
check_file() {
    if [ -f "$1" ]; then
        local size=$(stat -f%z "$1" 2>/dev/null || stat -c%s "$1" 2>/dev/null)
        echo -e "${GREEN}✓ $1 exists (${size} bytes)${NC}"
        return 0
    else
        echo -e "${RED}✗ $1 not found${NC}"
        ((ERRORS++))
        return 1
    fi
}

# 1. Check required commands
echo -e "${YELLOW}1. Checking required commands...${NC}"
check_command kubectl
check_command rsync
check_command docker || echo -e "${YELLOW}⚠ docker not found (needed on cluster master)${NC}"
echo

# 2. Check project structure
echo -e "${YELLOW}2. Checking project files...${NC}"
check_file "database/migrations/001_initial_schema.sql"
check_file "services/analyzer/Dockerfile"
check_file "services/analyzer/requirements.txt"
check_file "services/analyzer/src/celery_app.py"
check_file "services/analyzer/src/tasks.py"
check_file "services/analyzer/src/config.py"
check_file "scripts/deploy-to-cluster.sh"
check_file "scripts/test-cluster-deployment.sh"
echo

# 3. Check shared models
echo -e "${YELLOW}3. Checking shared models...${NC}"
if [ -d "shared/models" ]; then
    echo -e "${GREEN}✓ shared/models directory exists${NC}"
    MODEL_COUNT=$(find shared/models -name "*.py" | grep -v __pycache__ | wc -l)
    echo -e "${GREEN}  Found ${MODEL_COUNT} model files${NC}"
else
    echo -e "${RED}✗ shared/models directory not found${NC}"
    ((ERRORS++))
fi
echo

# 4. Verify scripts are executable
echo -e "${YELLOW}4. Checking script permissions...${NC}"
if [ -x "scripts/deploy-to-cluster.sh" ]; then
    echo -e "${GREEN}✓ deploy-to-cluster.sh is executable${NC}"
else
    echo -e "${YELLOW}⚠ deploy-to-cluster.sh is not executable${NC}"
    chmod +x scripts/deploy-to-cluster.sh
    echo -e "${GREEN}  Fixed: Made executable${NC}"
fi

if [ -x "scripts/test-cluster-deployment.sh" ]; then
    echo -e "${GREEN}✓ test-cluster-deployment.sh is executable${NC}"
else
    echo -e "${YELLOW}⚠ test-cluster-deployment.sh is not executable${NC}"
    chmod +x scripts/test-cluster-deployment.sh
    echo -e "${GREEN}  Fixed: Made executable${NC}"
fi
echo

# 5. Check cluster connectivity
echo -e "${YELLOW}5. Checking cluster connectivity...${NC}"
if kubectl cluster-info &>/dev/null; then
    echo -e "${GREEN}✓ kubectl can connect to cluster${NC}"

    # Check nodes
    NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l)
    echo -e "${GREEN}  Cluster has ${NODE_COUNT} nodes${NC}"

    # Check for worker nodes
    WORKER_COUNT=$(kubectl get nodes -l node-role.kubernetes.io/worker=true --no-headers 2>/dev/null | wc -l)
    if [ "$WORKER_COUNT" -gt 0 ]; then
        echo -e "${GREEN}  Found ${WORKER_COUNT} worker nodes${NC}"
    else
        echo -e "${YELLOW}⚠ No worker nodes found (need to label them)${NC}"
        ((WARNINGS++))
    fi
else
    echo -e "${RED}✗ Cannot connect to cluster${NC}"
    echo -e "${YELLOW}  Run: export KUBECONFIG=/path/to/kubeconfig${NC}"
    ((ERRORS++))
fi
echo

# 6. Check for PostgreSQL
echo -e "${YELLOW}6. Checking for PostgreSQL...${NC}"
if kubectl get svc postgres -n default &>/dev/null; then
    echo -e "${GREEN}✓ PostgreSQL service found in 'default' namespace${NC}"

    # Try to get endpoint
    POSTGRES_IP=$(kubectl get svc postgres -n default -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
    echo -e "${GREEN}  PostgreSQL ClusterIP: ${POSTGRES_IP}${NC}"
else
    echo -e "${YELLOW}⚠ PostgreSQL service not found in 'default' namespace${NC}"
    echo -e "${YELLOW}  You'll need to provide PostgreSQL connection details during deployment${NC}"
    ((WARNINGS++))
fi
echo

# 7. Check for Redis
echo -e "${YELLOW}7. Checking for Redis...${NC}"
if kubectl get svc redis -n default &>/dev/null; then
    echo -e "${GREEN}✓ Redis service found in 'default' namespace${NC}"
else
    echo -e "${YELLOW}⚠ Redis service not found${NC}"
    echo -e "${YELLOW}  Deployment script will create Redis${NC}"
    ((WARNINGS++))
fi
echo

# 8. Check database schema file
echo -e "${YELLOW}8. Validating database schema...${NC}"
if grep -q "CREATE SCHEMA IF NOT EXISTS financial_screener" database/migrations/001_initial_schema.sql; then
    echo -e "${GREEN}✓ Schema file creates 'financial_screener' schema${NC}"
else
    echo -e "${RED}✗ Schema file missing schema creation${NC}"
    ((ERRORS++))
fi

if grep -q "financial_screener.asset_type_enum" database/migrations/001_initial_schema.sql; then
    echo -e "${GREEN}✓ Custom types are schema-qualified${NC}"
else
    echo -e "${YELLOW}⚠ Custom types may not be schema-qualified${NC}"
    ((WARNINGS++))
fi
echo

# 9. Check Python dependencies (if Python available)
echo -e "${YELLOW}9. Checking Python environment (optional)...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓ Python installed: ${PYTHON_VERSION}${NC}"

    # Try to import key packages
    if python3 -c "import polars" 2>/dev/null; then
        echo -e "${GREEN}✓ polars is installed${NC}"
    else
        echo -e "${YELLOW}⚠ polars not installed (needed for local tests)${NC}"
    fi

    if python3 -c "import celery" 2>/dev/null; then
        echo -e "${GREEN}✓ celery is installed${NC}"
    else
        echo -e "${YELLOW}⚠ celery not installed (needed for local tests)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Python not available (skipping dependency check)${NC}"
fi
echo

# 10. Estimate transfer size
echo -e "${YELLOW}10. Estimating transfer size...${NC}"
TOTAL_SIZE=$(du -sh . 2>/dev/null | cut -f1)
echo -e "${GREEN}  Project size: ${TOTAL_SIZE}${NC}"

# Calculate without .git, node_modules, __pycache__
TRANSFER_SIZE=$(du -sh --exclude='.git' --exclude='node_modules' --exclude='__pycache__' --exclude='*.pyc' . 2>/dev/null | cut -f1 || echo "Unknown")
echo -e "${GREEN}  Estimated transfer size: ${TRANSFER_SIZE}${NC}"
echo

# Summary
echo -e "${YELLOW}=== Verification Summary ===${NC}\n"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed! Ready to deploy.${NC}\n"
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Transfer code to cluster:"
    echo "   rsync -avz --exclude='.git' --exclude='__pycache__' . pi@192.168.1.240:~/financial-screener/"
    echo ""
    echo "2. SSH to master node:"
    echo "   ssh pi@192.168.1.240"
    echo ""
    echo "3. Build Docker image:"
    echo "   cd ~/financial-screener"
    echo "   docker build -f services/analyzer/Dockerfile -t financial-analyzer:latest ."
    echo ""
    echo "4. Deploy services:"
    echo "   ./scripts/deploy-to-cluster.sh"
    echo ""
    echo "5. Run tests:"
    echo "   ./scripts/test-cluster-deployment.sh"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ ${WARNINGS} warning(s) found${NC}"
    echo -e "${GREEN}No critical errors. You can proceed with deployment.${NC}\n"
    exit 0
else
    echo -e "${RED}✗ ${ERRORS} error(s) found${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}⚠ ${WARNINGS} warning(s) found${NC}"
    fi
    echo -e "${RED}Please fix errors before deploying.${NC}\n"
    exit 1
fi
