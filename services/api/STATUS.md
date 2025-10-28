# API Service

**Status:** 🔜 **PLANNED** (Phase 4 - Q1 2025)

## Purpose
FastAPI-based REST and GraphQL API for querying financial data, running screens, and generating buy/sell recommendations.

## Planned Implementation

### Architecture
- **Framework:** FastAPI (async Python)
- **API Styles:** REST + GraphQL (via Strawberry)
- **Authentication:** JWT tokens
- **Rate Limiting:** Redis-based (per-user quotas)
- **Caching:** Three-tier (Redis → PostgreSQL → Compute)
- **Deployment:** Kubernetes Deployment (3 replicas)

### Core Endpoints

#### 1. Asset Data
```
GET  /api/v1/assets                    # List all assets
GET  /api/v1/assets/{ticker}           # Get single asset
GET  /api/v1/assets/{ticker}/prices    # Historical prices
GET  /api/v1/assets/{ticker}/fundamentals
GET  /api/v1/assets/{ticker}/indicators
```

#### 2. Screening
```
POST /api/v1/screens                   # Run custom screen
GET  /api/v1/screens/presets           # List preset screens
GET  /api/v1/screens/presets/{id}      # Run preset screen
```

Example screen query:
```json
{
  "filters": {
    "market_cap": {"min": 1000000000},
    "pe_ratio": {"max": 20},
    "rsi_14": {"min": 30, "max": 70},
    "sector": {"in": ["Technology", "Healthcare"]}
  },
  "sort": {"field": "market_cap", "order": "desc"},
  "limit": 50
}
```

#### 3. Recommendations
```
GET  /api/v1/recommendations           # Latest recommendations
GET  /api/v1/recommendations/{ticker}  # Ticker-specific
POST /api/v1/recommendations/generate  # Trigger regeneration
```

#### 4. Portfolio
```
GET  /api/v1/portfolio                 # User portfolio
POST /api/v1/portfolio/import          # Import from DEGIRO CSV
GET  /api/v1/portfolio/analysis        # Portfolio-level recommendations
```

#### 5. Watchlists
```
GET  /api/v1/watchlists                # User watchlists
POST /api/v1/watchlists                # Create watchlist
POST /api/v1/watchlists/{id}/tickers   # Add ticker to watchlist
```

### GraphQL Schema
```graphql
type Asset {
  ticker: String!
  name: String!
  exchange: String!
  sector: String
  marketCap: Float
  peRatio: Float
  prices(from: Date, to: Date): [Price!]!
  indicators(from: Date, to: Date): [TechnicalIndicator!]!
  recommendation: Recommendation
}

type Query {
  asset(ticker: String!): Asset
  screen(filters: ScreenInput!): [Asset!]!
  recommendations(limit: Int): [Recommendation!]!
}
```

### Technology Stack
- **FastAPI** 0.100+
- **Strawberry** (GraphQL for Python)
- **Pydantic** v2 (data validation)
- **SQLAlchemy** 2.0+ (ORM with async support)
- **asyncpg** (PostgreSQL async driver)
- **Redis** 7+ (caching + rate limiting)
- **JWT** (authentication)

### Performance Targets
- **Response Time:** <100ms for cached queries
- **Response Time:** <500ms for database queries
- **Throughput:** 1000 req/sec per replica
- **Concurrency:** Handle 100 concurrent connections per replica

### Caching Strategy

**Three-tier caching:**
```
Request → Redis Cache (TTL: 5min)
            ↓ (miss)
         PostgreSQL Materialized Views (refresh: 1hr)
            ↓ (miss)
         Real-time Query (cache result)
```

**Cache Keys:**
- Asset data: `asset:{ticker}` (TTL: 1 hour)
- Screen results: `screen:{hash}` (TTL: 5 minutes)
- Recommendations: `rec:{ticker}` (TTL: 24 hours)

## Dependencies
**Prerequisites:**
- ✅ Phase 2 complete (data collection)
- ✅ Phase 3 complete (technical indicators)
- ⏳ Database views created for common queries
- ⏳ Redis cluster deployed

**Required Services:**
- PostgreSQL (read replicas recommended)
- Redis (cluster mode for HA)
- Celery workers (for async recommendation generation)

## Implementation Plan

### Step 1: Core API (Weeks 1-2)
- FastAPI project structure
- Asset CRUD endpoints
- Authentication middleware
- Database connection pooling
- Basic error handling

### Step 2: Screening Engine (Weeks 3-4)
- Query builder for complex filters
- Preset screens (value, growth, momentum)
- Optimization with database indexes
- Result caching

### Step 3: GraphQL Integration (Week 5)
- Strawberry schema definition
- DataLoader for N+1 prevention
- Query complexity limits
- Subscription support (future: WebSockets)

### Step 4: Recommendations Integration (Week 6)
- Integrate with analyzer service (Celery)
- Async recommendation generation
- Real-time updates via WebSocket

### Step 5: Testing & Deployment (Week 7)
- Unit tests (pytest + httpx)
- Integration tests with database
- Load testing (Locust)
- Production deployment

## API Documentation
- **OpenAPI:** Auto-generated at `/docs` (Swagger UI)
- **ReDoc:** Available at `/redoc`
- **GraphQL Playground:** Available at `/graphql`

## Security Features
- JWT authentication
- Rate limiting (per-user + global)
- Input validation (Pydantic)
- SQL injection prevention (SQLAlchemy)
- CORS configuration
- API key authentication (for programmatic access)

## Monitoring
- Prometheus metrics (`/metrics`)
- Request/response logging
- Slow query detection
- Error tracking (Sentry integration planned)

## Timeline
- **Start Date:** After Phase 3 complete
- **Duration:** 7 weeks
- **Go-Live:** Q2 2025

## Success Metrics
- [ ] 99.9% uptime
- [ ] <100ms average response time (cached)
- [ ] <500ms average response time (database)
- [ ] Zero security vulnerabilities
- [ ] API documentation complete
- [ ] 100% test coverage for core endpoints

## Related Documentation
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Strawberry GraphQL](https://strawberry.rocks/)

## Notes
- Consider using Alembic for API-side schema management
- Implement graceful degradation if analyzer service down
- Add OpenTelemetry for distributed tracing
- Plan for API versioning (v1, v2)

**Last Updated:** 2025-10-28
