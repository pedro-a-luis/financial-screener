-- Migration: 007_smart_fundamental_refresh.sql
-- Purpose: Add smart fundamental data refresh tracking
-- Author: Financial Screener Team
-- Date: 2025-10-28
-- Dependencies: 005_process_metadata_tables.sql
--
-- Background:
-- Fundamental data (company info, financials, etc.) changes infrequently (quarterly/annually)
-- Fetching daily wastes 10 API calls per ticker (10 × 21,817 = 218,170 calls/day)
-- This migration adds configurable refresh frequencies to reduce API usage by 80-90%

SET search_path TO financial_screener, public;

-- =====================================================
-- ENUM: fundamental_refresh_frequency
-- Defines how often to refresh fundamental data
-- =====================================================

CREATE TYPE fundamental_refresh_frequency AS ENUM (
    'daily',      -- Refresh every day (not recommended - API intensive)
    'weekly',     -- Refresh once per week (recommended for most stocks)
    'monthly',    -- Refresh once per month (for stable large caps)
    'quarterly',  -- Refresh once per quarter (aligned with earnings)
    'never'       -- Manual refresh only (for inactive/delisted stocks)
);

COMMENT ON TYPE fundamental_refresh_frequency IS 'Frequency for fundamental data refresh';

-- =====================================================
-- ALTER TABLE: asset_processing_state
-- Add fundamental refresh tracking columns
-- =====================================================

-- Add fundamental refresh columns
ALTER TABLE asset_processing_state
ADD COLUMN last_fundamental_update TIMESTAMP,
ADD COLUMN fundamental_refresh_frequency fundamental_refresh_frequency DEFAULT 'weekly',
ADD COLUMN next_fundamental_refresh DATE;

-- Add indexes for efficient delta discovery
CREATE INDEX idx_asset_state_fundamental_refresh
    ON asset_processing_state(next_fundamental_refresh)
    WHERE next_fundamental_refresh IS NOT NULL
      AND next_fundamental_refresh <= CURRENT_DATE;

CREATE INDEX idx_asset_state_refresh_frequency
    ON asset_processing_state(fundamental_refresh_frequency, next_fundamental_refresh);

-- Comments
COMMENT ON COLUMN asset_processing_state.last_fundamental_update IS 'Timestamp of last successful fundamental data update';
COMMENT ON COLUMN asset_processing_state.fundamental_refresh_frequency IS 'How often to refresh fundamental data (daily/weekly/monthly/quarterly/never)';
COMMENT ON COLUMN asset_processing_state.next_fundamental_refresh IS 'Date when fundamental data should be refreshed next';

-- =====================================================
-- ALTER TABLE: assets
-- Add market cap and liquidity flags for smart refresh
-- =====================================================

-- Add columns to help determine optimal refresh frequency
ALTER TABLE assets
ADD COLUMN market_cap_category VARCHAR(20),
ADD COLUMN is_high_volume BOOLEAN DEFAULT FALSE,
ADD COLUMN optimal_refresh_frequency fundamental_refresh_frequency;

-- Index for categorization
CREATE INDEX idx_assets_market_cap_category ON assets(market_cap_category)
    WHERE market_cap_category IS NOT NULL;

-- Comments
COMMENT ON COLUMN assets.market_cap_category IS 'Mega/Large/Mid/Small/Micro - helps determine refresh frequency';
COMMENT ON COLUMN assets.is_high_volume BOOLEAN IS 'High trading volume stocks may need more frequent fundamental updates';
COMMENT ON COLUMN assets.optimal_refresh_frequency IS 'Recommended refresh frequency based on market cap and volume';

-- =====================================================
-- VIEWS: Fundamental refresh delta discovery
-- =====================================================

-- View: Assets needing fundamental refresh (based on schedule)
CREATE OR REPLACE VIEW v_assets_needing_fundamental_refresh AS
SELECT
    aps.ticker,
    aps.last_fundamental_update,
    aps.fundamental_refresh_frequency,
    aps.next_fundamental_refresh,
    CASE
        WHEN aps.next_fundamental_refresh IS NULL THEN 'never_loaded'
        WHEN aps.next_fundamental_refresh <= CURRENT_DATE THEN 'refresh_due'
        ELSE 'up_to_date'
    END as refresh_status,
    CURRENT_DATE - DATE(aps.last_fundamental_update) as days_since_update,
    aps.next_fundamental_refresh - CURRENT_DATE as days_until_refresh,
    a.exchange,
    a.asset_type,
    a.market_cap_category,
    a.is_active
