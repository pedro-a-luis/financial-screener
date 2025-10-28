#!/bin/bash
# Test PostgreSQL Connection for DBeaver
# This simulates what DBeaver does when connecting

echo "=== PostgreSQL Connection Test ==="
echo ""

# Check if tunnel is running
echo "1. Checking SSH tunnel..."
if systemctl is-active --quiet postgres-tunnel.service; then
    echo "   ✅ SSH tunnel service is running"
    POD_IP=$(journalctl -u postgres-tunnel.service -n 10 --no-pager | grep "PostgreSQL pod IP" | tail -1 | awk '{print $NF}')
    echo "   📍 Tunneling to pod IP: $POD_IP"
else
    echo "   ❌ SSH tunnel service is NOT running"
    echo "   Fix: systemctl start postgres-tunnel.service"
    exit 1
fi

# Check if port is accessible
echo ""
echo "2. Checking local port 5432..."
if timeout 2 bash -c 'cat < /dev/null > /dev/tcp/localhost/5432' 2>/dev/null; then
    echo "   ✅ Port 5432 is accessible"
else
    echo "   ❌ Port 5432 is NOT accessible"
    echo "   Fix: systemctl restart postgres-tunnel.service"
    exit 1
fi

# Try to connect via SSH and test database
echo ""
echo "3. Testing database connection..."
RESULT=$(ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- \
   psql -U appuser -d appdb -c 'SELECT 1 as test;'" 2>&1)

if echo "$RESULT" | grep -q "1 row"; then
    echo "   ✅ Database is accessible and responding"
else
    echo "   ❌ Database connection failed"
    echo "   Output: $RESULT"
    exit 1
fi

# Test financial_screener schema
echo ""
echo "4. Testing financial_screener schema..."
COUNT=$(ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl exec -n databases postgresql-primary-0 -- \
   psql -U appuser -d appdb -c \"SET search_path TO financial_screener; SELECT COUNT(*) FROM assets;\"" 2>&1 | grep -oP '\d+' | head -1)

if [ -n "$COUNT" ]; then
    echo "   ✅ Schema accessible"
    echo "   📊 Assets in database: $COUNT"
else
    echo "   ❌ Schema test failed"
    exit 1
fi

echo ""
echo "=== ✅ ALL TESTS PASSED ==="
echo ""
echo "DBeaver Connection Details:"
echo "  Host:     localhost"
echo "  Port:     5432"
echo "  Database: appdb"
echo "  Username: appuser"
echo "  Password: AppUser123"
echo "  Schema:   financial_screener"
echo ""
echo "First query to run after connecting:"
echo "  SET search_path TO financial_screener;"
echo ""
