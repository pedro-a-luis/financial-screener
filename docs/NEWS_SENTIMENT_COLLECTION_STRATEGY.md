# News & Sentiment Data Collection Strategy

## Overview
Three EODHD APIs provide comprehensive news and sentiment data for market analysis and screening.

## API Sources

### 1. Financial News API
- **Endpoint**: `GET https://eodhd.com/api/news`
- **Data**: News articles with titles, content, links, symbols, tags, and sentiment scores
- **Update Frequency**: Real-time (new articles appear constantly)
- **Collection Strategy**:
  - Historical: Last 30 days for all tickers
  - Incremental: Daily fetch of new articles (last 24 hours)
- **Database**: `news_articles` table
- **Key Fields**: title, content, published_date, sentiment_score, tags[], symbols[]

### 2. Sentiment Data API
- **Endpoint**: `GET https://eodhd.com/api/sentiments`
- **Data**: Aggregated daily sentiment scores (-1 to +1) from news + social media
- **Update Frequency**: Daily aggregation
- **Collection Strategy**:
  - Historical: Last 90 days for all tickers
  - Incremental: Daily update (yesterday's sentiment)
- **Database**: `sentiment_summary` table
- **Key Fields**: avg_sentiment_score, total_articles, positive/neutral/negative counts

### 3. News Word Weights API
- **Endpoint**: `GET https://eodhd.com/api/news-word-weights`
- **Data**: AI-powered keyword analysis with weighted relevance scores
- **Update Frequency**: On-demand (computationally expensive)
- **Collection Strategy**:
  - Historical: Skip (too slow for bulk)
  - Incremental: Weekly analysis for top 100 trending tickers
- **Database**: New table needed: `news_keywords`
- **Key Fields**: ticker, date_range, keywords (JSONB), news_processed count

## Collection Approach

### News Articles (API #1)
**Historical Load** (ONE-TIME):
- Fetch last 30 days of articles for all 5,000+ tickers
- Batch by 50 tickers per API call
- ~100 API calls (50 tickers × 2 calls for US/International)
- Store: title, content, sentiment, tags, symbols

**Incremental Load** (DAILY):
- Fetch articles from last 24 hours
- Single API call per ticker with `from=yesterday`
- ~5,000 API calls daily
- Filter out duplicates by URL

### Sentiment Scores (API #2)
**Historical Load** (ONE-TIME):
- Fetch last 90 days of aggregated sentiment
- Batch multiple tickers in single call: `s=AAPL.US,MSFT.US,GOOGL.US`
- ~50 API calls (100 tickers per call × 50 batches)
- Store: daily sentiment scores with article counts

**Incremental Load** (DAILY):
- Fetch yesterday's sentiment for all tickers
- Batch 100 tickers per call
- ~50 API calls daily
- Upsert into `sentiment_summary`

### Keyword Analysis (API #3)
**No Historical Load** (too slow for bulk):
- Skip initial load (AI processing takes time)

**Incremental Load** (WEEKLY):
- Analyze top 100 tickers by:
  - Trading volume
  - Price change %
  - News article count
- Fetch keywords for last 7 days
- ~100 API calls weekly
- Store weighted keywords in JSONB

## DAG Structure

| DAG | Schedule | API | Purpose |
|-----|----------|-----|---------|
| **dag_05_historical_news** | Manual (ONE-TIME) | News API | 30 days articles |
| **dag_06_incremental_news** | Daily 23:00 UTC | News API | Last 24h articles |
| **dag_07_historical_sentiment** | Manual (ONE-TIME) | Sentiment API | 90 days scores |
| **dag_08_incremental_sentiment** | Daily 23:30 UTC | Sentiment API | Yesterday's scores |
| **dag_09_weekly_keywords** | Weekly Sunday 03:00 UTC | Keywords API | Top 100 tickers |

## Database Schema Updates Needed

### New Table: `news_keywords`
```sql
CREATE TABLE news_keywords (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id),
    ticker VARCHAR(20) NOT NULL,
    date_from DATE NOT NULL,
    date_to DATE NOT NULL,
    keywords JSONB NOT NULL,  -- {word: weight, ...}
    news_processed INTEGER,
    news_found INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ticker, date_from, date_to)
);
CREATE INDEX idx_news_keywords_ticker ON news_keywords(ticker);
CREATE INDEX idx_news_keywords_dates ON news_keywords(date_from, date_to);
```

### Update `news_articles` Table
Add columns if missing:
- `symbols` TEXT[] - Array of tickers mentioned
- `tags` TEXT[] - Article topic tags
- `sentiment_polarity` NUMERIC - Detailed sentiment (-1 to 1)
- `sentiment_neg` NUMERIC - Negative score
- `sentiment_neu` NUMERIC - Neutral score  
- `sentiment_pos` NUMERIC - Positive score
- `link` VARCHAR(500) - Article URL (for deduplication)

## API Call Estimates

### Historical Loads (ONE-TIME):
- News (30 days): ~100 calls
- Sentiment (90 days): ~50 calls
- **Total**: 150 calls

### Daily Operations:
- News (24h): ~5,000 calls
- Sentiment (yesterday): ~50 calls
- **Daily Total**: ~5,050 calls

### Weekly Operations:
- Keywords (top 100): ~100 calls

## Implementation Priority

1. ✅ **Phase 1**: Update database schema (add news_keywords table)
2. ✅ **Phase 2**: Create EODHD news/sentiment fetchers
3. ✅ **Phase 3**: Create dag_05 & dag_07 (historical loads)
4. ✅ **Phase 4**: Create dag_06 & dag_08 (daily incrementals)
5. ⏳ **Phase 5**: Create dag_09 (weekly keywords - optional)

## Benefits

### For Screening:
- Filter stocks by sentiment trends (improving/declining)
- Find stocks with negative sentiment but strong fundamentals (value plays)
- Identify stocks with high media attention (momentum plays)

### For Analysis:
- Correlate sentiment with price movements
- Track keyword trends over time
- Detect sentiment divergence (news vs price action)

### For Alerts:
- Alert on sudden sentiment drops
- Alert on high-volume keywords (e.g., "lawsuit", "merger", "bankruptcy")
- Alert on sentiment-price divergence

## Next Steps

1. Review and approve this strategy
2. Create database migration for `news_keywords` table
3. Implement EODHD news/sentiment fetchers in data-collector
4. Create DAGs 05-09
5. Test with sample tickers
6. Run historical loads
7. Enable incremental DAGs
