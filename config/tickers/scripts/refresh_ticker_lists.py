#!/usr/bin/env python3
"""
Automated Ticker List Refresh System

Fetches and organizes ticker lists from EODHD API by market/region.
Stores exchange information that will be saved to PostgreSQL assets table.

Usage:
    python scripts/refresh_ticker_lists.py --region US
    python scripts/refresh_ticker_lists.py --region EUROPE
    python scripts/refresh_ticker_lists.py --region ALL
"""

import argparse
import os
import sys
import requests
from datetime import datetime
from typing import List, Dict
from pathlib import Path


# Market configurations with exchange codes for PostgreSQL
MARKETS = {
    # === UNITED STATES ===
    "US_NYSE": {
        "exchange_code": "US",  # EODHD API exchange
        "exchange_name": "NYSE",  # Actual exchange for PostgreSQL
        "filter_exchanges": ["NYSE"],
        "asset_type": "Common Stock",
        "description": "New York Stock Exchange (NYSE)",
        "output": "config/tickers/usa/nyse.txt",
        "region": "USA",
    },
    "US_NASDAQ": {
        "exchange_code": "US",
        "exchange_name": "NASDAQ",
        "filter_exchanges": ["NASDAQ"],
        "asset_type": "Common Stock",
        "description": "NASDAQ Stock Exchange",
        "output": "config/tickers/usa/nasdaq.txt",
        "region": "USA",
    },

    # === EUROPE - UK ===
    "LSE": {
        "exchange_code": "LSE",
        "exchange_name": "LSE",
        "asset_type": "Common Stock",
        "description": "London Stock Exchange",
        "output": "config/tickers/europe/uk_lse.txt",
        "region": "EUROPE",
        "country": "UK",
    },

    # === EUROPE - GERMANY ===
    "XETRA": {
        "exchange_code": "XETRA",
        "exchange_name": "XETRA",
        "asset_type": "Common Stock",
        "description": "XETRA (German Electronic Exchange)",
        "output": "config/tickers/europe/germany_xetra.txt",
        "region": "EUROPE",
        "country": "Germany",
    },
    "FRANKFURT": {
        "exchange_code": "F",
        "exchange_name": "FRA",
        "asset_type": "Common Stock",
        "description": "Frankfurt Stock Exchange",
        "output": "config/tickers/europe/germany_frankfurt.txt",
        "region": "EUROPE",
        "country": "Germany",
    },

    # === EUROPE - FRANCE ===
    "EURONEXT_PARIS": {
        "exchange_code": "PA",
        "exchange_name": "PAR",
        "asset_type": "Common Stock",
        "description": "Euronext Paris (CAC 40)",
        "output": "config/tickers/europe/france_euronext.txt",
        "region": "EUROPE",
        "country": "France",
    },

    # === EUROPE - SPAIN ===
    "MADRID": {
        "exchange_code": "MC",
        "exchange_name": "BME",
        "asset_type": "Common Stock",
        "description": "Madrid Stock Exchange (IBEX 35)",
        "output": "config/tickers/europe/spain_madrid.txt",
        "region": "EUROPE",
        "country": "Spain",
    },

    # === EUROPE - NETHERLANDS ===
    "EURONEXT_AMSTERDAM": {
        "exchange_code": "AS",
        "exchange_name": "AMS",
        "asset_type": "Common Stock",
        "description": "Euronext Amsterdam (AEX)",
        "output": "config/tickers/europe/netherlands_euronext.txt",
        "region": "EUROPE",
        "country": "Netherlands",
    },

    # === EUROPE - SWITZERLAND ===
    "SIX_SWISS": {
        "exchange_code": "SW",
        "exchange_name": "SIX",
        "asset_type": "Common Stock",
        "description": "SIX Swiss Exchange (SMI)",
        "output": "config/tickers/europe/switzerland_six.txt",
        "region": "EUROPE",
        "country": "Switzerland",
    },

    # === EUROPE - PORTUGAL ===
    "EURONEXT_LISBON": {
        "exchange_code": "LS",
        "exchange_name": "LIS",
        "asset_type": "Common Stock",
        "description": "Euronext Lisbon (PSI 20)",
        "output": "config/tickers/europe/portugal_euronext.txt",
        "region": "EUROPE",
        "country": "Portugal",
    },

    # === EUROPE - BELGIUM ===
    "EURONEXT_BRUSSELS": {
        "exchange_code": "BR",
        "exchange_name": "BRU",
        "asset_type": "Common Stock",
        "description": "Euronext Brussels (BEL 20)",
        "output": "config/tickers/europe/belgium_euronext.txt",
        "region": "EUROPE",
        "country": "Belgium",
    },

    # === NORDIC COUNTRIES ===
    "STOCKHOLM": {
        "exchange_code": "ST",
        "exchange_name": "STO",
        "asset_type": "Common Stock",
        "description": "Stockholm Stock Exchange (OMX)",
        "output": "config/tickers/europe/sweden_stockholm.txt",
        "region": "NORDIC",
        "country": "Sweden",
    },
    "OSLO": {
        "exchange_code": "OL",
        "exchange_name": "OSL",
        "asset_type": "Common Stock",
        "description": "Oslo Stock Exchange",
        "output": "config/tickers/europe/norway_oslo.txt",
        "region": "NORDIC",
        "country": "Norway",
    },
    "COPENHAGEN": {
        "exchange_code": "CO",
        "exchange_name": "CPH",
        "asset_type": "Common Stock",
        "description": "Copenhagen Stock Exchange (OMX)",
        "output": "config/tickers/europe/denmark_copenhagen.txt",
        "region": "NORDIC",
        "country": "Denmark",
    },
    "HELSINKI": {
        "exchange_code": "HE",
        "exchange_name": "HEL",
        "asset_type": "Common Stock",
        "description": "Helsinki Stock Exchange (OMX)",
        "output": "config/tickers/europe/finland_helsinki.txt",
        "region": "NORDIC",
        "country": "Finland",
    },

    # === AUSTRIA ===
    "VIENNA": {
        "exchange_code": "VI",
        "exchange_name": "VIE",
        "asset_type": "Common Stock",
        "description": "Vienna Stock Exchange",
        "output": "config/tickers/europe/austria_vienna.txt",
        "region": "EUROPE",
        "country": "Austria",
    },
}


