#!/usr/bin/env python3
"""
Automated Ticker List Refresh System

Fetches and organizes ticker lists from EODHD API by market/region.
Runs weekly to keep ticker lists up to date with IPOs, delistings, etc.

Usage:
    python scripts/refresh_ticker_lists.py --api-key YOUR_KEY
    python scripts/refresh_ticker_lists.py --region US
    python scripts/refresh_ticker_lists.py --region EUROPE --markets LSE,XETRA,PA
"""

import argparse
import os
import sys
import requests
from datetime import datetime
from typing import List, Dict
from pathlib import Path


# Market configurations
MARKETS = {
    # US Markets
    "US_NYSE": {
        "exchange": "US",
        "filter_exchanges": ["NYSE"],
        "asset_type": "Common Stock",
        "description": "New York Stock Exchange (NYSE)",
        "output": "config/tickers/us_nyse.txt",
    },
    "US_NASDAQ": {
        "exchange": "US",
        "filter_exchanges": ["NASDAQ"],
        "asset_type": "Common Stock",
        "description": "NASDAQ Stock Exchange",
        "output": "config/tickers/us_nasdaq.txt",
    },
    "US_LARGE_CAP": {
        "exchange": "US",
        "filter_exchanges": ["NYSE", "NASDAQ"],
        "asset_type": "Common Stock",
        "description": "US Large Cap (NYSE + NASDAQ Combined)",
        "output": "config/tickers/us_large_cap.txt",
    },

    # UK
    "LSE": {
        "exchange": "LSE",
        "asset_type": "Common Stock",
        "description": "London Stock Exchange",
        "output": "config/tickers/uk_lse.txt",
    },

    # Germany
    "XETRA": {
        "exchange": "XETRA",
        "asset_type": "Common Stock",
        "description": "XETRA (German Electronic Exchange)",
        "output": "config/tickers/germany_xetra.txt",
    },
    "FRANKFURT": {
        "exchange": "F",
        "asset_type": "Common Stock",
        "description": "Frankfurt Stock Exchange",
        "output": "config/tickers/germany_frankfurt.txt",
    },

    # France
    "EURONEXT_PARIS": {
        "exchange": "PA",
        "asset_type": "Common Stock",
        "description": "Euronext Paris",
        "output": "config/tickers/france_euronext.txt",
    },

    # Spain
    "MADRID": {
        "exchange": "MC",
        "asset_type": "Common Stock",
        "description": "Madrid Stock Exchange",
        "output": "config/tickers/spain_madrid.txt",
    },

    # Italy
    "MILAN": {
        "exchange": "MI",
        "asset_type": "Common Stock",
        "description": "Milan Stock Exchange",
        "output": "config/tickers/italy_milan.txt",
    },

    # Netherlands
    "EURONEXT_AMSTERDAM": {
        "exchange": "AS",
        "asset_type": "Common Stock",
        "description": "Euronext Amsterdam",
        "output": "config/tickers/netherlands_euronext.txt",
    },

    # Switzerland
    "SIX_SWISS": {
        "exchange": "SW",
        "asset_type": "Common Stock",
        "description": "SIX Swiss Exchange",
        "output": "config/tickers/switzerland_six.txt",
    },

    # Portugal
    "EURONEXT_LISBON": {
        "exchange": "LS",
        "asset_type": "Common Stock",
        "description": "Euronext Lisbon (PSI 20)",
        "output": "config/tickers/portugal_euronext.txt",
    },

    # Belgium
    "EURONEXT_BRUSSELS": {
        "exchange": "BR",
        "asset_type": "Common Stock",
        "description": "Euronext Brussels",
        "output": "config/tickers/belgium_euronext.txt",
    },

    # Nordic Countries
    "STOCKHOLM": {
        "exchange": "ST",
        "asset_type": "Common Stock",
        "description": "Stockholm Stock Exchange",
        "output": "config/tickers/sweden_stockholm.txt",
    },
    "OSLO": {
        "exchange": "OL",
        "asset_type": "Common Stock",
        "description": "Oslo Stock Exchange",
        "output": "config/tickers/norway_oslo.txt",
    },
    "COPENHAGEN": {
        "exchange": "CO",
        "asset_type": "Common Stock",
        "description": "Copenhagen Stock Exchange",
        "output": "config/tickers/denmark_copenhagen.txt",
    },
    "HELSINKI": {
        "exchange": "HE",
        "asset_type": "Common Stock",
        "description": "Helsinki Stock Exchange",
        "output": "config/tickers/finland_helsinki.txt",
    },

    # Austria
    "VIENNA": {
        "exchange": "VI",
        "asset_type": "Common Stock",
        "description": "Vienna Stock Exchange",
        "output": "config/tickers/austria_vienna.txt",
    },
}


def fetch_exchange_tickers(exchange: str, api_key: str) -> List[Dict]:
    """Fetch all tickers for an exchange from EODHD API."""
    url = f"https://eodhd.com/api/exchange-symbol-list/{exchange}"
    params = {
        "api_token": api_key,
        "fmt": "json",
    }

    print(f"  Fetching from EODHD API: {exchange}...", end=" ")
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    print(f"✓ {len(data)} tickers")
    return data


