# Kalshi Weather Market Engine

Kalshi runs daily markets on each city's high temperature: "Will Austin's high be 84–85°F tomorrow?", one market per 2° bracket. The National Weather Service publishes a forecast for the same thing, at the exact station the market settles on.

This project collects both, every hour, so I can answer one question: **how do market prices move relative to the official forecast, and is the market ever mispriced against it?**

> **Status:** data collection is live and runs every hour on its own. Analysis and a forecast-based pricing model are next.

## What it collects

**`fetch_kalshi_data.py`**: snapshots every open bracket for each city (bid, ask, last price, volume, close time) into SQLite, timestamped.

**`nws.py`**: pulls the NWS forecast for the station each market settles on, with the daily high for each upcoming day.

Cities are inputs, not hardcoded. Adding one means one line in `stations.json`:

| Series | City | Settlement station |
|---|---|---|
| KXHIGHAUS | Austin | KAUS (Austin-Bergstrom) |
| KXHIGHNY | New York | KNYC (Central Park) |
| KXHIGHCHI | Chicago | KMDW (Midway, not O'Hare) |

## How it runs

A GitHub Actions workflow (`.github/workflows/collect.yml`) runs both collectors every hour. GitHub's own scheduler is best-effort and was skipping runs, so an external cron service triggers the workflow through GitHub's API instead, with GitHub's schedule kept as a backup.

The database lives on a separate `data` branch that gets overwritten each run, so `main` stays clean and the repo doesn't grow with every snapshot. The workflow refuses to run if it can't load the existing database, so a network blip can't wipe the history.

```
cron-job.org ──hourly──► GitHub Actions
                           ├─ load kalshi.db from the data branch
                           ├─ fetch_kalshi_data.py  (Kalshi public API)
                           ├─ nws.py                (api.weather.gov)
                           └─ push kalshi.db back to the data branch
```

## Decisions taken

**Match the settlement station exactly.** Kalshi settles on a specific station's daily climate report. Chicago settles on Midway, not O'Hare, and the two can differ by several degrees. Using the wrong station would make every comparison meaningless.

**Store raw JSON next to the parsed fields.** APIs change their field names (Kalshi has moved some prices from cents to dollar strings). Keeping the full response means old snapshots can be re-parsed later instead of lost.

**SQLite over a hosted database.** It's one file, free, and versionable on a branch. At one snapshot an hour for a few cities, it'll be fine for years.

## Running it locally

```bash
pip install -r requirements.txt
python fetch_kalshi_data.py KXHIGHAUS KXHIGHNY KXHIGHCHI
python nws.py KXHIGHAUS KXHIGHNY KXHIGHCHI
python fetch_kalshi_data.py --show KXHIGHAUS     # summary + latest prices
python nws.py --show KXHIGHAUS                   # latest forecast
```

No API keys needed: both APIs are public.

## What's next

- [x] Hourly price snapshots for any list of cities
- [x] Matching NWS forecasts at each settlement station
- [x] Unattended hourly collection
- [ ] Pull the observed highs the markets actually settle on
- [ ] Measure NWS forecast error by city and lead time
- [ ] Turn forecast + error into a probability for each bracket
- [ ] Compare that probability to the market price, and chart calibration over time

## License

See [LICENSE](LICENSE).
