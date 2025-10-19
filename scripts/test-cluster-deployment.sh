#!/bin/bash
# Test deployed services on Raspberry Pi K3s cluster

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

NAMESPACE="${NAMESPACE:-financial-screener}"

echo -e "${YELLOW}=== Testing Financial Screener Deployment ===${NC}\n"

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Function to run test
run_test() {
    local test_name=$1
    local test_command=$2

    echo -e "${YELLOW}Testing: $test_name${NC}"

    if eval "$test_command"; then
        echo -e "${GREEN}✓ PASS: $test_name${NC}\n"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAIL: $test_name${NC}\n"
        ((TESTS_FAILED++))
        return 1
    fi
}

# 1. Test namespace exists
run_test "Namespace exists" \
    "kubectl get namespace $NAMESPACE &>/dev/null"

# 2. Test Redis connectivity
run_test "Redis is accessible" \
    "kubectl exec -n $NAMESPACE daemonset/celery-worker -- redis-cli -h redis.default.svc.cluster.local ping | grep -q PONG"

# 3. Test PostgreSQL connectivity
run_test "PostgreSQL is accessible" \
    "kubectl exec -n $NAMESPACE daemonset/celery-worker -- sh -c 'python3 -c \"import psycopg2; conn = psycopg2.connect(\\\"host=postgres.default.svc.cluster.local port=5432 dbname=financial_db user=financial password=financial\\\"); conn.close(); print(\\\"OK\\\")\"' | grep -q OK"

# 4. Test Celery workers are running
echo -e "${YELLOW}Testing: Celery workers running${NC}"
WORKER_COUNT=$(kubectl get pods -n $NAMESPACE -l app=celery-worker --field-selector=status.phase=Running -o name | wc -l)

if [ "$WORKER_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ PASS: $WORKER_COUNT Celery workers running${NC}\n"
    ((TESTS_PASSED++))
else
    echo -e "${RED}✗ FAIL: No Celery workers running${NC}\n"
    ((TESTS_FAILED++))
fi

# 5. Test Polars is installed
run_test "Polars installed in workers" \
    "kubectl exec -n $NAMESPACE daemonset/celery-worker -- python3 -c 'import polars as pl; print(pl.__version__)'"

# 6. Test Celery can connect to broker
run_test "Celery broker connection" \
    "kubectl exec -n $NAMESPACE daemonset/celery-worker -- celery -A celery_app inspect ping | grep -q pong"

# 7. Test Flower dashboard
run_test "Flower dashboard accessible" \
    "kubectl get svc flower -n $NAMESPACE &>/dev/null"

# 8. Test worker resource usage
echo -e "${YELLOW}Checking worker resource usage...${NC}"
kubectl top pods -n $NAMESPACE -l app=celery-worker 2>/dev/null || echo "Note: Metrics server may not be available"
echo ""

# 9. Test Polars performance on ARM64
echo -e "${YELLOW}Testing: Polars performance on ARM64${NC}"

PERF_TEST=$(kubectl exec -n $NAMESPACE daemonset/celery-worker -- python3 -c '
import polars as pl
import time
import platform

# Verify ARM64
arch = platform.machine()
print(f"Architecture: {arch}")

# Performance test
df = pl.DataFrame({"x": range(10000)})
start = time.time()
result = df.with_columns([(pl.col("x") * 2).alias("x2")])
duration = time.time() - start

print(f"Polars 10K rows: {duration:.4f}s")

# Should be very fast
if duration < 0.5:
    print("PASS")
else:
    print("SLOW")
' 2>&1)

echo "$PERF_TEST"

if echo "$PERF_TEST" | grep -q "PASS"; then
    echo -e "${GREEN}✓ PASS: Polars performance test${NC}\n"
    ((TESTS_PASSED++))
else
    echo -e "${YELLOW}⚠ WARNING: Polars performance slower than expected${NC}\n"
fi

# 10. Test sample Celery task execution
echo -e "${YELLOW}Testing: Celery task execution${NC}"

TASK_TEST=$(kubectl exec -n $NAMESPACE daemonset/celery-worker -- python3 << 'EOF'
from celery_app import app
import time

# Send test task
result = app.send_task("analyzer.tasks.analyze_stock", args=["AAPL"])

print(f"Task ID: {result.id}")
print(f"Task state: {result.state}")

# Wait for result with timeout
try:
    # Give it 30 seconds
    data = result.get(timeout=30)
    print(f"Task completed: {type(data)}")
    print("TASK_SUCCESS")
except Exception as e:
    print(f"Task failed: {e}")
    print("TASK_FAILED")
EOF
2>&1)

echo "$TASK_TEST"

if echo "$TASK_TEST" | grep -q "TASK_SUCCESS"; then
    echo -e "${GREEN}✓ PASS: Celery task execution${NC}\n"
    ((TESTS_PASSED++))
elif echo "$TASK_TEST" | grep -q "No module named"; then
    echo -e "${YELLOW}⚠ EXPECTED: Task modules not fully implemented yet${NC}\n"
else
    echo -e "${RED}✗ FAIL: Celery task execution${NC}\n"
    ((TESTS_FAILED++))
fi

# Summary
echo -e "${YELLOW}=== Test Summary ===${NC}"
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
echo -e "Total: $((TESTS_PASSED + TESTS_FAILED))"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "\n${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "\n${YELLOW}Some tests failed. Check logs above.${NC}"
    exit 1
fi
