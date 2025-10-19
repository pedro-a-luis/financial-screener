"""
Cache Manager using Redis

Implements smart caching strategy to minimize API calls.
"""

import redis.asyncio as redis
import json
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger()


class CacheManager:
    """Manage Redis caching operations."""

    def __init__(self, redis_url: str):
        """Initialize cache manager."""
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None

    async def connect(self):
        """Connect to Redis."""
        self.client = await redis.from_url(
            self.redis_url, encoding="utf-8", decode_responses=True
        )
        logger.info("cache_connected")

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            logger.info("cache_disconnected")

    async def set_latest_price(self, ticker: str, price_data: Dict, ttl: int = 3600):
        """
        Cache latest price for a ticker.

        Args:
            ticker: Stock symbol
            price_data: Price dictionary
            ttl: Time to live in seconds (default 1 hour)
        """
        key = f"price:latest:{ticker.upper()}"
        value = json.dumps(price_data, default=str)
        await self.client.setex(key, ttl, value)

        logger.debug("price_cached", ticker=ticker, ttl=ttl)

    async def get_latest_price(self, ticker: str) -> Optional[Dict]:
        """Get cached latest price."""
        key = f"price:latest:{ticker.upper()}"
        value = await self.client.get(key)

        if value:
            logger.debug("price_cache_hit", ticker=ticker)
            return json.loads(value)

        logger.debug("price_cache_miss", ticker=ticker)
        return None

    async def set_fundamentals(
        self, ticker: str, fundamentals: Dict, ttl: int = 86400
    ):
        """
        Cache fundamentals (TTL 24 hours).

        Args:
            ticker: Stock symbol
            fundamentals: Fundamentals dictionary
            ttl: Time to live in seconds (default 24 hours)
        """
        key = f"fundamentals:{ticker.upper()}"
        value = json.dumps(fundamentals, default=str)
        await self.client.setex(key, ttl, value)

        logger.debug("fundamentals_cached", ticker=ticker)

    async def get_fundamentals(self, ticker: str) -> Optional[Dict]:
        """Get cached fundamentals."""
        key = f"fundamentals:{ticker.upper()}"
        value = await self.client.get(key)

        if value:
            logger.debug("fundamentals_cache_hit", ticker=ticker)
            return json.loads(value)

        return None

    async def invalidate_ticker(self, ticker: str):
        """Invalidate all cached data for a ticker."""
        pattern = f"*:{ticker.upper()}"
        keys = []

        async for key in self.client.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            await self.client.delete(*keys)
            logger.info("cache_invalidated", ticker=ticker, keys_deleted=len(keys))
