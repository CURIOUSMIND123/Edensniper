"""The indicator on MCX crude oil, 2026 (asked on 23 October 2026: "crude is also giving good trades using this
indicator"). Upstox's free candles cover only crude contracts still trading (November 2026 on, from October), so the
prices are rebuilt: Dukascopy's free 1-minute WTI crude candles (LIGHT.CMD/USD, the same NYMEX crude MCX follows) x the
day's USD/INR (Yahoo Finance, the day before's close), in rupees per barrel like MCX CRUDEOIL. A first look: MCX's own
prices differ by a small premium and their own spikes.

As TradingView runs the indicator on a crude chart (its price is under 50,000, so the Nifty settings; times are IST):
the CPR from the day before's whole MCX session (9:00-23:30), the CPR Magnet at 9:16 or the 9:30 breakout, the 3-day
volume lines and yesterday's POC from NIFTYBEES volume (the indicator's "Volume from" symbol), stops at most 55 points,
the CPR BREAK (60 / 35) and OPEN HIGH LOW calls, everything between 9:15 and 15:15. One lot = 100 barrels (Rs 100 a
point). Costs 4 points a trade (as the indicator counts); a candle reaching both the stop and the target counts as the
stop.

    python crude_2026.py              (downloads ~200 days the first time: slow, Dukascopy limits the rate)
    python crude_2026.py evening      the same rules on the US-hours session instead: 18:30-00:45 IST treated as 9:15-15:30
    python crude_2026.py own          (also with evening) the volume profile from crude's own volume, not NIFTYBEES
"""
import collections, datetime as dt, json, lzma, os, struct, sys, time, urllib.request
sys.path.insert(0, '../../alerts')
import cprb_alerts as A

EVENING = 'evening' in sys.argv[1:]
OWN = 'own' in sys.argv[1:] or EVENING          # NIFTYBEES doesn't trade in the evening
RAW = '../.cache/crude'                       # downloaded data only (no code)
os.makedirs(RAW, exist_ok=True)
D0, D1 = dt.date(2025, 11, 1), dt.date(2026, 10, 22)   # November-December 2025 only for the first contexts
COST = 4.0

def get(url, tries=8):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return b''
            time.sleep(30 * (k + 1))              # 503: Dukascopy's rate limit; wait it out
        except Exception:
            time.sleep(30 * (k + 1))
    raise RuntimeError('no data: ' + url)

