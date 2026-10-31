"""Bitcoin data for the longer BTC tests (btc_signs.py, btc_stop_autopsy.py): BTCUSDT perpetual (Binance futures UM)
January 2024 - October 2026 from the public archives at data.binance.vision:

  ../.cache/btc_long     1-minute candles with the taker-buy volume (monthly files, October 2026 daily files)
  ../.cache/btc_metrics  open interest and the trader long / short ratios every 5 minutes (daily files) and the funding
                         rate every 8 hours (monthly files)

    python -I btc_data.py --download      fetch whatever is missing (about 60 MB)

Points are "points at $70,000": every move is taken as a share of the price and multiplied by 70,000, so a 450-point
target is 0.64% of the price whatever BTC cost then (BTC was $40,000-125,000 in these years; 58,000-80,000 in
July-October 2026, where the earlier BTC tests used plain points).
"""
import datetime as dt, io, os, subprocess, sys, zipfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '..', '.cache')
KL, MET = os.path.join(CACHE, 'btc_long'), os.path.join(CACHE, 'btc_metrics')
REF = 70000.0
COST = 0.0006 * REF              # 0.06% a trade (taker in, maker out) = 42 points
BASE = 'https://data.binance.vision/data/futures/um'
FIRST, LAST_MONTH = dt.date(2024, 1, 1), dt.date(2026, 9, 1)     # monthly files to September 2026, then daily

def download(last=None):
    last = last or dt.date.today() - dt.timedelta(days=1)
    os.makedirs(KL, exist_ok=True); os.makedirs(MET, exist_ok=True)
    jobs, d = [], FIRST
    while d <= LAST_MONTH:
        ym = f"{d:%Y-%m}"
        jobs += [(f"{BASE}/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-{ym}.zip", KL),
                 (f"{BASE}/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-{ym}.zip", MET)]
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    d = (LAST_MONTH + dt.timedelta(days=31)).replace(day=1)
    while d <= last:
        jobs.append((f"{BASE}/daily/klines/BTCUSDT/1m/BTCUSDT-1m-{d}.zip", KL))
        d += dt.timedelta(days=1)
    d = FIRST
    while d <= last:
        jobs.append((f"{BASE}/daily/metrics/BTCUSDT/BTCUSDT-metrics-{d}.zip", MET))
        d += dt.timedelta(days=1)
    for url, to in jobs:
        f = os.path.join(to, url.rsplit('/', 1)[1])
        if not (os.path.exists(f) and zipfile.is_zipfile(f)):
            subprocess.run(['curl', '-sSf', '-o', f, url])

def _rows(path):
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            for line in io.TextIOWrapper(z.open(name)):
                if line[:1].isdigit():
                    yield line.rstrip().split(',')

def load():
    """-> dict of numpy arrays: m (minute number since 1970), o, h, l, c, v, tb (taker-buy volume); oi (open interest,
    the last 5-minute value at or before each minute), top (top traders' long / short account ratio), taker (taker long
    / short volume ratio), fund (the last funding rate)."""
    npz = os.path.join(CACHE, 'btc_long.npz')
    files = sorted(f for f in os.listdir(KL) if f.endswith('.zip'))
    stamp = f"{len(files)}:{files[-1]}:{len(os.listdir(MET))}"
    if os.path.exists(npz):
        z = np.load(npz)
        if str(z['stamp']) == stamp:
            return {k: z[k] for k in z.files if k != 'stamp'}
    k = {}
    for fn in files:
        p = os.path.join(KL, fn)
        if not zipfile.is_zipfile(p):
            continue                                  # a day not published yet (the archive answers 404)
        for r in _rows(p):
            t = int(r[0])
            t = t // 1000 if t > 10 ** 14 else t          # microseconds in some newer files
            k[t // 60000] = (float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[9]))
    m = np.array(sorted(k), dtype=np.int64)
    a = np.array([k[x] for x in m])
    del k
    out = dict(m=m, o=a[:, 0], h=a[:, 1], l=a[:, 2], c=a[:, 3], v=a[:, 4], tb=a[:, 5])
    met, fund = {}, {}
    for fn in sorted(os.listdir(MET)):
        p = os.path.join(MET, fn)
        if not zipfile.is_zipfile(p):
            continue
        if 'metrics' in fn:
            for r in _rows(p):
                t = int(dt.datetime.fromisoformat(r[0]).replace(tzinfo=dt.timezone.utc).timestamp()) // 60
                try:
                    met[t] = (float(r[2]), float(r[4] or 'nan'), float(r[7] or 'nan'))
                except ValueError:
                    pass
        else:
            for r in _rows(p):
                fund[int(r[0]) // 60000] = float(r[2])
    mt = np.array(sorted(met), dtype=np.int64)
    ma = np.array([met[x] for x in mt])
    j = np.searchsorted(mt, m, side='right') - 1                     # the last value known at each minute
    ok = j >= 0
    ma[ma <= 0] = np.nan                                              # a few broken rows say 0
    for n, col in (('oi', 0), ('top', 1), ('taker', 2)):
        x = np.full(len(m), np.nan)
        x[ok] = ma[j[ok], col]
        x[ok & (m - mt[np.maximum(j, 0)] > 30)] = np.nan              # missing more than 30 minutes
        out[n] = x
    ft = np.array(sorted(fund), dtype=np.int64)
    fa = np.array([fund[x] for x in ft])
    j = np.searchsorted(ft, m, side='right') - 1
    out['fund'] = np.where(j >= 0, fa[np.maximum(j, 0)], np.nan)
    np.savez(npz, stamp=stamp, **out)
    return out

D = load() if __name__ != '__main__' else None

def when(minute):
    return dt.datetime.fromtimestamp(int(minute) * 60, dt.timezone.utc)

def first_hit(i, side, e, up, down, n=1440):
    """From the candle after index i: which comes first, `up` points (at $70,000) the trade's way or `down` against, within
    n minutes. -> ('win' | 'loss' | 'time', exit index, points after costs). A candle reaching both counts as the loss."""
    h, l, c = D['h'][i + 1:i + 1 + n], D['l'][i + 1:i + 1 + n], D['c'][i + 1:i + 1 + n]
    if not len(h):
        return None
    k = e / REF
    tgt, stp = e + side * up * k, e - side * down * k
    win = (h >= tgt) if side > 0 else (l <= tgt)
    los = (l <= stp) if side > 0 else (h >= stp)
    jw = int(np.argmax(win)) if win.any() else 10 ** 9
    jl = int(np.argmax(los)) if los.any() else 10 ** 9
    if jl <= jw and jl < 10 ** 9:
        return 'loss', i + 1 + jl, -down - COST
    if jw < 10 ** 9:
        return 'win', i + 1 + jw, up - COST
    return 'time', i + len(h), side * (c[-1] - e) / k - COST

if __name__ == '__main__' and '--download' in sys.argv:
    download()
