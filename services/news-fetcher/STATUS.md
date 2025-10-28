# News Fetcher Service

**Status:** 🔜 **PLANNED** (Phase 6 - Q2-Q3 2025)

## Purpose
Collect financial news articles from multiple sources for sentiment analysis and contextual recommendations.

## Planned Implementation

### Architecture
- **Collection Method:** Scheduled scraping + RSS feeds + News APIs
- **Storage:** PostgreSQL (`news_articles` table)
- **Orchestration:** Airflow DAG (hourly execution)
- **Deployment:** Kubernetes CronJob

### Data Sources

**Tier 1: Paid APIs (High Quality)**
1. **NewsAPI.org**
   - Coverage: Global financial news
   - Cost: $449/month (Business plan)
   - Rate Limit: 250 requests/day
   -
2. **Alpha Vantage News Sentiment API**
   - Coverage: Real-time news with pre-calculated sentiment
   - Cost: Included in Premium plan ($49.99/month)
   - Rate Limit: 1000 requests/day

**Tier 2: Free RSS Feeds**
1. **Yahoo Finance RSS**
   - Coverage: Major stocks, market news
   - Cost: Free
   - Rate Limit: None (reasonable use)

2. **Financial Times RSS**
   - Coverage: Global markets, business news
   - Cost: Free for RSS
   - Rate Limit: None

3. **Reuters Business RSS**
   - Coverage: Breaking financial news
   - Cost: Free
   - Rate Limit: None

**Tier 3: Web Scraping (Last Resort)**
- Bloomberg headlines (public pages only)
- CNBC articles
- MarketWatch
- **Note:** Respect robots.txt, use polite scraping

### Database Schema

```sql
CREATE TABLE news_articles (
    id BIGSERIAL PRIMARY KEY,

    -- Source info
    source VARCHAR(100) NOT NULL,           -- 'newsapi', 'yahoo_rss', 'reuters'
    source_url TEXT NOT NULL UNIQUE,

    -- Content
    title TEXT NOT NULL,
    description TEXT,
    content TEXT,
    author VARCHAR(255),

    -- Metadata
    published_at TIMESTAMP NOT NULL,
    fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Relevance
    tickers VARCHAR(20)[],                  -- Array of related tickers
    categories VARCHAR(50)[],               -- ['earnings', 'merger', 'ipo']

    -- Sentiment (calculated by sentiment-engine service)
    sentiment_score DECIMAL(3,2),           -- -1.00 to +1.00
    sentiment_label VARCHAR(20),            -- 'positive', 'neutral', 'negative'
    sentiment_confidence DECIMAL(3,2),      -- 0.00 to 1.00

    -- Full-text search
    search_vector tsvector,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_news_published ON news_articles(published_at DESC);
CREATE INDEX idx_news_tickers ON news_articles USING GIN(tickers);
CREATE INDEX idx_news_sentiment ON news_articles(sentiment_score) WHERE sentiment_score IS NOT NULL;
CREATE INDEX idx_news_search ON news_articles USING GIN(search_vector);
```

### Collection Strategy

**Hourly DAG:**
```python
# dag_fetch_news.py
from airflow import DAG
from airflow.operators.python import PythonOperator

dag = DAG(
    'fetch_news',
    schedule='0 * * * *',  # Every hour
    catchup=False
)

# Tier 1: Paid APIs (most reliable)
fetch_newsapi = PythonOperator(
    task_id='fetch_newsapi',
    python_callable=fetch_from_newsapi,
    op_kwargs={'keywords': ['stocks', 'earnings', 'merger', 'ipo']}
)

fetch_alphavantage_news = PythonOperator(
    task_id='fetch_alphavantage',
    python_callable=fetch_from_alphavantage,
    op_kwargs={'tickers': get_watchlist_tickers()}  # Top 100 most followed
)

# Tier 2: Free RSS feeds
fetch_yahoo_rss = PythonOperator(
    task_id='fetch_yahoo_rss',
    python_callable=fetch_rss_feed,
    op_kwargs={'url': 'https://finance.yahoo.com/news/rssindex'}
)

fetch_reuters_rss = PythonOperator(
    task_id='fetch_reuters_rss',
    python_callable=fetch_rss_feed,
    op_kwargs={'url': 'https://www.reutersagency.com/feed/'}
)

# Deduplicate and enrich
deduplicate = PythonOperator(
    task_id='deduplicate',
    python_callable=remove_duplicate_articles,
    trigger_rule='all_done'  # Run even if some sources fail
)

extract_tickers = PythonOperator(
    task_id='extract_tickers',
    python_callable=extract_ticker_mentions
)

# Trigger sentiment analysis
trigger_sentiment = PythonOperator(
    task_id='trigger_sentiment',
    python_callable=lambda: analyze_articles.delay()  # Celery task
)

# Dependencies
[fetch_newsapi, fetch_alphavantage_news, fetch_yahoo_rss, fetch_reuters_rss] >> deduplicate >> extract_tickers >> trigger_sentiment
```