def wti_day(d):
    """Dukascopy WTI 1-minute candles of UTC day d: {utc minute of the day: (o, h, l, c, volume)}."""
    p = f'{RAW}/wti_{d}.json'
    if os.path.exists(p):
        return {int(k): v for k, v in json.load(open(p)).items()}
    if d.weekday() >= 5:                          # a weekend: nothing of an IST trading day (9:00 IST - 00:45 = 3:30 -
        return {}                                 # 19:15 UTC the same day)
    raw = get(f"https://datafeed.dukascopy.com/datafeed/LIGHTCMDUSD/{d.year}/{d.month - 1:02d}/{d.day:02d}/BID_candles_min_1.bi5")
    time.sleep(2)
    out = {}
    if raw:
        b = lzma.decompress(raw)
        for i in range(len(b) // 24):
            t, o, c, l, h, v = struct.unpack('>5if', b[24 * i:24 * i + 24])
            if v > 0:
                out[t // 60] = (o / 1000, h / 1000, l / 1000, c / 1000, v)
    json.dump(out, open(p, 'w'))
    return out

def usdinr():
    p = f'{RAW}/usdinr.json'
    if not os.path.exists(p):
        t0, t1 = int(dt.datetime(2025, 10, 1).timestamp()), int(dt.datetime(2026, 10, 24).timestamp())
        d = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/INR=X?period1={t0}&period2={t1}&interval=1d"))
        r = d['chart']['result'][0]
        out = {dt.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d'): c for t, c in zip(r['timestamp'], r['indicators']['quote'][0]['close']) if c}
        json.dump(out, open(p, 'w'))
    return json.load(open(p))

def load():
    days = [D0 + dt.timedelta(days=k) for k in range((D1 - D0).days + 2)]
    utc = {}
    for k, d in enumerate(days):                  # one at a time: Dukascopy refuses bursts
        utc[d] = wti_day(d)
        if k % 25 == 24:
            print(f"  ... {d}", flush=True)
    fx = usdinr()
    fxd = sorted(fx)
    sess, daily, own = {}, {}, {}
    for d in days[:-1]:
        if d.weekday() >= 5:
            continue
        prev = [x for x in fxd if x < str(d)]
        if not prev:
            continue
        r = fx[prev[-1]]
        ist = {}                                  # IST minute of day d -> candle in rupees
        for m, (o, h, l, c, v) in utc.get(d, {}).items():
            mi = m + 330                           # IST = UTC + 5:30
            if 540 <= mi < 1440 + 45:              # 9:00 IST to 00:45 the next night (3:30 - 19:15 UTC)
                ist[mi] = (o * r, h * r, l * r, c * r, v)
        if len([m for m in ist if 540 <= m < 1410]) < 600:
            continue                              # a holiday / a short day
        full = [ist[m] for m in sorted(ist) if 540 <= m < 1410]         # MCX's session 9:00-23:30
        daily[str(d)] = (full[0][0], max(x[1] for x in full), min(x[2] for x in full), full[-1][3])
        base = 1110 - 555 if EVENING else 0       # evening: 18:30 IST plays the part of 9:15
        sess[str(d)] = [(m - base,) + tuple(round(x, 2) for x in ist[m][:4]) for m in sorted(ist)
                        if A.OPEN <= m - base < A.CLOSE]
        own[str(d)] = {m - base: ist[m][4] for m in ist if A.OPEN <= m - base < A.CLOSE}
    return sess, daily, own

def bees_volume(days):
    p = f'{RAW}/niftybees.json'
    if not os.path.exists(p):
        raw = A.fetch_range(A.BEES, D0, D1)
        json.dump({d: {str(m): v for m, v in mm.items()} for d, mm in raw.items()}, open(p, 'w'))
    raw = json.load(open(p))
    return {d: {int(m): v[4] for m, v in mm.items()} for d, mm in raw.items()}

if __name__ == '__main__':
    sess, daily, own = load()
    vol = own if OWN else bees_volume(sess)
    A.RULES, A.SWEEP = 'classic', False
    A.OIWALL_CALLS, A.REENTRY_CALLS, A.GAPFILL_CALLS = {}, {}, {}
    spec = dict(A.SPEC['nifty'], cost=COST)       # as TradingView runs it on a chart under 50,000
    days = [d for d in sorted(sess) if d >= '2026-01-01' and len(sess[d]) >= 300]
    by = collections.defaultdict(list)
    for d in days:
        try:
            cx = A.context(spec, sess, vol, d, daily)
        except SystemExit:
            continue
        cx['tvol'] = vol.get(d, {})
        for t in A.day_trades(cx, sess[d], A.CLOSE - 1, True, False, 'classic'):
            if t['taken'] and t['exit']:
                by[t['src']].append((d, t['exit']['pnl']))
                by['ALL' if t['src'] not in A.EXTRA_SRC else 'EXTRA'].append((d, t['exit']['pnl']))
    print(f"MCX crude (rebuilt from WTI x USD/INR), {days[0]} - {days[-1]}, {len(days)} sessions, "
          f"{'the US-hours session' if EVENING else '9:15-15:30 IST as on TradingView'}, volume from "
          f"{'crude itself' if OWN else 'NIFTYBEES'}; costs {COST:g} points (Rs {100 * COST:g} a lot)")
    print("  trades, won %, net points (Rs per lot = x100); worst trade; months that made money")
    for k in ['ALL', 'MAGNET', 'BREAKOUT', 'REVERSAL', 'VOLUME LINE', 'EXTRA', 'CPR BREAK', 'OPEN HIGH LOW']:
        p = [x for d, x in by.get(k, [])]
        if not p:
            continue
        mon = collections.defaultdict(float)
        for d, x in by[k]:
            mon[d[:7]] += x
        print(f"  {k:14} {len(p):4} tr {round(100 * sum(x > 0 for x in p) / len(p)):3}% {sum(p):+8,.0f}  worst {min(p):+6.0f}  "
              f"{sum(v > 0 for v in mon.values())} of {len(mon)} months +  " + ' '.join(f"{m[5:]}:{v:+.0f}" for m, v in sorted(mon.items())))