def fetch_exchange_tickers(exchange_code: str, api_key: str) -> List[Dict]:
    """Fetch all tickers for an exchange from EODHD API."""
    url = f"https://eodhd.com/api/exchange-symbol-list/{exchange_code}"
    params = {
        "api_token": api_key,
        "fmt": "json",
    }

    print(f"  Fetching from EODHD: {exchange_code}...", end=" ")
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


def write_ticker_file(
    tickers: List[Dict],
    output_path: str,
    description: str,
    market_name: str,
    exchange_name: str,
    country: str = None,
):
    """Write tickers to file with metadata for PostgreSQL import."""
    # Create directory if needed
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        f.write(f"# {description}\n")
        f.write(f"# Market: {market_name}\n")
        f.write(f"# Exchange: {exchange_name} (for PostgreSQL assets.exchange column)\n")
        if country:
            f.write(f"# Country: {country}\n")
        f.write(f"# Auto-generated from EODHD API\n")
        f.write(f"# Generated: {datetime.utcnow().isoformat()}Z\n")
        f.write(f"# Total tickers: {len(tickers)}\n")
        f.write(f"#\n")
        f.write(f"# Format: TICKER (exchange={exchange_name} will be stored in PostgreSQL)\n")
        f.write(f"# Lines starting with # are ignored\n\n")

        for ticker in sorted(tickers, key=lambda t: t["Code"]):
            f.write(f"{ticker['Code']}\n")

    print(f"    ✓ Written {len(tickers)} tickers to {output_path}")


def refresh_market(market_name: str, config: Dict, api_key: str) -> Dict:
    """Refresh ticker list for a single market."""
    print(f"\n📊 {market_name}: {config['description']}")

    # Fetch from API
    tickers = fetch_exchange_tickers(config["exchange_code"], api_key)

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
        config["exchange_name"],
        config.get("country"),
    )

    return {
        "market": market_name,
        "exchange": config["exchange_name"],
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
            markets_to_refresh = ["US_NYSE", "US_NASDAQ"]
        elif args.region == "EUROPE":
            markets_to_refresh = [
                "LSE", "XETRA", "FRANKFURT",
                "EURONEXT_PARIS", "MADRID",
                "EURONEXT_AMSTERDAM", "SIX_SWISS",
                "EURONEXT_LISBON", "EURONEXT_BRUSSELS",
                "VIENNA",
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
    print(f"Output directory: config/tickers/{{usa,europe}}/")
    print(f"Exchange codes will be stored in PostgreSQL assets.exchange column")
    print()

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

    if successful > 0:
        print("\nExchange codes (for PostgreSQL assets.exchange):")
        exchanges = {}
        for r in results:
            if "error" not in r and "exchange" in r:
                ex = r["exchange"]
                exchanges[ex] = exchanges.get(ex, 0) + r["filtered"]

        for ex, count in sorted(exchanges.items()):
            print(f"  {ex:10s} - {count:5,} tickers")

    if failed > 0:
        print(f"\n⚠️  {failed} markets failed:")
        for r in results:
            if "error" in r:
                print(f"  - {r['market']}: {r['error']}")

    print("\n✓ Ticker list refresh complete!")
    print(f"Files organized by market: config/tickers/usa/ and config/tickers/europe/")


if __name__ == "__main__":
    main()
