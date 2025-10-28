"""
EODHD (EOD Historical Data) Fetcher

Primary data source for stock prices and fundamentals.
https://eodhd.com/financial-apis/

Free tier: 20 API calls/day
Paid tier: $99.99/month for full access
"""

import asyncio
from datetime import date, datetime
from typing import List, Dict, Optional
import requests
import structlog

logger = structlog.get_logger()

# Rate limiting: Be conservative with API calls
RATE_LIMIT_DELAY = 1.0  # 1 second between calls


class EODHDFetcher:
    """Fetch stock data using EODHD API."""

    def __init__(self, api_key: str):
        """
        Initialize EODHD fetcher.

        Args:
            api_key: EODHD API key
        """
        self.api_key = api_key
        self.base_url = "https://eodhd.com/api"
        self.last_call_time = None

    async def _rate_limit(self):
        """Enforce rate limiting to avoid hitting API limits."""
        if self.last_call_time:
            elapsed = (datetime.now() - self.last_call_time).total_seconds()
            if elapsed < RATE_LIMIT_DELAY:
                wait_time = RATE_LIMIT_DELAY - elapsed
                await asyncio.sleep(wait_time)

        self.last_call_time = datetime.now()

    def _normalize_ticker(self, ticker: str) -> str:
        """
        Normalize ticker format for EODHD.

        EODHD format: TICKER.EXCHANGE
        Examples:
            AAPL (US) -> AAPL.US
            EDP.LS (Portugal) -> EDP.LS (already correct)
            SAP.DE (Germany) -> SAP.DE (already correct)

        Args:
            ticker: Stock symbol

        Returns:
            Normalized ticker for EODHD
        """
        if '.' not in ticker:
            # US stocks without exchange suffix
            return f"{ticker}.US"
        return ticker

    async def fetch_prices(
        self, ticker: str, start_date: date, end_date: date
    ) -> List[Dict]:
        """
        Fetch OHLCV price data for a stock.

        API endpoint: GET /eod/{TICKER}.{EXCHANGE}
        Params: from=YYYY-MM-DD, to=YYYY-MM-DD, api_token=API_KEY, fmt=json, period=d

        Args:
            ticker: Stock symbol
            start_date: Start date
            end_date: End date

        Returns:
            List of price dictionaries
        """
        try:
            normalized_ticker = self._normalize_ticker(ticker)

            await self._rate_limit()

            # Construct URL
            url = f"{self.base_url}/eod/{normalized_ticker}"
            params = {
                "from": start_date.strftime("%Y-%m-%d"),
                "to": end_date.strftime("%Y-%m-%d"),
                "api_token": self.api_key,
                "fmt": "json",
                "period": "d",  # Daily data
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Check for API errors
            if isinstance(data, dict) and "error" in data:
                logger.error("eodhd_error", ticker=ticker, error=data["error"])
                return []

            if not isinstance(data, list):
                logger.warning("unexpected_eodhd_response", ticker=ticker, type=type(data).__name__)
                return []

            if not data:
                logger.warning("no_eodhd_data", ticker=ticker)
                return []

            # Convert to our format
            prices = []
            for item in data:
                prices.append({
                    "date": datetime.strptime(item["date"], "%Y-%m-%d").date(),
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": int(item["volume"]),
                })

            # Add metadata to first record for asset creation
            if prices:
                # Get company info from fundamentals (cached)
                info = await self._fetch_general_info(normalized_ticker)
                if info:
                    prices[0]["name"] = info.get("Name", ticker)
                    prices[0]["exchange"] = info.get("Exchange", "")
                    prices[0]["country"] = info.get("CountryName", "")
                    prices[0]["sector"] = info.get("Sector", "")
                    prices[0]["industry"] = info.get("Industry", "")
                    prices[0]["currency"] = info.get("CurrencyCode", "")
                else:
                    # Fallback when fundamentals are not available
                    prices[0]["name"] = ticker
                    prices[0]["exchange"] = ""  # Leave empty, will try to get from ticker list
                    prices[0]["country"] = ""
                    prices[0]["sector"] = ""
                    prices[0]["industry"] = ""
                    prices[0]["currency"] = ""

            logger.info(
                "eodhd_prices_fetched",
                ticker=ticker,
                count=len(prices),
            )

            return prices

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning("eodhd_ticker_not_found", ticker=ticker)
            else:
                logger.error("eodhd_http_error", ticker=ticker, status=e.response.status_code)
            return []
        except Exception as e:
            logger.error("eodhd_fetch_failed", ticker=ticker, error=str(e))
            return []

    async def _fetch_general_info(self, normalized_ticker: str) -> Optional[Dict]:
        """
        Fetch general company information from fundamentals endpoint.

        API endpoint: GET /fundamentals/{TICKER}.{EXCHANGE}
        Params: api_token=API_KEY, fmt=json

        Note: Don't use filter=General - it causes 403 errors

        Args:
            normalized_ticker: EODHD-formatted ticker (e.g., AAPL.US)

        Returns:
            Dictionary with General section from fundamentals
        """
        try:
            await self._rate_limit()

            url = f"{self.base_url}/fundamentals/{normalized_ticker}"
            params = {
                "api_token": self.api_key,
                "fmt": "json",
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and "error" not in data:
                # Extract General section if it exists
                return data.get("General", data)

            return None

        except Exception as e:
            logger.debug("eodhd_general_info_failed", ticker=normalized_ticker, error=str(e))
            return None

    async def fetch_complete_asset_data(self, ticker: str) -> Optional[Dict]:
        """
        Fetch ALL available data from EODHD API for comprehensive asset storage.

        Returns complete data with all sections:
        - General, Highlights, Valuation, SharesStats, Technicals
        - SplitsDividends, AnalystRatings, Holders, InsiderTransactions
        - ESGScores, OutstandingShares, Earnings, Financials

        Args:
            ticker: Stock symbol

        Returns:
            Dictionary with complete EODHD data
        """
        try:
            normalized_ticker = self._normalize_ticker(ticker)
            await self._rate_limit()

            url = f"{self.base_url}/fundamentals/{normalized_ticker}"
            params = {
                "api_token": self.api_key,
                "fmt": "json",
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and "error" in data:
                logger.error("eodhd_complete_data_error", ticker=ticker, error=data["error"])
                return None

            logger.info("eodhd_complete_data_fetched", ticker=ticker, sections=list(data.keys()))
            return data

        except Exception as e:
            logger.error("eodhd_complete_data_failed", ticker=ticker, error=str(e))
            return None

    def extract_asset_metadata(self, complete_data: Dict, ticker: str) -> Dict:
        """
        Extract ALL asset metadata from complete EODHD data for database storage.
        This extracts EVERYTHING - key fields as columns + complete sections as JSONB.

        Args:
            complete_data: Complete EODHD API response with all sections
            ticker: Stock ticker

        Returns:
            Dictionary with ALL asset fields ready for database insertion
        """
        general = complete_data.get("General", {})
        highlights = complete_data.get("Highlights", {})
        valuation = complete_data.get("Valuation", {})
        analyst = complete_data.get("AnalystRatings", {})
        technicals = complete_data.get("Technicals", {})

        return {
            # Core identification
            "ticker": ticker.upper(),
            "name": general.get("Name", ticker),
            "exchange": general.get("Exchange", ""),  # Actual exchange: NASDAQ, NYSE, etc.
            "currency": general.get("CurrencyCode", "USD"),
            "country": general.get("CountryName", ""),
            "country_iso": general.get("CountryISO", ""),
            "asset_subtype": general.get("Type", ""),

            # Industry classification
            "sector": general.get("Sector", ""),
            "industry": general.get("Industry", ""),
            "gic_sector": general.get("GicSector", ""),
            "gic_group": general.get("GicGroup", ""),
            "gic_industry": general.get("GicIndustry", ""),
            "gic_sub_industry": general.get("GicSubIndustry", ""),

            # Identifiers
            "isin": general.get("ISIN"),
            "cusip": general.get("CUSIP"),
            "cik": general.get("CIK"),
            "figi": general.get("OpenFigi"),

            # Company info
            "description": general.get("Description"),
            "ipo_date": general.get("IPODate"),
            "is_delisted": general.get("IsDelisted", False),

            # KEY FINANCIAL METRICS (from Highlights - for fast screening)
            "market_cap": self._safe_int(highlights.get("MarketCapitalization")),
            "pe_ratio": self._safe_float(highlights.get("PERatio")),
            "peg_ratio": self._safe_float(highlights.get("PEGRatio")),
            "book_value": self._safe_float(highlights.get("BookValue")),
            "dividend_yield": self._safe_float(highlights.get("DividendYield")),
            "dividend_per_share": self._safe_float(highlights.get("DividendShare")),
            "earnings_per_share": self._safe_float(highlights.get("EarningsShare")),
            "ebitda": self._safe_int(highlights.get("EBITDA")),
            "eps_estimate_current_year": self._safe_float(highlights.get("EPSEstimateCurrentYear")),
            "eps_estimate_next_year": self._safe_float(highlights.get("EPSEstimateNextYear")),
            "wall_street_target_price": self._safe_float(highlights.get("WallStreetTargetPrice")),

            # VALUATION METRICS (for screening)
            "trailing_pe": self._safe_float(valuation.get("TrailingPE")),
            "forward_pe": self._safe_float(valuation.get("ForwardPE")),
            "price_sales_ttm": self._safe_float(valuation.get("PriceSalesTTM")),
            "price_book": self._safe_float(valuation.get("PriceBookMRQ")),
            "enterprise_value": self._safe_int(valuation.get("EnterpriseValue")),
            "ev_revenue": self._safe_float(valuation.get("EnterpriseValueRevenue")),
            "ev_ebitda": self._safe_float(valuation.get("EnterpriseValueEbitda")),

            # ANALYST RATINGS
            "analyst_rating": self._safe_float(analyst.get("Rating")),
            "analyst_target_price": self._safe_float(analyst.get("TargetPrice")),
            "analyst_strong_buy": self._safe_int(analyst.get("StrongBuy")),
            "analyst_buy": self._safe_int(analyst.get("Buy")),
            "analyst_hold": self._safe_int(analyst.get("Hold")),
            "analyst_sell": self._safe_int(analyst.get("Sell")),
            "analyst_strong_sell": self._safe_int(analyst.get("StrongSell")),

            # TECHNICALS (from API)
            "beta": self._safe_float(technicals.get("Beta")),
            "week_52_high": self._safe_float(technicals.get("52WeekHigh")),
            "week_52_low": self._safe_float(technicals.get("52WeekLow")),
            "ma_50_day": self._safe_float(technicals.get("50DayMA")),
            "ma_200_day": self._safe_float(technicals.get("200DayMA")),
            "shares_short": self._safe_int(technicals.get("SharesShort")),
            "short_ratio": self._safe_float(technicals.get("ShortRatio")),
            "short_percent": self._safe_float(technicals.get("ShortPercent")),

            # COMPLETE JSONB SECTIONS (ALL raw data stored)
            "eodhd_general": general if general else None,
            "eodhd_highlights": highlights if highlights else None,
            "eodhd_valuation": valuation if valuation else None,
            "eodhd_shares_stats": complete_data.get("SharesStats"),
            "eodhd_technicals": technicals if technicals else None,
            "eodhd_splits_dividends": complete_data.get("SplitsDividends"),
            "eodhd_analyst_ratings": analyst if analyst else None,
            "eodhd_holders": complete_data.get("Holders"),
            "eodhd_insider_transactions": complete_data.get("InsiderTransactions"),
            "eodhd_esg_scores": complete_data.get("ESGScores"),
            "eodhd_outstanding_shares": complete_data.get("outstandingShares"),
            "eodhd_earnings": complete_data.get("Earnings"),
            "eodhd_financials": complete_data.get("Financials"),  # 64+32+34 fields × years/quarters!
        }

    def _safe_int(self, value) -> Optional[int]:
        """Safely convert value to int."""
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    async def fetch_fundamentals(self, ticker: str) -> Optional[Dict]:
        """
        Fetch fundamental data for a stock.

        API endpoint: GET /fundamentals/{TICKER}.{EXCHANGE}
        Params: api_token=API_KEY, fmt=json

        Args:
            ticker: Stock symbol

        Returns:
            Dictionary of fundamental metrics
        """
        try:
            normalized_ticker = self._normalize_ticker(ticker)

            await self._rate_limit()

            url = f"{self.base_url}/fundamentals/{normalized_ticker}"
            params = {
                "api_token": self.api_key,
                "fmt": "json",
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and "error" in data:
                logger.error("eodhd_fundamentals_error", ticker=ticker, error=data["error"])
                return None

            # Extract fundamental metrics from EODHD format
            highlights = data.get("Highlights", {})
            valuation = data.get("Valuation", {})
            technicals = data.get("Technicals", {})
            financials = data.get("Financials", {})
            balance_sheet = financials.get("Balance_Sheet", {}).get("yearly", {})
            income_statement = financials.get("Income_Statement", {}).get("yearly", {})
            cash_flow = financials.get("Cash_Flow", {}).get("yearly", {})

            # Get most recent financial data
            latest_bs = balance_sheet.get(list(balance_sheet.keys())[0], {}) if balance_sheet else {}
            latest_is = income_statement.get(list(income_statement.keys())[0], {}) if income_statement else {}
            latest_cf = cash_flow.get(list(cash_flow.keys())[0], {}) if cash_flow else {}

            fundamentals = {
                "period_end_date": date.today(),
                "period_type": "annual",
                # Valuation
                "market_cap": self._safe_float(highlights.get("MarketCapitalization")),
                "enterprise_value": self._safe_float(highlights.get("EnterpriseValue")),
                "pe_ratio": self._safe_float(highlights.get("PERatio")),
                "pb_ratio": self._safe_float(highlights.get("PriceBookMRQ")),
                "ps_ratio": self._safe_float(highlights.get("PriceSalesTTM")),
                "peg_ratio": self._safe_float(highlights.get("PEGRatio")),
                "ev_ebitda": self._safe_float(highlights.get("EnterpriseValueEbitda")),
                # Profitability
                "gross_margin": self._safe_float(highlights.get("GrossMarginTTM")),
                "operating_margin": self._safe_float(highlights.get("OperatingMarginTTM")),
                "profit_margin": self._safe_float(highlights.get("ProfitMargin")),
                "roe": self._safe_float(highlights.get("ReturnOnEquityTTM")),
                "roa": self._safe_float(highlights.get("ReturnOnAssetsTTM")),
                # Financial health
                "current_ratio": self._safe_float(technicals.get("CurrentRatio")),
                "debt_to_equity": self._safe_float(highlights.get("DebtToEquity")),
                # Revenue and earnings
                "revenue": self._safe_float(latest_is.get("totalRevenue")),
                "gross_profit": self._safe_float(latest_is.get("grossProfit")),
                "ebitda": self._safe_float(highlights.get("EBITDA")),
                "net_income": self._safe_float(latest_is.get("netIncome")),
                "eps": self._safe_float(highlights.get("EarningsPerShareTTM")),
                # Cash flow
                "operating_cash_flow": self._safe_float(latest_cf.get("totalCashFromOperatingActivities")),
                "free_cash_flow": self._safe_float(latest_cf.get("freeCashFlow")),
                # Growth
                "revenue_growth": self._safe_float(highlights.get("RevenuePerShareTTM")),
                "earnings_growth": self._safe_float(highlights.get("QuarterlyEarningsGrowthYOY")),
                # Dividend
                "dividend_yield": self._safe_float(highlights.get("DividendYield")),
                "dividend_per_share": self._safe_float(highlights.get("DividendPerShareTTM")),
                "payout_ratio": self._safe_float(highlights.get("PayoutRatio")),
            }

            # Remove None values
            fundamentals = {k: v for k, v in fundamentals.items() if v is not None}

            logger.info("eodhd_fundamentals_fetched", ticker=ticker, metrics=len(fundamentals))

            return fundamentals

        except Exception as e:
            logger.error("eodhd_fundamentals_failed", ticker=ticker, error=str(e))
            return None

    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float."""
        if value is None or value == "None" or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
