-- Migration: 002_enhance_assets_table.sql
-- Add comprehensive asset metadata and key financial metrics from EODHD API
-- Strategy: Store frequently-queried metrics as columns + complete raw data as JSONB

SET search_path TO financial_screener, public;

-- Drop table and recreate with all fields
DROP TABLE IF EXISTS assets CASCADE;

CREATE TABLE assets (
    id SERIAL PRIMARY KEY,

    -- Core identification
    ticker VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    asset_type asset_type_enum NOT NULL,
    asset_subtype VARCHAR(50),  -- 'Common Stock', 'Preferred Stock', 'ADR', etc.

    -- Exchange & Geographic
    exchange VARCHAR(50),        -- Actual exchange: 'NASDAQ', 'NYSE', 'LSE', etc. (NOT country code!)
    currency VARCHAR(3) DEFAULT 'USD',
    country VARCHAR(100),        -- Full country name: 'USA', 'United Kingdom', etc.
    country_iso VARCHAR(2),      -- ISO code: 'US', 'GB', etc.

    -- Industry Classification
    sector VARCHAR(100),         -- Basic sector
    industry VARCHAR(100),       -- Basic industry
    gic_sector VARCHAR(100),     -- GICS Sector
    gic_group VARCHAR(100),      -- GICS Group
    gic_industry VARCHAR(150),   -- GICS Industry
    gic_sub_industry VARCHAR(150), -- GICS Sub-Industry

    -- Identifiers
    isin VARCHAR(20),
    cusip VARCHAR(20),
    cik VARCHAR(20),
    figi VARCHAR(20),

    -- Company Info
    description TEXT,
    ipo_date DATE,
    is_delisted BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,

    -- KEY FINANCIAL METRICS (from Highlights - for fast screening)
    market_cap BIGINT,                    -- Market capitalization
    pe_ratio DECIMAL(10, 2),              -- Price/Earnings ratio
    peg_ratio DECIMAL(10, 4),             -- PEG ratio (growth-adjusted PE)
    book_value DECIMAL(10, 4),            -- Book value per share
    dividend_yield DECIMAL(10, 6),        -- Dividend yield (%)
    dividend_per_share DECIMAL(10, 4),    -- Annual dividend per share
    earnings_per_share DECIMAL(10, 4),    -- EPS (TTM)
    ebitda BIGINT,                        -- EBITDA
    eps_estimate_current_year DECIMAL(10, 4),  -- Analyst EPS estimate
    eps_estimate_next_year DECIMAL(10, 4),     -- Next year EPS estimate
    wall_street_target_price DECIMAL(12, 4),   -- Average analyst target price

    -- VALUATION METRICS (for screening)
    trailing_pe DECIMAL(10, 2),
    forward_pe DECIMAL(10, 2),
    price_sales_ttm DECIMAL(10, 4),       -- Price/Sales ratio
    price_book DECIMAL(10, 4),            -- Price/Book ratio
    enterprise_value BIGINT,
    ev_revenue DECIMAL(10, 4),            -- EV/Revenue
    ev_ebitda DECIMAL(10, 4),             -- EV/EBITDA

    -- ANALYST RATINGS (for recommendations)
    analyst_rating DECIMAL(5, 3),         -- Average rating (1-5 scale)
    analyst_target_price DECIMAL(12, 4),  -- Consensus target price
    analyst_strong_buy INTEGER,           -- Number of Strong Buy ratings
    analyst_buy INTEGER,                  -- Number of Buy ratings
    analyst_hold INTEGER,                 -- Number of Hold ratings
    analyst_sell INTEGER,                 -- Number of Sell ratings
    analyst_strong_sell INTEGER,          -- Number of Strong Sell ratings

    -- TECHNICALS (for momentum/signals)
    beta DECIMAL(10, 4),                  -- Market beta
    week_52_high DECIMAL(12, 4),          -- 52-week high
    week_52_low DECIMAL(12, 4),           -- 52-week low
    ma_50_day DECIMAL(12, 4),             -- 50-day moving average
    ma_200_day DECIMAL(12, 4),            -- 200-day moving average
    shares_short BIGINT,                  -- Shares sold short
    short_ratio DECIMAL(10, 2),           -- Days to cover shorts
    short_percent DECIMAL(10, 6),         -- % of float shorted

    -- RAW EODHD DATA (complete API response as JSONB)
    eodhd_general JSONB,                  -- General section (company info, addresses, officers, etc.)
    eodhd_highlights JSONB,               -- Complete Highlights section
    eodhd_valuation JSONB,                -- Complete Valuation section
    eodhd_shares_stats JSONB,             -- Share statistics
    eodhd_technicals JSONB,               -- Complete Technicals section
    eodhd_splits_dividends JSONB,         -- Historical splits/dividends
    eodhd_analyst_ratings JSONB,          -- Complete analyst data
    eodhd_holders JSONB,                  -- Institutional holders
    eodhd_insider_transactions JSONB,     -- Insider trading
    eodhd_esg_scores JSONB,               -- ESG ratings
    eodhd_outstanding_shares JSONB,       -- Shares outstanding history
    eodhd_earnings JSONB,                 -- Earnings history
    eodhd_financials JSONB,               -- Income statement, balance sheet, cash flow
    eodhd_last_update TIMESTAMP,          -- When EODHD data was last fetched

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for core fields
CREATE INDEX idx_assets_ticker ON assets(ticker);
CREATE INDEX idx_assets_type ON assets(asset_type);
CREATE INDEX idx_assets_sector ON assets(sector);
CREATE INDEX idx_assets_industry ON assets(industry);
CREATE INDEX idx_assets_exchange ON assets(exchange);
CREATE INDEX idx_assets_country ON assets(country);
CREATE INDEX idx_assets_active ON assets(is_active);

-- Indexes for identifiers
CREATE INDEX idx_assets_isin ON assets(isin) WHERE isin IS NOT NULL;
CREATE INDEX idx_assets_cusip ON assets(cusip) WHERE cusip IS NOT NULL;
CREATE INDEX idx_assets_cik ON assets(cik) WHERE cik IS NOT NULL;

-- Indexes for GICS classification
CREATE INDEX idx_assets_gic_sector ON assets(gic_sector);
CREATE INDEX idx_assets_gic_industry ON assets(gic_industry);

-- Indexes for SCREENING (most important!)
CREATE INDEX idx_assets_market_cap ON assets(market_cap DESC);
CREATE INDEX idx_assets_pe_ratio ON assets(pe_ratio);
CREATE INDEX idx_assets_dividend_yield ON assets(dividend_yield DESC);
CREATE INDEX idx_assets_analyst_rating ON assets(analyst_rating DESC);
CREATE INDEX idx_assets_beta ON assets(beta);

-- Composite index for common screening queries
CREATE INDEX idx_assets_screening ON assets(asset_type, sector, market_cap DESC, pe_ratio);

-- JSONB indexes for querying nested data
CREATE INDEX idx_assets_eodhd_general ON assets USING GIN (eodhd_general);
CREATE INDEX idx_assets_eodhd_highlights ON assets USING GIN (eodhd_highlights);
CREATE INDEX idx_assets_eodhd_valuation ON assets USING GIN (eodhd_valuation);

-- Full-text search on description
CREATE INDEX idx_assets_description_fts ON assets USING GIN (to_tsvector('english', description));

-- Text search on ticker (for autocomplete)
CREATE INDEX idx_assets_ticker_trgm ON assets USING gin(ticker gin_trgm_ops);

-- Add comments
COMMENT ON TABLE assets IS 'Master assets table with comprehensive EODHD financial metrics';
COMMENT ON COLUMN assets.exchange IS 'Actual exchange name (NASDAQ, NYSE, LSE, etc.) - NOT country code';
COMMENT ON COLUMN assets.country IS 'Full country name (USA, United Kingdom, etc.)';
COMMENT ON COLUMN assets.market_cap IS 'Market capitalization in dollars';
COMMENT ON COLUMN assets.pe_ratio IS 'Price-to-Earnings ratio (trailing 12 months)';
COMMENT ON COLUMN assets.dividend_yield IS 'Annual dividend yield as decimal (0.04 = 4%)';
COMMENT ON COLUMN assets.analyst_rating IS 'Average analyst rating: 5=Strong Buy, 4=Buy, 3=Hold, 2=Sell, 1=Strong Sell';
COMMENT ON COLUMN assets.beta IS 'Market beta (volatility vs. market)';
COMMENT ON COLUMN assets.eodhd_highlights IS 'Complete Highlights section from EODHD (key metrics)';
COMMENT ON COLUMN assets.eodhd_valuation IS 'Complete Valuation section from EODHD (all ratios)';
COMMENT ON COLUMN assets.eodhd_analyst_ratings IS 'Complete analyst ratings and price targets';
COMMENT ON COLUMN assets.eodhd_financials IS 'Complete financial statements (income, balance sheet, cash flow)';