def filter_tickers(
    tickers: List[Dict],
    asset_type: str = "Common Stock",
    filter_exchanges: List[str] = None,
) -> List[Dict]:
    """Filter tickers by criteria."""
    filtered = []

    for ticker in tickers:
        # Filter by type
        if asset_type and ticker.get("Type") != asset_type:
            continue

        # Filter by exchange (if specified)
        if filter_exchanges and ticker.get("Exchange") not in filter_exchanges:
            continue

        filtered.append(ticker)

    return filtered


def write_ticker_file(tickers: List[Dict], output_path: str, description: str, market_name: str):
    """Write tickers to file with metadata."""
    # Create directory if needed
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write(f"# {description}\n")
        f.write(f"# Market: {market_name}\n")
        f.write(f"# Auto-generated from EODHD API\n")
        f.write(f"# Generated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"# Total tickers: {len(tickers)}\n")
        f.write(f"#\n")
        f.write(f"# Format: One ticker per line (lines starting with # are ignored)\n\n")

        for ticker in sorted(tickers, key=lambda t: t["Code"]):
            f.write(f"{ticker['Code']}\n")

    print(f"    ✓ Written {len(tickers)} tickers to {output_path}")


def refresh_market(market_name: str, config: Dict, api_key: str) -> Dict:
    """Refresh ticker list for a single market."""
    print(f"\n📊 {market_name}: {config['description']}")

    # Fetch from API
    tickers = fetch_exchange_tickers(config["exchange"], api_key)

    # Apply filters
    filtered = filter_tickers(
        tickers,
        asset_type=config.get("asset_type"),
        filter_exchanges=config.get("filter_exchanges"),
    )

    print(f"  Filtered: {len(filtered)} tickers (from {len(tickers)} total)")

    # Write to file
    write_ticker_file(
        filtered,
        config["output"],
        config["description"],
        market_name,
    )

    return {
        "market": market_name,
        "total": len(tickers),
        "filtered": len(filtered),
        "file": config["output"],
    }


def main():
    parser = argparse.ArgumentParser(description="Refresh ticker lists from EODHD API")
    parser.add_argument(
        "--api-key",
        help="EODHD API key (or set EODHD_API_KEY env var)",
    )
    parser.add_argument(
        "--markets",
        help="Comma-separated list of markets to refresh (default: all)",
    )
    parser.add_argument(
        "--region",
        choices=["US", "EUROPE", "NORDIC", "ALL"],
        help="Refresh all markets in a region",
    )

    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or os.getenv("EODHD_API_KEY")
    if not api_key:
        print("❌ ERROR: EODHD_API_KEY not provided (use --api-key or set env var)")
        sys.exit(1)

    # Determine which markets to refresh
    markets_to_refresh = []

    if args.markets:
        requested = [m.strip() for m in args.markets.split(",")]
        for m in requested:
            if m not in MARKETS:
                print(f"⚠️  WARNING: Unknown market '{m}', skipping")
            else:
                markets_to_refresh.append(m)
    elif args.region:
        if args.region == "US":
            markets_to_refresh = ["US_NYSE", "US_NASDAQ", "US_LARGE_CAP"]
        elif args.region == "EUROPE":
            markets_to_refresh = [
                "LSE", "XETRA", "FRANKFURT",
                "EURONEXT_PARIS", "MADRID", "MILAN",
                "EURONEXT_AMSTERDAM", "SIX_SWISS",
                "EURONEXT_LISBON", "EURONEXT_BRUSSELS",
            ]
        elif args.region == "NORDIC":
            markets_to_refresh = ["STOCKHOLM", "OSLO", "COPENHAGEN", "HELSINKI"]
        elif args.region == "ALL":
            markets_to_refresh = list(MARKETS.keys())
    else:
        # Default: refresh all
        markets_to_refresh = list(MARKETS.keys())

    if not markets_to_refresh:
        print("❌ No markets to refresh")
        sys.exit(1)

    print("=" * 80)
    print("🔄 Ticker List Refresh System")
    print("=" * 80)
    print(f"Markets to refresh: {len(markets_to_refresh)}")
    print(f"  {', '.join(markets_to_refresh[:5])}" + (f" ... ({len(markets_to_refresh) - 5} more)" if len(markets_to_refresh) > 5 else ""))

    # Refresh each market
    results = []
    for market in markets_to_refresh:
        try:
            result = refresh_market(market, MARKETS[market], api_key)
            results.append(result)
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append({
                "market": market,
                "error": str(e),
            })

    # Summary
    print("\n" + "=" * 80)
    print("📈 SUMMARY")
    print("=" * 80)

    total_tickers = sum(r.get("filtered", 0) for r in results)
    successful = sum(1 for r in results if "error" not in r)
    failed = len(results) - successful

    print(f"Markets refreshed: {successful}/{len(results)}")
    print(f"Total tickers collected: {total_tickers:,}")

    if failed > 0:
        print(f"\n⚠️  {failed} markets failed:")
        for r in results:
            if "error" in r:
                print(f"  - {r['market']}: {r['error']}")

    print("\n✓ Ticker list refresh complete!")
    print(f"Files written to: config/tickers/")


if __name__ == "__main__":
    main()
