# Financial Screener - Kubernetes-Native Financial Analysis Agent

A comprehensive financial analysis system designed to run on a Raspberry Pi K3s cluster. This system tracks, analyzes, and provides buy/sell recommendations for stocks, ETFs, and bonds using **Polars** for high-performance data processing and **Celery** for distributed task execution.

## Features

- **Multi-Asset Support**: Stocks, ETFs, and Bonds with asset-specific screening criteria
- **High-Performance Processing**: Polars DataFrame library (2-10x faster than Pandas, 50% less memory)
- **Distributed Analysis**: Celery workers across 8 Raspberry Pi nodes for parallel processing
- **News & Sentiment Analysis**: Real-time news aggregation from multiple sources with NLP sentiment scoring
- **Buy/Sell Recommendations**: Actionable investment guidance based on fundamentals, sentiment, technicals, and risk
- **Portfolio Management**: DEGIRO CSV import, holdings tracking, and portfolio-level recommendations
- **Modern Web UI**: React + TypeScript + Material-UI dashboard with real-time updates
- **Smart Caching**: Three-tier caching strategy (PostgreSQL, Redis, Frontend) to minimize API calls
- **ARM64 Optimized**: Native support for Raspberry Pi architecture with Rust-based Polars

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      React Web Dashboard                        │
│         (TypeScript + Material-UI + Redux + React Query)        │
└────────────────────────┬────────────────────────────────────────┘
                         │ REST API
┌────────────────────────▼────────────────────────────────────────┐
│                     FastAPI Service                              │
│              (Async Python + Pydantic + SQLAlchemy)             │
└─┬──────────────────┬──────────────────┬────────────────────────┘
  │                  │                  │
  ├──────────────────┼──────────────────┤
  │                  │                  │
┌─▼─────────┐  ┌────▼──────┐  ┌───────▼────────────────────────┐
│PostgreSQL │  │   Redis   │  │  Celery Workers (×8 Pis)       │
│(Cold Data)│  │(Warm Cache│  │  Each worker: Polars + Analysis│
│           │  │  + Queue) │  │  Distributed task processing   │
└───────────┘  └───────────┘  └────────────────────────────────┘
     ▲              ▲                ▲
     │              │                │
┌────┴──────────────┴────────────────┴───────────────────┐
│           Data Collection Services (CronJobs)           │
│  ┌─────────────────┐  ┌────────────────────────────┐  │
│  │ Data Collector  │  │     News Fetcher            │  │
│  │(yfinance+Polars)│  │  (Multiple Sources)         │  │
│  └─────────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Why Polars + Celery?

**Polars** is a blazingly fast DataFrame library written in Rust that:
- ✅ Runs 2-10x faster than Pandas on Raspberry Pi
- ✅ Uses 50% less memory (critical for 8GB nodes)
- ✅ Automatically parallelizes across all CPU cores
- ✅ Has perfect ARM64 support (no JVM overhead like Spark)
- ✅ Supports lazy evaluation for query optimization

**Celery** distributes work across your 8-node cluster:
- ✅ Simple task queue using Redis as broker
- ✅ Each Pi processes batches in parallel
- ✅ Easy monitoring and error handling
- ✅ No complex cluster management like Spark

**Result**: Simpler, faster, and more efficient than PySpark for this workload.

## Technology Stack

### Backend
- **Python 3.11+**: Main programming language
- **Polars**: High-performance DataFrame library (Rust-based)
- **Celery**: Distributed task queue
- **FastAPI**: Modern, fast web framework
- **yfinance**: Stock/ETF/Bond data collection
- **TextBlob/VADER**: Sentiment analysis
- **PostgreSQL 16**: Persistent data storage
- **Redis 7**: Caching and job queue
- **SQLAlchemy**: ORM and database migrations

### Frontend
- **React 18+**: UI framework
- **TypeScript**: Type-safe JavaScript
- **Material-UI (MUI v5)**: Component library
- **Redux Toolkit**: State management
- **React Query**: Data fetching and caching
- **Recharts**: Data visualization
- **Vite**: Build tool

