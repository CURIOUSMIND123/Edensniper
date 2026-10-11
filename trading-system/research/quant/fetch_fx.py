"""1-minute candles for gold, crude oil and currency pairs from Dukascopy's free historical data feed.

    python fetch_fx.py                 (all)    or: python fetch_fx.py XAUUSD EURUSD

Symbols: XAUUSD (gold, USD an ounce), LIGHTCMDUSD (WTI crude, USD a barrel), EURUSD, GBPUSD, USDJPY.
1 October 2025 to 9 October 2026, bid prices, UTC times, tick volume. Saved to ../.cache/fx_{symbol}.npz with arrays
t (epoch minutes, UTC), o, h, l, c, v. Gold and crude on MCX follow these international prices closely.
"""
import datetime as dt, lzma, os, struct, sys, time, urllib.request
import numpy as np

SYMS = {'XAUUSD': 1000.0, 'LIGHTCMDUSD': 1000.0, 'EURUSD': 100000.0, 'GBPUSD': 100000.0, 'USDJPY': 1000.0}
HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Referer': 'https://www.dukascopy.com/swiss/english/marketwatch/historical/'}
FIRST, LAST = dt.date(2025, 10, 1), dt.date(2026, 10, 9)

def day(sym, d):
    url = f"https://datafeed.dukascopy.com/datafeed/{sym}/{d.year}/{d.month - 1:02d}/{d.day:02d}/BID_candles_min_1.bi5"
    for k in range(8):
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
            time.sleep(5 * (k + 1))
        except Exception:
            time.sleep(3 * (k + 1))
    raise RuntimeError(f'{sym} {d}: no data')

if __name__ == '__main__':
    from concurrent.futures import ThreadPoolExecutor
    syms = [s for s in (sys.argv[1:] or SYMS) if not os.path.exists(f'../.cache/fx_{s}.npz')]
    days = []
    d = FIRST
    while d <= LAST:
        if d.weekday() != 5: days.append(d)            # Sunday evening opens the week; Saturday is closed
        d += dt.timedelta(days=1)
    jobs = [(s, d) for s in syms for d in days]
    got = {}
    with ThreadPoolExecutor(10) as ex:
        for k, ((s, d), rows) in enumerate(zip(jobs, ex.map(lambda j: day(*j), jobs))):
            got[(s, d)] = rows
            if k % 100 == 99: print(k + 1, 'of', len(jobs), flush=True)
    for s in syms:
        a = np.array([r for d in days for r in got[(s, d)]], float)
        a = a[a[:, 5] > 0]                                  # minutes without trading are flat placeholders
        np.savez_compressed(f'../.cache/fx_{s}.npz', t=a[:, 0], o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4], v=a[:, 5])
        print(s, len(a), 'minutes saved', flush=True)
