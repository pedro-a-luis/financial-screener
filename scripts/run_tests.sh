#!/bin/bash
# Test Runner Script for Financial Screener
#
# Run all tests or specific test suites

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Financial Screener Test Suite ===${NC}\n"

# Function to run tests
run_test() {
    local test_name=$1
    local test_path=$2

    echo -e "${YELLOW}Running: $test_name${NC}"

    if pytest "$test_path" -v --tb=short --cov --cov-report=term-missing; then
        echo -e "${GREEN}✓ $test_name PASSED${NC}\n"
        return 0
    else
        echo -e "${RED}✗ $test_name FAILED${NC}\n"
        return 1
    fi
}

# Track failures
failed_tests=()

# 1. Test Shared Models
if ! run_test "Shared Models" "shared/tests/test_models.py"; then
    failed_tests+=("Shared Models")
fi

# 2. Test Analyzer Calculators
if ! run_test "Analyzer Calculators" "services/analyzer/tests/test_calculators.py"; then
    failed_tests+=("Analyzer Calculators")
fi

# 3. Test Data Collector (if tests exist)
if [ -f "services/data-collector/tests/test_fetchers.py" ]; then
    if ! run_test "Data Collector" "services/data-collector/tests/test_fetchers.py"; then
        failed_tests+=("Data Collector")
    fi
fi

# Summary
echo -e "${YELLOW}=== Test Summary ===${NC}"

if [ ${#failed_tests[@]} -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Failed tests:${NC}"
    for test in "${failed_tests[@]}"; do
        echo -e "${RED}  - $test${NC}"
    done
    exit 1
fi
