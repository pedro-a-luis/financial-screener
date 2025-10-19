#!/bin/bash
# Deploy Financial Screener to Raspberry Pi K3s Cluster
#
# This script deploys core services to the existing cluster infrastructure

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
NAMESPACE="${NAMESPACE:-financial-screener}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres.default.svc.cluster.local}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-financial_db}"
REDIS_HOST="${REDIS_HOST:-redis.default.svc.cluster.local}"

echo -e "${YELLOW}=== Financial Screener Deployment ===${NC}\n"

# Function to check if resource exists
resource_exists() {
    kubectl get "$1" "$2" -n "$NAMESPACE" &>/dev/null
}

# Function to wait for pod
wait_for_pod() {
    local label=$1
    local timeout=${2:-300}

    echo -e "${YELLOW}Waiting for pod with label $label...${NC}"
    kubectl wait --for=condition=ready pod -l "$label" -n "$NAMESPACE" --timeout="${timeout}s" || {
        echo -e "${RED}Pod not ready after ${timeout}s${NC}"
        return 1
    }
    echo -e "${GREEN}✓ Pod ready${NC}"
}

# 1. Check cluster connectivity
echo -e "${YELLOW}1. Checking cluster connectivity...${NC}"
if ! kubectl cluster-info &>/dev/null; then
    echo -e "${RED}✗ Cannot connect to Kubernetes cluster${NC}"
    echo "Please configure kubectl to access your cluster"
    exit 1
fi
echo -e "${GREEN}✓ Connected to cluster${NC}\n"

# 2. Check existing PostgreSQL
echo -e "${YELLOW}2. Checking existing PostgreSQL...${NC}"
if kubectl get svc postgres -n default &>/dev/null; then
    echo -e "${GREEN}✓ Found existing PostgreSQL in 'default' namespace${NC}"
    POSTGRES_HOST="postgres.default.svc.cluster.local"
else
    echo -e "${YELLOW}PostgreSQL not found in default namespace${NC}"
    echo "Enter PostgreSQL connection details:"
    read -p "PostgreSQL host: " POSTGRES_HOST
    read -p "PostgreSQL port [5432]: " POSTGRES_PORT
    POSTGRES_PORT=${POSTGRES_PORT:-5432}
fi

# 3. Check existing Redis
echo -e "\n${YELLOW}3. Checking existing Redis...${NC}"
if kubectl get svc redis -n default &>/dev/null; then
    echo -e "${GREEN}✓ Found existing Redis in 'default' namespace${NC}"
    REDIS_HOST="redis.default.svc.cluster.local"
else
    echo -e "${YELLOW}Redis not found. Will deploy Redis...${NC}"
    DEPLOY_REDIS=true
fi

# 4. Create namespace
echo -e "\n${YELLOW}4. Creating namespace...${NC}"
if kubectl get namespace "$NAMESPACE" &>/dev/null; then
    echo -e "${GREEN}✓ Namespace $NAMESPACE already exists${NC}"
else
    kubectl create namespace "$NAMESPACE"
    echo -e "${GREEN}✓ Created namespace $NAMESPACE${NC}"
fi

# 5. Create secrets
echo -e "\n${YELLOW}5. Creating secrets...${NC}"

# Database credentials
if resource_exists secret postgres-secret; then
    echo -e "${GREEN}✓ PostgreSQL secret already exists${NC}"
else
    read -p "PostgreSQL database name [financial_db]: " DB_NAME
    DB_NAME=${DB_NAME:-financial_db}

    read -p "PostgreSQL username [financial]: " DB_USER
    DB_USER=${DB_USER:-financial}

    read -sp "PostgreSQL password: " DB_PASSWORD
    echo

    # Database URL with schema search path for multi-project database
    DB_URL="postgresql://$DB_USER:$DB_PASSWORD@$POSTGRES_HOST:$POSTGRES_PORT/$DB_NAME?options=-c%20search_path%3Dfinancial_screener%2Cpublic"

    kubectl create secret generic postgres-secret \
        --from-literal=POSTGRES_DB="$DB_NAME" \
        --from-literal=POSTGRES_USER="$DB_USER" \
        --from-literal=POSTGRES_PASSWORD="$DB_PASSWORD" \
        --from-literal=DATABASE_URL="$DB_URL" \
        --from-literal=DATABASE_SCHEMA="financial_screener" \
        -n "$NAMESPACE"

    echo -e "${GREEN}✓ Created PostgreSQL secret${NC}"
fi

# 6. Deploy Redis (if needed)
if [ "$DEPLOY_REDIS" = true ]; then
    echo -e "\n${YELLOW}6. Deploying Redis...${NC}"

    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: $NAMESPACE
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          exec:
            command:
            - redis-cli
            - ping
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - redis-cli
            - ping
          initialDelaySeconds: 5
          periodSeconds: 5
EOF

    wait_for_pod "app=redis" 60
    REDIS_HOST="redis.$NAMESPACE.svc.cluster.local"
else
    echo -e "\n${YELLOW}6. Skipping Redis deployment (using existing)${NC}"
fi

# 7. Initialize database schema
echo -e "\n${YELLOW}7. Initializing database schema...${NC}"

# Create ConfigMap with schema file
kubectl create configmap schema-init \
    --from-file=001_initial_schema.sql=database/migrations/001_initial_schema.sql \
    --dry-run=client -o yaml | kubectl apply -f - -n "$NAMESPACE"

# Create a job to initialize the database
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: init-database-$(date +%s)
  namespace: $NAMESPACE
