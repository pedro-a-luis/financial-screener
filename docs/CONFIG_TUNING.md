# Configuration & Model Tuning Guide

This guide explains how to tune the Financial Screener's analysis models by adjusting parameters in the YAML configuration file.

## Configuration Architecture

The system uses a centralized configuration approach:

```
config/model-config.yaml          # Source configuration file
├── Kubernetes ConfigMap          # Deployed to cluster
└── /app/config/model-config.yaml # Mounted in pods
```

## Configuration Categories

### 1. Analysis Thresholds

Control the criteria for rating stocks, ETFs, and bonds:

#### Quality Metrics
```yaml
quality:
  roe_excellent: 0.20        # Return on Equity > 20% = Excellent
  roe_good: 0.15             # ROE > 15% = Good
  roe_minimum: 0.10          # ROE < 10% = Poor
  roa_excellent: 0.10        # Return on Assets > 10% = Excellent
  debt_to_equity_max: 2.0    # D/E Ratio > 2.0 = High risk
  current_ratio_min: 1.5     # Current Ratio < 1.5 = Liquidity concern
```

**When to adjust:**
- **Conservative investors**: Increase thresholds (e.g., `roe_excellent: 0.25`)
- **Aggressive investors**: Decrease thresholds (e.g., `roe_excellent: 0.15`)
- **High-risk tolerance**: Increase `debt_to_equity_max` to `3.0`

#### Growth Metrics
```yaml
growth:
  revenue_growth_excellent: 0.20   # Revenue growth > 20%/year
  earnings_growth_excellent: 0.15  # Earnings growth > 15%/year
  negative_growth_threshold: -0.05 # < -5% = Concerning
```

**When to adjust:**
- **Growth-focused strategy**: Increase excellent thresholds to `0.30`
- **Value investing**: Lower thresholds to `0.10`
- **Bear market**: Accept negative growth up to `-0.10`

#### Risk Metrics
```yaml
risk:
  volatility_low: 0.15       # Volatility < 15% = Low risk
  volatility_high: 0.30      # Volatility > 30% = High risk
  sharpe_ratio_excellent: 2.0     # Sharpe > 2.0 = Excellent
  max_drawdown_acceptable: -0.20  # Max drawdown > -20%
```

**When to adjust:**
- **Low-risk portfolio**: Set `volatility_high: 0.20`
- **High-risk trading**: Set `volatility_high: 0.50`
- **Crisis periods**: Increase `max_drawdown_acceptable: -0.35`

#### Valuation Metrics
```yaml
valuation:
  pe_ratio_undervalued: 15.0      # P/E < 15 = Undervalued
  pe_ratio_overvalued: 30.0       # P/E > 30 = Overvalued
  peg_ratio_fair: 1.0             # PEG around 1.0 = Fair
  dividend_yield_attractive: 0.03 # Dividend > 3%
```

**When to adjust:**
- **Value investing**: Set `pe_ratio_undervalued: 12.0`
- **Growth investing**: Set `pe_ratio_overvalued: 40.0`
- **Income focus**: Increase `dividend_yield_attractive: 0.05`

### 2. Recommendation Weights

Control how different factors influence buy/sell decisions:

```yaml
recommendation_weights:
  quality_score: 0.30        # 30% weight
  growth_score: 0.25         # 25% weight
  risk_score: 0.20           # 20% weight
  valuation_score: 0.15      # 15% weight
  sentiment_score: 0.10      # 10% weight
```

**Must sum to 1.0!**

**Example adjustments:**

**Value Investing Strategy:**
```yaml
quality_score: 0.25
growth_score: 0.15
risk_score: 0.15
valuation_score: 0.35    # Emphasize valuation
sentiment_score: 0.10
```

**Growth Investing Strategy:**
```yaml
quality_score: 0.20
growth_score: 0.40       # Emphasize growth
risk_score: 0.10
valuation_score: 0.10
sentiment_score: 0.20
```

