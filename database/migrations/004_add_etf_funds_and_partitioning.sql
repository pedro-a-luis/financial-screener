-- Migration 004: Add ETF/Funds Support and Table Partitioning
-- PostgreSQL 16+
-- Schema: financial_screener
--
-- Changes:
-- 1. Update assets table to support stocks, ETFs, and funds (unified table)
-- 2. Add asset_category column to differentiate asset types
-- 3. Add unified columns (no prefixes) that work for all asset types
-- 4. Add partitioning to stock_prices table (by year)
-- 5. Add partitioning to technical_indicators table (by year)
-- 6. Drop deprecated stock_fundamentals table

SET search_path TO financial_screener, public;

-- =====================================================
-- 1. UPDATE ASSET_TYPE ENUM TO INCLUDE ETF AND FUND
-- =====================================================

-- Add new asset types to existing enum
ALTER TYPE financial_screener.asset_type_enum ADD VALUE IF NOT EXISTS 'etf';
ALTER TYPE financial_screener.asset_type_enum ADD VALUE IF NOT EXISTS 'fund';

COMMENT ON TYPE financial_screener.asset_type_enum IS 'Asset types: stock, etf, fund, bond';

-- =====================================================
-- 2. ADD ASSET_CATEGORY COLUMN (DIFFERENTIATES ASSET TYPES)
-- =====================================================

-- This column distinguishes between stock/etf/fund more granularly
-- Examples: 'common_stock', 'preferred_stock', 'equity_etf', 'bond_etf',
--           'equity_fund', 'balanced_fund', 'money_market_fund'
ALTER TABLE assets ADD COLUMN IF NOT EXISTS asset_category VARCHAR(50);

CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(asset_category);

COMMENT ON COLUMN assets.asset_category IS 'Granular asset category: common_stock, equity_etf, bond_etf, equity_fund, balanced_fund, etc.';

-- =====================================================
-- 3. ADD UNIFIED COLUMNS (NO PREFIXES - WORK FOR ALL ASSETS)
-- =====================================================

-- Company/Issuer (for ETFs and Funds)
-- Stocks: NULL
-- ETFs: BlackRock, Vanguard, State Street, etc.
-- Funds: Vanguard, Fidelity, T. Rowe Price, etc.
ALTER TABLE assets ADD COLUMN IF NOT EXISTS company VARCHAR(255);

-- Category (for ETFs and Funds)
-- Stocks: NULL (use sector/industry instead)
-- ETFs: Large Cap Equity, Government Bonds, Gold, etc.
-- Funds: Large Growth, Mid Value, Balanced, etc.
ALTER TABLE assets ADD COLUMN IF NOT EXISTS category VARCHAR(100);

-- Investment Type/Style
-- Stocks: NULL
-- ETFs: Growth, Value, Blend, Government Bonds, etc.
-- Funds: Aggressive Growth, Conservative, Income, etc.
ALTER TABLE assets ADD COLUMN IF NOT EXISTS investment_type VARCHAR(100);

-- Net Assets (AUM) - for ETFs and Funds
ALTER TABLE assets ADD COLUMN IF NOT EXISTS net_assets BIGINT;

-- Expense Ratio - for ETFs and Funds
ALTER TABLE assets ADD COLUMN IF NOT EXISTS expense_ratio DECIMAL(6, 4);

-- Yield - for all assets (stocks: dividend yield, ETFs/Funds: current yield)
ALTER TABLE assets ADD COLUMN IF NOT EXISTS yield DECIMAL(10, 6);

-- Inception Date - for ETFs and Funds (stocks already have ipo_date)
ALTER TABLE assets ADD COLUMN IF NOT EXISTS inception_date DATE;

-- Fund-specific fields
ALTER TABLE assets ADD COLUMN IF NOT EXISTS minimum_investment DECIMAL(12, 2);
ALTER TABLE assets ADD COLUMN IF NOT EXISTS load_type VARCHAR(20);  -- no_load, front_load, back_load, level_load
ALTER TABLE assets ADD COLUMN IF NOT EXISTS front_load DECIMAL(6, 4);
ALTER TABLE assets ADD COLUMN IF NOT EXISTS back_load DECIMAL(6, 4);
ALTER TABLE assets ADD COLUMN IF NOT EXISTS turnover_ratio DECIMAL(10, 2);

