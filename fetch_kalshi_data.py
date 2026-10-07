"""Snapshot open Kalshi markets for any series into a SQLite database.

Each run saves one timestamped row per open market, for every series
ticker you pass in.

Usage:
    python fetch.py KXHIGHAUS                       # one city
    python fetch.py KXHIGHAUS KXHIGHNY KXHIGHCHI    # as many as you want
    python fetch.py --show                          # summarize everything saved
    python fetch.py --show KXHIGHAUS                # plus that series' latest prices
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://external-api.kalshi.com/trade-api/v2"
DB_PATH = Path(__file__).parent / "data" / "kalshi.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    fetched_at   TEXT NOT NULL,   -- UTC, ISO 8601
    series       TEXT NOT NULL,   -- e.g. KXHIGHAUS
    event_ticker TEXT,            -- one event = one city-day
    ticker       TEXT NOT NULL,   -- one market = one bracket
    label        TEXT,            -- e.g. "84° to 85°"
    floor_strike REAL,
    cap_strike   REAL,
    yes_bid      INTEGER,         -- cents
    yes_ask      INTEGER,         -- cents
    last_price   INTEGER,         -- cents
    volume       INTEGER,
    close_time   TEXT,
    raw          TEXT             -- full market JSON, in case fields change
);
CREATE INDEX IF NOT EXISTS idx_ticker_time ON snapshots (ticker, fetched_at);
"""


def cents(m, key):
    """Price in cents, whether Kalshi sends `yes_bid` (cents) or
    `yes_bid_dollars` (a dollar string like "0.3400")."""
    if m.get(key) is not None:
        return m[key]
    dollars = m.get(f"{key}_dollars")
    return round(float(dollars) * 100) if dollars is not None else None


def fetch_open_markets(series):
    resp = requests.get(
        f"{BASE}/markets",
        params={"series_ticker": series, "status": "open"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("markets", [])


def to_row(now, series, m):
    return (
        now, series, m.get("event_ticker"), m["ticker"],
        m.get("yes_sub_title") or m.get("subtitle"),
        m.get("floor_strike"), m.get("cap_strike"),
        cents(m, "yes_bid"), cents(m, "yes_ask"), cents(m, "last_price"),
        m.get("volume"), m.get("close_time"), json.dumps(m),
    )


def snapshot(con, series_list):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for series in series_list:
        try:
            markets = fetch_open_markets(series)
        except requests.RequestException as e:
            # One series failing shouldn't lose the others.
            print(f"{series}: request failed ({e})")
            continue
        con.executemany(
            "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [to_row(now, series, m) for m in markets],
        )
        print(f"{series}: saved {len(markets)} markets")
    con.commit()


def show(con, series_list):
    print("Saved so far:")
    for series, n_snaps, n_rows, last in con.execute(
        """SELECT series, COUNT(DISTINCT fetched_at), COUNT(*), MAX(fetched_at)
           FROM snapshots GROUP BY series"""
    ):
        print(f"  {series:<12} {n_snaps} snapshots, {n_rows} rows, latest {last}")

    for series in series_list:
        print(f"\nLatest {series}:")
        for label, bid, ask in con.execute(
            """SELECT label, yes_bid, yes_ask FROM snapshots
               WHERE series = ? AND fetched_at =
                 (SELECT MAX(fetched_at) FROM snapshots WHERE series = ?)
               ORDER BY floor_strike""",
            (series, series),
        ):
            print(f"  {str(label):<20} bid {bid}  ask {ask}")


def main():
    args = sys.argv[1:]
    showing = "--show" in args
    series_list = [a for a in args if a != "--show"]
    if not showing and not series_list:
        print(__doc__)
        return

    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    show(con, series_list) if showing else snapshot(con, series_list)
    con.close()


if __name__ == "__main__":
    main()