**Conservative Strategy:**
```yaml
quality_score: 0.35      # Emphasize quality
growth_score: 0.10
risk_score: 0.35         # Emphasize low risk
valuation_score: 0.15
sentiment_score: 0.05
```

### 3. Recommendation Thresholds

Control when to issue buy/sell signals:

```yaml
recommendation_thresholds:
  strong_buy: 0.80           # Score >= 80% = STRONG_BUY
  buy: 0.65                  # Score >= 65% = BUY
  hold: 0.45                 # Score >= 45% = HOLD
  sell: 0.30                 # Score >= 30% = SELL
  # Below 30% = STRONG_SELL
```

**When to adjust:**
- **Strict filtering**: Increase thresholds (e.g., `strong_buy: 0.90`)
- **More opportunities**: Decrease thresholds (e.g., `buy: 0.60`)
- **Risk averse**: Narrow HOLD range (`hold: 0.50`)

### 4. Screening Criteria

Filter stocks before analysis:

```yaml
screening:
  stock:
    min_market_cap: 1000000000      # $1B minimum
    min_volume: 100000              # 100K daily volume
    max_pe_ratio: 50.0              # Skip P/E > 50
    min_price: 5.0                  # No penny stocks
```

**When to adjust:**
- **Large-cap only**: Set `min_market_cap: 10000000000` ($10B)
- **Small-cap hunting**: Set `min_market_cap: 250000000` ($250M)
- **Include penny stocks**: Set `min_price: 1.0`

### 5. Performance Tuning

Optimize for your cluster:

```yaml
performance:
  polars_threads: 4              # Threads per Polars operation
  enable_lazy_evaluation: true   # Use Polars lazy API
  chunk_size: 10000              # Process 10K rows at once
  enable_query_cache: true       # Cache frequent queries
```

**When to adjust:**
- **More CPU cores**: Increase `polars_threads: 8`
- **Low memory**: Decrease `chunk_size: 5000`
- **Real-time analysis**: Disable `enable_query_cache: false`

## How to Update Configuration

### Method 1: Edit and Redeploy ConfigMap

1. **Edit local config:**
   ```bash
   nano config/model-config.yaml
   ```

2. **Update ConfigMap:**
   ```bash
   kubectl apply -f kubernetes/configmap-model-config.yaml
   ```

3. **Restart workers** (config is loaded at startup):
   ```bash
   kubectl delete pods -n financial-screener -l app=celery-worker
   ```

### Method 2: Direct ConfigMap Edit (Quick Changes)

1. **Edit ConfigMap directly:**
   ```bash
   kubectl edit configmap model-config -n financial-screener
   ```

2. **Restart workers:**
   ```bash
   kubectl delete pods -n financial-screener -l app=celery-worker
   ```

### Method 3: Hot Reload (Advanced)

Add a reload endpoint to the API service (future enhancement):
```python
@app.post("/admin/reload-config")
def reload_config():
    from config_loader import reload_config
    reload_config()
    return {"status": "Config reloaded"}
```

## Configuration Validation

The configuration loader uses Pydantic for validation:

```python
from config_loader import get_config

config = get_config()
print(f"Quality weight: {config.recommendation.quality_weight}")
print(f"ROE excellent: {config.thresholds.roe_excellent}")
```

**Validation errors will prevent startup**, ensuring safe configuration changes.

## Example Use Cases

### Scenario 1: Conservative Dividend Portfolio

**Goal:** High-quality, low-risk stocks with good dividends

```yaml
# Thresholds
thresholds:
  quality:
    roe_excellent: 0.25          # Higher quality bar
    debt_to_equity_max: 1.5      # Lower debt tolerance
  valuation:
    dividend_yield_attractive: 0.04  # 4% dividend minimum

# Weights
recommendation_weights:
  quality_score: 0.40            # Prioritize quality
  growth_score: 0.05             # De-prioritize growth
  risk_score: 0.30               # Prioritize low risk
  valuation_score: 0.20          # Focus on dividends
  sentiment_score: 0.05

# Thresholds
recommendation_thresholds:
  strong_buy: 0.85               # Be selective
  buy: 0.70
```