-- Add indexes for new columns
CREATE INDEX IF NOT EXISTS idx_assets_company ON assets(company);
CREATE INDEX IF NOT EXISTS idx_assets_net_assets ON assets(net_assets DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_assets_expense_ratio ON assets(expense_ratio);

-- Add comments
COMMENT ON COLUMN assets.company IS 'Issuer/provider for ETFs (BlackRock, Vanguard) or fund family for Funds (Fidelity, T. Rowe Price). NULL for stocks.';
COMMENT ON COLUMN assets.category IS 'Category for ETFs/Funds (Large Cap Equity, Government Bonds, Balanced). NULL for stocks (use sector/industry instead).';
COMMENT ON COLUMN assets.net_assets IS 'Assets under management in USD (for ETFs and Funds). NULL for stocks.';
COMMENT ON COLUMN assets.expense_ratio IS 'Annual expense ratio for ETFs/Funds (e.g., 0.0003 = 0.03%). NULL for stocks.';
COMMENT ON COLUMN assets.yield IS 'Current yield: dividend yield for stocks, distribution yield for ETFs/Funds.';
COMMENT ON COLUMN assets.inception_date IS 'Launch date for ETFs/Funds. For stocks, use ipo_date instead.';
COMMENT ON COLUMN assets.minimum_investment IS 'Minimum initial investment (Funds only). NULL for stocks/ETFs.';
COMMENT ON COLUMN assets.load_type IS 'Load type for Funds: no_load, front_load, back_load, level_load. NULL for stocks/ETFs.';

-- =====================================================
-- 4. ADD ETF/FUND-SPECIFIC JSONB COLUMNS
-- =====================================================

-- ETF/Fund holdings composition
ALTER TABLE assets ADD COLUMN IF NOT EXISTS eodhd_holdings JSONB;

-- Asset allocation breakdown (stocks vs bonds vs cash)
ALTER TABLE assets ADD COLUMN IF NOT EXISTS eodhd_asset_allocation JSONB;

-- Geographic exposure (US, Europe, Asia, etc.)
ALTER TABLE assets ADD COLUMN IF NOT EXISTS eodhd_world_regions JSONB;

-- Sector weights (for equity ETFs/Funds)
ALTER TABLE assets ADD COLUMN IF NOT EXISTS eodhd_sector_weights JSONB;

-- Fixed income details (for bond ETFs/Funds)
ALTER TABLE assets ADD COLUMN IF NOT EXISTS eodhd_fixed_income JSONB;

-- Valuation and growth metrics
ALTER TABLE assets ADD COLUMN IF NOT EXISTS eodhd_valuations_growth JSONB;

-- MorningStar ratings and analysis
ALTER TABLE assets ADD COLUMN IF NOT EXISTS eodhd_morning_star JSONB;

-- Performance history
ALTER TABLE assets ADD COLUMN IF NOT EXISTS eodhd_performance JSONB;

COMMENT ON COLUMN assets.eodhd_holdings IS 'Top holdings for ETFs/Funds (ticker, name, weight). NULL for stocks.';
COMMENT ON COLUMN assets.eodhd_asset_allocation IS 'Asset allocation breakdown (stocks %, bonds %, cash %). NULL for stocks.';
COMMENT ON COLUMN assets.eodhd_world_regions IS 'Geographic exposure by region. NULL for stocks.';
COMMENT ON COLUMN assets.eodhd_sector_weights IS 'Sector allocation weights. NULL for stocks.';
COMMENT ON COLUMN assets.eodhd_fixed_income IS 'Bond ETF/Fund specific data (duration, maturity, credit quality). NULL for stocks/equity funds.';
COMMENT ON COLUMN assets.eodhd_morning_star IS 'MorningStar ratings and analysis. NULL for stocks.';

-- =====================================================
-- 5. PARTITION STOCK_PRICES TABLE BY YEAR
-- =====================================================

-- Rename existing table
ALTER TABLE IF EXISTS stock_prices RENAME TO stock_prices_old;

-- Create new partitioned table
CREATE TABLE stock_prices (
    id BIGSERIAL,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    open DECIMAL(12, 4) NOT NULL,
    high DECIMAL(12, 4) NOT NULL,
    low DECIMAL(12, 4) NOT NULL,
    close DECIMAL(12, 4) NOT NULL,
    volume BIGINT NOT NULL,
    adj_close DECIMAL(12, 4),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (date, asset_id)
) PARTITION BY RANGE (date);

COMMENT ON TABLE stock_prices IS 'Daily OHLCV price data for all assets (stocks, ETFs, funds) - partitioned by year';

-- Create partitions for 2020-2030 (10 years)
CREATE TABLE stock_prices_2020 PARTITION OF stock_prices FOR VALUES FROM ('2020-01-01') TO ('2021-01-01');
CREATE TABLE stock_prices_2021 PARTITION OF stock_prices FOR VALUES FROM ('2021-01-01') TO ('2022-01-01');
CREATE TABLE stock_prices_2022 PARTITION OF stock_prices FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');
CREATE TABLE stock_prices_2023 PARTITION OF stock_prices FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
CREATE TABLE stock_prices_2024 PARTITION OF stock_prices FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE stock_prices_2025 PARTITION OF stock_prices FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE stock_prices_2026 PARTITION OF stock_prices FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE stock_prices_2027 PARTITION OF stock_prices FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');
CREATE TABLE stock_prices_2028 PARTITION OF stock_prices FOR VALUES FROM ('2028-01-01') TO ('2029-01-01');
CREATE TABLE stock_prices_2029 PARTITION OF stock_prices FOR VALUES FROM ('2029-01-01') TO ('2030-01-01');
CREATE TABLE stock_prices_2030 PARTITION OF stock_prices FOR VALUES FROM ('2030-01-01') TO ('2031-01-01');

-- Create indexes on partitioned table
CREATE INDEX idx_prices_asset_date ON stock_prices(asset_id, date DESC);
CREATE INDEX idx_prices_date ON stock_prices(date DESC);
CREATE INDEX idx_prices_asset ON stock_prices(asset_id);

-- Copy data from old table if it exists
INSERT INTO stock_prices
SELECT * FROM stock_prices_old
ON CONFLICT (date, asset_id) DO NOTHING;

-- Drop old table
DROP TABLE IF EXISTS stock_prices_old CASCADE;

-- =====================================================
-- 6. PARTITION TECHNICAL_INDICATORS TABLE BY YEAR
-- =====================================================

-- Rename existing table
ALTER TABLE IF EXISTS technical_indicators RENAME TO technical_indicators_old;

-- Create new partitioned table
CREATE TABLE technical_indicators (
    id BIGSERIAL,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,
    calculation_date DATE NOT NULL,

    -- MOVING AVERAGES (5 fields)
    sma_50 DECIMAL(12, 4),
    sma_200 DECIMAL(12, 4),
    ema_12 DECIMAL(12, 4),
    ema_26 DECIMAL(12, 4),
    wma_20 DECIMAL(12, 4),

    -- MOMENTUM INDICATORS (5 fields)
    rsi_14 DECIMAL(10, 4),
    stoch_k DECIMAL(10, 4),
    stoch_d DECIMAL(10, 4),
    stoch_rsi DECIMAL(10, 4),
    cci_20 DECIMAL(12, 4),

    -- TREND INDICATORS (6 fields)
    macd DECIMAL(12, 6),
    macd_signal DECIMAL(12, 6),
    macd_histogram DECIMAL(12, 6),
    dmi_plus DECIMAL(10, 4),
    dmi_minus DECIMAL(10, 4),
    adx DECIMAL(10, 4),

    -- VOLATILITY INDICATORS (7 fields)
    atr_14 DECIMAL(12, 4),
    volatility DECIMAL(10, 4),
    std_dev DECIMAL(12, 6),
    bb_upper DECIMAL(12, 4),
    bb_middle DECIMAL(12, 4),
    bb_lower DECIMAL(12, 4),
    bb_bandwidth DECIMAL(10, 6),

    -- OTHER INDICATORS (3 fields)
    sar DECIMAL(12, 4),
    beta DECIMAL(10, 4),
    slope DECIMAL(12, 6),

    -- VOLUME & PRICE LEVELS (5 fields)
    avg_volume_30 BIGINT,
    avg_volume_90 BIGINT,
    week_52_high DECIMAL(12, 4),
    week_52_low DECIMAL(12, 4),
    current_price DECIMAL(12, 4),

    -- METADATA
    data_points_used INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (calculation_date, asset_id)
) PARTITION BY RANGE (calculation_date);

COMMENT ON TABLE technical_indicators IS 'Calculated technical indicators for all assets - partitioned by year';

-- Create partitions for 2020-2030
CREATE TABLE technical_indicators_2020 PARTITION OF technical_indicators FOR VALUES FROM ('2020-01-01') TO ('2021-01-01');
CREATE TABLE technical_indicators_2021 PARTITION OF technical_indicators FOR VALUES FROM ('2021-01-01') TO ('2022-01-01');
CREATE TABLE technical_indicators_2022 PARTITION OF technical_indicators FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');
CREATE TABLE technical_indicators_2023 PARTITION OF technical_indicators FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
CREATE TABLE technical_indicators_2024 PARTITION OF technical_indicators FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE technical_indicators_2025 PARTITION OF technical_indicators FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE technical_indicators_2026 PARTITION OF technical_indicators FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE technical_indicators_2027 PARTITION OF technical_indicators FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');
CREATE TABLE technical_indicators_2028 PARTITION OF technical_indicators FOR VALUES FROM ('2028-01-01') TO ('2029-01-01');
CREATE TABLE technical_indicators_2029 PARTITION OF technical_indicators FOR VALUES FROM ('2029-01-01') TO ('2030-01-01');
CREATE TABLE technical_indicators_2030 PARTITION OF technical_indicators FOR VALUES FROM ('2030-01-01') TO ('2031-01-01');

-- Create indexes on partitioned table
CREATE INDEX idx_tech_indicators_asset ON technical_indicators(asset_id);
CREATE INDEX idx_tech_indicators_date ON technical_indicators(calculation_date DESC);
CREATE INDEX idx_tech_indicators_ticker ON technical_indicators(ticker);

-- Copy data from old table if it exists
INSERT INTO technical_indicators
SELECT * FROM technical_indicators_old
ON CONFLICT (calculation_date, asset_id) DO NOTHING;

-- Drop old table
DROP TABLE IF EXISTS technical_indicators_old CASCADE;

-- =====================================================
-- 7. DROP DEPRECATED STOCK_FUNDAMENTALS TABLE
-- =====================================================

DROP TABLE IF EXISTS stock_fundamentals CASCADE;

COMMENT ON COLUMN assets.eodhd_financials IS 'Complete financial statements from EODHD API (Balance Sheet, Cash Flow, Income Statement) - replaces deprecated stock_fundamentals table. Only applicable to stocks.';

-- =====================================================
-- 8. CREATE USEFUL VIEWS FOR DIFFERENT ASSET TYPES
-- =====================================================

-- View for active stocks only
CREATE OR REPLACE VIEW active_stocks AS
SELECT
    id,
    ticker,
    name,
    exchange,
    sector,
    industry,
    market_cap,
    pe_ratio,
    dividend_yield,
    analyst_rating,
    beta,
    week_52_high,
    week_52_low
FROM assets
WHERE asset_type = 'stock'
  AND is_active = true
  AND is_delisted = false
ORDER BY market_cap DESC NULLS LAST;

COMMENT ON VIEW active_stocks IS 'Active stocks only (excludes ETFs and Funds)';

-- View for active ETFs only
CREATE OR REPLACE VIEW active_etfs AS
SELECT
    id,
    ticker,
    name,
    exchange,
    company,
    category,
    asset_category,
    net_assets,
    expense_ratio,
    yield,
    beta,
    week_52_high,
    week_52_low
FROM assets
WHERE asset_type = 'etf'
  AND is_active = true
  AND is_delisted = false
ORDER BY net_assets DESC NULLS LAST;

COMMENT ON VIEW active_etfs IS 'Active ETFs only (excludes stocks and Funds)';

-- View for active funds only
CREATE OR REPLACE VIEW active_funds AS
SELECT
    id,
    ticker,
    name,
    exchange,
    company,
    category,
    asset_category,
    net_assets,
    expense_ratio,
    yield,
    minimum_investment,
    load_type,
    beta
FROM assets
WHERE asset_type = 'fund'
  AND is_active = true
  AND is_delisted = false
ORDER BY net_assets DESC NULLS LAST;

COMMENT ON VIEW active_funds IS 'Active mutual funds only (excludes stocks and ETFs)';

-- View for all active assets
CREATE OR REPLACE VIEW all_active_assets AS
SELECT
    id,
    ticker,
    name,
    asset_type,
    asset_category,
    exchange,
    country,

    -- Stock-specific
    sector,
    industry,

    -- ETF/Fund-specific
    company,
    category,

    -- Shared metrics
    market_cap,
    net_assets,
    pe_ratio,
    beta,
    yield,
    dividend_yield,
    expense_ratio,

    week_52_high,
    week_52_low,
    is_active,
    created_at,
    updated_at
FROM assets
WHERE is_active = true
  AND is_delisted = false
ORDER BY
    CASE asset_type
        WHEN 'stock' THEN market_cap
        WHEN 'etf' THEN net_assets
        WHEN 'fund' THEN net_assets
    END DESC NULLS LAST;

COMMENT ON VIEW all_active_assets IS 'All active assets (stocks + ETFs + funds) with unified columns';

-- =====================================================
-- 9. ADD AUTOMATIC PARTITION CREATION FUNCTION
-- =====================================================

CREATE OR REPLACE FUNCTION create_next_year_partitions()
RETURNS void AS $$
DECLARE
    next_year INTEGER;
    next_year_plus_one INTEGER;
    partition_exists BOOLEAN;
BEGIN
    next_year := EXTRACT(YEAR FROM CURRENT_DATE) + 1;
    next_year_plus_one := next_year + 1;

    -- Check if stock_prices partition exists
    SELECT EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'financial_screener'
        AND tablename = 'stock_prices_' || next_year
    ) INTO partition_exists;

    IF NOT partition_exists THEN
        EXECUTE format('
            CREATE TABLE stock_prices_%s PARTITION OF stock_prices
            FOR VALUES FROM (%L) TO (%L)',
            next_year,
            next_year || '-01-01',
            next_year_plus_one || '-01-01'
        );
        RAISE NOTICE 'Created partition stock_prices_%', next_year;
    END IF;

    -- Check if technical_indicators partition exists
    SELECT EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'financial_screener'
        AND tablename = 'technical_indicators_' || next_year
    ) INTO partition_exists;

    IF NOT partition_exists THEN
        EXECUTE format('
            CREATE TABLE technical_indicators_%s PARTITION OF technical_indicators
            FOR VALUES FROM (%L) TO (%L)',
            next_year,
            next_year || '-01-01',
            next_year_plus_one || '-01-01'
        );
        RAISE NOTICE 'Created partition technical_indicators_%', next_year;
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION create_next_year_partitions() IS 'Automatically creates partitions for next year - run annually';

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================

DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Migration 004 Complete';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE '✓ Updated assets table to support stocks, ETFs, and funds';
    RAISE NOTICE '✓ Added asset_category column for granular classification';
    RAISE NOTICE '✓ Added unified columns (NO prefixes):';
    RAISE NOTICE '    - company, category, investment_type';
    RAISE NOTICE '    - net_assets, expense_ratio, yield';
    RAISE NOTICE '    - inception_date, minimum_investment, load_type';
    RAISE NOTICE '✓ Added 8 new JSONB columns for ETF/Fund data';
    RAISE NOTICE '✓ Partitioned stock_prices by year (2020-2030)';
    RAISE NOTICE '✓ Partitioned technical_indicators by year (2020-2030)';
    RAISE NOTICE '✓ Dropped deprecated stock_fundamentals table';
    RAISE NOTICE '✓ Created views:';
    RAISE NOTICE '    - active_stocks (stocks only)';
    RAISE NOTICE '    - active_etfs (ETFs only)';
    RAISE NOTICE '    - active_funds (Funds only)';
    RAISE NOTICE '    - all_active_assets (unified view)';
    RAISE NOTICE '';
    RAISE NOTICE 'Table Structure:';
    RAISE NOTICE '  assets → All securities (stocks, ETFs, funds) in ONE table';
    RAISE NOTICE '  Filter by: asset_type (stock/etf/fund) or asset_category (common_stock, equity_etf, etc.)';
    RAISE NOTICE '';
    RAISE NOTICE 'Column Usage by Asset Type:';
    RAISE NOTICE '  Stocks: sector, industry, ipo_date, analyst_rating, eodhd_financials, etc.';
    RAISE NOTICE '  ETFs:   company, category, net_assets, expense_ratio, eodhd_holdings, etc.';
    RAISE NOTICE '  Funds:  company, category, net_assets, minimum_investment, load_type, etc.';
    RAISE NOTICE '  Shared: market_cap, pe_ratio, beta, yield, dividend_yield, technicals';
    RAISE NOTICE '';
END $$;