### Infrastructure
- **K3s**: Lightweight Kubernetes
- **Docker**: Containerization (ARM64)
- **Spark Operator**: Spark on Kubernetes
- **NFS CSI**: Persistent storage

## Target Hardware

- **Cluster**: 8× Raspberry Pi 5 (8GB RAM each)
- **Architecture**: ARM64 (aarch64)
- **Kubernetes**: K3s v1.32.2+k3s1
- **Master Node**: 192.168.1.240
- **Worker Nodes**: 192.168.1.241-247
- **Storage**: Synology DS118 NFS (192.168.1.10)

## Project Structure

```
financial-screener/
├── services/              # Microservices
│   ├── data-collector/    # Stock/ETF/Bond data fetching (CronJob, Polars)
│   ├── news-fetcher/      # News aggregation service (CronJob)
│   ├── analyzer/          # Celery workers - analysis engine (Polars)
│   ├── sentiment-engine/  # Sentiment analysis (TextBlob/VADER)
│   └── api/               # FastAPI REST service
├── frontend/              # React web dashboard
│   ├── src/
│   │   ├── components/    # Reusable UI components
│   │   ├── pages/         # Page-level components
│   │   ├── store/         # Redux state management
│   │   ├── services/      # API client
│   │   └── types/         # TypeScript definitions
│   └── public/            # Static assets
├── shared/                # Shared Python libraries
│   ├── models/            # Common data models
│   ├── database/          # Database utilities
│   ├── cache/             # Redis utilities
│   └── utils/             # Common utilities
├── kubernetes/            # Kubernetes manifests
│   ├── base/              # Base configurations
│   └── overlays/          # Environment-specific overlays
├── database/              # Database scripts
│   ├── migrations/        # SQL migration scripts
│   └── seeds/             # Seed data
├── docs/                  # Documentation
├── scripts/               # Utility scripts
└── .github/               # CI/CD workflows
```

## Asset Types Supported

### Stocks (Equities)
- Individual company stocks
- Common and preferred shares
- ADRs (American Depositary Receipts)

**Screening Criteria**:
- Value Metrics: P/E, P/B, PEG, Price/Sales, EV/EBITDA
- Quality: ROE, ROA, Profit Margins, ROIC
- Financial Health: Debt/Equity, Current Ratio, Free Cash Flow
- Growth: Revenue/Earnings CAGR, YoY growth
- Momentum: RSI, MACD, Moving Averages
- Dividend: Yield, Payout Ratio, Growth Rate

### ETFs (Exchange-Traded Funds)
- Equity ETFs
- Bond ETFs
- Commodity ETFs
- Sector/Industry ETFs
- International/Regional ETFs

**Screening Criteria**:
- Cost: Expense Ratio, Tracking Error
- Performance: Total Return, Sharpe Ratio
- Size: AUM, Average Volume
- Holdings: Top 10 Concentration, Diversification
- Tax Efficiency: Distribution Frequency

### Bonds (Fixed Income)
- Government bonds (Treasury, Municipal)
- Corporate bonds
- Bond ETFs
- Inflation-protected securities (TIPS)

**Screening Criteria**:
- Yield: YTM, Current Yield, Yield to Call
- Duration: Macaulay, Modified, Effective Duration
- Credit: Rating, Spread, Probability of Default
- Maturity: Time to Maturity, Call Provisions
- Income: Coupon Rate, Payment Frequency

## Buy/Sell Recommendation System

The system generates comprehensive recommendations based on:

1. **Fundamental Analysis** (40% weight): Financial metrics and ratios
2. **Sentiment Analysis** (30% weight): News sentiment from multiple sources
3. **Technical Analysis** (20% weight): Price momentum and indicators
4. **Risk Assessment** (10% weight): Volatility, beta, drawdown

**Recommendation Levels**:
- **STRONG BUY** 🚀 (8.5-10.0): Exceptional opportunity
- **BUY** 📈 (7.0-8.5): Good entry point
- **HOLD** ⏸️ (5.0-7.0): Maintain position
- **SELL** 📉 (3.0-5.0): Reduce exposure
- **STRONG SELL** ⚠️ (0.0-3.0): Exit position

