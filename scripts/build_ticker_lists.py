#!/usr/bin/env python3
"""
Build Ticker Lists from EODHD API

Fetches ticker lists from EODHD exchange-symbol-list API and creates
filtered ticker files for data collection.

Usage:
    python scripts/build_ticker_lists.py --exchange US --output config/tickers/us_large_cap.txt
    python scripts/build_ticker_lists.py --exchange LSE --output config/tickers/ftse.txt
"""

import argparse
import requests
import sys
from typing import List, Dict


def fetch_exchange_tickers(exchange: str, api_key: str) -> List[Dict]:
    """Fetch all tickers for an exchange from EODHD API."""
    url = f"https://eodhd.com/api/exchange-symbol-list/{exchange}"
    params = {
        "api_token": api_key,
        "fmt": "json",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    return response.json()


def filter_tickers(
    tickers: List[Dict],
    asset_type: str = "Common Stock",
    exchanges: List[str] = None,
    min_market_cap: int = None,
) -> List[Dict]:
    """Filter tickers by criteria."""
    filtered = []

    for ticker in tickers:
        # Filter by type
        if ticker.get("Type") != asset_type:
            continue

        # Filter by exchange (if specified)
        if exchanges and ticker.get("Exchange") not in exchanges:
            continue

        # TODO: Filter by market cap (requires fundamentals API call)
        # For now, we filter by exchange to avoid penny stocks

        filtered.append(ticker)

    return filtered


def write_ticker_file(tickers: List[Dict], output_path: str):
    """Write tickers to file, one per line."""
    with open(output_path, "w") as f:
        f.write("# Auto-generated ticker list from EODHD API\n")
        f.write(f"# Total tickers: {len(tickers)}\n\n")

        for ticker in tickers:
            f.write(f"{ticker['Code']}\n")

    print(f"✓ Written {len(tickers)} tickers to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Build ticker lists from EODHD API")
    parser.add_argument("--exchange", required=True, help="Exchange code (e.g., US, LSE, XETRA)")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--api-key", help="EODHD API key (or set EODHD_API_KEY env var)")
    parser.add_argument(
        "--asset-type",
        default="Common Stock",
        help="Asset type to filter (default: Common Stock)",
    )
    parser.add_argument(
        "--exchanges",
        help="Comma-separated list of exchanges to include (e.g., NYSE,NASDAQ)",
    )
    parser.add_argument(
        "--min-market-cap",
        type=int,
        help="Minimum market cap in millions (requires fundamentals API calls)",
    )

    args = parser.parse_args()

    # Get API key
    import os
    api_key = args.api_key or os.getenv("EODHD_API_KEY")
    if not api_key:
        print("ERROR: EODHD_API_KEY not provided (use --api-key or set env var)")
        sys.exit(1)

    print(f"Fetching tickers for exchange: {args.exchange}")
    tickers = fetch_exchange_tickers(args.exchange, api_key)
    print(f"  Found {len(tickers)} total tickers")

    # Parse exchanges filter
    exchanges_filter = None
    if args.exchanges:
        exchanges_filter = [e.strip() for e in args.exchanges.split(",")]
        print(f"  Filtering by exchanges: {exchanges_filter}")

    # Filter tickers
    filtered = filter_tickers(
        tickers,
        asset_type=args.asset_type,
        exchanges=exchanges_filter,
        min_market_cap=args.min_market_cap,
    )
    print(f"  After filtering: {len(filtered)} tickers")

    # Write to file
    write_ticker_file(filtered, args.output)

    print("\nSample tickers:")
    for ticker in filtered[:10]:
        print(f"  {ticker['Code']:10s} - {ticker.get('Name', 'N/A')[:50]}")


if __name__ == "__main__":
    main()
