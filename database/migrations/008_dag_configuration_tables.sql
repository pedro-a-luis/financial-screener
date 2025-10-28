-- Migration: 008_dag_configuration_tables.sql
-- Purpose: Create configuration tables for Airflow DAG management
-- Author: Financial Screener Team
-- Date: 2025-10-28
-- Description: Removes hardcoded values from DAGs, enabling runtime configuration
--              of resources, batch sizes, exchange groupings, and timeouts

SET search_path TO financial_screener, public;

-- =====================================================
-- TABLE: dag_configuration
-- Stores runtime configuration for DAG execution
-- =====================================================

CREATE TABLE dag_configuration (
    id SERIAL PRIMARY KEY,

    -- Configuration identification
    dag_name VARCHAR(100) NOT NULL,              -- 'data_collection_equities', 'calculate_indicators', etc.
    job_name VARCHAR(100) NOT NULL,              -- 'us_markets', 'lse', 'german_markets', 'all', etc.

    -- Resource limits (Kubernetes)
    cpu_request VARCHAR(20) DEFAULT '500m',      -- CPU request (e.g., '500m', '1000m', '2')
    cpu_limit VARCHAR(20) DEFAULT '2000m',       -- CPU limit
    memory_request VARCHAR(20) DEFAULT '1Gi',    -- Memory request (e.g., '1Gi', '2Gi')
    memory_limit VARCHAR(20) DEFAULT '2Gi',      -- Memory limit

    -- Processing configuration
    batch_size INTEGER DEFAULT 500,              -- Number of assets per batch
    timeout_seconds INTEGER DEFAULT 600,         -- Pod completion timeout

    -- Retry configuration
    max_retries INTEGER DEFAULT 2,               -- Number of Airflow task retries
    retry_delay_minutes INTEGER DEFAULT 5,       -- Initial retry delay
    retry_backoff_enabled BOOLEAN DEFAULT TRUE,  -- Use exponential backoff

    -- Job control
    enabled BOOLEAN DEFAULT TRUE,                -- Allow disabling jobs without code changes
    priority INTEGER DEFAULT 5,                  -- Job priority (1-10, higher = more important)

    -- Metadata
    description TEXT,                            -- Purpose of this configuration
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT 'system',

    -- Ensure one config per DAG+job combination
    UNIQUE(dag_name, job_name)
);

-- Indexes
CREATE INDEX idx_dag_config_dag_name ON dag_configuration(dag_name);
CREATE INDEX idx_dag_config_enabled ON dag_configuration(enabled) WHERE enabled = TRUE;

-- Comments
COMMENT ON TABLE dag_configuration IS 'Runtime configuration for Airflow DAGs - enables tuning without code changes';
COMMENT ON COLUMN dag_configuration.dag_name IS 'Airflow DAG ID';
COMMENT ON COLUMN dag_configuration.job_name IS 'Specific job within DAG (e.g., exchange group or ''all'')';
COMMENT ON COLUMN dag_configuration.batch_size IS 'Assets processed per batch - auto-adjusted by quota system';
COMMENT ON COLUMN dag_configuration.enabled IS 'Allows disabling jobs temporarily without code changes';

-- =====================================================
-- TABLE: exchange_groups
-- Defines market exchange groupings for parallel processing
-- =====================================================

