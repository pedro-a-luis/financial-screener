-- Migration: 003_technical_indicators_table.sql
-- Create table to store calculated technical indicators

SET search_path TO financial_screener, public;

-- Technical indicators table (one row per asset, updated daily)
CREATE TABLE technical_indicators (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    ticker VARCHAR(20) NOT NULL,

    -- MOVING AVERAGES
    sma_50 DECIMAL(12, 4),           -- 50-day Simple Moving Average
    sma_200 DECIMAL(12, 4),          -- 200-day Simple Moving Average
    ema_12 DECIMAL(12, 4),           -- 12-day Exponential Moving Average
    ema_26 DECIMAL(12, 4),           -- 26-day Exponential Moving Average
    wma_20 DECIMAL(12, 4),           -- 20-day Weighted Moving Average

    -- MOMENTUM INDICATORS
    rsi_14 DECIMAL(10, 4),           -- 14-period Relative Strength Index (0-100)
    stoch_k DECIMAL(10, 4),          -- Stochastic %K
    stoch_d DECIMAL(10, 4),          -- Stochastic %D
    stoch_rsi DECIMAL(10, 4),        -- Stochastic RSI
    cci_20 DECIMAL(12, 4),           -- 20-period Commodity Channel Index

    -- TREND INDICATORS
    macd DECIMAL(12, 6),             -- MACD line
    macd_signal DECIMAL(12, 6),      -- MACD signal line
    macd_histogram DECIMAL(12, 6),   -- MACD histogram
    dmi_plus DECIMAL(10, 4),         -- Directional Movement Index +DI
    dmi_minus DECIMAL(10, 4),        -- Directional Movement Index -DI
    adx DECIMAL(10, 4),              -- Average Directional Index (trend strength)

    -- VOLATILITY INDICATORS
    atr_14 DECIMAL(12, 4),           -- 14-period Average True Range
    volatility DECIMAL(10, 4),       -- Historical volatility (annualized %)
    std_dev DECIMAL(12, 6),          -- 20-period Standard Deviation

    -- BOLLINGER BANDS
    bb_upper DECIMAL(12, 4),         -- Upper Bollinger Band
    bb_middle DECIMAL(12, 4),        -- Middle Bollinger Band (20-day SMA)
    bb_lower DECIMAL(12, 4),         -- Lower Bollinger Band
    bb_bandwidth DECIMAL(10, 6),     -- Bollinger Band Width

    -- OTHER INDICATORS
    sar DECIMAL(12, 4),              -- Parabolic SAR
    beta DECIMAL(10, 4),             -- Beta (vs market)
    slope DECIMAL(12, 6),            -- Linear regression slope (20-period)

    -- VOLUME INDICATORS
    avg_volume_30 BIGINT,            -- 30-day average volume
    avg_volume_90 BIGINT,            -- 90-day average volume

    -- PRICE LEVELS
    week_52_high DECIMAL(12, 4),     -- 52-week high
    week_52_low DECIMAL(12, 4),      -- 52-week low
    current_price DECIMAL(12, 4),    -- Current closing price

    -- METADATA
    calculation_date DATE NOT NULL,   -- Date indicators were calculated
    data_points_used INTEGER,         -- Number of price data points used
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(asset_id, calculation_date)
);

-- Indexes for fast queries
CREATE INDEX idx_technical_asset ON technical_indicators(asset_id);
CREATE INDEX idx_technical_ticker ON technical_indicators(ticker);
CREATE INDEX idx_technical_date ON technical_indicators(calculation_date DESC);

-- Indexes for screening queries
CREATE INDEX idx_technical_rsi ON technical_indicators(rsi_14);
CREATE INDEX idx_technical_macd ON technical_indicators(macd_histogram);
CREATE INDEX idx_technical_adx ON technical_indicators(adx DESC);
CREATE INDEX idx_technical_bb_position ON technical_indicators(bb_upper, bb_lower, current_price);

-- Composite index for common technical screening
CREATE INDEX idx_technical_screening ON technical_indicators(
    calculation_date DESC,
    rsi_14,
    macd_histogram,
    adx
);

-- View for latest technical indicators per asset
CREATE VIEW v_latest_technical_indicators AS
SELECT DISTINCT ON (asset_id)
    ti.*,
    a.name,
    a.sector,
    a.exchange
FROM technical_indicators ti
JOIN assets a ON a.id = ti.asset_id
WHERE a.is_active = true
ORDER BY ti.asset_id, ti.calculation_date DESC;

-- Add trigger for updated_at
CREATE TRIGGER update_technical_indicators_updated_at
BEFORE UPDATE ON technical_indicators
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments
COMMENT ON TABLE technical_indicators IS 'Calculated technical indicators for all assets (updated daily)';
COMMENT ON COLUMN technical_indicators.rsi_14 IS 'RSI: <30 oversold, >70 overbought';
COMMENT ON COLUMN technical_indicators.macd_histogram IS 'Positive=bullish, negative=bearish';
COMMENT ON COLUMN technical_indicators.adx IS 'Trend strength: >25 strong trend, <20 weak';
COMMENT ON COLUMN technical_indicators.stoch_k IS 'Stochastic %K: <20 oversold, >80 overbought';
COMMENT ON COLUMN technical_indicators.cci_20 IS 'CCI: >100 overbought, <-100 oversold';
COMMENT ON COLUMN technical_indicators.bb_bandwidth IS 'Bollinger Band Width: measures volatility';
COMMENT ON COLUMN technical_indicators.volatility IS 'Annualized volatility percentage';
COMMENT ON COLUMN technical_indicators.beta IS 'Market beta: >1 more volatile than market, <1 less volatile';
