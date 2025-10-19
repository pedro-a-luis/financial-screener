#!/bin/bash
# Wrapper script to read ticker files and pass to main.py
# Usage: ./run_with_ticker_file.sh --mode incremental --tickers-file config/tickers/sp500.txt

set -e

MODE="incremental"
TICKER_FILE=""
ASSET_TYPE="stock"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --tickers-file)
      TICKER_FILE="$2"
      shift 2
      ;;
    --asset-type)
      ASSET_TYPE="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

# Validate ticker file
if [ -z "$TICKER_FILE" ]; then
  echo "Error: --tickers-file is required"
  exit 1
fi

if [ ! -f "$TICKER_FILE" ]; then
  echo "Error: Ticker file not found: $TICKER_FILE"
  exit 1
fi

# Read tickers from file (skip comments and empty lines)
TICKERS=$(grep -v '^#' "$TICKER_FILE" | grep -v '^$' | tr '\n' ',' | sed 's/,$//')

if [ -z "$TICKERS" ]; then
  echo "Error: No tickers found in $TICKER_FILE"
  exit 1
fi

echo "Loading tickers from: $TICKER_FILE"
echo "Mode: $MODE"
echo "Asset type: $ASSET_TYPE"
echo "Ticker count: $(echo $TICKERS | tr ',' '\n' | wc -l)"

# Call main.py with comma-separated tickers
python /app/src/main.py --mode "$MODE" --asset-type "$ASSET_TYPE" --tickers "$TICKERS"
