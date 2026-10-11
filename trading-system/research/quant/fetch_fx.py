"""1-minute candles for gold, crude oil and currency pairs from Dukascopy's free historical data feed.

    python fetch_fx.py                 (all)    or: python fetch_fx.py XAUUSD EURUSD

Symbols: XAUUSD (gold, USD an ounce), LIGHTCMDUSD (WTI crude, USD a barrel), EURUSD, GBPUSD, USDJPY.
15 May to 9 October 2026 (the last 3 months tested, plus history for the profiles), bid prices, UTC times, tick volume. Saved to ../.cache/fx_{symbol}.npz with arrays
t (epoch minutes, UTC), o, h, l, c, v. Gold and crude on MCX follow these international prices closely.
"""
import datetime as dt, lzma, os, struct, sys, time, urllib.request
import numpy as np

SYMS = {'XAUUSD': 1000.0, 'LIGHTCMDUSD': 1000.0, 'EURUSD': 100000.0, 'GBPUSD': 100000.0, 'USDJPY': 1000.0}
HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://www.dukascopy.com/swiss/english/marketwatch/historical/'}
FIRST, LAST = dt.date(2026, 5, 15), dt.date(2026, 10, 9)

def day(sym, d):
    url = f"https://datafeed.dukascopy.com/datafeed/{sym}/{d.year}/{d.month - 1:02d}/{d.day:02d}/BID_candles_min_1.bi5"
    for k in range(12):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=60) as r:
                raw = r.read()
            if not raw: return []
            data = lzma.decompress(raw)
            base = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp()) // 60
            div = SYMS[sym]
            return [(base + t // 60, o / div, h / div, l / div, c / div, v)
                    for t, o, c, l, h, v in (struct.unpack('>IIIIIf', data[i:i + 24]) for i in range(0, len(data), 24))]
        except urllib.error.HTTPError as e:
            if e.code == 404: return []
            time.sleep(min(60, 5 * (k + 1)))
        except Exception:
            time.sleep(min(60, 3 * (k + 1)))
    return None                                          # refused for now: tried again on the next pass

DAYS = '../.cache/fx_days'

def cached_day(sym, d):
    """One day, kept on disk as soon as it arrives (so an interrupted download resumes)."""
    f = f'{DAYS}/{sym}_{d}.npy'
    if os.path.exists(f): return np.load(f).tolist()
    rows = day(sym, d)
    if rows is None: return None
    np.save(f, np.array(rows, float).reshape(-1, 6))
    return rows

if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(DAYS, exist_ok=True)
    syms = [s for s in (sys.argv[1:] or SYMS) if not os.path.exists(f'../.cache/fx_{s}.npz')]
    days = []
    d = FIRST
    while d <= LAST:
        if d.weekday() != 5: days.append(d)            # Sunday evening opens the week; Saturday is closed
        d += dt.timedelta(days=1)
    todo = [(s, d) for s in syms for d in days]
    for rnd in range(6):
        if not todo: break
        left = []
        with ThreadPoolExecutor(6) as ex:
            for k, ((s, d), rows) in enumerate(zip(todo, ex.map(lambda j: cached_day(*j), todo))):
                if rows is None: left.append((s, d))
                if k % 100 == 99: print(f'pass {rnd + 1}: {k + 1} of {len(todo)}', flush=True)
        print(f'pass {rnd + 1} done, {len(left)} days refused; trying them again', flush=True)
        todo = left
        if todo: time.sleep(60)
    for s in syms:
        parts = [np.load(f'{DAYS}/{s}_{d}.npy') for d in days if os.path.exists(f'{DAYS}/{s}_{d}.npy')]
        a = np.concatenate([p for p in parts if len(p)])
        a = a[a[:, 5] > 0]                                  # minutes without trading are flat placeholders
        np.savez_compressed(f'../.cache/fx_{s}.npz', t=a[:, 0], o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4], v=a[:, 5])
        print(s, len(a), 'minutes saved', sum(1 for d in days if not os.path.exists(f'{DAYS}/{s}_{d}.npy')), 'days missing', flush=True)
