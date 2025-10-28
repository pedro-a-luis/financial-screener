# Ticker Lists - Organized by Exchange

All ticker files are auto-generated from EODHD API and organized by stock exchange.

## 📊 Exchange-Based Ticker Lists

| Exchange | File | Tickers | Region | Description |
|----------|------|---------|--------|-------------|
| **NYSE** | `nyse.txt` | 2,339 | 🇺🇸 USA | New York Stock Exchange |
| **NASDAQ** | `nasdaq.txt` | 4,086 | 🇺🇸 USA | NASDAQ Stock Exchange |
| **LSE** | `lse.txt` | 3,145 | 🇬🇧 UK | London Stock Exchange |
| **XETRA** | `xetra.txt` | 691 | 🇩🇪 Germany | XETRA Electronic Exchange |
| **FRANKFURT** | `frankfurt.txt` | 10,209 | 🇩🇪 Germany | Frankfurt Stock Exchange |
| **EURONEXT** | `euronext.txt` | 889 | 🇪🇺 Europe | Euronext (Paris, Amsterdam, Brussels, Lisbon) |
| **BME** | `bme.txt` | 239 | 🇪🇸 Spain | Bolsa de Madrid |
| **SIX** | `six.txt` | 218 | 🇨🇭 Switzerland | SIX Swiss Exchange |

**Total: 21,816 tickers** across 8 major exchanges

## 📁 File Organization

- **Flat structure**: All files in `config/tickers/`
- **Named by exchange**: Files use exchange codes (e.g., `nyse.txt`, `euronext.txt`)
- **Exchange metadata**: Each file header contains exchange info for PostgreSQL `assets.exchange` column

## 📝 File Format

Each ticker file contains:
```
# Exchange Name
# Exchange: CODE (stored in PostgreSQL)
# Auto-generated from EODHD API
# Total tickers: XXXX

TICKER1
TICKER2
...
```

Lines starting with `#` are comments and ignored during import.

## 🔄 Refreshing Ticker Lists

Use the automated refresh script:

```bash
# Refresh all US exchanges (NYSE, NASDAQ)
python3 scripts/refresh_ticker_lists.py --region US --api-key YOUR_KEY

# Refresh all European exchanges
python3 scripts/refresh_ticker_lists.py --region EUROPE --api-key YOUR_KEY

# Refresh specific exchange
python3 scripts/refresh_ticker_lists.py --markets NYSE,LSE --api-key YOUR_KEY

# Refresh everything
python3 scripts/refresh_ticker_lists.py --region ALL --api-key YOUR_KEY
```

**Recommendation**: Run weekly to capture IPOs and delistings.

## 🗄️ PostgreSQL Integration

The exchange code from each file's header is stored in the `assets.exchange` column:

```sql
-- Example: Assets from different exchanges
SELECT ticker, name, exchange, country
FROM financial_screener.assets
WHERE exchange IN ('NYSE', 'NASDAQ', 'LSE', 'XETRA');
```

This allows querying stocks by exchange:
- Filter by market (e.g., all US stocks: `exchange IN ('NYSE', 'NASDAQ')`)
- Market-specific analysis (e.g., European stocks only)
- Trading hours grouping
- Currency grouping by exchange

## 🌍 Exchange Codes Reference

| Code | Full Name | Trading Hours (UTC) | Currency |
|------|-----------|---------------------|----------|
| NYSE | New York Stock Exchange | 14:30-21:00 | USD |
| NASDAQ | NASDAQ Stock Market | 14:30-21:00 | USD |
| LSE | London Stock Exchange | 08:00-16:30 | GBP |
| XETRA | XETRA (Deutsche Börse) | 08:00-16:30 | EUR |
| FRA | Frankfurt Stock Exchange | 08:00-20:00 | EUR |
| PAR | Euronext Paris | 08:00-16:30 | EUR |
| AMS | Euronext Amsterdam | 08:00-16:30 | EUR |
| BRU | Euronext Brussels | 08:00-16:30 | EUR |
| LIS | Euronext Lisbon | 08:00-16:30 | EUR |
| BME | Bolsa de Madrid | 08:00-16:30 | EUR |
| SIX | SIX Swiss Exchange | 08:00-16:30 | CHF |

## 🚀 Data Collection Strategy

### Recommended Approach

**Phase 1: Major US Exchanges** (6,425 stocks)
- NYSE + NASDAQ
- ~12,850 API calls (2 per stock)
- Time: ~3.5 hours
- Coverage: Large/mid cap US stocks

**Phase 2: Major European Exchanges** (4,073 stocks)
- LSE + XETRA + Euronext
- ~8,146 API calls
- Time: ~2.3 hours
- Coverage: UK, Germany, France, Netherlands, Belgium

**Phase 3: Additional Markets** (11,318 stocks)
- Frankfurt + BME + SIX
- ~22,636 API calls
- Time: ~6.3 hours
- Coverage: Complete European coverage

### API Quota Usage

With EODHD All-In-One plan (100,000 calls/day):

| Phase | Stocks | API Calls | Time | Daily Quota % |
|-------|--------|-----------|------|---------------|
| Phase 1 (US) | 6,425 | 12,850 | 3.5h | 13% |
| Phase 2 (EU Major) | 4,073 | 8,146 | 2.3h | 8% |
| Phase 3 (EU All) | 11,318 | 22,636 | 6.3h | 23% |
| **Total** | **21,816** | **43,632** | **12.1h** | **44%** |

*Each stock requires 2 API calls: prices + fundamentals*

## 🔍 Notes

### Euronext Consolidation
The `euronext.txt` file combines all Euronext markets:
- **Euronext Paris** (France) - CAC 40
- **Euronext Amsterdam** (Netherlands) - AEX
- **Euronext Brussels** (Belgium) - BEL 20
- **Euronext Lisbon** (Portugal) - PSI 20

All tickers use exchange code `EURONEXT` in PostgreSQL.

### Tradegate
Tradegate is a trading platform, not a listing exchange. German stocks are covered through XETRA and Frankfurt exchanges.

### German Exchanges
Two German exchanges are included:
- **XETRA**: Primary electronic exchange (691 stocks)
- **Frankfurt**: Traditional floor exchange (10,209 stocks - includes many duplicates)

Recommended: Use XETRA for primary German stocks to avoid duplicates.

## 📅 Maintenance

**Refresh Schedule**:
- **Weekly**: Automated refresh (captures IPOs/delistings)
- **Monthly**: Manual validation
- **Quarterly**: Review filters and exchange codes

**Future**: Orchestration via Apache Airflow DAGs

## 🛠️ Technical Details

### Data Source
- **API**: EODHD Exchange Symbol List
- **Endpoint**: `https://eodhd.com/api/exchange-symbol-list/{EXCHANGE}`
- **Format**: JSON
- **Filters**: Common Stock type only (excludes ETFs, funds, warrants)

### Generated By
- **Script**: `scripts/refresh_ticker_lists.py`
- **Version**: 2.0
- **Last updated**: Check individual file headers

## 📄 License

Ticker data provided by EODHD. Subject to their terms of service.
