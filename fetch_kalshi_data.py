"""Pull today's open Kalshi high-temperature markets for one city.

Usage:
    python fetch_one.py            # Austin
    python fetch_one.py KXHIGHNY   # any other city's series
"""
import json
import sys

import requests

BASE = "https://external-api.kalshi.com/trade-api/v2"
SERIES = sys.argv[1] if len(sys.argv) > 1 else "KXHIGHAUS"


def main():
    resp = requests.get(
        f"{BASE}/markets",
        params={"series_ticker": SERIES, "status": "open"},
        timeout=15,
    )
    resp.raise_for_status()
    markets = resp.json().get("markets", [])

    if not markets:
        print(f"No open markets for {SERIES}. Check the ticker on kalshi.com.")
        return

    # Step 1: look at one raw market so you learn the real field names.
    print("=== One raw market ===")
    print(json.dumps(markets[0], indent=2))

    # Step 2: a readable table of every bracket.
    print(f"\n=== {SERIES}: {len(markets)} open brackets ===")
    for m in sorted(markets, key=lambda m: m.get("floor_strike") or -999):
        label = m.get("yes_sub_title") or m.get("subtitle") or m.get("title")
        bid, ask = m.get("yes_bid"), m.get("yes_ask")
        print(f"{m['ticker']:<30} {str(label):<20} bid {bid}  ask {ask}")


if __name__ == "__main__":
    main()
