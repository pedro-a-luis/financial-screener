# Analyzer Service

**Status:** 🔜 **PLANNED** (Phase 4-6 - Q2 2025)

## Purpose
Celery-based distributed recommendation engine that generates buy/sell/hold recommendations using fundamentals, technical indicators, sentiment, and risk analysis.

## Planned Implementation

### Architecture
- **Task Queue:** Celery with Redis broker
- **Workers:** 8 Celery workers (one per Pi node)
- **Processing Engine:** Polars for data aggregation
- **ML Framework:** scikit-learn (initially), PyTorch (future)
- **Orchestration:** Airflow DAG + API-triggered ad-hoc

### Recommendation Algorithm

**Multi-Factor Scoring Model:**
```
Final Score = w1×Fundamental + w2×Technical + w3×Sentiment + w4×Risk

Where weights (w) are configurable:
- w1 = 0.35 (fundamental analysis)
- w2 = 0.30 (technical indicators)
- w3 = 0.20 (news sentiment)
- w4 = 0.15 (risk metrics)
```

#### 1. Fundamental Analysis (35% weight)
```python
def calculate_fundamental_score(ticker_data):
    score = 0

    # Value metrics
    if pe_ratio < sector_avg_pe * 0.8:
        score += 20
    if pb_ratio < 3.0:
        score += 15

    # Growth metrics
    if revenue_growth_yoy > 0.15:
        score += 15
    if earnings_growth_yoy > 0.20:
        score += 15

    # Financial health
    if debt_to_equity < 1.0:
        score += 10
    if current_ratio > 1.5:
        score += 10

    # Profitability
    if roe > 0.15:
        score += 10
    if profit_margin > 0.10:
        score += 10

    return min(score, 100)  # Cap at 100
```

#### 2. Technical Analysis (30% weight)
```python
def calculate_technical_score(indicators):
    score = 0

    # Trend
    if sma_20 > sma_50 > sma_200:
        score += 25  # Golden cross

    # Momentum
    if 30 < rsi_14 < 70:
        score += 20  # Healthy momentum
    elif rsi_14 < 30:
        score += 30  # Oversold (potential buy)

    # MACD
    if macd > macd_signal:
        score += 20  # Bullish signal

    # Bollinger Bands
    if close < bollinger_lower:
        score += 15  # Potential reversal

    # Volume confirmation
    if volume_sma_20 > volume_sma_50:
        score += 10  # Increasing volume

    return min(score, 100)
```

#### 3. Sentiment Analysis (20% weight)
```python
def calculate_sentiment_score(news_data):
    # Average sentiment from last 30 days news
    sentiment_avg = mean([article.sentiment for article in news_data])

    # Convert -1 to +1 scale to 0-100 scale
    score = (sentiment_avg + 1) * 50

    # Boost if recent news very positive
    if recent_7d_sentiment > 0.5:
        score += 10

    return min(score, 100)
```

#### 4. Risk Analysis (15% weight)
```python
def calculate_risk_score(historical_prices):
    # Lower risk = higher score
    volatility = std(daily_returns[-252:])  # Annual volatility
    max_drawdown = calculate_max_drawdown(historical_prices)
    beta = calculate_beta(historical_prices, market_index)

    score = 100

    # Penalize high volatility
    if volatility > 0.40:
        score -= 30
    elif volatility > 0.25:
        score -= 15

    # Penalize large drawdowns
    if max_drawdown < -0.50:
        score -= 30
    elif max_drawdown < -0.30:
        score -= 15

    # Penalize high beta (market sensitivity)
    if beta > 1.5:
        score -= 10

    return max(score, 0)
```

### Recommendation Output

**Final Classification:**
```python
if final_score >= 75:
    recommendation = "STRONG BUY"
elif final_score >= 60:
    recommendation = "BUY"
elif final_score >= 40:
    recommendation = "HOLD"
elif final_score >= 25:
    recommendation = "SELL"
else:
    recommendation = "STRONG SELL"
```

**Confidence Level:**
```python
# Based on data completeness and agreement between factors
confidence = calculate_confidence(
    data_completeness=0.95,  # % of required data available
    factor_agreement=0.80    # How aligned are the 4 factors
)
# confidence: HIGH (>80%), MEDIUM (50-80%), LOW (<50%)
```

### Celery Task Structure

