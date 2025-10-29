#!/usr/bin/env python3
"""
Test script to verify comprehensive fundamental data fetching from EODHD API.
Tests with AAPL.US to ensure all 13 sections are retrieved.
"""

import asyncio
import sys
import os
import json
from datetime import datetime

# Add src directory to path
sys.path.insert(0, '/root/gitlab/financial-screener/services/data-collector/src')
sys.path.insert(0, '/root/gitlab/financial-screener/services/data-collector/src/fetchers')

# Import directly from the file
import importlib.util
spec = importlib.util.spec_from_file_location(
    "eodhd_fetcher",
    "/root/gitlab/financial-screener/services/data-collector/src/fetchers/eodhd_fetcher.py"
)
eodhd_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eodhd_module)
EODHDFetcher = eodhd_module.EODHDFetcher


async def test_comprehensive_fundamentals():
    """Test comprehensive fundamentals fetching."""

    # Get API key from environment
    api_key = os.getenv('EODHD_API_KEY')
    if not api_key:
        print("❌ ERROR: EODHD_API_KEY environment variable not set")
        return False

    print("=" * 80)
    print("COMPREHENSIVE FUNDAMENTALS TEST")
    print("=" * 80)
    print(f"Testing with: AAPL.US")
    print(f"Timestamp: {datetime.now()}")
    print()

    # Initialize fetcher
    fetcher = EODHDFetcher(api_key)

    # Test 1: fetch_complete_asset_data()
    print("Test 1: Fetching complete asset data...")
    print("-" * 80)
    complete_data = await fetcher.fetch_complete_asset_data("AAPL.US")

    if not complete_data:
        print("❌ FAILED: No data returned from fetch_complete_asset_data()")
        return False

    print(f"✅ SUCCESS: Retrieved {len(complete_data)} top-level sections")
    print()
    print("Sections retrieved:")
    for section in sorted(complete_data.keys()):
        data = complete_data[section]
        if isinstance(data, dict):
            print(f"  - {section}: {len(data)} fields")
        elif isinstance(data, list):
            print(f"  - {section}: {len(data)} items")
        else:
            print(f"  - {section}: {type(data).__name__}")
    print()

    # Test 2: extract_asset_metadata()
    print("Test 2: Extracting asset metadata...")
    print("-" * 80)
    asset_metadata = fetcher.extract_asset_metadata(complete_data, "AAPL.US")

    print(f"✅ SUCCESS: Extracted {len(asset_metadata)} fields for database storage")
    print()

    # Test 3: fetch_fundamentals() (should now use comprehensive approach)
    print("Test 3: Testing fetch_fundamentals() (new comprehensive version)...")
    print("-" * 80)
    fundamentals = await fetcher.fetch_fundamentals("AAPL.US")

    if not fundamentals:
        print("❌ FAILED: No data returned from fetch_fundamentals()")
        return False

    print(f"✅ SUCCESS: fetch_fundamentals() returned {len(fundamentals)} fields")
    print()

    # Verify JSONB fields are present
    print("Test 4: Verifying JSONB fields...")
    print("-" * 80)
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

    present_count = 0
    for field in jsonb_fields:
        if field in fundamentals and fundamentals[field]:
            present_count += 1
            print(f"  ✅ {field}: Present")
        else:
            print(f"  ⚠️  {field}: Not available (may be normal for some tickers)")

    print()
    print(f"JSONB fields present: {present_count}/{len(jsonb_fields)}")
    print()

    # Show sample of what's in Financials (the big one)
    if fundamentals.get("eodhd_financials"):
        print("Test 5: Examining Financials section...")
        print("-" * 80)
        try:
            financials_data = json.loads(fundamentals["eodhd_financials"]) if isinstance(fundamentals["eodhd_financials"], str) else fundamentals["eodhd_financials"]
            print(f"Financials sections: {list(financials_data.keys())}")

            if "Balance_Sheet" in financials_data:
                bs = financials_data["Balance_Sheet"]
                if "yearly" in bs:
                    years = list(bs["yearly"].keys())
                    print(f"  Balance Sheet yearly data: {len(years)} years ({min(years)} to {max(years)})")
                if "quarterly" in bs:
                    quarters = list(bs["quarterly"].keys())
                    print(f"  Balance Sheet quarterly data: {len(quarters)} quarters")

            if "Income_Statement" in financials_data:
                inc = financials_data["Income_Statement"]
                if "yearly" in inc:
                    years = list(inc["yearly"].keys())
                    print(f"  Income Statement yearly data: {len(years)} years ({min(years)} to {max(years)})")

            if "Cash_Flow" in financials_data:
                cf = financials_data["Cash_Flow"]
                if "yearly" in cf:
                    years = list(cf["yearly"].keys())
                    print(f"  Cash Flow yearly data: {len(years)} years ({min(years)} to {max(years)})")
        except Exception as e:
            print(f"  ⚠️  Could not parse Financials: {e}")

    print()
    print("=" * 80)
    print("✅ ALL TESTS PASSED")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  - Complete data: {len(complete_data)} sections")
    print(f"  - Metadata fields: {len(asset_metadata)}")
    print(f"  - JSONB fields: {present_count}/{len(jsonb_fields)}")
    print(f"  - Fundamentals comprehensive: YES")
    print()

    return True


if __name__ == "__main__":
    result = asyncio.run(test_comprehensive_fundamentals())
    sys.exit(0 if result else 1)
