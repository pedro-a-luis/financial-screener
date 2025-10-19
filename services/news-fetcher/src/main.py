#!/usr/bin/env python3
"""
News Fetcher Service

Fetches financial news from multiple sources for tracked assets.
Designed to run as a Kubernetes CronJob.

Sources:
- Yahoo Finance RSS
- Alpha Vantage News API (if API key provided)
- NewsAPI.org (if API key provided)
- Google Finance RSS
"""

import argparse
import asyncio
from datetime import datetime
from typing import List

import structlog

from config import Settings
from sources import YahooFinanceNews, AlphaVantageNews, NewsAPISource
from database import NewsDatabase

logger = structlog.get_logger()


async def fetch_news_for_tickers(
    tickers: List[str],
    settings: Settings,
    db: NewsDatabase,
) -> dict:
    """
    Fetch news for a list of tickers from all available sources.

    Args:
        tickers: List of stock symbols
        settings: Application settings
        db: Database instance

    Returns:
        dict: Statistics about news fetched
    """
    stats = {
        "total_articles": 0,
        "new_articles": 0,
        "duplicates": 0,
        "errors": 0,
    }

    # Initialize news sources
    sources = [
        YahooFinanceNews(),
    ]

    # Add optional API sources if keys are configured
    if settings.alpha_vantage_api_key:
        sources.append(AlphaVantageNews(settings.alpha_vantage_api_key))

    if settings.news_api_key:
        sources.append(NewsAPISource(settings.news_api_key))

    logger.info("fetching_news", tickers=len(tickers), sources=len(sources))

    # Fetch from each source
    for source in sources:
        logger.info("fetching_from_source", source=source.name)

        for ticker in tickers:
            try:
                articles = await source.fetch_news(ticker)

                if not articles:
                    continue

                # Store in database
                for article in articles:
                    # Check if article already exists (by URL)
                    existing = await db.article_exists(article["url"])

                    if existing:
                        stats["duplicates"] += 1
                        continue

                    # Get or create asset_id
                    asset_id = await db.get_asset_id_by_ticker(ticker)

                    # Insert article
                    await db.insert_article(
                        asset_id=asset_id,
                        ticker=ticker,
                        title=article["title"],
                        description=article.get("description"),
                        content=article.get("content"),
                        url=article["url"],
                        source=source.name,
                        author=article.get("author"),
                        published_date=article["published_date"],
                        category=article.get("category"),
                    )

                    stats["new_articles"] += 1
                    stats["total_articles"] += 1

                logger.info(
                    "news_fetched",
                    ticker=ticker,
                    source=source.name,
                    articles=len(articles),
                )

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(
                    "fetch_news_failed", ticker=ticker, source=source.name, error=str(e)
                )
                stats["errors"] += 1

    return stats


async def fetch_trending_news(settings: Settings, db: NewsDatabase) -> dict:
    """
    Fetch general market news (not ticker-specific).

    Args:
        settings: Application settings
        db: Database instance

    Returns:
        dict: Statistics
    """
    stats = {"total_articles": 0, "new_articles": 0}

    # Fetch general market news
    # This could be from general RSS feeds or news APIs

    logger.info("trending_news_fetched", stats=stats)

    return stats


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Financial News Fetcher")
    parser.add_argument(
        "--mode",
        choices=["portfolio", "watchlist", "all", "trending"],
        default="portfolio",
        help="Fetch mode",
    )
    parser.add_argument(
        "--tickers", type=str, help="Comma-separated list of tickers"
    )
    parser.add_argument(
        "--limit", type=int, default=100, help="Max tickers to process"
    )

    args = parser.parse_args()

    # Load settings
    settings = Settings()

    # Initialize database
    db = NewsDatabase(settings.database_url)
    await db.connect()

    try:
        start_time = datetime.now()

        if args.mode == "trending":
            stats = await fetch_trending_news(settings, db)
        else:
            # Get tickers to fetch news for
            tickers = []

            if args.tickers:
                tickers = [t.strip().upper() for t in args.tickers.split(",")]
            elif args.mode == "portfolio":
                # Get portfolio holdings
                tickers = await db.get_portfolio_tickers(limit=args.limit)
            elif args.mode == "watchlist":
                # Get watchlist tickers
                tickers = await db.get_watchlist_tickers(limit=args.limit)
            elif args.mode == "all":
                # Get all active tickers
                tickers = await db.get_all_active_tickers(limit=args.limit)

            if not tickers:
                logger.warning("no_tickers_found", mode=args.mode)
                return

            logger.info("starting_news_fetch", mode=args.mode, ticker_count=len(tickers))

            stats = await fetch_news_for_tickers(tickers, settings, db)

        duration = (datetime.now() - start_time).total_seconds()

        logger.info(
            "news_fetch_complete",
            mode=args.mode,
            duration_seconds=duration,
            stats=stats,
        )

        # Log to database
        await db.log_fetch_job(
            job_type=f"news_{args.mode}",
            status="success" if stats["errors"] == 0 else "partial",
            records_processed=stats["new_articles"],
            duration_ms=int(duration * 1000),
        )

    except Exception as e:
        logger.error("news_fetch_failed", error=str(e))
        raise

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
