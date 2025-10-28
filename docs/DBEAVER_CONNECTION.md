# DBeaver Connection Guide - Financial Screener Database

## Connection Details

### Quick Connection (SSH Tunnel Already Running)

An SSH tunnel is already active on your system, forwarding `localhost:5432` to the PostgreSQL database.

**DBeaver Connection Settings:**

```
Connection Type:    PostgreSQL
Host:              localhost
Port:              5432
Database:          appdb
Username:          appuser
Password:          AppUser123
```

### Database Schema

After connecting, set the default schema to:
```
financial_screener
```

---

## Step-by-Step DBeaver Setup

### 1. Create New Connection

1. Open DBeaver
2. Click **Database** → **New Database Connection**
3. Select **PostgreSQL**
4. Click **Next**

### 2. Main Settings

Fill in the connection details:

| Field        | Value          |
|--------------|----------------|
| **Host**     | `localhost`    |
| **Port**     | `5432`         |
| **Database** | `appdb`        |
| **Username** | `appuser`      |
| **Password** | `AppUser123`   |

### 3. PostgreSQL Settings (Advanced)

Click on **PostgreSQL** tab:
- **Show all databases**: ✅ Checked
- **Show template databases**: ❌ Unchecked

### 4. SSH Tunnel (Optional - Already Running)

**Note:** You already have an SSH tunnel running, so you can skip this section.
However, if the tunnel stops, you can either:

**Option A: Use existing SSH tunnel**
The tunnel is managed by systemd service `postgres-tunnel.service`
```bash
systemctl status postgres-tunnel.service
systemctl restart postgres-tunnel.service
```

**Option B: Configure SSH in DBeaver**
1. Go to **SSH** tab in connection settings
2. ✅ Check "Use SSH Tunnel"
3. Fill in SSH details:
   - **Host/IP**: `192.168.1.240`
   - **Port**: `22`
   - **User Name**: `admin`
   - **Authentication Method**: `Public Key`
   - **Private Key**: `/root/.ssh/pi_cluster`
   - **Passphrase**: (if your key has one)

4. In **Main** tab, change:
   - **Host**: `postgresql-primary.databases.svc.cluster.local`
   - **Port**: `5432`

### 5. Connection Name

Give your connection a meaningful name:
```
Financial Screener - Pi Cluster
```

### 6. Test Connection

1. Click **Test Connection**
2. If prompted, download PostgreSQL driver
3. Should see: ✅ **"Connected"**

### 7. Finish

Click **Finish** to save the connection.

---

## Setting Default Schema

After connecting:

### Method 1: Connection Properties
1. Right-click connection → **Edit Connection**
2. Go to **Connection details** → **Initialization**
3. Add SQL script to run on connect:
   ```sql
   SET search_path TO financial_screener, public;
   ```

### Method 2: Manual (Each Session)
Run this after connecting:
```sql
SET search_path TO financial_screener;
```

---

## Database Structure

### Main Tables (financial_screener schema)

| Table                  | Description                           | Records (Target) |
|------------------------|---------------------------------------|------------------|
| `assets`               | Stock metadata + JSONB data           | 21,816           |
| `stock_prices`         | Daily OHLCV price data                | ~27 million      |
| `technical_indicators` | Calculated technical indicators       | 21,816           |
| `data_fetch_log`       | Data collection audit log             | ~100             |
| `news_articles`        | News articles (future)                | 0                |
| `sentiment_summary`    | Sentiment analysis (future)           | 0                |
| `screening_results`    | Screening results (future)            | 0                |
| `portfolios`           | User portfolios (future)              | 0                |

### Useful Queries

**Check total assets:**
```sql
SET search_path TO financial_screener;
SELECT COUNT(*) as total_assets,
       COUNT(DISTINCT ticker) as unique_tickers
FROM assets;
```

**Top 10 stocks by market cap:**
```sql
SET search_path TO financial_screener;
SELECT ticker, name, market_cap, pe_ratio, analyst_rating
FROM assets
ORDER BY market_cap DESC NULLS LAST
LIMIT 10;
```