spec:
  ttlSecondsAfterFinished: 100
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: init-db
        image: postgres:16-alpine
        command:
        - /bin/sh
        - -c
        - |
          echo "Waiting for PostgreSQL..."
          until pg_isready -h $POSTGRES_HOST -p $POSTGRES_PORT -U \$POSTGRES_USER; do
            sleep 2
          done

          echo "Creating database if not exists..."
          psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U \$POSTGRES_USER -tc "SELECT 1 FROM pg_database WHERE datname = '\$POSTGRES_DB'" | grep -q 1 || \
          psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U \$POSTGRES_USER -c "CREATE DATABASE \$POSTGRES_DB"

          echo "Running schema migration..."
          psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U \$POSTGRES_USER -d \$POSTGRES_DB -f /schema/001_initial_schema.sql

          echo "Verifying schema..."
          psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U \$POSTGRES_USER -d \$POSTGRES_DB -c "\\dt financial_screener.*"

          echo "Database schema initialized successfully!"
        env:
        - name: POSTGRES_DB
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: POSTGRES_DB
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: POSTGRES_USER
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: POSTGRES_PASSWORD
        - name: POSTGRES_HOST
          value: "$POSTGRES_HOST"
        - name: POSTGRES_PORT
          value: "$POSTGRES_PORT"
        volumeMounts:
        - name: schema
          mountPath: /schema
      volumes:
      - name: schema
        configMap:
          name: schema-init
EOF

echo -e "${GREEN}✓ Database initialization job created${NC}"

# 8. Build and deploy Celery workers
echo -e "\n${YELLOW}8. Deploying Celery workers...${NC}"

# First, create ConfigMap with connection info
kubectl create configmap analyzer-config \
    --from-literal=REDIS_URL="redis://$REDIS_HOST:6379/0" \
    --from-literal=POSTGRES_HOST="$POSTGRES_HOST" \
    --from-literal=POSTGRES_PORT="$POSTGRES_PORT" \
    --dry-run=client -o yaml | kubectl apply -f - -n "$NAMESPACE"

# Deploy Celery workers as DaemonSet
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: celery-worker
  namespace: $NAMESPACE
spec:
  selector:
    matchLabels:
      app: celery-worker
  template:
    metadata:
      labels:
        app: celery-worker
    spec:
      nodeSelector:
        node-role.kubernetes.io/worker: "true"
      containers:
      - name: celery-worker
        image: financial-analyzer:latest
        imagePullPolicy: Never  # Use local image
        command:
        - celery
        - -A
        - celery_app
        - worker
        - --loglevel=info
        - --concurrency=4
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: DATABASE_URL
        - name: REDIS_URL
          valueFrom:
            configMapKeyRef:
              name: analyzer-config
              key: REDIS_URL
        - name: CELERY_BROKER_URL
          valueFrom:
            configMapKeyRef:
              name: analyzer-config
              key: REDIS_URL
        - name: CELERY_RESULT_BACKEND
          valueFrom:
            configMapKeyRef:
              name: analyzer-config
              key: REDIS_URL
        - name: LOG_LEVEL
          value: "INFO"
        - name: CELERY_WORKER_CONCURRENCY
          value: "4"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "4000m"
EOF

echo -e "${GREEN}✓ Celery workers deployed${NC}"

# 9. Deploy Flower (monitoring)
echo -e "\n${YELLOW}9. Deploying Flower dashboard...${NC}"

cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: flower
  namespace: $NAMESPACE
spec:
  selector:
    app: flower
  ports:
  - port: 5555
    targetPort: 5555
  type: LoadBalancer
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flower
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: flower
  template:
    metadata:
      labels:
        app: flower
    spec:
      containers:
      - name: flower
        image: financial-analyzer:latest
        imagePullPolicy: Never
        command:
        - celery
        - -A
        - celery_app
        - flower
        - --port=5555
        env:
        - name: CELERY_BROKER_URL
          valueFrom:
            configMapKeyRef:
              name: analyzer-config
              key: REDIS_URL
        - name: CELERY_RESULT_BACKEND
          valueFrom:
            configMapKeyRef:
              name: analyzer-config
              key: REDIS_URL
        ports:
        - containerPort: 5555
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"
EOF

echo -e "${GREEN}✓ Flower deployed${NC}"

# 10. Summary
echo -e "\n${GREEN}=== Deployment Complete ===${NC}\n"

echo -e "${YELLOW}Deployed resources:${NC}"
kubectl get all -n "$NAMESPACE"

echo -e "\n${YELLOW}Connection Details:${NC}"
echo "PostgreSQL: $POSTGRES_HOST:$POSTGRES_PORT"
echo "Redis: $REDIS_HOST:6379"
echo "Namespace: $NAMESPACE"

echo -e "\n${YELLOW}Next Steps:${NC}"
echo "1. Check pod status:"
echo "   kubectl get pods -n $NAMESPACE"
echo ""
echo "2. View Celery worker logs:"
echo "   kubectl logs -f daemonset/celery-worker -n $NAMESPACE"
echo ""
echo "3. Access Flower dashboard:"
echo "   kubectl port-forward svc/flower 5555:5555 -n $NAMESPACE"
echo "   Then open: http://localhost:5555"
echo ""
echo "4. Run tests:"
echo "   kubectl exec -it daemonset/celery-worker -n $NAMESPACE -- pytest /app/tests/"
echo ""

echo -e "${GREEN}Deployment successful! 🚀${NC}"
