"""Snapshot the NWS daily-high forecast at each series' settlement station.

Stations live in stations.json (series ticker -> NWS station ID), so adding
a city means adding one line there, not editing code. Forecasts go into the
same SQLite database as the Kalshi prices.

Usage:
    python nws.py KXHIGHAUS KXHIGHNY KXHIGHCHI
    python nws.py --show KXHIGHAUS
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).parent
DB_PATH = HERE / "data" / "kalshi.db"
STATIONS = json.loads((HERE / "stations.json").read_text())
API = "https://api.weather.gov"
# NWS requires a User-Agent that identifies you. Put your own email here.
HEADERS = {"User-Agent": "kalshi-weather-engine (your-email@example.com)",
           "Accept": "application/geo+json"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS nws_forecasts (
    fetched_at       TEXT NOT NULL,  -- UTC, when we pulled it
    series           TEXT NOT NULL,  -- e.g. KXHIGHAUS
    station          TEXT NOT NULL,  -- e.g. KAUS (the settlement station)
    forecast_date    TEXT NOT NULL,  -- local date the high is for, YYYY-MM-DD
    period_name      TEXT,           -- e.g. "Thursday", "This Afternoon"
    high_f           INTEGER,        -- forecast daytime high, °F
    short_forecast   TEXT,
    forecast_updated TEXT,           -- when NWS last updated this forecast
    raw              TEXT
);
CREATE INDEX IF NOT EXISTS idx_nws_series_date
    ON nws_forecasts (series, forecast_date, fetched_at);
"""


def get(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()


def forecast_url(station):
    """Station ID -> the forecast for the NWS grid cell the station sits in."""
    lon, lat = get(f"{API}/stations/{station}")["geometry"]["coordinates"]
    return get(f"{API}/points/{lat:.4f},{lon:.4f}")["properties"]["forecast"]


def daytime_highs(station):
    props = get(forecast_url(station))["properties"]
    updated = props.get("updateTime") or props.get("generatedAt")
    for p in props["periods"]:
        if not p.get("isDaytime"):
            continue  # night periods carry the low, not the high
        temp = p.get("temperature")
        if isinstance(temp, dict):  # newer API format: {"value": ..., "unitCode": ...}
            temp = temp.get("value")
        if p.get("temperatureUnit", "F") == "C" and temp is not None:
            temp = round(temp * 9 / 5 + 32)
        yield p["startTime"][:10], p.get("name"), temp, p.get("shortForecast"), updated, p


def snapshot(con, series_list):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for series in series_list:
        if series not in STATIONS:
            print(f"{series}: no station in stations.json, skipped")
            continue
        station = STATIONS[series]["station"]
        try:
            rows = [
                (now, series, station, d, name, t, short, upd, json.dumps(raw))
                for d, name, t, short, upd, raw in daytime_highs(station)
            ]
        except (requests.RequestException, KeyError) as e:
            print(f"{series} ({station}): failed ({e})")
            continue
        con.executemany(
            "INSERT INTO nws_forecasts VALUES (?,?,?,?,?,?,?,?,?)", rows
        )
        first = rows[0] if rows else None
        print(f"{series} ({station}): saved {len(rows)} days"
              + (f", next high {first[5]}°F on {first[3]}" if first else ""))
    con.commit()


def show(con, series_list):
    print("NWS forecasts saved so far:")
    for series, station, n, last in con.execute(
        """SELECT series, station, COUNT(DISTINCT fetched_at), MAX(fetched_at)
           FROM nws_forecasts GROUP BY series, station"""
    ):
        print(f"  {series:<12} {station}  {n} snapshots, latest {last}")
    for series in series_list:
        print(f"\nLatest {series} forecast:")
        for d, name, t, short in con.execute(
            """SELECT forecast_date, period_name, high_f, short_forecast
               FROM nws_forecasts WHERE series = ? AND fetched_at =
                 (SELECT MAX(fetched_at) FROM nws_forecasts WHERE series = ?)
               ORDER BY forecast_date""",
            (series, series),
        ):
            print(f"  {d}  {str(name):<16} high {t}°F  {short}")


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
