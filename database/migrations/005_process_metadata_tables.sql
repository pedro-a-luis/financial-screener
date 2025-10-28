-- Migration: 005_process_metadata_tables.sql
-- Purpose: Create metadata tables for Airflow orchestration
-- Author: Financial Screener Team
-- Date: 2025-10-21

SET search_path TO financial_screener, public;

-- =====================================================
-- TABLE: process_executions
-- Tracks every DAG run with parameters and results
-- =====================================================

CREATE TABLE process_executions (
    id BIGSERIAL PRIMARY KEY,

    -- Process identification
    process_name VARCHAR(100) NOT NULL,          -- 'data_collection_equities', 'calculate_indicators'
    execution_id VARCHAR(255) NOT NULL UNIQUE,   -- Airflow run_id (e.g., 'scheduled__2025-10-21T21:30:00+00:00')

    -- Execution parameters (store ALL inputs as JSONB for flexibility)
    parameters JSONB NOT NULL DEFAULT '{}'::JSONB,  -- {mode: 'bulk', batch_size: 500, tickers: [...]}

    -- Execution state
    status VARCHAR(20) NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'partial', 'failed')),

    -- Metrics
    assets_discovered INTEGER DEFAULT 0,         -- Total tickers found in config files
    assets_processed INTEGER DEFAULT 0,          -- Tickers actually processed
    assets_succeeded INTEGER DEFAULT 0,          -- Successful operations
    assets_failed INTEGER DEFAULT 0,             -- Failed operations
    api_calls_used INTEGER DEFAULT 0,            -- Total API calls consumed

    -- Timing
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_seconds INTEGER,

    -- Error tracking
    error_message TEXT,
    error_details JSONB,

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_process_exec_name_date ON process_executions(process_name, started_at DESC);
CREATE INDEX idx_process_exec_id ON process_executions(execution_id);
CREATE INDEX idx_process_exec_status ON process_executions(status, started_at DESC) WHERE status IN ('failed', 'partial');
CREATE INDEX idx_process_exec_started ON process_executions(started_at DESC);

-- Comments
COMMENT ON TABLE process_executions IS 'Tracks every DAG run execution with full parameters and results';
COMMENT ON COLUMN process_executions.process_name IS 'DAG name that executed';
COMMENT ON COLUMN process_executions.execution_id IS 'Airflow run_id for traceability';
COMMENT ON COLUMN process_executions.parameters IS 'Full execution parameters as JSONB';
COMMENT ON COLUMN process_executions.status IS 'running, success, partial (>10% failures), failed';

-- =====================================================
-- TABLE: asset_processing_state
-- State machine tracking processing status of each ticker
-- =====================================================

