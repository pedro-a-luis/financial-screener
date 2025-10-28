#!/bin/bash
#
# Financial Screener - Airflow System Health Check
# Comprehensive health check for all components
#

set -e

echo "==============================================="
echo "Financial Screener - System Health Check"
echo "$(date)"
echo "==============================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# SSH key for cluster access
SSH_KEY="~/.ssh/pi_cluster"
CONTROL_NODE="admin@192.168.1.240"

echo ""
echo "=== 1. Airflow Health ==="
ssh -i $SSH_KEY $CONTROL_NODE "kubectl get pods -n airflow" || {
    echo -e "${RED}✗ Failed to get Airflow pods${NC}"
    exit 1
}

echo ""
echo "=== 2. DAG Status ==="
ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
    airflow dags list | grep -E 'data_collection|calculate_indicators'" || {
    echo -e "${YELLOW}⚠ DAGs not loaded yet${NC}"
}

echo ""
echo "=== 3. Recent DAG Runs (Last 5) ==="
ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
    airflow dags list-runs -d data_collection_equities --limit 5" 2>/dev/null || {
    echo -e "${YELLOW}⚠ No DAG runs yet${NC}"
}

echo ""
echo "=== 4. Active Jobs ==="
ssh -i $SSH_KEY $CONTROL_NODE "kubectl get jobs -n financial-screener" 2>/dev/null || {
    echo "No active jobs"
}

echo ""
echo "=== 5. Recent Pods (Last 5) ==="
ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl get pods -n financial-screener --sort-by=.metadata.creationTimestamp 2>/dev/null | tail -5" || {
    echo "No pods yet"
}

echo ""
echo "=== 6. Database Connectivity ==="
ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c 'SELECT 1 as connected;'" >/dev/null && {
    echo -e "${GREEN}✓ Database connected${NC}"
} || {
    echo -e "${RED}✗ Database connection failed${NC}"
    exit 1
}

echo ""
echo "=== 7. Metadata Tables ==="
ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
    \"SET search_path TO financial_screener;
     SELECT
        (SELECT COUNT(*) FROM process_executions) as total_executions,
        (SELECT COUNT(*) FROM asset_processing_state) as total_assets,
        (SELECT COUNT(*) FROM asset_processing_details) as total_operations;\"" || {
    echo -e "${RED}✗ Failed to query metadata tables${NC}"
}

echo ""
echo "=== 8. Processing Progress ==="
ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -t -c \
    \"SET search_path TO financial_screener;
     SELECT * FROM get_processing_progress();\"" 2>/dev/null || {
    echo -e "${YELLOW}⚠ No processing data yet${NC}"
}

echo ""
echo "=== 9. Today's API Usage ==="
API_USAGE=$(ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -t -c \
    \"SET search_path TO financial_screener;
     SELECT COALESCE(SUM(api_calls_used), 0) as api_calls
     FROM asset_processing_details
     WHERE DATE(created_at) = CURRENT_DATE;\"" 2>/dev/null | tr -d ' ')

if [ -n "$API_USAGE" ] && [ "$API_USAGE" -gt 0 ]; then
    if [ "$API_USAGE" -lt 90000 ]; then
        echo -e "${GREEN}✓ API Usage: $API_USAGE / 100,000 (${((API_USAGE * 100 / 100000))% used)${NC}"
    else
        echo -e "${YELLOW}⚠ API Usage: $API_USAGE / 100,000 (${((API_USAGE * 100 / 100000))% used)${NC}"
    fi
else
    echo "API Usage: 0 / 100,000 (no activity today)"
fi

echo ""
echo "=== 10. Recent Errors ==="
ERRORS=$(ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -t -c \
    \"SET search_path TO financial_screener;
     SELECT COUNT(*)
     FROM asset_processing_state
     WHERE consecutive_failures >= 3;\"" 2>/dev/null | tr -d ' ')

if [ -n "$ERRORS" ] && [ "$ERRORS" -gt 0 ]; then
    echo -e "${YELLOW}⚠ Tickers with 3+ consecutive failures: $ERRORS${NC}"

    echo ""
    echo "Top 10 failing tickers:"
    ssh -i $SSH_KEY $CONTROL_NODE \
        "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \
        \"SET search_path TO financial_screener;
         SELECT ticker, consecutive_failures, LEFT(last_error_message, 50) as error
         FROM asset_processing_state
         WHERE consecutive_failures >= 3
         ORDER BY consecutive_failures DESC
         LIMIT 10;\""
else
    echo -e "${GREEN}✓ No tickers with repeated failures${NC}"
fi

echo ""
echo "=== 11. Secrets Status ==="
ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl get secrets -n financial-screener postgres-secret data-api-secrets 2>/dev/null" && {
    echo -e "${GREEN}✓ All secrets exist${NC}"
} || {
    echo -e "${RED}✗ Secrets missing${NC}"
}

echo ""
echo "=== 12. Docker Images (Node 192.168.1.241) ==="
ssh -i $SSH_KEY admin@192.168.1.241 \
    "sudo ctr -n k8s.io images ls | grep -E 'data-collector|technical-analyzer'" 2>/dev/null || {
    echo -e "${YELLOW}⚠ Images not distributed yet${NC}"
}

echo ""
echo "==============================================="
echo "Health Check Complete"
echo "==============================================="

# Summary
echo ""
echo "SUMMARY:"
echo "--------"

# Count successes/warnings
WARNINGS=0

# Check Airflow
ssh -i $SSH_KEY $CONTROL_NODE "kubectl get pods -n airflow" | grep -q "Running" && {
    echo -e "${GREEN}✓ Airflow is running${NC}"
} || {
    echo -e "${RED}✗ Airflow issues detected${NC}"
    WARNINGS=$((WARNINGS + 1))
}

# Check DAGs
ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl exec -n airflow airflow-scheduler-0 -c scheduler -- \
    airflow dags list 2>/dev/null" | grep -q "data_collection" && {
    echo -e "${GREEN}✓ DAGs loaded${NC}"
} || {
    echo -e "${YELLOW}⚠ DAGs not loaded yet${NC}"
    WARNINGS=$((WARNINGS + 1))
}

# Check database
ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c 'SELECT 1;'" >/dev/null 2>&1 && {
    echo -e "${GREEN}✓ Database accessible${NC}"
} || {
    echo -e "${RED}✗ Database connection issues${NC}"
    WARNINGS=$((WARNINGS + 1))
}

# Check metadata
ASSET_COUNT=$(ssh -i $SSH_KEY $CONTROL_NODE \
    "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -t -c \
    \"SET search_path TO financial_screener;
     SELECT COUNT(*) FROM asset_processing_state;\"" 2>/dev/null | tr -d ' ')

if [ -n "$ASSET_COUNT" ] && [ "$ASSET_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Metadata populated ($ASSET_COUNT assets)${NC}"
else
    echo -e "${YELLOW}⚠ Metadata not populated yet${NC}"
    WARNINGS=$((WARNINGS + 1))
fi

# Final status
echo ""
if [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}System Status: ALL SYSTEMS OPERATIONAL${NC}"
    echo -e "${GREEN}========================================${NC}"
    exit 0
elif [ $WARNINGS -le 2 ]; then
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}System Status: MINOR ISSUES DETECTED${NC}"
    echo -e "${YELLOW}========================================${NC}"
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}System Status: ATTENTION REQUIRED${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
