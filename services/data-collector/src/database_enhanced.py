"""
Enhanced Database Manager for Complete EODHD Asset Data
Handles all 72 asset columns including JSONB fields
"""

import asyncpg
import json
from typing import Dict, Optional
from datetime import datetime, date
import structlog

logger = structlog.get_logger()


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """Convert date string to Python date object."""
    if not date_str or date_str == "":
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


async def upsert_complete_asset(
    conn: asyncpg.Connection,
    asset_data: Dict,
    asset_type: str = "stock"
) -> int:
    """
    Insert or update asset with ALL fields from EODHD API.

    Args:
        conn: Database connection
        asset_data: Complete asset data from EODHD fetcher
        asset_type: Asset type (stock/etf/bond)

    Returns:
        int: asset_id
    """
    ticker = asset_data["ticker"].upper()

    # Prepare JSONB fields (convert dict to JSON string)
    jsonb_fields = [
        "eodhd_general",
        "eodhd_highlights",
        "eodhd_valuation",
        "eodhd_shares_stats",
        "eodhd_technicals",
        "eodhd_splits_dividends",
        "eodhd_analyst_ratings",
        "eodhd_holders",
        "eodhd_insider_transactions",
        "eodhd_esg_scores",
        "eodhd_outstanding_shares",
        "eodhd_earnings",
        "eodhd_financials",
    ]

    for field in jsonb_fields:
        if field in asset_data and asset_data[field] is not None:
            asset_data[field] = json.dumps(asset_data[field])

    # Upsert with all fields
    row = await conn.fetchrow(
        """
        INSERT INTO assets (
            ticker, name, asset_type, asset_subtype,
            exchange, currency, country, country_iso,
            sector, industry, gic_sector, gic_group, gic_industry, gic_sub_industry,
            isin, cusip, cik, figi,
            description, ipo_date, is_delisted,
            market_cap, pe_ratio, peg_ratio, book_value,
            dividend_yield, dividend_per_share, earnings_per_share, ebitda,
            eps_estimate_current_year, eps_estimate_next_year, wall_street_target_price,
            trailing_pe, forward_pe, price_sales_ttm, price_book,
            enterprise_value, ev_revenue, ev_ebitda,
            analyst_rating, analyst_target_price,
            analyst_strong_buy, analyst_buy, analyst_hold, analyst_sell, analyst_strong_sell,
            beta, week_52_high, week_52_low, ma_50_day, ma_200_day,
            shares_short, short_ratio, short_percent,
            eodhd_general, eodhd_highlights, eodhd_valuation,
            eodhd_shares_stats, eodhd_technicals, eodhd_splits_dividends,
            eodhd_analyst_ratings, eodhd_holders, eodhd_insider_transactions,
            eodhd_esg_scores, eodhd_outstanding_shares, eodhd_earnings, eodhd_financials,
            eodhd_last_update
        )
        VALUES (
            $1, $2, $3, $4,
            $5, $6, $7, $8,
            $9, $10, $11, $12, $13, $14,
            $15, $16, $17, $18,
            $19, $20, $21,
            $22, $23, $24, $25,
            $26, $27, $28, $29,
            $30, $31, $32,
            $33, $34, $35, $36,
            $37, $38, $39,
            $40, $41,
            $42, $43, $44, $45, $46,
            $47, $48, $49, $50, $51,
            $52, $53, $54,
            $55::jsonb, $56::jsonb, $57::jsonb,
            $58::jsonb, $59::jsonb, $60::jsonb,
            $61::jsonb, $62::jsonb, $63::jsonb,
            $64::jsonb, $65::jsonb, $66::jsonb, $67::jsonb,
            NOW()
        )
        ON CONFLICT (ticker) DO UPDATE SET
            name = EXCLUDED.name,
            asset_subtype = EXCLUDED.asset_subtype,
            exchange = EXCLUDED.exchange,
            currency = EXCLUDED.currency,
            country = EXCLUDED.country,
            country_iso = EXCLUDED.country_iso,
            sector = EXCLUDED.sector,
            industry = EXCLUDED.industry,
            gic_sector = EXCLUDED.gic_sector,
            gic_group = EXCLUDED.gic_group,
            gic_industry = EXCLUDED.gic_industry,
            gic_sub_industry = EXCLUDED.gic_sub_industry,
            isin = EXCLUDED.isin,
            cusip = EXCLUDED.cusip,
            cik = EXCLUDED.cik,
            figi = EXCLUDED.figi,
            description = EXCLUDED.description,
            ipo_date = EXCLUDED.ipo_date,
            is_delisted = EXCLUDED.is_delisted,
            market_cap = EXCLUDED.market_cap,
            pe_ratio = EXCLUDED.pe_ratio,
            peg_ratio = EXCLUDED.peg_ratio,
            book_value = EXCLUDED.book_value,
            dividend_yield = EXCLUDED.dividend_yield,
            dividend_per_share = EXCLUDED.dividend_per_share,
            earnings_per_share = EXCLUDED.earnings_per_share,
            ebitda = EXCLUDED.ebitda,
            eps_estimate_current_year = EXCLUDED.eps_estimate_current_year,
            eps_estimate_next_year = EXCLUDED.eps_estimate_next_year,
            wall_street_target_price = EXCLUDED.wall_street_target_price,
            trailing_pe = EXCLUDED.trailing_pe,
            forward_pe = EXCLUDED.forward_pe,
            price_sales_ttm = EXCLUDED.price_sales_ttm,
            price_book = EXCLUDED.price_book,
            enterprise_value = EXCLUDED.enterprise_value,
            ev_revenue = EXCLUDED.ev_revenue,
            ev_ebitda = EXCLUDED.ev_ebitda,
            analyst_rating = EXCLUDED.analyst_rating,
            analyst_target_price = EXCLUDED.analyst_target_price,
            analyst_strong_buy = EXCLUDED.analyst_strong_buy,
            analyst_buy = EXCLUDED.analyst_buy,
            analyst_hold = EXCLUDED.analyst_hold,
            analyst_sell = EXCLUDED.analyst_sell,
            analyst_strong_sell = EXCLUDED.analyst_strong_sell,
            beta = EXCLUDED.beta,
            week_52_high = EXCLUDED.week_52_high,
            week_52_low = EXCLUDED.week_52_low,
            ma_50_day = EXCLUDED.ma_50_day,
            ma_200_day = EXCLUDED.ma_200_day,
            shares_short = EXCLUDED.shares_short,
            short_ratio = EXCLUDED.short_ratio,
            short_percent = EXCLUDED.short_percent,
            eodhd_general = EXCLUDED.eodhd_general,
            eodhd_highlights = EXCLUDED.eodhd_highlights,
            eodhd_valuation = EXCLUDED.eodhd_valuation,
            eodhd_shares_stats = EXCLUDED.eodhd_shares_stats,
            eodhd_technicals = EXCLUDED.eodhd_technicals,
            eodhd_splits_dividends = EXCLUDED.eodhd_splits_dividends,
            eodhd_analyst_ratings = EXCLUDED.eodhd_analyst_ratings,
            eodhd_holders = EXCLUDED.eodhd_holders,
            eodhd_insider_transactions = EXCLUDED.eodhd_insider_transactions,
            eodhd_esg_scores = EXCLUDED.eodhd_esg_scores,
            eodhd_outstanding_shares = EXCLUDED.eodhd_outstanding_shares,
            eodhd_earnings = EXCLUDED.eodhd_earnings,
            eodhd_financials = EXCLUDED.eodhd_financials,
            eodhd_last_update = NOW(),
            updated_at = NOW()
        RETURNING id
        """,
        ticker,
        asset_data.get("name"),
        asset_type,
        asset_data.get("asset_subtype"),
        asset_data.get("exchange"),
        asset_data.get("currency"),
        asset_data.get("country"),
        asset_data.get("country_iso"),
        asset_data.get("sector"),
        asset_data.get("industry"),
        asset_data.get("gic_sector"),
        asset_data.get("gic_group"),
        asset_data.get("gic_industry"),
        asset_data.get("gic_sub_industry"),
        asset_data.get("isin"),
        asset_data.get("cusip"),
        asset_data.get("cik"),
        asset_data.get("figi"),
        asset_data.get("description"),
        parse_date(asset_data.get("ipo_date")),
        asset_data.get("is_delisted"),
        asset_data.get("market_cap"),
        asset_data.get("pe_ratio"),
        asset_data.get("peg_ratio"),
        asset_data.get("book_value"),
        asset_data.get("dividend_yield"),
        asset_data.get("dividend_per_share"),
        asset_data.get("earnings_per_share"),
        asset_data.get("ebitda"),
        asset_data.get("eps_estimate_current_year"),
        asset_data.get("eps_estimate_next_year"),
        asset_data.get("wall_street_target_price"),
        asset_data.get("trailing_pe"),
        asset_data.get("forward_pe"),
        asset_data.get("price_sales_ttm"),
        asset_data.get("price_book"),
        asset_data.get("enterprise_value"),
        asset_data.get("ev_revenue"),
        asset_data.get("ev_ebitda"),
        asset_data.get("analyst_rating"),
        asset_data.get("analyst_target_price"),
        asset_data.get("analyst_strong_buy"),
        asset_data.get("analyst_buy"),
        asset_data.get("analyst_hold"),
        asset_data.get("analyst_sell"),
        asset_data.get("analyst_strong_sell"),
        asset_data.get("beta"),
        asset_data.get("week_52_high"),
        asset_data.get("week_52_low"),
        asset_data.get("ma_50_day"),
        asset_data.get("ma_200_day"),
        asset_data.get("shares_short"),
        asset_data.get("short_ratio"),
        asset_data.get("short_percent"),
        asset_data.get("eodhd_general"),
        asset_data.get("eodhd_highlights"),
        asset_data.get("eodhd_valuation"),
        asset_data.get("eodhd_shares_stats"),
        asset_data.get("eodhd_technicals"),
        asset_data.get("eodhd_splits_dividends"),
        asset_data.get("eodhd_analyst_ratings"),
        asset_data.get("eodhd_holders"),
        asset_data.get("eodhd_insider_transactions"),
        asset_data.get("eodhd_esg_scores"),
        asset_data.get("eodhd_outstanding_shares"),
        asset_data.get("eodhd_earnings"),
        asset_data.get("eodhd_financials"),
    )

    logger.info("asset_upserted", ticker=ticker, asset_id=row["id"])
    return row["id"]