FROM asset_processing_state aps
LEFT JOIN assets a ON a.ticker = aps.ticker
WHERE
    -- Never loaded OR due for refresh
    (aps.next_fundamental_refresh IS NULL OR aps.next_fundamental_refresh <= CURRENT_DATE)
    AND aps.fundamental_refresh_frequency != 'never'
    AND aps.consecutive_failures < 5
    AND a.is_active = TRUE
ORDER BY
    CASE
        WHEN aps.next_fundamental_refresh IS NULL THEN 1  -- Never loaded first
        ELSE 2
    END,
    aps.next_fundamental_refresh ASC NULLS FIRST,
    aps.ticker;

COMMENT ON VIEW v_assets_needing_fundamental_refresh IS 'Assets due for fundamental data refresh based on their schedule';

-- View: Fundamental refresh summary statistics
CREATE OR REPLACE VIEW v_fundamental_refresh_summary AS
SELECT
    fundamental_refresh_frequency,
    COUNT(*) as ticker_count,
    COUNT(*) FILTER (WHERE next_fundamental_refresh <= CURRENT_DATE) as due_for_refresh,
    COUNT(*) FILTER (WHERE next_fundamental_refresh > CURRENT_DATE) as up_to_date,
    COUNT(*) FILTER (WHERE next_fundamental_refresh IS NULL) as never_loaded,
    MIN(last_fundamental_update) as oldest_update,
    MAX(last_fundamental_update) as newest_update
FROM asset_processing_state
GROUP BY fundamental_refresh_frequency
ORDER BY fundamental_refresh_frequency;

COMMENT ON VIEW v_fundamental_refresh_summary IS 'Summary of fundamental refresh status by frequency';

-- View: Updated processing needs (replaces v_assets_needing_processing)
CREATE OR REPLACE VIEW v_assets_needing_processing AS
SELECT
    aps.ticker,
    CASE
        -- Check if fundamentals need refresh (based on schedule)
        WHEN (aps.next_fundamental_refresh IS NULL OR aps.next_fundamental_refresh <= CURRENT_DATE)
             AND aps.fundamental_refresh_frequency != 'never'
            THEN 'bulk_load'  -- Includes both fundamentals + prices
        WHEN aps.prices_last_date IS NULL OR aps.prices_last_date < CURRENT_DATE - 1 OR aps.needs_prices_reprocess = TRUE
            THEN 'price_update'  -- Prices only
        WHEN aps.indicators_calculated = FALSE
             OR aps.indicators_calculated_at IS NULL
             OR aps.indicators_calculated_at < CURRENT_DATE
             OR aps.needs_indicators_reprocess = TRUE
            THEN 'indicator_calc'
        ELSE 'up_to_date'
    END as processing_need,
    aps.prices_last_date,
    aps.last_fundamental_update,
    aps.next_fundamental_refresh,
    aps.fundamental_refresh_frequency,
    aps.indicators_calculated_at,
    aps.consecutive_failures,
    aps.last_error_message
FROM asset_processing_state aps
LEFT JOIN assets a ON a.ticker = aps.ticker
WHERE aps.consecutive_failures < 5  -- Skip permanently broken tickers
  AND (a.is_active = TRUE OR a.is_active IS NULL)
ORDER BY
    CASE
        WHEN aps.next_fundamental_refresh IS NULL OR aps.next_fundamental_refresh <= CURRENT_DATE THEN 1
        WHEN aps.prices_last_date IS NULL OR aps.prices_last_date < CURRENT_DATE - 1 THEN 2
        WHEN aps.indicators_calculated = FALSE OR aps.indicators_calculated_at IS NULL THEN 3
        ELSE 4
    END,
    aps.ticker;

COMMENT ON VIEW v_assets_needing_processing IS 'Delta discovery view with smart fundamental refresh (replaces old version)';

-- =====================================================
-- FUNCTIONS: Fundamental refresh management
-- =====================================================

