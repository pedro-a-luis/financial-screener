-- Financial Screener Database Schema
-- PostgreSQL 16
-- Schema: financial_screener

-- Create schema
CREATE SCHEMA IF NOT EXISTS financial_screener;

-- Set search path
SET search_path TO financial_screener;

-- ============================================================================
-- ASSETS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(255),
    asset_type VARCHAR(20) NOT NULL CHECK (asset_type IN ('stock', 'etf', 'bond')),
    exchange VARCHAR(50),
    sector VARCHAR(100),
    industry VARCHAR(100),
    country VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_assets_ticker ON assets(ticker);
CREATE INDEX idx_assets_type ON assets(asset_type);
CREATE INDEX idx_assets_exchange ON assets(exchange);

-- ============================================================================
-- STOCK PRICES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS stock_prices (
    id BIGSERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    open DECIMAL(15, 4),
    high DECIMAL(15, 4),
    low DECIMAL(15, 4),
    close DECIMAL(15, 4) NOT NULL,
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, date)
);

CREATE INDEX idx_stock_prices_asset_id ON stock_prices(asset_id);
CREATE INDEX idx_stock_prices_date ON stock_prices(date);
CREATE INDEX idx_stock_prices_asset_date ON stock_prices(asset_id, date DESC);

-- ============================================================================
-- FUNDAMENTALS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS fundamentals (
    id BIGSERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    period_end_date DATE NOT NULL,
    period_type VARCHAR(20) CHECK (period_type IN ('annual', 'quarterly', 'ttm')),

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

    -- Financial health
    current_ratio DECIMAL(10, 2),
    quick_ratio DECIMAL(10, 2),
    debt_to_equity DECIMAL(10, 2),

    -- Income statement
    revenue BIGINT,
    gross_profit BIGINT,
    ebitda BIGINT,
    net_income BIGINT,
    eps DECIMAL(10, 2),

    -- Cash flow
    operating_cash_flow BIGINT,
    free_cash_flow BIGINT,

    -- Growth metrics
    revenue_growth DECIMAL(10, 4),
    earnings_growth DECIMAL(10, 4),

    -- Dividend metrics
    dividend_yield DECIMAL(10, 4),
    dividend_per_share DECIMAL(10, 2),
    payout_ratio DECIMAL(10, 4),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, period_end_date, period_type)
);

CREATE INDEX idx_fundamentals_asset_id ON fundamentals(asset_id);
CREATE INDEX idx_fundamentals_period ON fundamentals(period_end_date DESC);

-- ============================================================================
-- TECHNICAL INDICATORS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS technical_indicators (
    id BIGSERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    date DATE NOT NULL,

    -- Moving averages
    sma_20 DECIMAL(15, 4),
    sma_50 DECIMAL(15, 4),
    sma_200 DECIMAL(15, 4),
    ema_12 DECIMAL(15, 4),
    ema_26 DECIMAL(15, 4),

    -- Momentum indicators
    rsi_14 DECIMAL(10, 2),
    macd DECIMAL(15, 4),
    macd_signal DECIMAL(15, 4),
    macd_histogram DECIMAL(15, 4),

    -- Volatility
    bollinger_upper DECIMAL(15, 4),
    bollinger_middle DECIMAL(15, 4),
    bollinger_lower DECIMAL(15, 4),
    atr_14 DECIMAL(15, 4),

    -- Volume
    volume_sma_20 BIGINT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, date)
);

CREATE INDEX idx_technical_indicators_asset_id ON technical_indicators(asset_id);
CREATE INDEX idx_technical_indicators_date ON technical_indicators(date);

-- ============================================================================
-- RECOMMENDATIONS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS recommendations (
    id BIGSERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    date DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Overall recommendation
    recommendation VARCHAR(20) CHECK (recommendation IN ('STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL')),
    confidence DECIMAL(5, 2), -- 0-100

    -- Component scores (0-1)
    quality_score DECIMAL(5, 4),
    growth_score DECIMAL(5, 4),
    risk_score DECIMAL(5, 4),
    valuation_score DECIMAL(5, 4),
    sentiment_score DECIMAL(5, 4),
    technical_score DECIMAL(5, 4),

    -- Weighted final score (0-1)
    final_score DECIMAL(5, 4),

    -- Reasoning
    reasoning TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, date)
);

CREATE INDEX idx_recommendations_asset_id ON recommendations(asset_id);
CREATE INDEX idx_recommendations_date ON recommendations(date DESC);
CREATE INDEX idx_recommendations_recommendation ON recommendations(recommendation);

-- ============================================================================
-- DATA FETCH LOG TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS data_fetch_log (
    id BIGSERIAL PRIMARY KEY,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) CHECK (status IN ('success', 'partial', 'failed')),
    records_processed INTEGER,
    error_message TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER
);

CREATE INDEX idx_data_fetch_log_job_type ON data_fetch_log(job_type);
CREATE INDEX idx_data_fetch_log_started_at ON data_fetch_log(started_at DESC);

-- ============================================================================
-- WATCHLISTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS watchlists (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- WATCHLIST ITEMS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS watchlist_items (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(watchlist_id, asset_id)
);

CREATE INDEX idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);
CREATE INDEX idx_watchlist_items_asset_id ON watchlist_items(asset_id);

-- ============================================================================
-- ETF DETAILS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS etf_details (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE UNIQUE,
    expense_ratio DECIMAL(5, 4),
    aum BIGINT, -- Assets under management
    inception_date DATE,
    category VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- ETF HOLDINGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS etf_holdings (
    id BIGSERIAL PRIMARY KEY,
    etf_asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    holding_ticker VARCHAR(20),
    holding_name VARCHAR(255),
    weight DECIMAL(7, 4), -- Percentage weight
    shares BIGINT,
    market_value BIGINT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_etf_holdings_etf_id ON etf_holdings(etf_asset_id);

-- ============================================================================
-- BOND DETAILS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS bond_details (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE UNIQUE,
    coupon_rate DECIMAL(7, 4),
    maturity_date DATE,
    yield_to_maturity DECIMAL(7, 4),
    duration DECIMAL(10, 4),
    credit_rating VARCHAR(10),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- GRANT PERMISSIONS
-- ============================================================================
GRANT USAGE ON SCHEMA financial_screener TO appuser;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA financial_screener TO appuser;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA financial_screener TO appuser;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA financial_screener GRANT ALL ON TABLES TO appuser;
ALTER DEFAULT PRIVILEGES IN SCHEMA financial_screener GRANT ALL ON SEQUENCES TO appuser;

-- ============================================================================
-- COMPLETED
-- ============================================================================
\echo 'Financial Screener schema created successfully!'
