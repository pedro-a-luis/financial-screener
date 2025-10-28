#!/usr/bin/env python3
"""
Test script to verify complete EODHD data collection
Tests the complete pipeline: API fetch → Extract → Store
"""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fetchers.eodhd_fetcher import EODHDFetcher
from database_enhanced import upsert_complete_asset
import asyncpg


async def test_complete_collection():
    """Test complete data collection for a single stock."""

    # Configuration
    api_key = os.getenv("EODHD_API_KEY", "68f521d8d5e1f7.88465516")
    db_url = os.getenv("DATABASE_URL", "postgresql://appuser:AppUser123@192.168.1.240:5432/appdb")
    test_ticker = "AAPL"

    print(f"=== Testing Complete Data Collection ===")
    print(f"Ticker: {test_ticker}")
    print(f"API Key: {api_key[:20]}...")
    print()

    # Step 1: Fetch complete data from EODHD API
    print("Step 1: Fetching complete data from EODHD API...")
    fetcher = EODHDFetcher(api_key)
    complete_data = await fetcher.fetch_complete_asset_data(test_ticker)

    if not complete_data:
        print("✗ Failed to fetch data from API")
        return False

    print(f"✓ Fetched {len(complete_data)} sections from API")
    print(f"  Sections: {list(complete_data.keys())}")
    print()

    # Step 2: Extract asset metadata
    print("Step 2: Extracting asset metadata...")
    asset_data = fetcher.extract_asset_metadata(complete_data, test_ticker)

    print(f"✓ Extracted {len(asset_data)} fields")
    print(f"  Name: {asset_data.get('name')}")
    print(f"  Exchange: {asset_data.get('exchange')}")
    print(f"  Sector: {asset_data.get('sector')}")
    print(f"  Market Cap: ${asset_data.get('market_cap'):,}" if asset_data.get('market_cap') else "  Market Cap: N/A")
    print(f"  PE Ratio: {asset_data.get('pe_ratio')}")
    print(f"  Analyst Rating: {asset_data.get('analyst_rating')}")
    print(f"  JSONB sections: {sum(1 for k, v in asset_data.items() if k.startswith('eodhd_') and v is not None)}")
    print()

    # Step 3: Store in database
    print("Step 3: Storing in PostgreSQL...")
    try:
        conn = await asyncpg.connect(db_url)
        await conn.execute("SET search_path TO financial_screener")

        asset_id = await upsert_complete_asset(conn, asset_data, asset_type="stock")

        print(f"✓ Asset stored with ID: {asset_id}")

        # Verify stored data
        row = await conn.fetchrow(
            "SELECT ticker, name, exchange, sector, market_cap, pe_ratio, analyst_rating FROM assets WHERE id = $1",
            asset_id
        )
        print(f"✓ Verified in database:")
        print(f"  Ticker: {row['ticker']}")
        print(f"  Name: {row['name']}")
        print(f"  Exchange: {row['exchange']}")
        print(f"  Sector: {row['sector']}")
        print(f"  Market Cap: ${row['market_cap']:,}" if row['market_cap'] else "  Market Cap: N/A")
        print(f"  PE Ratio: {row['pe_ratio']}")
        print(f"  Analyst Rating: {row['analyst_rating']}")

        await conn.close()
        print()

    except Exception as e:
        print(f"✗ Database error: {e}")
        return False

    print("=== SUCCESS: Complete data collection pipeline working! ===")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_complete_collection())
    sys.exit(0 if success else 1)