-- Function: Calculate next refresh date based on frequency
CREATE OR REPLACE FUNCTION calculate_next_refresh_date(
    p_frequency fundamental_refresh_frequency,
    p_from_date DATE DEFAULT CURRENT_DATE
)
RETURNS DATE AS $$
BEGIN
    RETURN CASE p_frequency
        WHEN 'daily' THEN p_from_date + INTERVAL '1 day'
        WHEN 'weekly' THEN p_from_date + INTERVAL '7 days'
        WHEN 'monthly' THEN p_from_date + INTERVAL '1 month'
        WHEN 'quarterly' THEN p_from_date + INTERVAL '3 months'
        WHEN 'never' THEN NULL  -- Manual refresh only
    END::DATE;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION calculate_next_refresh_date IS 'Calculate next refresh date based on frequency setting';

-- Function: Set fundamental refresh frequency for ticker
CREATE OR REPLACE FUNCTION set_fundamental_refresh_frequency(
    p_ticker VARCHAR(20),
    p_frequency fundamental_refresh_frequency,
    p_recalculate_next_refresh BOOLEAN DEFAULT TRUE
)
RETURNS VOID AS $$
DECLARE
    v_next_refresh DATE;
BEGIN
    -- Calculate next refresh date if requested
    IF p_recalculate_next_refresh THEN
        v_next_refresh := calculate_next_refresh_date(p_frequency, CURRENT_DATE);
    ELSE
        v_next_refresh := NULL;
    END IF;

    -- Update ticker settings
    UPDATE asset_processing_state
    SET fundamental_refresh_frequency = p_frequency,
        next_fundamental_refresh = v_next_refresh,
        updated_at = NOW()
    WHERE ticker = p_ticker;

    RAISE NOTICE 'Ticker % refresh frequency set to % (next refresh: %)',
        p_ticker, p_frequency, v_next_refresh;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION set_fundamental_refresh_frequency IS 'Set fundamental refresh frequency for a specific ticker';

-- Function: Bulk set refresh frequency by market cap category
CREATE OR REPLACE FUNCTION set_refresh_frequency_by_category(
    p_market_cap_category VARCHAR(20),
    p_frequency fundamental_refresh_frequency
)
RETURNS INTEGER AS $$
DECLARE
    v_updated_count INTEGER;
BEGIN
    WITH updated AS (
        UPDATE asset_processing_state aps
        SET fundamental_refresh_frequency = p_frequency,
            next_fundamental_refresh = calculate_next_refresh_date(p_frequency, CURRENT_DATE),
            updated_at = NOW()
        FROM assets a
        WHERE a.ticker = aps.ticker
          AND a.market_cap_category = p_market_cap_category
        RETURNING aps.ticker
    )
    SELECT COUNT(*) INTO v_updated_count FROM updated;

    RAISE NOTICE 'Updated % tickers in category % to frequency %',
        v_updated_count, p_market_cap_category, p_frequency;

    RETURN v_updated_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION set_refresh_frequency_by_category IS 'Bulk set refresh frequency for all tickers in a market cap category';

-- Function: Update fundamental refresh after successful load
CREATE OR REPLACE FUNCTION update_fundamental_refresh_timestamp(
    p_ticker VARCHAR(20)
)
RETURNS VOID AS $$
DECLARE
    v_frequency fundamental_refresh_frequency;
    v_next_refresh DATE;
BEGIN
    -- Get current frequency setting
    SELECT fundamental_refresh_frequency INTO v_frequency
    FROM asset_processing_state
    WHERE ticker = p_ticker;

    -- Calculate next refresh date
    v_next_refresh := calculate_next_refresh_date(v_frequency, CURRENT_DATE);

    -- Update timestamp and next refresh date
    UPDATE asset_processing_state
    SET last_fundamental_update = NOW(),
        next_fundamental_refresh = v_next_refresh,
        fundamentals_loaded = TRUE,
        updated_at = NOW()
    WHERE ticker = p_ticker;

    RAISE DEBUG 'Fundamental refresh updated for % (frequency: %, next refresh: %)',
        p_ticker, v_frequency, v_next_refresh;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_fundamental_refresh_timestamp IS 'Update fundamental refresh timestamp after successful data load';

-- =====================================================
-- INITIAL DATA: Set default refresh frequencies
-- =====================================================

-- Initialize last_fundamental_update for existing tickers that have fundamentals loaded
UPDATE asset_processing_state
SET last_fundamental_update = fundamentals_loaded_at,
    next_fundamental_refresh = calculate_next_refresh_date('weekly', CURRENT_DATE)
WHERE fundamentals_loaded = TRUE
  AND last_fundamental_update IS NULL;

