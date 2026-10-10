"""Download the exchange's official daily candles for Nifty and Sensex into ../.cache/{nifty,sensex}_daily.json.

    python fetch_daily.py

cpr_backtest.py uses their high / low / close for the CPR and pivots (the official close often differs from the
last 1-minute candle). Covers November 2025 to today.
"""
import datetime as dt, json, urllib.parse, urllib.request
for name, key in (('nifty', 'NSE_INDEX|Nifty 50'), ('sensex', 'BSE_INDEX|SENSEX')):
    url = f"https://api.upstox.com/v3/historical-candle/{urllib.parse.quote(key, safe='')}/days/1/{dt.date.today()}/2025-11-01"
    rows = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'curl/8.5.0'}), timeout=60))['data']['candles']
    json.dump({r[0][:10]: r for r in rows}, open(f'../.cache/{name}_daily.json', 'w'))
    print(name, len(rows), 'days')
