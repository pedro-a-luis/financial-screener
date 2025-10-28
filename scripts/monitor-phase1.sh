#!/bin/bash
# Monitor Phase 1 US Markets Bulk Load

echo "=== Phase 1: US Markets Bulk Load Monitor ==="
echo ""

while true; do
    clear
    echo "=== Phase 1: US Markets Bulk Load Monitor ==="
    echo "Target: 6,433 stocks (NYSE + NASDAQ)"
    echo "Started: $(date)"
    echo ""

    # Get job status
    echo "📊 Job Status:"
    ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl get job phase1-us-markets -n financial-screener 2>/dev/null" || echo "Job not found"
    echo ""

    # Get pod status
    echo "🔧 Pod Status:"
    ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl get pods -n financial-screener -l phase=phase1 2>/dev/null" || echo "No pods found"
    echo ""

    # Check database counts
    echo "💾 Database Progress:"
    ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl exec -n databases postgresql-primary-0 -- psql -U appuser -d appdb -c \"SET search_path TO financial_screener; SELECT COUNT(*) as assets, COUNT(DISTINCT ticker) as unique_tickers FROM assets;\" 2>/dev/null" || echo "Database unavailable"
    echo ""

    # Show recent logs
    echo "📝 Recent Activity (last 10 lines):"
    ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 "kubectl logs -n financial-screener -l phase=phase1 --tail=10 2>&1 | grep -E '(batch_complete|data_collection_complete|successes|failures)'" || echo "No logs available"
    echo ""

    echo "Press Ctrl+C to exit. Refreshing in 30 seconds..."
    sleep 30
done