### Ticker Extraction

```python
import re

def extract_ticker_mentions(article_text: str) -> list[str]:
    """Extract ticker symbols from article text"""
    tickers = []

    # Pattern: $AAPL, AAPL:US, AAPL.US
    patterns = [
        r'\$([A-Z]{1,5})\b',        # $AAPL
        r'\b([A-Z]{1,5})\.US\b',    # AAPL.US
        r'\b([A-Z]{1,5}):US\b',     # AAPL:US
    ]

    for pattern in patterns:
        matches = re.findall(pattern, article_text)
        tickers.extend(matches)

    # Validate against known tickers in database
    valid_tickers = validate_tickers(tickers)

    return list(set(valid_tickers))  # Deduplicate
```

### Rate Limiting & Quotas

```python
# src/rate_limiter.py
from redis import Redis
import time

class RateLimiter:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    def check_limit(self, source: str, limit: int, window_seconds: int):
        """Check if we're within rate limit"""
        key = f"news_fetcher:rate:{source}"
        current = self.redis.incr(key)

        if current == 1:
            self.redis.expire(key, window_seconds)

        if current > limit:
            ttl = self.redis.ttl(key)
            raise RateLimitExceeded(f"Rate limit exceeded. Retry in {ttl}s")

        return True

# Usage
rate_limiter = RateLimiter(redis_client)
rate_limiter.check_limit('newsapi', limit=250, window_seconds=86400)  # 250/day
```

## Dependencies
**Prerequisites:**
- ✅ PostgreSQL schema (table already exists)
- ⏳ News API subscriptions
- ⏳ sentiment-engine service (for sentiment analysis)
- ⏳ Redis (for rate limiting)

**Technology Stack:**
- Python 3.11+
- `requests` + `beautifulsoup4` (scraping)
- `feedparser` (RSS feeds)
- `newspaper3k` (article extraction)
- Redis (rate limiting)
- PostgreSQL (storage)

## Implementation Plan

### Step 1: API Integrations (Week 1)
- Implement NewsAPI.org client
- Implement Alpha Vantage news client
- Add rate limiting

### Step 2: RSS Feed Parsing (Week 2)
- Yahoo Finance RSS parser
- Reuters RSS parser
- FT RSS parser
- Deduplica tion logic

### Step 3: Ticker Extraction (Week 3)
- Regex-based extraction
- Validation against database
- Company name → ticker mapping

### Step 4: Web Scraping (Week 4 - Optional)
- Bloomberg scraper (polite, robots.txt compliant)
- CNBC scraper
- Rate limiting and retries

### Step 5: Airflow Integration (Week 5)
- Create hourly DAG
- Error handling
- Monitoring and alerts

### Step 6: Testing & Deployment (Week 6)
- Unit tests
- Integration tests
- Production deployment

## Performance Targets
- **Collection Rate:** 500-1000 articles/day
- **Latency:** <5 minutes from publication to database
- **Deduplication Accuracy:** >95%
- **Ticker Extraction Accuracy:** >80%

## Monitoring
```sql
-- Articles collected today
SELECT source, COUNT(*) as articles
FROM news_articles
WHERE fetched_at >= CURRENT_DATE
GROUP BY source;

-- Average sentiment by source
SELECT source,
       AVG(sentiment_score) as avg_sentiment,
       COUNT(*) as articles
FROM news_articles
WHERE published_at >= NOW() - INTERVAL '7 days'
  AND sentiment_score IS NOT NULL
GROUP BY source;

-- Most mentioned tickers (last 24h)
SELECT ticker, COUNT(*) as mentions
FROM news_articles,
     UNNEST(tickers) as ticker
WHERE published_at >= NOW() - INTERVAL '24 hours'
GROUP BY ticker
ORDER BY mentions DESC
LIMIT 20;
```

## Timeline
- **Start Date:** After Phase 4 complete (API + Analyzer)
- **Duration:** 6 weeks
- **Go-Live:** Q3 2025

## Success Metrics
- [ ] 500+ articles/day collected
- [ ] <5 minute latency from publication
- [ ] >95% deduplication accuracy
- [ ] >80% ticker extraction accuracy
- [ ] Zero API quota violations

## Related Documentation
- [NewsAPI Documentation](https://newsapi.org/docs)
- [Alpha Vantage News API](https://www.alphavantage.co/documentation/#news-sentiment)

## Notes
- Start with Tier 2 (free sources) for MVP
- Add Tier 1 (paid APIs) for production quality
- Consider using NER (Named Entity Recognition) for better ticker extraction
- Add article categorization (earnings, merger, IPO, etc.)
- Store raw HTML for potential reprocessing

**Last Updated:** 2025-10-28