CREATE TABLE asset_processing_state (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL UNIQUE,

    -- Data Collection State (Fundamentals)
    fundamentals_loaded BOOLEAN DEFAULT FALSE,
    fundamentals_loaded_at TIMESTAMP,
    fundamentals_execution_id VARCHAR(255),      -- Reference to process_executions.execution_id

    -- Data Collection State (Prices)
    prices_loaded BOOLEAN DEFAULT FALSE,
    prices_first_date DATE,                      -- Earliest price date loaded
    prices_last_date DATE,                       -- Most recent price date loaded
    prices_last_updated_at TIMESTAMP,
    prices_execution_id VARCHAR(255),

    -- Technical Indicators State
    indicators_calculated BOOLEAN DEFAULT FALSE,
    indicators_calculated_at TIMESTAMP,
    indicators_execution_id VARCHAR(255),

    -- Reprocessing Flags (set manually or by DAG logic)
    needs_fundamentals_reprocess BOOLEAN DEFAULT FALSE,
    needs_prices_reprocess BOOLEAN DEFAULT FALSE,
    needs_indicators_reprocess BOOLEAN DEFAULT FALSE,

    -- Failure Tracking
    last_error_at TIMESTAMP,
    last_error_message TEXT,
    consecutive_failures INTEGER DEFAULT 0,      -- Reset to 0 on success, increment on failure

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for fast delta discovery
CREATE UNIQUE INDEX idx_asset_state_ticker ON asset_processing_state(ticker);

-- Index for finding assets needing fundamentals
CREATE INDEX idx_asset_state_needs_fundamentals ON asset_processing_state(fundamentals_loaded, needs_fundamentals_reprocess)
WHERE fundamentals_loaded = FALSE OR needs_fundamentals_reprocess = TRUE;

-- Index for finding assets needing price updates
CREATE INDEX idx_asset_state_prices_stale ON asset_processing_state(prices_last_date)
WHERE prices_last_date < CURRENT_DATE - 1;

-- Index for finding assets needing indicator calculation
CREATE INDEX idx_asset_state_indicators_stale ON asset_processing_state(indicators_calculated_at)
WHERE indicators_calculated = FALSE OR indicators_calculated_at < CURRENT_DATE;

-- Index for failed assets
CREATE INDEX idx_asset_state_failures ON asset_processing_state(consecutive_failures, last_error_at DESC)
WHERE consecutive_failures > 0;

-- Comments
COMMENT ON TABLE asset_processing_state IS 'State machine tracking processing status of each ticker (21,817 rows)';
COMMENT ON COLUMN asset_processing_state.fundamentals_loaded IS 'TRUE after successful bulk load';
COMMENT ON COLUMN asset_processing_state.prices_last_date IS 'Most recent price date - used for delta discovery';
COMMENT ON COLUMN asset_processing_state.consecutive_failures IS 'Skip processing after 5 consecutive failures';
COMMENT ON COLUMN asset_processing_state.needs_fundamentals_reprocess IS 'Set TRUE to force reload on next execution';

-- =====================================================
-- TABLE: asset_processing_details
-- Detailed log of each operation on each ticker
-- =====================================================

CREATE TABLE asset_processing_details (
    id BIGSERIAL PRIMARY KEY,
    execution_id VARCHAR(255) NOT NULL,          -- Foreign key to process_executions.execution_id
    ticker VARCHAR(20) NOT NULL,

    -- What was processed
    operation VARCHAR(50) NOT NULL,              -- 'fundamentals_bulk', 'prices_incremental', 'indicators_calc'

    -- Results
    status VARCHAR(20) NOT NULL CHECK (status IN ('success', 'failed', 'skipped')),
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    api_calls_used INTEGER DEFAULT 0,

    -- Error details (if failed)
    error_message TEXT,
    error_code VARCHAR(50),                      -- 'api_limit', 'network_error', '404_not_found'

    -- Timing
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_ms INTEGER,

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_asset_details_execution ON asset_processing_details(execution_id, created_at DESC);
CREATE INDEX idx_asset_details_ticker ON asset_processing_details(ticker, created_at DESC);
CREATE INDEX idx_asset_details_status ON asset_processing_details(status, created_at DESC) WHERE status = 'failed';
CREATE INDEX idx_asset_details_date_operation ON asset_processing_details((DATE(created_at)), operation, status);

-- Foreign key (soft - doesn't prevent cleanup)
-- Not using FOREIGN KEY constraint to allow process_executions cleanup without cascading deletes
COMMENT ON COLUMN asset_processing_details.execution_id IS 'Links to process_executions.execution_id (soft FK)';

-- Comments
COMMENT ON TABLE asset_processing_details IS 'Granular log of each operation on each ticker (~8M rows/year)';
COMMENT ON COLUMN asset_processing_details.operation IS 'fundamentals_bulk (10 API calls), prices_incremental (1 API call), indicators_calc (0 calls)';
COMMENT ON COLUMN asset_processing_details.status IS 'success, failed, skipped';

-- =====================================================
-- VIEWS: Helper views for monitoring and delta discovery
-- =====================================================

-- View: Assets needing processing (delta discovery)
CREATE VIEW v_assets_needing_processing AS
SELECT
    aps.ticker,
    CASE
        WHEN aps.fundamentals_loaded = FALSE OR aps.needs_fundamentals_reprocess = TRUE
            THEN 'bulk_load'
        WHEN aps.prices_last_date IS NULL OR aps.prices_last_date < CURRENT_DATE - 1 OR aps.needs_prices_reprocess = TRUE
            THEN 'price_update'
        WHEN aps.indicators_calculated = FALSE
             OR aps.indicators_calculated_at IS NULL
             OR aps.indicators_calculated_at < CURRENT_DATE
             OR aps.needs_indicators_reprocess = TRUE
            THEN 'indicator_calc'
        ELSE 'up_to_date'
    END as processing_need,
    aps.prices_last_date,
    aps.indicators_calculated_at,
    aps.consecutive_failures,
    aps.last_error_message
FROM asset_processing_state aps
WHERE aps.consecutive_failures < 5  -- Skip permanently broken tickers
ORDER BY
    CASE
        WHEN aps.fundamentals_loaded = FALSE OR aps.needs_fundamentals_reprocess = TRUE THEN 1
        WHEN aps.prices_last_date IS NULL OR aps.prices_last_date < CURRENT_DATE - 1 OR aps.needs_prices_reprocess = TRUE THEN 2
        WHEN aps.indicators_calculated = FALSE OR aps.indicators_calculated_at IS NULL OR aps.indicators_calculated_at < CURRENT_DATE THEN 3
        ELSE 4
    END,
    aps.ticker;

COMMENT ON VIEW v_assets_needing_processing IS 'Delta discovery view - shows what each ticker needs';

-- View: Recent execution summary
CREATE VIEW v_recent_executions AS
SELECT
    pe.process_name,
    pe.execution_id,
    pe.status,
    pe.assets_processed,
    pe.assets_succeeded,
    pe.assets_failed,
    pe.api_calls_used,
    pe.started_at,
    pe.completed_at,
    pe.duration_seconds,
    CASE
        WHEN pe.assets_processed > 0
        THEN ROUND(100.0 * pe.assets_succeeded / pe.assets_processed, 2)
        ELSE NULL
    END as success_rate_pct
FROM process_executions pe
WHERE pe.started_at > NOW() - INTERVAL '7 days'
ORDER BY pe.started_at DESC;

COMMENT ON VIEW v_recent_executions IS 'Recent DAG runs with success rates (last 7 days)';

-- View: Daily execution summary
CREATE VIEW v_daily_execution_summary AS
SELECT
    DATE(pe.started_at) as execution_date,
    pe.process_name,
    COUNT(*) as runs,
    SUM(pe.assets_processed) as total_assets,
    SUM(pe.assets_succeeded) as total_succeeded,
    SUM(pe.assets_failed) as total_failed,
    SUM(pe.api_calls_used) as total_api_calls,
    ROUND(AVG(pe.duration_seconds), 0) as avg_duration_sec
FROM process_executions pe
WHERE pe.started_at > CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(pe.started_at), pe.process_name
ORDER BY execution_date DESC, process_name;

COMMENT ON VIEW v_daily_execution_summary IS 'Daily aggregated execution statistics (last 30 days)';

-- View: Ticker processing status with asset details
CREATE VIEW v_ticker_processing_status AS
SELECT
    aps.ticker,
    aps.fundamentals_loaded,
    aps.prices_last_date,
    CURRENT_DATE - aps.prices_last_date as days_since_price_update,
    aps.indicators_calculated_at,
    CASE
        WHEN aps.indicators_calculated_at IS NULL THEN NULL
        ELSE CURRENT_DATE - DATE(aps.indicators_calculated_at)
    END as days_since_indicator_calc,
    aps.consecutive_failures,
    aps.last_error_message,
    a.name,
    a.exchange,
    a.asset_type,
    a.is_active
FROM asset_processing_state aps
LEFT JOIN assets a ON a.ticker = aps.ticker
ORDER BY aps.ticker;

COMMENT ON VIEW v_ticker_processing_status IS 'Complete ticker status with asset metadata';

-- View: Today's processing activity
CREATE VIEW v_today_processing_activity AS
SELECT
    apd.operation,
    apd.status,
    COUNT(*) as count,
    SUM(apd.api_calls_used) as total_api_calls,
    ROUND(AVG(apd.duration_ms), 0) as avg_duration_ms,
    MIN(apd.started_at) as first_operation,
    MAX(apd.completed_at) as last_operation
FROM asset_processing_details apd
WHERE DATE(apd.created_at) = CURRENT_DATE
GROUP BY apd.operation, apd.status
ORDER BY apd.operation, apd.status;

COMMENT ON VIEW v_today_processing_activity IS 'Real-time view of today''s processing activity';

-- =====================================================
-- FUNCTIONS: Helper functions for state management
-- =====================================================

-- Function: Reset ticker for reprocessing
CREATE OR REPLACE FUNCTION reset_ticker_for_reprocessing(
    p_ticker VARCHAR(20),
    p_component VARCHAR(50) DEFAULT 'all'  -- 'fundamentals', 'prices', 'indicators', 'all'
)
RETURNS VOID AS $$
BEGIN
    IF p_component = 'all' THEN
        UPDATE asset_processing_state
        SET needs_fundamentals_reprocess = TRUE,
            needs_prices_reprocess = TRUE,
            needs_indicators_reprocess = TRUE,
            consecutive_failures = 0,
            updated_at = NOW()
        WHERE ticker = p_ticker;
    ELSIF p_component = 'fundamentals' THEN
        UPDATE asset_processing_state
        SET needs_fundamentals_reprocess = TRUE,
            consecutive_failures = 0,
            updated_at = NOW()
        WHERE ticker = p_ticker;
    ELSIF p_component = 'prices' THEN
        UPDATE asset_processing_state
        SET needs_prices_reprocess = TRUE,
            consecutive_failures = 0,
            updated_at = NOW()
        WHERE ticker = p_ticker;
    ELSIF p_component = 'indicators' THEN
        UPDATE asset_processing_state
        SET needs_indicators_reprocess = TRUE,
            consecutive_failures = 0,
            updated_at = NOW()
        WHERE ticker = p_ticker;
    ELSE
        RAISE EXCEPTION 'Invalid component: %', p_component;
    END IF;

    RAISE NOTICE 'Ticker % marked for reprocessing: %', p_ticker, p_component;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION reset_ticker_for_reprocessing IS 'Mark a ticker for reprocessing (fundamentals, prices, indicators, or all)';

-- Function: Get processing progress summary
CREATE OR REPLACE FUNCTION get_processing_progress()
RETURNS TABLE(
    metric VARCHAR(50),
    value BIGINT,
    percentage NUMERIC(5,2)
) AS $$
DECLARE
    total_tickers BIGINT;
BEGIN
    SELECT COUNT(*) INTO total_tickers FROM asset_processing_state;

    RETURN QUERY
    SELECT
        'total_tickers'::VARCHAR(50),
        total_tickers,
        100.00::NUMERIC(5,2)
    UNION ALL
    SELECT
        'fundamentals_complete'::VARCHAR(50),
        COUNT(*),
        ROUND(100.0 * COUNT(*) / total_tickers, 2)::NUMERIC(5,2)
    FROM asset_processing_state WHERE fundamentals_loaded = TRUE
    UNION ALL
    SELECT
        'prices_up_to_date'::VARCHAR(50),
        COUNT(*),
        ROUND(100.0 * COUNT(*) / total_tickers, 2)::NUMERIC(5,2)
    FROM asset_processing_state WHERE prices_last_date >= CURRENT_DATE - 1
    UNION ALL
    SELECT
        'indicators_current'::VARCHAR(50),
        COUNT(*),
        ROUND(100.0 * COUNT(*) / total_tickers, 2)::NUMERIC(5,2)
    FROM asset_processing_state WHERE indicators_calculated_at >= CURRENT_DATE
    UNION ALL
    SELECT
        'failed_tickers'::VARCHAR(50),
        COUNT(*),
        ROUND(100.0 * COUNT(*) / total_tickers, 2)::NUMERIC(5,2)
    FROM asset_processing_state WHERE consecutive_failures >= 3;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_processing_progress IS 'Returns processing progress summary';

-- =====================================================
-- TRIGGERS: Automatically update timestamps
-- =====================================================

-- Trigger function for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add trigger to asset_processing_state
CREATE TRIGGER update_asset_processing_state_updated_at
BEFORE UPDATE ON asset_processing_state
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- SAMPLE QUERIES (for reference)
-- =====================================================

/*
-- Delta discovery: Assets needing bulk load
SELECT ticker FROM v_assets_needing_processing WHERE processing_need = 'bulk_load';

-- Delta discovery: Assets needing price update
SELECT ticker FROM v_assets_needing_processing WHERE processing_need = 'price_update';

-- Processing progress
SELECT * FROM get_processing_progress();

-- Today's activity
SELECT * FROM v_today_processing_activity;

-- Recent executions
SELECT * FROM v_recent_executions LIMIT 10;

-- Failed operations today
SELECT ticker, operation, error_message, started_at
FROM asset_processing_details
WHERE status = 'failed' AND DATE(created_at) = CURRENT_DATE
ORDER BY started_at DESC;

-- Mark ticker for reprocessing
SELECT reset_ticker_for_reprocessing('AAPL', 'all');
*/

-- =====================================================
-- INITIALIZATION
-- =====================================================

-- Insert all known tickers from config files (will be populated by DAG on first run)
-- This is a placeholder - actual population done by Airflow DAG
COMMENT ON TABLE asset_processing_state IS 'Populated by Airflow DAG on first run from config/tickers/*.txt files';

-- End of migration
