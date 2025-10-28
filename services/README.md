# Financial Screener Services

This directory contains all microservices that make up the Financial Screener platform. Each service has its own STATUS.md file explaining its purpose, implementation status, and timeline.

---

## Service Overview

### ✅ Production Services (Phase 2)

#### [data-collector](data-collector/)
**Status:** ✅ ACTIVE
**Purpose:** Collects fundamental and price data from EODHD API
**Tech Stack:** Python, Airflow, PostgreSQL, Kubernetes
**Daily Processing:** 21,817 tickers, ~27K API calls
**[Full Details →](data-collector/STATUS.md)**

---

### 🔜 Planned Services

#### [technical-analyzer](technical-analyzer/)
**Status:** 🔜 Phase 3 (Q1 2025)
**Purpose:** Calculate technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
**Tech Stack:** Polars, Python, Airflow
**Target Performance:** 21,817 tickers in <15 minutes
**[Full Details →](technical-analyzer/STATUS.md)**

#### [api](api/)
**Status:** 🔜 Phase 4 (Q1 2025)
**Purpose:** FastAPI REST/GraphQL API for querying and screening
**Tech Stack:** FastAPI, Strawberry GraphQL, Redis, PostgreSQL
**Target Performance:** 1000 req/sec, <100ms cached, <500ms database queries
**[Full Details →](api/STATUS.md)**

#### [analyzer](analyzer/)
**Status:** 🔜 Phase 4-6 (Q2 2025)
**Purpose:** Celery-based recommendation engine (buy/sell/hold)
**Tech Stack:** Celery, Polars, scikit-learn, Redis
**Algorithm:** Multi-factor scoring (fundamentals 35%, technical 30%, sentiment 20%, risk 15%)
**Target Performance:** 1000 tickers/minute, >60% accuracy
**[Full Details →](analyzer/STATUS.md)**

#### [news-fetcher](news-fetcher/)
**Status:** 🔜 Phase 6 (Q2-Q3 2025)
**Purpose:** Collect financial news from multiple sources
**Tech Stack:** Python, NewsAPI, RSS feeds, web scraping
**Target:** 500-1000 articles/day
**[Full Details →](news-fetcher/STATUS.md)**

#### [sentiment-engine](sentiment-engine/)
**Status:** 🔜 Phase 6 (Q3 2025)
**Purpose:** NLP sentiment analysis of financial news
**Tech Stack:** VADER, FinBERT, Celery, transformers
**Target Performance:** 500 articles/minute, >80% accuracy
**[Full Details →](sentiment-engine/STATUS.md)**

---

## Service Dependencies

```
                 React Frontend
                       ↓
                   API Service
                       ↓
         ┌─────────────┴─────────────┐
         │                           │
    PostgreSQL ←→ Redis      Celery (Analyzer)
         ↑                           ↑
         │                           │
         └───────┬──────────┬────────┘
                 │          │
         ┌───────┴────┐ ┌───┴───────────┐
         │            │ │               │
   data-collector  technical-analyzer  │
         ↑                              │
         │                              │
   ┌─────┴─────┐                  ┌────┴─────┐
   │           │                  │          │
news-fetcher  sentiment-engine    │          │
                                   └──────────┘
```

## Phase Timeline

| Phase | Services | Timeline | Status |
|-------|----------|----------|--------|
| **Phase 2** | data-collector | Oct 2024 | ✅ Complete |
| **Phase 3** | technical-analyzer | Q1 2025 | 📋 Planned |
| **Phase 4** | api, analyzer | Q1-Q2 2025 | 📋 Planned |
| **Phase 5** | frontend | Q2 2025 | 📋 Planned |
| **Phase 6** | news-fetcher, sentiment-engine | Q2-Q3 2025 | 📋 Planned |

---

## Development Standards

### Service Structure
Each service follows this standard structure:
```
service-name/
├── STATUS.md              ← Overview, timeline, implementation plan
├── Dockerfile             ← Container definition
├── requirements.txt       ← Python dependencies
├── src/
│   ├── main.py           ← Entry point
│   ├── config.py         ← Configuration
│   └── ...               ← Business logic
└── tests/
    └── ...               ← Unit and integration tests
```

### Testing Requirements
- Unit tests for all business logic
- Integration tests with database
- End-to-end tests for critical paths
- Minimum 80% code coverage

### Deployment Standards
- All services deployed to Kubernetes
- Resource limits defined (CPU, memory)
- Health checks configured
- Prometheus metrics exposed
- Structured logging to stdout

### Documentation Requirements
- STATUS.md with clear phase and timeline
- Inline code documentation (docstrings)
- API documentation (for api service)
- Deployment runbooks

---

## Getting Started

### For data-collector (ACTIVE)
```bash
# Build Docker image
cd data-collector
docker build -t financial-data-collector:latest .

# Run locally (requires DATABASE_URL and EODHD_API_KEY)
python src/main.py \
  --execution-id "manual_test" \
  --exchanges "NYSE" \
  --batch-size 10

# See full documentation
cat STATUS.md
```

### For future services
See individual STATUS.md files for implementation plans.

---

## Contributing

When adding a new service:
1. Create service directory following standard structure
2. Create STATUS.md with clear phase, purpose, and timeline
3. Follow existing patterns (Celery for async, Polars for data processing)
4. Add to this README.md
5. Update dependency diagram
6. Document in `.claude.md`

---

## Related Documentation
- [.claude.md](../.claude.md) - Complete project overview
- [PERFORMANCE_AND_STABILITY_ASSESSMENT.md](../docs/PERFORMANCE_AND_STABILITY_ASSESSMENT.md)
- [README.md](../README.md) - Main project README

**Last Updated:** 2025-10-28
