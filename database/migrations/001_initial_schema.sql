-- Financial Screener Database Schema
-- PostgreSQL 16+
-- Migration: 001_initial_schema.sql
--
-- This schema is designed to coexist with other projects in the same database.
-- All tables are created in the 'financial_screener' schema.

-- Create dedicated schema for this project
CREATE SCHEMA IF NOT EXISTS financial_screener;

-- Set search path for this migration
SET search_path TO financial_screener, public;

-- Enable extensions (if not already enabled globally)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- =====================================================
-- CORE ASSET TABLES
-- =====================================================

-- Asset types enum
CREATE TYPE financial_screener.asset_type_enum AS ENUM ('stock', 'etf', 'bond');

-- Recommendation enum
CREATE TYPE financial_screener.recommendation_enum AS ENUM (
    'STRONG_BUY',
    'BUY',
    'HOLD',
    'SELL',
    'STRONG_SELL'
);

-- Sentiment enum
CREATE TYPE financial_screener.sentiment_enum AS ENUM ('positive', 'neutral', 'negative');

-- Assets master table (stocks, ETFs, bonds)
CREATE TABLE assets (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    asset_type asset_type_enum NOT NULL,
    exchange VARCHAR(20),
    currency VARCHAR(3) DEFAULT 'USD',
    sector VARCHAR(100),
    industry VARCHAR(100),
    country VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_assets_ticker ON assets(ticker);
CREATE INDEX idx_assets_type ON assets(asset_type);
CREATE INDEX idx_assets_sector ON assets(sector);
CREATE INDEX idx_assets_active ON assets(is_active);
CREATE INDEX idx_assets_ticker_trgm ON assets USING gin(ticker gin_trgm_ops);

-- =====================================================
-- PRICE DATA
-- =====================================================

-- Daily price data (OHLCV)
CREATE TABLE stock_prices (
    id BIGSERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    open DECIMAL(12, 4) NOT NULL,
    high DECIMAL(12, 4) NOT NULL,
    low DECIMAL(12, 4) NOT NULL,
    close DECIMAL(12, 4) NOT NULL,
    volume BIGINT NOT NULL,
    adj_close DECIMAL(12, 4),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(asset_id, date)
);

-- Partition by year for performance (optional, can add later)
CREATE INDEX idx_prices_asset_date ON stock_prices(asset_id, date DESC);
CREATE INDEX idx_prices_date ON stock_prices(date DESC);

-- =====================================================
-- STOCK-SPECIFIC DATA
-- =====================================================

-- Stock fundamentals (quarterly/annual)
CREATE TABLE stock_fundamentals (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    period_end_date DATE NOT NULL,
    period_type VARCHAR(10) NOT NULL,  -- 'quarterly' or 'annual'

    -- Valuation metrics
    market_cap BIGINT,
    enterprise_value BIGINT,
    pe_ratio DECIMAL(10, 2),
    pb_ratio DECIMAL(10, 2),
    ps_ratio DECIMAL(10, 2),
    peg_ratio DECIMAL(10, 2),
    ev_ebitda DECIMAL(10, 2),

    -- Profitability metrics
    gross_margin DECIMAL(10, 4),
    operating_margin DECIMAL(10, 4),
    profit_margin DECIMAL(10, 4),
    roe DECIMAL(10, 4),
    roa DECIMAL(10, 4),
    roic DECIMAL(10, 4),

    -- Financial health
    current_ratio DECIMAL(10, 2),
    quick_ratio DECIMAL(10, 2),
    debt_to_equity DECIMAL(10, 2),
    interest_coverage DECIMAL(10, 2),

    -- Cash flow
    operating_cash_flow BIGINT,
    free_cash_flow BIGINT,
    fcf_per_share DECIMAL(10, 2),

    -- Income statement
    revenue BIGINT,
    gross_profit BIGINT,
    operating_income BIGINT,
    net_income BIGINT,
    ebitda BIGINT,
    eps DECIMAL(10, 2),

    -- Balance sheet
    total_assets BIGINT,
    total_liabilities BIGINT,
    total_debt BIGINT,
    cash_and_equivalents BIGINT,

    -- Growth metrics (YoY)
    revenue_growth DECIMAL(10, 4),
    earnings_growth DECIMAL(10, 4),

    -- Dividend info
    dividend_yield DECIMAL(10, 4),
    dividend_per_share DECIMAL(10, 2),
    payout_ratio DECIMAL(10, 4),

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(asset_id, period_end_date, period_type)
);

CREATE INDEX idx_fundamentals_asset_period ON stock_fundamentals(asset_id, period_end_date DESC);

-- =====================================================
-- ETF-SPECIFIC DATA
-- =====================================================

-- ETF details
CREATE TABLE etf_details (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,

    -- Basic info
    expense_ratio DECIMAL(10, 4),
    aum BIGINT,  -- Assets under management
    inception_date DATE,

    -- Performance metrics
    ytd_return DECIMAL(10, 4),
    one_year_return DECIMAL(10, 4),
    three_year_return DECIMAL(10, 4),
    five_year_return DECIMAL(10, 4),

    -- Risk metrics
    beta DECIMAL(10, 4),
    sharpe_ratio DECIMAL(10, 4),
    sortino_ratio DECIMAL(10, 4),
    tracking_error DECIMAL(10, 4),

    -- ETF structure
    fund_family VARCHAR(100),
    benchmark_index VARCHAR(100),
    replication_method VARCHAR(50),  -- 'physical' or 'synthetic'

    -- Holdings info
    num_holdings INTEGER,
    top_10_concentration DECIMAL(10, 4),

    -- Distributions
    distribution_frequency VARCHAR(50),
    last_distribution_date DATE,
    last_distribution_amount DECIMAL(10, 4),

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(asset_id)
);

CREATE INDEX idx_etf_details_asset ON etf_details(asset_id);

-- ETF holdings (top holdings)
CREATE TABLE etf_holdings (
    id SERIAL PRIMARY KEY,
    etf_asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    holding_ticker VARCHAR(20),
    holding_name VARCHAR(255),
    weight DECIMAL(10, 4),  -- Percentage
    shares BIGINT,
    market_value BIGINT,
    snapshot_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(etf_asset_id, holding_ticker, snapshot_date)
);

CREATE INDEX idx_etf_holdings_etf_date ON etf_holdings(etf_asset_id, snapshot_date DESC);

-- =====================================================
-- BOND-SPECIFIC DATA
-- =====================================================

-- Bond details
CREATE TABLE bond_details (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,

    -- Basic info
    issuer VARCHAR(255),
    bond_type VARCHAR(50),  -- 'government', 'corporate', 'municipal', 'tips'

    -- Yield metrics
    coupon_rate DECIMAL(10, 4),
    yield_to_maturity DECIMAL(10, 4),
    current_yield DECIMAL(10, 4),
    yield_to_call DECIMAL(10, 4),
    yield_to_worst DECIMAL(10, 4),

    -- Duration and sensitivity
    macaulay_duration DECIMAL(10, 4),
    modified_duration DECIMAL(10, 4),
    effective_duration DECIMAL(10, 4),
    convexity DECIMAL(10, 4),

    -- Credit analysis
    credit_rating_sp VARCHAR(10),
    credit_rating_moody VARCHAR(10),
    credit_rating_fitch VARCHAR(10),
    credit_spread DECIMAL(10, 4),

    -- Maturity info
    issue_date DATE,
    maturity_date DATE,
    first_call_date DATE,

    -- Payment info
    payment_frequency VARCHAR(50),  -- 'monthly', 'quarterly', 'semi-annual', 'annual'
    last_payment_date DATE,
    next_payment_date DATE,

    -- Pricing
    par_value DECIMAL(12, 2),
    price DECIMAL(12, 4),
    face_value BIGINT,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(asset_id)
);

CREATE INDEX idx_bond_details_asset ON bond_details(asset_id);
CREATE INDEX idx_bond_maturity ON bond_details(maturity_date);
CREATE INDEX idx_bond_rating_sp ON bond_details(credit_rating_sp);

-- =====================================================
-- NEWS & SENTIMENT
-- =====================================================

-- News articles
CREATE TABLE news_articles (
    id BIGSERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id) ON DELETE SET NULL,
    ticker VARCHAR(20),  -- Denormalized for faster lookup

    -- Article details
    title VARCHAR(500) NOT NULL,
    description TEXT,
    content TEXT,
    url VARCHAR(1000) UNIQUE,

    -- Source info
    source VARCHAR(100),
    author VARCHAR(255),
    published_date TIMESTAMP NOT NULL,

    -- Categorization
    category VARCHAR(100),
    tags TEXT[],

    -- Sentiment (to be filled by sentiment engine)
    sentiment sentiment_enum,
    sentiment_score DECIMAL(10, 4),  -- -1 to 1

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_news_asset_date ON news_articles(asset_id, published_date DESC);
CREATE INDEX idx_news_ticker_date ON news_articles(ticker, published_date DESC);
CREATE INDEX idx_news_published ON news_articles(published_date DESC);
CREATE INDEX idx_news_sentiment ON news_articles(sentiment, sentiment_score);
CREATE INDEX idx_news_url_hash ON news_articles USING hash(url);

-- Sentiment summary per asset
CREATE TABLE sentiment_summary (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,

    -- Aggregate sentiment
    avg_sentiment_score DECIMAL(10, 4),
    positive_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,
    total_articles INTEGER DEFAULT 0,

    -- Time period
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    period_type VARCHAR(20) NOT NULL,  -- 'daily', 'weekly', 'monthly'

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(asset_id, period_start, period_type)
);

CREATE INDEX idx_sentiment_asset_period ON sentiment_summary(asset_id, period_start DESC);

-- =====================================================
-- SCREENING & RECOMMENDATIONS
-- =====================================================

-- Screening results cache
CREATE TABLE screening_results (
    id BIGSERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,
    asset_type asset_type_enum NOT NULL,

    -- Composite scores
    composite_score DECIMAL(10, 4),
    fundamental_score DECIMAL(10, 4),
    sentiment_score DECIMAL(10, 4),
    technical_score DECIMAL(10, 4),
    risk_score DECIMAL(10, 4),

    -- Recommendation
    recommendation recommendation_enum NOT NULL,
    confidence DECIMAL(10, 4),

    -- Individual metric scores (for filtering)
    value_score DECIMAL(10, 4),
    quality_score DECIMAL(10, 4),
    growth_score DECIMAL(10, 4),
    momentum_score DECIMAL(10, 4),

    -- Metadata
    screened_at TIMESTAMP NOT NULL DEFAULT NOW(),
    valid_until TIMESTAMP,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_screening_composite ON screening_results(composite_score DESC, screened_at DESC);
CREATE INDEX idx_screening_recommendation ON screening_results(recommendation, composite_score DESC);
CREATE INDEX idx_screening_asset_type ON screening_results(asset_type, composite_score DESC);
CREATE INDEX idx_screening_ticker ON screening_results(ticker);

-- Recommendation history (track changes over time)
CREATE TABLE recommendation_history (
    id BIGSERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,

    recommendation recommendation_enum NOT NULL,
    composite_score DECIMAL(10, 4),

    -- Previous values (for change tracking)
    previous_recommendation recommendation_enum,
    previous_score DECIMAL(10, 4),

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_recommendation_history_asset ON recommendation_history(asset_id, created_at DESC);

-- =====================================================
-- PORTFOLIO MANAGEMENT
-- =====================================================

-- Portfolios (users can have multiple portfolios)
CREATE TABLE portfolios (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    user_id VARCHAR(100),  -- For future multi-user support
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolios_user ON portfolios(user_id);

-- Portfolio holdings
CREATE TABLE portfolio_holdings (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,

    -- Position details
    quantity DECIMAL(18, 8) NOT NULL,
    avg_buy_price DECIMAL(12, 4),
    current_price DECIMAL(12, 4),

    -- Calculated values
    total_cost DECIMAL(18, 2),
    current_value DECIMAL(18, 2),
    unrealized_gain_loss DECIMAL(18, 2),
    unrealized_gain_loss_pct DECIMAL(10, 4),

    -- Metadata
    first_purchase_date DATE,
    last_updated TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(portfolio_id, asset_id)
);

CREATE INDEX idx_holdings_portfolio ON portfolio_holdings(portfolio_id);
CREATE INDEX idx_holdings_asset ON portfolio_holdings(asset_id);

-- Transactions (for tracking buy/sell history)
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,

    -- Transaction details
    transaction_type VARCHAR(20) NOT NULL,  -- 'buy', 'sell', 'dividend'
    quantity DECIMAL(18, 8) NOT NULL,
    price DECIMAL(12, 4) NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL,
    fees DECIMAL(12, 2) DEFAULT 0,

    -- Source info
    transaction_date DATE NOT NULL,
    source VARCHAR(50),  -- 'manual', 'degiro', 'api'
    external_id VARCHAR(100),  -- ID from DEGIRO or other platform

    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_transactions_portfolio ON transactions(portfolio_id, transaction_date DESC);
CREATE INDEX idx_transactions_asset ON transactions(asset_id, transaction_date DESC);
CREATE INDEX idx_transactions_external ON transactions(external_id);

-- =====================================================
-- WATCHLISTS
-- =====================================================

-- Watchlists (separate from portfolios - for tracking interests)
CREATE TABLE watchlists (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    user_id VARCHAR(100),
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_watchlists_user ON watchlists(user_id);

-- Watchlist items
CREATE TABLE watchlist_items (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,

    -- Optional target price for alerts
    target_buy_price DECIMAL(12, 4),
    target_sell_price DECIMAL(12, 4),

    notes TEXT,
    added_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(watchlist_id, asset_id)
);

CREATE INDEX idx_watchlist_items_list ON watchlist_items(watchlist_id);
CREATE INDEX idx_watchlist_items_asset ON watchlist_items(asset_id);

-- =====================================================
-- DATA COLLECTION TRACKING
-- =====================================================

-- Track data fetching jobs and their success/failure
CREATE TABLE data_fetch_log (
    id BIGSERIAL PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,  -- 'price', 'fundamental', 'news', 'sentiment'
    ticker VARCHAR(20),
    status VARCHAR(20) NOT NULL,  -- 'success', 'failed', 'partial'
    records_processed INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_ms INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fetch_log_job_type ON data_fetch_log(job_type, created_at DESC);
CREATE INDEX idx_fetch_log_ticker ON data_fetch_log(ticker, created_at DESC);

-- =====================================================
-- TRIGGERS FOR UPDATED_AT
-- =====================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to relevant tables
CREATE TRIGGER update_assets_updated_at BEFORE UPDATE ON assets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_stock_fundamentals_updated_at BEFORE UPDATE ON stock_fundamentals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_etf_details_updated_at BEFORE UPDATE ON etf_details
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_bond_details_updated_at BEFORE UPDATE ON bond_details
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_portfolios_updated_at BEFORE UPDATE ON portfolios
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- VIEWS FOR COMMON QUERIES
-- =====================================================

-- Latest prices view
CREATE VIEW v_latest_prices AS
SELECT DISTINCT ON (asset_id)
    sp.asset_id,
    a.ticker,
    a.name,
    a.asset_type,
    sp.date,
    sp.close AS price,
    sp.volume,
    sp.adj_close
FROM stock_prices sp
JOIN assets a ON a.id = sp.asset_id
WHERE a.is_active = true
ORDER BY sp.asset_id, sp.date DESC;

-- Latest fundamentals view
CREATE VIEW v_latest_fundamentals AS
SELECT DISTINCT ON (asset_id)
    sf.*,
    a.ticker,
    a.name
FROM stock_fundamentals sf
JOIN assets a ON a.id = sf.asset_id
WHERE a.is_active = true
ORDER BY sf.asset_id, sf.period_end_date DESC;

-- Portfolio summary view
CREATE VIEW v_portfolio_summary AS
SELECT
    ph.portfolio_id,
    p.name AS portfolio_name,
    COUNT(ph.id) AS num_holdings,
    SUM(ph.current_value) AS total_value,
    SUM(ph.total_cost) AS total_cost,
    SUM(ph.unrealized_gain_loss) AS total_gain_loss,
    CASE
        WHEN SUM(ph.total_cost) > 0
        THEN (SUM(ph.unrealized_gain_loss) / SUM(ph.total_cost)) * 100
        ELSE 0
    END AS total_gain_loss_pct
FROM portfolio_holdings ph
JOIN portfolios p ON p.id = ph.portfolio_id
GROUP BY ph.portfolio_id, p.name;

-- =====================================================
-- INITIAL DATA
-- =====================================================

-- Create default portfolio
INSERT INTO portfolios (name, description, is_default)
VALUES ('Default Portfolio', 'Default portfolio for tracking investments', true);

-- Create default watchlist
INSERT INTO watchlists (name, description, is_default)
VALUES ('Default Watchlist', 'Default watchlist for tracking potential investments', true);

-- =====================================================
-- PERFORMANCE INDEXES (Add as needed)
-- =====================================================

-- COMMENT: Additional indexes can be added based on actual query patterns
-- Run EXPLAIN ANALYZE on slow queries to identify needed indexes

-- Example: If frequently filtering by multiple columns
-- CREATE INDEX idx_screening_multi ON screening_results(asset_type, recommendation, composite_score DESC);

-- Example: If frequently joining prices with assets
-- Already covered by existing indexes

-- =====================================================
-- MAINTENANCE
-- =====================================================

-- Scheduled vacuum and analyze (configure in PostgreSQL)
-- Run weekly: VACUUM ANALYZE;

-- Check table sizes
-- SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
-- FROM pg_tables
-- WHERE schemaname = 'public'
-- ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