## Data Strategy

### Three-Tier Caching Architecture

1. **Cold Storage (PostgreSQL)**
   - 5 years of daily price data
   - 10 years of quarterly fundamentals
   - Complete news and sentiment archive

2. **Warm Cache (Redis)**
   - Today's prices (TTL: 1h-24h)
   - Screening results (TTL: 24h)
   - Asset details (TTL: 4h)
   - User portfolios (TTL: 1h)

3. **Hot Cache (Frontend)**
   - Currently viewed data
   - Active filters and results
   - User session data

### Data Loading Philosophy

- **Initial Load**: One-time bulk historical download (2-5 years)
- **Incremental Updates**: Daily fetches for new data only
- **Smart Fetching**: Check cache → database → API (in that order)
- **Batch Processing**: Process 100 stocks per batch

### CronJob Schedules (UTC)

| Job | Schedule | Purpose |
|-----|----------|---------|
| daily-price-update | 2 AM | Fetch yesterday's OHLCV |
| daily-fundamentals-check | 3 AM | Update quarterly data if available |
| daily-bond-update | 3:15 AM | Bond yields and ratings |
| news-fetch-portfolio | Every 30 min | News for holdings |
| sentiment-analysis | Every 2 hours | NLP sentiment scoring |
| trending-news | Every 4 hours | Market-wide trends |
| weekly-validation | Sunday 4 AM | Data quality check |
| monthly-etf-holdings | 1st of month | ETF holdings refresh |
| quarterly-fundamentals | 1st of quarter | Full fundamental refresh |

## Quick Start

### Prerequisites

```bash
# Raspberry Pi K3s cluster running
# kubectl configured to access cluster
# NFS storage provisioned

# Verify cluster access
kubectl get nodes

# Should show:
# NAME            STATUS   ROLES                  AGE   VERSION
# rpi-master      Ready    control-plane,master   Xd    v1.32.2+k3s1
# rpi-worker-01   Ready    <none>                 Xd    v1.32.2+k3s1
# rpi-worker-02   Ready    <none>                 Xd    v1.32.2+k3s1
# ...
```

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/financial-screener.git
cd financial-screener

# Create namespace
kubectl create namespace financial-screener

# Deploy PostgreSQL and Redis
kubectl apply -k kubernetes/overlays/production

# Build and push Docker images (from a machine with Docker)
./scripts/build-and-push.sh

# Deploy application services
kubectl apply -k kubernetes/overlays/production

# Verify deployment
kubectl get pods -n financial-screener

# Access the web UI
# Port forward or configure ingress
kubectl port-forward -n financial-screener svc/frontend 3000:80

# Open browser to http://localhost:3000
```

### Local Development

#### Backend Services

```bash
# Set up Python virtual environment
cd services/api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql://user:pass@localhost:5432/financial_db
export REDIS_URL=redis://localhost:6379/0

# Run database migrations
alembic upgrade head

# Start API server
uvicorn main:app --reload --port 8000

# API will be available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

#### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Frontend will be available at http://localhost:5173
```

## API Endpoints

### Screening

- `GET /api/screen?strategy=value&limit=20` - Screen stocks by strategy
- `GET /api/screen?asset_type=etf&recommendation=STRONG_BUY` - Filter by type and recommendation

### Stock Details

- `GET /api/ticker/{symbol}` - Get detailed analysis
- `GET /api/ticker/{symbol}/recommendation` - Get recommendation with reasoning
- `GET /api/ticker/{symbol}/news` - Get news articles
- `GET /api/ticker/{symbol}/sentiment` - Get sentiment analysis

### Portfolio

- `GET /api/portfolio` - Get portfolio holdings
- `GET /api/portfolio/recommendations` - Get recommendations for all holdings
- `GET /api/portfolio/actions` - Get suggested portfolio actions
- `GET /api/portfolio/news` - Aggregated news for holdings
- `POST /api/portfolio/import-degiro` - Import DEGIRO CSV

### News & Sentiment

- `GET /api/news/trending` - Trending financial news
- `GET /api/sentiment/summary` - Overall market sentiment

### Health

- `GET /api/health` - Service health check

Full API documentation available at `/docs` when running the API service.

## Configuration

### Environment Variables

Create a `.env` file in each service directory:

```bash
# Database
DATABASE_URL=postgresql://financial:password@postgres:5432/financial_db