CREATE TABLE exchange_groups (
    id SERIAL PRIMARY KEY,

    -- Group identification
    group_name VARCHAR(50) NOT NULL UNIQUE,      -- 'us_markets', 'lse', 'german_markets', etc.
    display_name VARCHAR(100) NOT NULL,          -- 'US Markets (NYSE, NASDAQ)'

    -- Exchange configuration
    exchanges TEXT[] NOT NULL,                   -- Array: ['NYSE', 'NASDAQ'] or ['LSE']

    -- Market characteristics
    primary_timezone VARCHAR(50) DEFAULT 'UTC',  -- 'America/New_York', 'Europe/London'
    market_open_utc TIME,                        -- Market opening time in UTC
    market_close_utc TIME,                       -- Market closing time in UTC

    -- Processing configuration
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 5,                  -- Processing priority (1-10)

    -- Metadata
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_exchange_groups_enabled ON exchange_groups(enabled) WHERE enabled = TRUE;
CREATE INDEX idx_exchange_groups_priority ON exchange_groups(priority DESC);

-- Comments
COMMENT ON TABLE exchange_groups IS 'Defines exchange groupings for parallel DAG processing';
COMMENT ON COLUMN exchange_groups.exchanges IS 'Array of exchange codes processed together';
COMMENT ON COLUMN exchange_groups.priority IS 'Higher priority groups processed first when resources are limited';

-- =====================================================
-- FUNCTION: get_dag_config
-- Retrieves configuration for a specific DAG job
-- =====================================================

CREATE OR REPLACE FUNCTION get_dag_config(
    p_dag_name VARCHAR(100),
    p_job_name VARCHAR(100) DEFAULT 'all'
)
RETURNS TABLE (
    cpu_request VARCHAR(20),
    cpu_limit VARCHAR(20),
    memory_request VARCHAR(20),
    memory_limit VARCHAR(20),
    batch_size INTEGER,
    timeout_seconds INTEGER,
    max_retries INTEGER,
    retry_delay_minutes INTEGER,
    retry_backoff_enabled BOOLEAN,
    enabled BOOLEAN
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.cpu_request,
        dc.cpu_limit,
        dc.memory_request,
        dc.memory_limit,
        dc.batch_size,
        dc.timeout_seconds,
        dc.max_retries,
        dc.retry_delay_minutes,
        dc.retry_backoff_enabled,
        dc.enabled
    FROM dag_configuration dc
    WHERE dc.dag_name = p_dag_name
      AND dc.job_name = p_job_name
      AND dc.enabled = TRUE;

    -- If no specific config found, return defaults
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT
            '500m'::VARCHAR(20),
            '2000m'::VARCHAR(20),
            '1Gi'::VARCHAR(20),
            '2Gi'::VARCHAR(20),
            500::INTEGER,
            600::INTEGER,
            2::INTEGER,
            5::INTEGER,
            TRUE::BOOLEAN,
            TRUE::BOOLEAN;
    END IF;
END;
$$;

COMMENT ON FUNCTION get_dag_config IS 'Retrieves DAG configuration with fallback to defaults';

-- =====================================================
-- FUNCTION: get_exchange_groups
-- Retrieves enabled exchange groups for processing
-- =====================================================

CREATE OR REPLACE FUNCTION get_exchange_groups()
RETURNS TABLE (
    group_name VARCHAR(50),
    display_name VARCHAR(100),
    exchanges TEXT[],
    priority INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        eg.group_name,
        eg.display_name,
        eg.exchanges,
        eg.priority
    FROM exchange_groups eg
    WHERE eg.enabled = TRUE
    ORDER BY eg.priority DESC, eg.group_name;
END;
$$;

COMMENT ON FUNCTION get_exchange_groups IS 'Returns enabled exchange groups ordered by priority';

-- =====================================================
-- FUNCTION: update_dag_config
-- Safely updates DAG configuration with audit trail
-- =====================================================

CREATE OR REPLACE FUNCTION update_dag_config(
    p_dag_name VARCHAR(100),
    p_job_name VARCHAR(100),
    p_cpu_request VARCHAR(20) DEFAULT NULL,
    p_cpu_limit VARCHAR(20) DEFAULT NULL,
    p_memory_request VARCHAR(20) DEFAULT NULL,
    p_memory_limit VARCHAR(20) DEFAULT NULL,
    p_batch_size INTEGER DEFAULT NULL,
    p_timeout_seconds INTEGER DEFAULT NULL,
    p_updated_by VARCHAR(100) DEFAULT 'system'
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    -- Update only non-NULL parameters
    UPDATE dag_configuration
    SET
        cpu_request = COALESCE(p_cpu_request, cpu_request),
        cpu_limit = COALESCE(p_cpu_limit, cpu_limit),
        memory_request = COALESCE(p_memory_request, memory_request),
        memory_limit = COALESCE(p_memory_limit, memory_limit),
        batch_size = COALESCE(p_batch_size, batch_size),
        timeout_seconds = COALESCE(p_timeout_seconds, timeout_seconds),
        updated_at = NOW(),
        created_by = p_updated_by
    WHERE dag_name = p_dag_name
      AND job_name = p_job_name;

    -- If no rows updated, insert new config
    IF NOT FOUND THEN
        INSERT INTO dag_configuration (
            dag_name, job_name, cpu_request, cpu_limit,
            memory_request, memory_limit, batch_size, timeout_seconds,
            created_by
        ) VALUES (
            p_dag_name, p_job_name,
            COALESCE(p_cpu_request, '500m'),
            COALESCE(p_cpu_limit, '2000m'),
            COALESCE(p_memory_request, '1Gi'),
            COALESCE(p_memory_limit, '2Gi'),
            COALESCE(p_batch_size, 500),
            COALESCE(p_timeout_seconds, 600),
            p_updated_by
        );
    END IF;
END;
$$;

COMMENT ON FUNCTION update_dag_config IS 'Updates DAG configuration with audit trail, creates if not exists';

-- =====================================================
-- INITIAL DATA: Exchange Groups
-- =====================================================

INSERT INTO exchange_groups (group_name, display_name, exchanges, primary_timezone, description, priority) VALUES
('us_markets', 'US Markets (NYSE, NASDAQ)', ARRAY['NYSE', 'NASDAQ'], 'America/New_York', 'Major US stock exchanges', 10),
('lse', 'London Stock Exchange', ARRAY['LSE'], 'Europe/London', 'UK primary exchange', 9),
('german_markets', 'German Markets (Frankfurt, XETRA)', ARRAY['FRANKFURT', 'XETRA'], 'Europe/Berlin', 'German stock exchanges', 8),
('european_markets', 'European Markets (Euronext, BME, SIX)', ARRAY['EURONEXT', 'BME', 'SIX'], 'Europe/Paris', 'Other major European exchanges', 7);

-- =====================================================
-- INITIAL DATA: DAG Configurations
-- =====================================================

-- Data Collection - US Markets (highest volume, more resources)
INSERT INTO dag_configuration (dag_name, job_name, cpu_request, cpu_limit, memory_request, memory_limit, batch_size, timeout_seconds, description, priority) VALUES
('data_collection_equities', 'us_markets', '500m', '2000m', '1Gi', '2Gi', 500, 600, 'US markets data collection - NYSE, NASDAQ', 10);

-- Data Collection - LSE
INSERT INTO dag_configuration (dag_name, job_name, cpu_request, cpu_limit, memory_request, memory_limit, batch_size, timeout_seconds, description, priority) VALUES
('data_collection_equities', 'lse', '500m', '2000m', '1Gi', '2Gi', 500, 600, 'London Stock Exchange data collection', 9);

-- Data Collection - German Markets
INSERT INTO dag_configuration (dag_name, job_name, cpu_request, cpu_limit, memory_request, memory_limit, batch_size, timeout_seconds, description, priority) VALUES
('data_collection_equities', 'german_markets', '500m', '2000m', '1Gi', '2Gi', 500, 600, 'German exchanges (Frankfurt, XETRA) data collection', 8);

-- Data Collection - European Markets
INSERT INTO dag_configuration (dag_name, job_name, cpu_request, cpu_limit, memory_request, memory_limit, batch_size, timeout_seconds, description, priority) VALUES
('data_collection_equities', 'european_markets', '500m', '2000m', '1Gi', '2Gi', 500, 600, 'Other European exchanges (Euronext, BME, SIX) data collection', 7);

-- Historical Load - Same as data collection
INSERT INTO dag_configuration (dag_name, job_name, cpu_request, cpu_limit, memory_request, memory_limit, batch_size, timeout_seconds, description, priority) VALUES
('historical_load_equities', 'us_markets', '500m', '2000m', '1Gi', '2Gi', 500, 600, 'US markets historical data load', 10),
('historical_load_equities', 'lse', '500m', '2000m', '1Gi', '2Gi', 500, 600, 'LSE historical data load', 9),
('historical_load_equities', 'german_markets', '500m', '2000m', '1Gi', '2Gi', 500, 600, 'German markets historical data load', 8),
('historical_load_equities', 'european_markets', '500m', '2000m', '1Gi', '2Gi', 500, 600, 'European markets historical data load', 7);

-- Technical Indicators (CPU-intensive, needs more resources)
INSERT INTO dag_configuration (dag_name, job_name, cpu_request, cpu_limit, memory_request, memory_limit, batch_size, timeout_seconds, description, priority) VALUES
('calculate_indicators', 'all', '1000m', '4000m', '2Gi', '4Gi', 1000, 3600, 'Technical indicators calculation (CPU-intensive)', 10);

-- =====================================================
-- AUDIT TRIGGER: Track configuration changes
-- =====================================================

CREATE TABLE dag_configuration_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    operation VARCHAR(10) NOT NULL,
    dag_name VARCHAR(100) NOT NULL,
    job_name VARCHAR(100) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by VARCHAR(100),
    changed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION audit_dag_configuration()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF (TG_OP = 'UPDATE') THEN
        INSERT INTO dag_configuration_audit (
            operation, dag_name, job_name, old_values, new_values, changed_by
        ) VALUES (
            'UPDATE',
            OLD.dag_name,
            OLD.job_name,
            to_jsonb(OLD),
            to_jsonb(NEW),
            NEW.created_by
        );
    ELSIF (TG_OP = 'INSERT') THEN
        INSERT INTO dag_configuration_audit (
            operation, dag_name, job_name, new_values, changed_by
        ) VALUES (
            'INSERT',
            NEW.dag_name,
            NEW.job_name,
            to_jsonb(NEW),
            NEW.created_by
        );
    ELSIF (TG_OP = 'DELETE') THEN
        INSERT INTO dag_configuration_audit (
            operation, dag_name, job_name, old_values, changed_by
        ) VALUES (
            'DELETE',
            OLD.dag_name,
            OLD.job_name,
            to_jsonb(OLD),
            OLD.created_by
        );
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trigger_audit_dag_configuration
AFTER INSERT OR UPDATE OR DELETE ON dag_configuration
FOR EACH ROW EXECUTE FUNCTION audit_dag_configuration();

COMMENT ON TABLE dag_configuration_audit IS 'Audit trail for all DAG configuration changes';

-- =====================================================
-- GRANTS
-- =====================================================

-- Grant appropriate permissions
GRANT SELECT ON dag_configuration TO PUBLIC;
GRANT SELECT ON exchange_groups TO PUBLIC;
GRANT SELECT ON dag_configuration_audit TO PUBLIC;

-- Grant execute on functions
GRANT EXECUTE ON FUNCTION get_dag_config TO PUBLIC;
GRANT EXECUTE ON FUNCTION get_exchange_groups TO PUBLIC;
GRANT EXECUTE ON FUNCTION update_dag_config TO PUBLIC;

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================

-- Verify installation
DO $$
DECLARE
    v_config_count INTEGER;
    v_groups_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_config_count FROM dag_configuration;
    SELECT COUNT(*) INTO v_groups_count FROM exchange_groups;

    RAISE NOTICE '========================================';
    RAISE NOTICE 'Migration 008 completed successfully!';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'DAG Configurations created: %', v_config_count;
    RAISE NOTICE 'Exchange Groups created: %', v_groups_count;
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '1. Update DAGs to read from dag_configuration table';
    RAISE NOTICE '2. Test configuration retrieval: SELECT * FROM get_dag_config(''data_collection_equities'', ''us_markets'');';
    RAISE NOTICE '3. View exchange groups: SELECT * FROM get_exchange_groups();';
    RAISE NOTICE '========================================';
END $$;
