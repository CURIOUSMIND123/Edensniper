"""Download again the candles the research scripts read from ../.cache (it isn't kept in git, so a new machine starts
without it): Nifty and Sensex 1-minute candles January 2023 - today, NIFTYBEES 1-minute candles with volume (2023-2024
in niftybees_1m_old.json, 2025 on in niftybees_1m.json) and the official daily candles. Upstox's public candle API.

    python rebuild_cache.py
"""
import calendar, datetime as dt, json, os, time, urllib.parse, urllib.request

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.cache')
KEYS = {'nifty': 'NSE_INDEX|Nifty 50', 'sensex': 'BSE_INDEX|SENSEX', 'niftybees': 'NSE_EQ|INF204KB14I2'}

def get(url):
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'curl/8.5.0'})
    for k in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)['data']['candles']
        except Exception as e:
            print('  retry', url[-40:], e)
            time.sleep(2 ** (k + 1))
    return []

def minutes(name, start, end):
    out, y, m = {}, start.year, start.month
    while (y, m) <= (end.year, end.month):
        a, b = dt.date(y, m, 1), min(dt.date(y, m, calendar.monthrange(y, m)[1]), end)
        for r in get(f"https://api.upstox.com/v3/historical-candle/{urllib.parse.quote(KEYS[name], safe='')}/minutes/1/{b}/{a}"):
            out[r[0][:16].replace('T', ' ')] = r[1:6] if name == 'niftybees' else r[1:5]
        time.sleep(0.4)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out

if __name__ == '__main__':
    os.makedirs(CACHE, exist_ok=True)
    today = dt.date.today()
    for name in ('nifty', 'sensex'):
        raw = minutes(name, dt.date(2023, 1, 1), today)
        json.dump(raw, open(os.path.join(CACHE, f'{name}_1m.json'), 'w'))
        print(name, len(raw), 'minutes', min(raw), '-', max(raw))
        rows = get(f"https://api.upstox.com/v3/historical-candle/{urllib.parse.quote(KEYS[name], safe='')}/days/1/{today}/2022-11-01")
        json.dump({r[0][:10]: r for r in rows}, open(os.path.join(CACHE, f'{name}_daily.json'), 'w'))
        print(name, len(rows), 'daily candles')
    bees = minutes('niftybees', dt.date(2023, 1, 1), today)
    json.dump({k: v for k, v in bees.items() if k < '2025'}, open(os.path.join(CACHE, 'niftybees_1m_old.json'), 'w'))
    json.dump({k: v for k, v in bees.items() if k >= '2025'}, open(os.path.join(CACHE, 'niftybees_1m.json'), 'w'))
    print('niftybees', len(bees), 'minutes')
