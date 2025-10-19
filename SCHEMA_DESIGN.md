# Database Schema Design - Multi-Project Support

## Overview

The Financial Screener is designed to coexist with other projects in a shared PostgreSQL database. All tables and custom types are created in a dedicated `financial_screener` schema.

## Architecture

### Schema Isolation

```
shared_database (e.g., "postgres")
├── public schema          (shared/default schema)
├── other_project schema   (other projects)
└── financial_screener schema  (this project) ⭐
    ├── Tables (14)
    ├── Custom Types (3)
    ├── Indexes
    ├── Triggers
    └── Views
```

### Benefits

1. **No Naming Conflicts**: Tables in different schemas can have the same names
2. **Security**: Schema-level permissions can isolate projects
3. **Organization**: Clear separation of concerns
4. **Maintenance**: Easy to backup/restore/drop single project's data
5. **Multi-tenancy**: Multiple applications share same PostgreSQL instance

## Implementation

### 1. Schema Creation

The migration creates the schema automatically:

```sql
-- Create dedicated schema for this project
CREATE SCHEMA IF NOT EXISTS financial_screener;

-- Set search path for this migration
SET search_path TO financial_screener, public;
```

### 2. Custom Types

All custom types are schema-qualified:

```sql
CREATE TYPE financial_screener.asset_type_enum AS ENUM ('stock', 'etf', 'bond');
CREATE TYPE financial_screener.recommendation_enum AS ENUM ('STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL');
CREATE TYPE financial_screener.sentiment_enum AS ENUM ('positive', 'neutral', 'negative');
```

### 3. Tables

All 14 tables are created in the `financial_screener` schema:

- `assets` - Master table for all assets (stocks, ETFs, bonds)
- `stock_prices` - Historical price data
- `stock_fundamentals` - Financial metrics
- `etf_details` - ETF-specific information
- `etf_holdings` - ETF portfolio composition
- `bond_details` - Bond-specific information
- `news_articles` - Financial news
- `sentiment_summary` - Aggregated sentiment scores
- `screening_results` - Screening criteria results
- `recommendations` - Buy/Sell recommendations
- `portfolios` - User portfolio tracking
- `portfolio_holdings` - Portfolio positions
- `transactions` - Transaction history
- `data_fetch_log` - ETL job tracking

### 4. Application Configuration

Applications connect with a search_path parameter:

```python
# Database URL with schema search path
DATABASE_URL = "postgresql://user:pass@host:5432/database?options=-c%20search_path%3Dfinancial_screener%2Cpublic"
```

This ensures:
- Queries default to `financial_screener` schema
- Falls back to `public` schema for extensions (uuid-ossp, pg_trgm)
- No need to schema-qualify table names in queries

### 5. Environment Variables

```bash
DATABASE_URL=postgresql://postgres:pass@postgres:5432/shared_db?options=-c%20search_path%3Dfinancial_screener%2Cpublic
DATABASE_SCHEMA=financial_screener
```

## Usage Examples

### Querying Tables

With search_path configured, tables can be queried without schema prefix:

```sql
-- Works because search_path includes financial_screener
SELECT * FROM assets WHERE ticker = 'AAPL';

-- Equivalent explicit query
SELECT * FROM financial_screener.assets WHERE ticker = 'AAPL';
```

### Joins with Other Projects

If needed, you can join with other schemas:

```sql
-- Join with another project's users table
SELECT a.*, u.username
FROM financial_screener.assets a
JOIN other_project.users u ON a.owner_id = u.id;
```

### Schema Introspection

```sql
-- List all tables in our schema
\dt financial_screener.*

-- List all custom types
\dT financial_screener.*

-- View schema details
\dn+ financial_screener

-- Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'financial_screener'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## Deployment

### Initial Setup

The deployment script handles schema creation:

1. Connects to existing shared database
2. Creates `financial_screener` schema (idempotent)
3. Runs migration to create all tables and types
4. Configures application with proper search_path

### Migration Script

```bash
# Deploy to cluster (script handles schema creation)
./scripts/deploy-to-cluster.sh

# Verify schema was created
kubectl exec -n financial-screener daemonset/celery-worker -- \
    psql -h postgres.default.svc.cluster.local \
    -U postgres -d postgres \
    -c "\dt financial_screener.*"
```

## Permissions

### Recommended Permissions Setup

For production, create a dedicated database user:

```sql
-- Create dedicated user for this project
CREATE USER financial_screener WITH PASSWORD 'secure_password';

-- Grant schema usage
GRANT USAGE ON SCHEMA financial_screener TO financial_screener;

-- Grant table permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA financial_screener TO financial_screener;
GRANT SELECT, USAGE ON ALL SEQUENCES IN SCHEMA financial_screener TO financial_screener;

-- Grant permissions on custom types
GRANT USAGE ON TYPE financial_screener.asset_type_enum TO financial_screener;
GRANT USAGE ON TYPE financial_screener.recommendation_enum TO financial_screener;
GRANT USAGE ON TYPE financial_screener.sentiment_enum TO financial_screener;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA financial_screener
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO financial_screener;

ALTER DEFAULT PRIVILEGES IN SCHEMA financial_screener
GRANT SELECT, USAGE ON SEQUENCES TO financial_screener;
```

## Maintenance

### Backup Single Project

```bash
# Backup just this project's schema
pg_dump -h postgres -U postgres -n financial_screener shared_db > financial_screener_backup.sql

# Restore
psql -h postgres -U postgres shared_db < financial_screener_backup.sql
```

### Drop Project Data

```bash
# WARNING: Drops all tables and types
DROP SCHEMA financial_screener CASCADE;
```

### Schema Migration

For future schema changes:

```sql
-- Use schema-qualified DDL
ALTER TABLE financial_screener.assets ADD COLUMN new_field VARCHAR(100);

-- Or set search_path first
SET search_path TO financial_screener, public;
ALTER TABLE assets ADD COLUMN new_field VARCHAR(100);
```

## Testing

### Verify Schema Isolation

```sql
-- Create test table in public schema (should not conflict)
CREATE TABLE public.assets (id SERIAL PRIMARY KEY, name VARCHAR(100));

-- Create table in our schema
INSERT INTO financial_screener.assets (ticker, name, asset_type)
VALUES ('TEST', 'Test Asset', 'stock');

-- Verify isolation
SELECT * FROM public.assets;  -- Empty
SELECT * FROM financial_screener.assets WHERE ticker = 'TEST';  -- Has data
```

## Best Practices

1. **Always Use Schema in Migrations**: Explicitly specify schema in DDL
2. **Configure search_path**: Set at connection level, not in code
3. **Schema-qualify Types**: Use `financial_screener.asset_type_enum`
4. **Document Dependencies**: Note if you reference other schemas
5. **Test Isolation**: Ensure your queries don't accidentally hit other schemas
6. **Monitor Size**: Track schema size as data grows
7. **Backup Strategy**: Regular backups of your schema

## References

- Migration file: [`database/migrations/001_initial_schema.sql`](database/migrations/001_initial_schema.sql)
- Config: [`services/analyzer/src/config.py`](services/analyzer/src/config.py)
- Deployment: [`scripts/deploy-to-cluster.sh`](scripts/deploy-to-cluster.sh)

---

**Last Updated**: 2025-10-19
**Schema Version**: 001 (initial schema)