```python
# src/tasks.py
from celery import Celery

app = Celery('financial_analyzer', broker='redis://redis:6379/0')

@app.task
def analyze_ticker(ticker: str) -> dict:
    """Generate recommendation for single ticker"""
    # Load data from database
    fundamentals = load_fundamentals(ticker)
    indicators = load_indicators(ticker)
    news = load_recent_news(ticker)
    prices = load_historical_prices(ticker)

    # Calculate scores
    fund_score = calculate_fundamental_score(fundamentals)
    tech_score = calculate_technical_score(indicators)
    sent_score = calculate_sentiment_score(news)
    risk_score = calculate_risk_score(prices)

    # Weighted final score
    final = (0.35*fund_score + 0.30*tech_score +
             0.20*sent_score + 0.15*risk_score)

    # Generate recommendation
    recommendation = classify_recommendation(final)
    confidence = calculate_confidence(...)

    # Save to database
    save_recommendation(ticker, recommendation, final, confidence)

    return {
        'ticker': ticker,
        'recommendation': recommendation,
        'score': final,
        'confidence': confidence,
        'breakdown': {
            'fundamental': fund_score,
            'technical': tech_score,
            'sentiment': sent_score,
            'risk': risk_score
        }
    }

@app.task
def batch_analyze(tickers: list[str]):
    """Analyze multiple tickers in parallel"""
    return group(analyze_ticker.s(t) for t in tickers)()
```

### Scheduling

**Airflow DAG:**
```python
# dag_generate_recommendations.py
dag = DAG(
    'generate_recommendations',
    schedule='0 22:00 * * *',  # Daily at 22:00 (after indicators)
    catchup=False
)

# Trigger Celery batch job
trigger_analysis = PythonOperator(
    task_id='trigger_celery_batch',
    python_callable=lambda: batch_analyze(get_all_tickers()).apply_async()
)
```

**On-Demand:**
```python
# Via API endpoint
@app.post("/api/v1/recommendations/generate")
async def generate_recommendation(ticker: str):
    task = analyze_ticker.delay(ticker)
    return {"task_id": task.id, "status": "processing"}
```

## Dependencies
**Prerequisites:**
- ✅ Phase 2 complete (data collection)
- ✅ Phase 3 complete (technical indicators)
- ⏳ Phase 6 complete (news & sentiment - optional initially)
- ⏳ Redis cluster deployed
- ⏳ Celery monitoring (Flower)

**Technology Stack:**
- **Celery** 5.3+
- **Redis** 7+ (broker + result backend)
- **Polars** (data processing)
- **scikit-learn** (ML models - future)
- **Python** 3.11+

## Implementation Plan

### Step 1: Core Algorithm (Weeks 1-2)
- Implement 4 scoring functions
- Unit tests with known-good examples
- Calibrate weights

### Step 2: Celery Integration (Week 3)
- Set up Celery workers
- Deploy Redis broker
- Create task definitions
- Test parallel execution

### Step 3: Database Integration (Week 4)
- Save recommendations to database
- Track recommendation history
- Performance tracking (how accurate are predictions?)

### Step 4: Airflow Orchestration (Week 5)
- Create daily recommendation DAG
- Integrate with existing workflows
- Error handling and retries

### Step 5: Testing & Validation (Week 6)
- Backtest recommendations against historical data
- Measure accuracy (% of BUY recommendations that went up)
- Tune weights and thresholds

### Step 6: Production Deployment (Week 7)
- Deploy to Kubernetes
- Set up monitoring (Flower dashboard)
- Documentation

## Performance Targets
- **Throughput:** 1000 tickers/minute (with 8 workers)
- **Latency:** <30 seconds per ticker
- **Accuracy:** >60% (BUY recommendations outperform market)
- **Resource Usage:** <500MB RAM per worker

## Monitoring
```python
# Celery Flower dashboard
http://192.168.1.240:30555

# Metrics to track:
- Tasks completed per hour
- Average task duration
- Worker utilization
- Failed task rate
- Recommendation accuracy (measured monthly)
```

## Timeline
- **Start Date:** After Phase 3 complete
- **Duration:** 7 weeks
- **Go-Live:** Q2 2025

## Success Metrics
- [ ] All 21,817 tickers analyzed daily
- [ ] <30 second average analysis time
- [ ] >60% recommendation accuracy (6-month horizon)
- [ ] Zero worker crashes
- [ ] Comprehensive recommendation history

## Related Documentation
- [Celery Documentation](https://docs.celeryq.dev/)
- [recommendation.py](src/recommendation.py) - Initial prototype
- [tasks.py](src/tasks.py) - Celery task definitions

## Notes
- Start simple with rule-based scoring
- Add ML models in Phase 7 (after 6 months of data)
- Consider ensemble methods (combine multiple models)
- Track recommendation performance for continuous improvement
- Add explainability (why this recommendation?)

**Last Updated:** 2025-10-28