# Redis
REDIS_URL=redis://redis:6379/0

# API Keys (free tiers)
ALPHA_VANTAGE_API_KEY=your_key_here
NEWS_API_KEY=your_key_here

# Application
LOG_LEVEL=INFO
ENVIRONMENT=production

# Kubernetes (if running locally)
KUBECONFIG=/path/to/kubeconfig
```

### Customization

Screening weights and thresholds can be customized in the web UI or via API.

## Development Guidelines

See [.clauderc](./.clauderc) for comprehensive development guidelines including:
- KISS and YAGNI principles
- Modular building blocks approach
- Coding standards (Python, TypeScript, SQL)
- Performance optimization
- Testing strategy
- Security considerations

## Monitoring

```bash
# Check pod status
kubectl get pods -n financial-screener

# View logs
kubectl logs -f deployment/api -n financial-screener
kubectl logs -f deployment/spark-analyzer -n financial-screener

# Check Spark jobs
kubectl get sparkapplications -n financial-screener

# Monitor resource usage
kubectl top pods -n financial-screener
kubectl top nodes
```

## Troubleshooting

### Data Collector Not Running

```bash
# Check CronJob status
kubectl get cronjobs -n financial-screener

# Manually trigger a job
kubectl create job --from=cronjob/data-collector manual-run-1 -n financial-screener

# Check job logs
kubectl logs job/manual-run-1 -n financial-screener
```

### API Not Responding

```bash
# Check API pod
kubectl get pod -l app=api -n financial-screener

# View logs
kubectl logs -f deployment/api -n financial-screener

# Check database connection
kubectl exec -it deployment/api -n financial-screener -- python -c "from database import test_connection; test_connection()"
```

### Spark Jobs Failing

```bash
# Check Spark operator
kubectl get pods -n spark-operator

# View Spark application status
kubectl describe sparkapplication screening-job -n financial-screener

# Check driver logs
kubectl logs -l spark-role=driver -n financial-screener
```

## Performance Tuning

### Database

```sql
-- Check query performance
EXPLAIN ANALYZE SELECT * FROM stock_prices WHERE ticker = 'AAPL' ORDER BY date DESC LIMIT 30;

-- Vacuum database
VACUUM ANALYZE;

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;
```

### Redis

```bash
# Check Redis memory usage
redis-cli INFO memory

# Clear cache if needed
redis-cli FLUSHDB
```

### Spark

Adjust executor memory and cores in `kubernetes/base/spark-analyzer/spark-application.yaml`:

```yaml
spec:
  executor:
    memory: "2g"  # Increase if needed (watch RAM usage)
    cores: 2       # Increase for faster processing
    instances: 6   # Adjust based on cluster size
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Follow the coding standards in `.clauderc`
4. Write tests for new functionality
5. Commit your changes (`git commit -m 'feat: Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

MIT License - See [LICENSE](LICENSE) file for details

## Acknowledgments

- **yfinance**: For providing free financial data
- **Apache Spark**: For distributed data processing
- **Material-UI**: For beautiful React components
- **K3s**: For lightweight Kubernetes on Raspberry Pi

## Support

- **Documentation**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/yourusername/financial-screener/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/financial-screener/discussions)

## Roadmap

- [x] Phase 1: Project setup and architecture
- [ ] Phase 2: Stock screening implementation
- [ ] Phase 3: ETF support
- [ ] Phase 4: Bond support
- [ ] Phase 5: News & sentiment analysis
- [ ] Phase 6: React dashboard
- [ ] Phase 7: Portfolio management
- [ ] Phase 8: Buy/sell recommendations
- [ ] Phase 9: DEGIRO integration
- [ ] Phase 10: Performance optimization
- [ ] Phase 11: Mobile app (optional)

---

**Built with ❤️ for the Raspberry Pi homelab community**
