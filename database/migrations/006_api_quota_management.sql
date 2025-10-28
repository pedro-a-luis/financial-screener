-- Migration: 006_api_quota_management.sql
-- Purpose: API usage tracking and quota management for EODHD API
-- Author: Financial Screener Team
-- Date: 2025-10-28
-- Dependencies: 005_process_metadata_tables.sql

SET search_path TO financial_screener, public;

-- =====================================================
-- TABLE: api_usage_log
-- Tracks all API calls with costs and daily aggregation
-- =====================================================

CREATE TABLE api_usage_log (
    id BIGSERIAL PRIMARY KEY,

    -- API call identification
    execution_id VARCHAR(255),                   -- Links to process_executions.execution_id (soft FK)
    ticker VARCHAR(20),                          -- Ticker processed (NULL for bulk exchange queries)
    api_endpoint VARCHAR(100) NOT NULL,          -- 'fundamentals', 'eod_prices', 'bulk_exchange'

    -- API costs (based on EODHD pricing)
    api_calls_count INTEGER NOT NULL DEFAULT 1,  -- Number of API calls consumed

    -- Request details
    request_url TEXT,                            -- Full URL called (for debugging)
    http_status_code INTEGER,                    -- 200, 402 (quota exceeded), 404, 500, etc.

    -- Response metadata
    response_time_ms INTEGER,                    -- API response time in milliseconds
    response_size_bytes INTEGER,                 -- Response payload size

    -- Error tracking
    error_code VARCHAR(50),                      -- 'quota_exceeded', 'not_found', 'network_error'
    error_message TEXT,

    -- Timing
    called_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_api_usage_date ON api_usage_log(DATE(called_at), api_endpoint);
CREATE INDEX idx_api_usage_execution ON api_usage_log(execution_id) WHERE execution_id IS NOT NULL;
CREATE INDEX idx_api_usage_ticker ON api_usage_log(ticker) WHERE ticker IS NOT NULL;
CREATE INDEX idx_api_usage_errors ON api_usage_log(http_status_code, called_at DESC)
    WHERE http_status_code >= 400;

-- Partitioning for performance (optional - future enhancement)
-- This table will grow large (~10M rows/month), consider partitioning by month
COMMENT ON TABLE api_usage_log IS 'Granular log of every API call made to EODHD (with actual costs)';
COMMENT ON COLUMN api_usage_log.api_calls_count IS 'EODHD pricing: fundamentals=10, eod_prices=1, bulk_exchange=100';
COMMENT ON COLUMN api_usage_log.api_endpoint IS 'fundamentals (10 calls), eod_prices (1 call), bulk_exchange (100 calls)';

-- =====================================================
-- TABLE: api_daily_quota
-- Daily quota tracking and limits
-- =====================================================

CREATE TABLE api_daily_quota (
    id BIGSERIAL PRIMARY KEY,

    -- Date tracking
    quota_date DATE NOT NULL UNIQUE,

    -- Quota limits (configurable)
    daily_limit INTEGER NOT NULL DEFAULT 100000,  -- EODHD All-World $79.99/month = 100K calls/day

    -- Usage counters (updated in real-time)
    calls_used INTEGER NOT NULL DEFAULT 0,
    calls_remaining INTEGER GENERATED ALWAYS AS (daily_limit - calls_used) STORED,

    -- Breakdown by endpoint type
    fundamentals_calls INTEGER NOT NULL DEFAULT 0,
    eod_prices_calls INTEGER NOT NULL DEFAULT 0,
    bulk_exchange_calls INTEGER NOT NULL DEFAULT 0,

    -- Status flags
    quota_exhausted BOOLEAN GENERATED ALWAYS AS (calls_used >= daily_limit) STORED,

    -- Projected usage (calculated by quota check logic)
    projected_total_calls INTEGER,               -- Expected calls if all jobs run
    projected_overage INTEGER,                   -- calls_used + projected - daily_limit

    -- Timing
    first_call_at TIMESTAMP,
    last_call_at TIMESTAMP,

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE UNIQUE INDEX idx_quota_date ON api_daily_quota(quota_date);
CREATE INDEX idx_quota_recent ON api_daily_quota(quota_date DESC) WHERE quota_date >= CURRENT_DATE - 7;

-- Comments
COMMENT ON TABLE api_daily_quota IS 'Daily quota tracking for EODHD API (100K calls/day limit)';
COMMENT ON COLUMN api_daily_quota.daily_limit IS 'Max calls per day (100,000 for All-World plan)';
COMMENT ON COLUMN api_daily_quota.calls_remaining IS 'Auto-calculated: daily_limit - calls_used';
COMMENT ON COLUMN api_daily_quota.projected_total_calls IS 'Expected calls if all pending jobs execute';

-- =====================================================
-- TABLE: api_ticker_priority
-- Priority system for ticker processing when quota is limited
-- =====================================================

CREATE TABLE api_ticker_priority (
    id BIGSERIAL PRIMARY KEY,

    ticker VARCHAR(20) NOT NULL UNIQUE,

    -- Priority levels (1 = highest, 5 = lowest)
    priority_level INTEGER NOT NULL DEFAULT 3 CHECK (priority_level BETWEEN 1 AND 5),

    -- Priority rules
    priority_reason VARCHAR(100),                -- 'sp500_large_cap', 'high_volume', 'user_watchlist'

    -- Processing preferences
    always_process BOOLEAN DEFAULT FALSE,        -- Force processing even when quota tight
    skip_when_limited BOOLEAN DEFAULT FALSE,     -- Skip if quota < 20% remaining

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE UNIQUE INDEX idx_priority_ticker ON api_ticker_priority(ticker);
CREATE INDEX idx_priority_level ON api_ticker_priority(priority_level, ticker) WHERE always_process = TRUE;

-- Comments
COMMENT ON TABLE api_ticker_priority IS 'Priority system for ticker processing when API quota is limited';
COMMENT ON COLUMN api_ticker_priority.priority_level IS '1=Critical (S&P500 large cap), 2=High, 3=Normal, 4=Low, 5=Skip';
COMMENT ON COLUMN api_ticker_priority.always_process IS 'Process even when quota tight (for critical tickers)';

-- =====================================================
-- VIEWS: API usage monitoring and quota checking
-- =====================================================

-- View: Today's API usage summary
CREATE VIEW v_api_usage_today AS
SELECT
    api_endpoint,
    COUNT(*) as total_requests,
    SUM(api_calls_count) as total_api_calls,
    COUNT(*) FILTER (WHERE http_status_code = 200) as successful_requests,
    COUNT(*) FILTER (WHERE http_status_code >= 400) as failed_requests,
    ROUND(AVG(response_time_ms), 0) as avg_response_ms,
    MIN(called_at) as first_call,
    MAX(called_at) as last_call
FROM api_usage_log
WHERE DATE(called_at) = CURRENT_DATE
GROUP BY api_endpoint
ORDER BY total_api_calls DESC;

COMMENT ON VIEW v_api_usage_today IS 'Today''s API usage breakdown by endpoint';

-- View: Quota status (real-time)
CREATE VIEW v_quota_status AS
SELECT
    q.quota_date,
    q.daily_limit,
    q.calls_used,
    q.calls_remaining,
    ROUND(100.0 * q.calls_used / q.daily_limit, 2) as usage_percentage,
    q.fundamentals_calls,
    q.eod_prices_calls,
    q.bulk_exchange_calls,
    q.quota_exhausted,
    q.projected_total_calls,
    q.projected_overage,
    CASE
        WHEN q.calls_remaining >= 50000 THEN 'healthy'
        WHEN q.calls_remaining >= 20000 THEN 'warning'
        WHEN q.calls_remaining >= 5000 THEN 'critical'
        ELSE 'exhausted'
    END as quota_health,
    q.first_call_at,
    q.last_call_at
FROM api_daily_quota q
WHERE q.quota_date >= CURRENT_DATE - 1
ORDER BY q.quota_date DESC;

COMMENT ON VIEW v_quota_status IS 'Real-time quota status with health indicators';

-- View: Last 7 days quota usage
CREATE VIEW v_quota_weekly_trend AS
SELECT
    q.quota_date,
    q.calls_used,
    ROUND(100.0 * q.calls_used / q.daily_limit, 2) as usage_pct,
    q.fundamentals_calls,
    q.eod_prices_calls,
    ROUND(100.0 * q.fundamentals_calls / NULLIF(q.calls_used, 0), 2) as fundamentals_pct,
    ROUND(100.0 * q.eod_prices_calls / NULLIF(q.calls_used, 0), 2) as prices_pct
FROM api_daily_quota q
WHERE q.quota_date >= CURRENT_DATE - 7
ORDER BY q.quota_date DESC;

COMMENT ON VIEW v_quota_weekly_trend IS 'Last 7 days quota usage trend';

-- View: API errors summary
CREATE VIEW v_api_errors_today AS
SELECT
    api_endpoint,
    http_status_code,
    error_code,
    COUNT(*) as error_count,
    MAX(called_at) as last_occurrence,
    ARRAY_AGG(DISTINCT ticker) FILTER (WHERE ticker IS NOT NULL) as affected_tickers
FROM api_usage_log
WHERE DATE(called_at) = CURRENT_DATE
  AND http_status_code >= 400
GROUP BY api_endpoint, http_status_code, error_code
ORDER BY error_count DESC;

COMMENT ON VIEW v_api_errors_today IS 'Today''s API errors grouped by type';

-- =====================================================
-- FUNCTIONS: API quota management
-- =====================================================

-- Function: Log API call
CREATE OR REPLACE FUNCTION log_api_call(
    p_execution_id VARCHAR(255),
    p_ticker VARCHAR(20),
    p_api_endpoint VARCHAR(100),
    p_api_calls_count INTEGER,
    p_http_status_code INTEGER DEFAULT 200,
    p_response_time_ms INTEGER DEFAULT NULL,
    p_error_code VARCHAR(50) DEFAULT NULL,
    p_error_message TEXT DEFAULT NULL
)
RETURNS VOID AS $$
DECLARE
    v_quota_date DATE := CURRENT_DATE;
BEGIN
    -- Insert into api_usage_log
    INSERT INTO api_usage_log (
        execution_id,
        ticker,
        api_endpoint,
        api_calls_count,
        http_status_code,
        response_time_ms,
        error_code,
        error_message
    ) VALUES (
        p_execution_id,
        p_ticker,
        p_api_endpoint,
        p_api_calls_count,
        p_http_status_code,
        p_response_time_ms,
        p_error_code,
        p_error_message
    );

    -- Update daily quota (create if not exists)
    INSERT INTO api_daily_quota (quota_date, calls_used, first_call_at, last_call_at)
    VALUES (v_quota_date, p_api_calls_count, NOW(), NOW())
    ON CONFLICT (quota_date) DO UPDATE SET
        calls_used = api_daily_quota.calls_used + p_api_calls_count,
        fundamentals_calls = api_daily_quota.fundamentals_calls +
            CASE WHEN p_api_endpoint = 'fundamentals' THEN p_api_calls_count ELSE 0 END,
        eod_prices_calls = api_daily_quota.eod_prices_calls +
            CASE WHEN p_api_endpoint = 'eod_prices' THEN p_api_calls_count ELSE 0 END,
        bulk_exchange_calls = api_daily_quota.bulk_exchange_calls +
            CASE WHEN p_api_endpoint = 'bulk_exchange' THEN p_api_calls_count ELSE 0 END,
        last_call_at = NOW(),
        updated_at = NOW();

END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION log_api_call IS 'Log API call and update daily quota counters automatically';

-- Function: Check quota availability
CREATE OR REPLACE FUNCTION check_quota_available(
    p_required_calls INTEGER,
    p_buffer_percentage NUMERIC DEFAULT 10.0  -- Keep 10% buffer
)
RETURNS TABLE(
    available BOOLEAN,
    calls_remaining INTEGER,
    calls_after_buffer INTEGER,
    can_proceed BOOLEAN,
    recommendation TEXT
) AS $$
DECLARE
    v_quota_date DATE := CURRENT_DATE;
    v_quota_record RECORD;
    v_buffer_calls INTEGER;
BEGIN
    -- Get or create today's quota record
    INSERT INTO api_daily_quota (quota_date)
    VALUES (v_quota_date)
    ON CONFLICT (quota_date) DO NOTHING;

    -- Get current quota status
    SELECT * INTO v_quota_record
    FROM api_daily_quota
    WHERE quota_date = v_quota_date;

    -- Calculate buffer
    v_buffer_calls := FLOOR(v_quota_record.daily_limit * p_buffer_percentage / 100.0);

    RETURN QUERY
    SELECT
        v_quota_record.calls_remaining > 0 as available,
        v_quota_record.calls_remaining as calls_remaining,
        v_quota_record.calls_remaining - v_buffer_calls as calls_after_buffer,
        (v_quota_record.calls_remaining - v_buffer_calls) >= p_required_calls as can_proceed,
        CASE
            WHEN v_quota_record.quota_exhausted THEN
                'STOP: Daily quota exhausted'
            WHEN (v_quota_record.calls_remaining - v_buffer_calls) >= p_required_calls THEN
                'PROCEED: Sufficient quota available'
            WHEN v_quota_record.calls_remaining >= p_required_calls THEN
                'CAUTION: Quota tight but available (within buffer)'
            ELSE
                'REDUCE: Insufficient quota - reduce batch size to ' ||
                (v_quota_record.calls_remaining - v_buffer_calls)::TEXT || ' calls'
        END as recommendation;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION check_quota_available IS 'Check if sufficient API quota available for planned operations';

-- Function: Calculate required API calls for processing
CREATE OR REPLACE FUNCTION calculate_required_api_calls(
    p_tickers_needing_bulk INTEGER,
    p_tickers_needing_prices INTEGER
)
RETURNS TABLE(
    bulk_load_calls INTEGER,
    price_update_calls INTEGER,
    total_calls INTEGER,
    cost_breakdown JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        p_tickers_needing_bulk * 11 as bulk_load_calls,      -- 10 fundamentals + 1 prices
        p_tickers_needing_prices * 1 as price_update_calls,  -- 1 price call
        (p_tickers_needing_bulk * 11) + (p_tickers_needing_prices * 1) as total_calls,
        jsonb_build_object(
            'bulk_load', jsonb_build_object(
                'tickers', p_tickers_needing_bulk,
                'calls_per_ticker', 11,
                'total_calls', p_tickers_needing_bulk * 11
            ),
            'price_update', jsonb_build_object(
                'tickers', p_tickers_needing_prices,
                'calls_per_ticker', 1,
                'total_calls', p_tickers_needing_prices * 1
            )
        ) as cost_breakdown;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_required_api_calls IS 'Calculate total API calls needed based on processing requirements';

-- Function: Get priority tickers
CREATE OR REPLACE FUNCTION get_priority_tickers(
    p_max_tickers INTEGER DEFAULT 1000,
    p_min_priority INTEGER DEFAULT 1
)
RETURNS TABLE(ticker VARCHAR(20), priority_level INTEGER) AS $$
BEGIN
    RETURN QUERY
    SELECT
        apt.ticker,
        apt.priority_level
    FROM api_ticker_priority apt
    WHERE apt.priority_level >= p_min_priority
    ORDER BY apt.priority_level ASC, apt.ticker
    LIMIT p_max_tickers;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_priority_tickers IS 'Get tickers to process based on priority (when quota limited)';

-- =====================================================
-- TRIGGERS: Automatic timestamp updates
-- =====================================================

-- Trigger for api_daily_quota.updated_at
CREATE TRIGGER update_api_quota_updated_at
BEFORE UPDATE ON api_daily_quota
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Trigger for api_ticker_priority.updated_at
CREATE TRIGGER update_api_priority_updated_at
BEFORE UPDATE ON api_ticker_priority
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- INITIAL DATA: Priority tickers (S&P 500 large caps)
-- =====================================================

-- Insert S&P 500 mega-cap stocks (market cap > $500B) as priority 1
-- This is a starter set - expand based on actual requirements
INSERT INTO api_ticker_priority (ticker, priority_level, priority_reason, always_process)
VALUES
    ('AAPL.US', 1, 'sp500_mega_cap', TRUE),
    ('MSFT.US', 1, 'sp500_mega_cap', TRUE),
    ('GOOGL.US', 1, 'sp500_mega_cap', TRUE),
    ('AMZN.US', 1, 'sp500_mega_cap', TRUE),
    ('NVDA.US', 1, 'sp500_mega_cap', TRUE),
    ('META.US', 1, 'sp500_mega_cap', TRUE),
    ('TSLA.US', 1, 'sp500_mega_cap', TRUE),
    ('BRK.B.US', 1, 'sp500_mega_cap', TRUE),
    ('V.US', 1, 'sp500_mega_cap', TRUE),
    ('JPM.US', 1, 'sp500_mega_cap', TRUE)
ON CONFLICT (ticker) DO NOTHING;

-- Initialize today's quota record
INSERT INTO api_daily_quota (quota_date)
VALUES (CURRENT_DATE)
ON CONFLICT (quota_date) DO NOTHING;

-- =====================================================
-- SAMPLE QUERIES (for reference)
-- =====================================================

/*
-- Check current quota status
SELECT * FROM v_quota_status WHERE quota_date = CURRENT_DATE;

-- Check if we can process 5000 tickers (bulk load)
SELECT * FROM check_quota_available(5000 * 11);

-- Calculate required calls for processing
SELECT * FROM calculate_required_api_calls(
    5000,  -- tickers needing bulk load
    15000  -- tickers needing price update
);

-- Today's API usage
SELECT * FROM v_api_usage_today;

-- Last 7 days trend
SELECT * FROM v_quota_weekly_trend;

-- API errors
SELECT * FROM v_api_errors_today;

-- Log an API call (called from Python code)
SELECT log_api_call(
    'manual_test_2025-10-28',  -- execution_id
    'AAPL.US',                  -- ticker
    'fundamentals',             -- api_endpoint
    10,                         -- api_calls_count
    200,                        -- http_status_code
    450,                        -- response_time_ms
    NULL,                       -- error_code
    NULL                        -- error_message
);

-- Get priority tickers (top 100)
SELECT * FROM get_priority_tickers(100, 1);

-- Update daily limit if plan changes
UPDATE api_daily_quota
SET daily_limit = 100000
WHERE quota_date = CURRENT_DATE;
*/

-- =====================================================
-- MAINTENANCE NOTES
-- =====================================================

/*
MAINTENANCE TASKS:

1. Daily quota reset:
   - Automatic via quota_date partition
   - Old records kept for historical analysis

2. Log cleanup (monthly):
   DELETE FROM api_usage_log
   WHERE called_at < CURRENT_DATE - INTERVAL '90 days';

3. Priority list maintenance:
   - Update api_ticker_priority based on:
     * Market cap changes
     * Trading volume
     * User watchlists
     * Sector representation

4. Monitoring:
   - Set up alerts when quota_health = 'critical'
   - Daily reports from v_quota_weekly_trend
   - Error rate monitoring from v_api_errors_today

5. Optimization:
   - Consider partitioning api_usage_log by month if > 10M rows
   - Archive old quota records (keep 90 days active)
*/

-- End of migration