-- Set default frequency to 'weekly' for all tickers
UPDATE asset_processing_state
SET fundamental_refresh_frequency = 'weekly',
    next_fundamental_refresh = calculate_next_refresh_date('weekly', CURRENT_DATE)
WHERE fundamental_refresh_frequency IS NULL;

-- =====================================================
-- RECOMMENDED CONFIGURATIONS
-- =====================================================

/*
Recommended refresh frequencies by market cap:

1. MEGA CAP (> $200B) - Monthly or Quarterly
   - Stable companies, fundamentals rarely change
   - Example: AAPL, MSFT, GOOGL
   - API savings: 90-95%

2. LARGE CAP ($10B - $200B) - Monthly
   - Well-established companies
   - Example: Most S&P 500 stocks
   - API savings: 85%

3. MID CAP ($2B - $10B) - Weekly
   - More dynamic, but still relatively stable
   - API savings: 75%

4. SMALL CAP ($300M - $2B) - Weekly
   - More volatile, may need more frequent updates
   - API savings: 75%

5. MICRO CAP (< $300M) - Weekly or Daily
   - High volatility, frequent changes
   - Consider daily for actively traded microcaps

Example configuration commands:

-- Set mega caps to quarterly refresh
SELECT set_refresh_frequency_by_category('Mega', 'quarterly');

-- Set large caps to monthly refresh
SELECT set_refresh_frequency_by_category('Large', 'monthly');

-- Set mid/small caps to weekly refresh
SELECT set_refresh_frequency_by_category('Mid', 'weekly');
SELECT set_refresh_frequency_by_category('Small', 'weekly');

-- Individual override for high-volatility ticker
SELECT set_fundamental_refresh_frequency('TSLA.US', 'weekly');
*/

-- =====================================================
-- API CALL SAVINGS CALCULATION
-- =====================================================

/*
BEFORE (Daily fundamental refresh):
- 21,817 tickers × 11 calls (10 fundamentals + 1 price) = 239,987 calls/day
- EXCEEDS 100,000 daily limit by 139,987 calls

AFTER (Smart refresh with weekly average):
- 21,817 tickers × 1 call (price only) = 21,817 calls/day
- ~3,117 tickers/week × 11 calls (fundamentals + price) = 34,287 calls/week = ~4,898 calls/day
- Total: 21,817 + 4,898 = 26,715 calls/day
- SAVINGS: 88.9% reduction in API calls
- WELL UNDER 100,000 daily limit

QUARTERLY REFRESH (for mega/large caps):
- 21,817 tickers × 1 call = 21,817 calls/day
- ~1,039 tickers/week × 11 calls = 11,429 calls/week = ~1,633 calls/day
- Total: 21,817 + 1,633 = 23,450 calls/day
- SAVINGS: 90.2% reduction in API calls
*/

-- =====================================================
-- MONITORING QUERIES
-- =====================================================

/*
-- Check refresh summary
SELECT * FROM v_fundamental_refresh_summary;

-- Find tickers due for refresh today
SELECT * FROM v_assets_needing_fundamental_refresh
WHERE refresh_status = 'refresh_due'
LIMIT 100;

-- Count tickers by refresh status
SELECT
    fundamental_refresh_frequency,
    COUNT(*) FILTER (WHERE next_fundamental_refresh IS NULL) as never_loaded,
    COUNT(*) FILTER (WHERE next_fundamental_refresh <= CURRENT_DATE) as due_now,
    COUNT(*) FILTER (WHERE next_fundamental_refresh > CURRENT_DATE) as scheduled_future
FROM asset_processing_state
GROUP BY fundamental_refresh_frequency;

-- Estimate today's API call requirement
WITH refresh_counts AS (
    SELECT
        COUNT(*) FILTER (WHERE next_fundamental_refresh IS NULL OR next_fundamental_refresh <= CURRENT_DATE) as fundamentals_due,
        COUNT(*) FILTER (WHERE prices_last_date IS NULL OR prices_last_date < CURRENT_DATE - 1) as prices_due
    FROM asset_processing_state
)
SELECT
    fundamentals_due,
    prices_due,
    (fundamentals_due * 11) as fundamental_calls,
    (prices_due * 1) as price_calls,
    (fundamentals_due * 11) + (prices_due * 1) as total_calls,
    CASE
        WHEN (fundamentals_due * 11) + (prices_due * 1) <= 100000 THEN '✓ Under quota'
        ELSE '✗ Exceeds quota'
    END as quota_status
FROM refresh_counts;
*/

-- End of migration