**Check price data volume:**
```sql
SET search_path TO financial_screener;
SELECT
    COUNT(*) as total_prices,
    COUNT(DISTINCT asset_id) as assets_with_prices,
    MIN(date) as earliest_date,
    MAX(date) as latest_date
FROM stock_prices;
```

**View JSONB fundamentals for a stock:**
```sql
SET search_path TO financial_screener;
SELECT
    ticker,
    name,
    eodhd_general->'IPODate' as ipo_date,
    eodhd_highlights->'MarketCapitalization' as market_cap,
    jsonb_object_keys(eodhd_financials) as financial_sections
FROM assets
WHERE ticker = 'AAPL';
```

**Check Phase 1 progress:**
```sql
SET search_path TO financial_screener;
SELECT
    COUNT(*) as loaded_stocks,
    COUNT(*) FILTER (WHERE exchange = 'NYSE') as nyse_stocks,
    COUNT(*) FILTER (WHERE exchange = 'NASDAQ') as nasdaq_stocks,
    pg_size_pretty(pg_total_relation_size('assets')) as assets_size,
    pg_size_pretty(pg_total_relation_size('stock_prices')) as prices_size
FROM assets;
```

---

## Troubleshooting

### Cannot Connect - Connection Refused

**Check if SSH tunnel is running:**
```bash
systemctl status postgres-tunnel.service
```

**Restart the tunnel:**
```bash
systemctl restart postgres-tunnel.service
```

**Test local connection:**
```bash
nc -zv localhost 5432
```

### Authentication Failed

Verify credentials:
```bash
ssh -i ~/.ssh/pi_cluster admin@192.168.1.240 \
  "kubectl get secret postgres-secret -n financial-screener -o jsonpath='{.data.DATABASE_URL}' | base64 -d"
```

### Schema Not Found

Make sure to set search_path:
```sql
SET search_path TO financial_screener;
```

Or check all schemas:
```sql
SELECT schema_name FROM information_schema.schemata;
```

### Slow Queries

The database is running on Raspberry Pi hardware. For large queries:
1. Use `LIMIT` clauses
2. Add indexes if needed
3. Use materialized views for complex aggregations

---

## SSH Tunnel Service (systemd)

The SSH tunnel is managed by a systemd service.

**Service file location:**
```
/etc/systemd/system/postgres-tunnel.service
```

**Service commands:**
```bash
# Check status
systemctl status postgres-tunnel.service

# Restart
systemctl restart postgres-tunnel.service

# Stop
systemctl stop postgres-tunnel.service

# Start
systemctl start postgres-tunnel.service

# View logs
journalctl -u postgres-tunnel.service -f
```

---

## Direct Connection (Without Tunnel)

If you're on the same network as the cluster (192.168.1.x), you can connect directly:

**Option 1: Via Node Port (if configured)**
```
Host: 192.168.1.240
Port: 30432 (or check NodePort service)
```

**Option 2: Via kubectl port-forward**
```bash
kubectl port-forward -n databases postgresql-primary-0 5432:5432
```

Then connect to `localhost:5432`

---

## Security Notes

⚠️ **Important:**
- The password `AppUser123` is stored in the cluster secret
- The SSH tunnel uses key-based authentication (`/root/.ssh/pi_cluster`)
- The database is NOT exposed to the internet (cluster-internal only)
- Only accessible via SSH tunnel or from within the cluster network

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────┐
│ DBeaver Connection - Financial Screener         │
├─────────────────────────────────────────────────┤
│ Host:     localhost                             │
│ Port:     5432                                  │
│ Database: appdb                                 │
│ Username: appuser                               │
│ Password: AppUser123                            │
│ Schema:   financial_screener                    │
└─────────────────────────────────────────────────┘

Default SQL to run after connect:
SET search_path TO financial_screener;
```

---

**Generated:** 2025-10-20
**Cluster:** pi-cluster (192.168.1.240)
**Database:** PostgreSQL 16 on ARM64