### Scenario 2: Aggressive Growth Trading

**Goal:** High-growth stocks, accept higher risk

```yaml
# Thresholds
thresholds:
  growth:
    revenue_growth_excellent: 0.30    # 30%+ growth
    earnings_growth_excellent: 0.25   # 25%+ earnings
  risk:
    volatility_high: 0.50             # Accept high volatility

# Weights
recommendation_weights:
  quality_score: 0.15
  growth_score: 0.50               # Prioritize growth
  risk_score: 0.05                 # De-prioritize risk
  valuation_score: 0.10
  sentiment_score: 0.20            # Use sentiment

# Screening
screening:
  stock:
    min_market_cap: 500000000      # Include mid-caps
    max_pe_ratio: 100.0            # Allow high P/E
```

### Scenario 3: Value Investing (Benjamin Graham Style)

**Goal:** Undervalued, financially strong companies

```yaml
# Thresholds
thresholds:
  quality:
    current_ratio_min: 2.0         # Strong liquidity
    debt_to_equity_max: 0.5        # Low debt
  valuation:
    pe_ratio_undervalued: 12.0     # Strict valuation
    pb_ratio_undervalued: 1.0      # Book value focus

# Weights
recommendation_weights:
  quality_score: 0.35
  growth_score: 0.10
  risk_score: 0.20
  valuation_score: 0.35            # Prioritize value
  sentiment_score: 0.00            # Ignore sentiment

# Screening
screening:
  stock:
    min_market_cap: 2000000000     # Established companies
```

## Monitoring Configuration Impact

After changing config, monitor:

1. **Recommendation distribution:**
   ```sql
   SELECT recommendation, COUNT(*)
   FROM screening_results
   WHERE created_at > NOW() - INTERVAL '1 day'
   GROUP BY recommendation;
   ```

2. **Average scores:**
   ```sql
   SELECT AVG(score)
   FROM screening_results
   WHERE recommendation = 'STRONG_BUY';
   ```

3. **Task performance:**
   ```bash
   kubectl logs -n financial-screener -l app=celery-worker | grep "Task completed"
   ```

## Troubleshooting

### Config Not Loading

**Symptom:** Workers use default values

**Check:**
1. ConfigMap exists:
   ```bash
   kubectl get configmap model-config -n financial-screener
   ```

2. Volume mounted:
   ```bash
   kubectl exec -n financial-screener celery-worker-xxx -- ls /app/config/
   ```

3. Environment variable set:
   ```bash
   kubectl exec -n financial-screener celery-worker-xxx -- env | grep MODEL_CONFIG
   ```

### Invalid Configuration

**Symptom:** Workers crash on startup

**Check logs:**
```bash
kubectl logs -n financial-screener celery-worker-xxx
```

**Common errors:**
- Weights don't sum to 1.0
- Negative values for positive metrics
- Invalid YAML syntax

### Performance Issues After Config Change

**Symptom:** Tasks taking longer

**Likely causes:**
- `polars_threads` too high (CPU thrashing)
- `chunk_size` too small (overhead)
- `enable_query_cache: false` (no caching)

**Solution:** Revert to defaults and adjust incrementally.

## Best Practices

1. **Version control your configs:** Commit changes to `config/model-config.yaml`
2. **Test in staging:** Use a separate namespace for testing config changes
3. **Document changes:** Add comments explaining why you changed values
4. **Monitor impact:** Track metrics before and after changes
5. **Small iterations:** Change one category at a time
6. **Backup working configs:** Keep copies of known-good configurations

## Configuration Reference

See [config/model-config.yaml](../config/model-config.yaml) for the complete configuration schema with all available parameters and their default values.
