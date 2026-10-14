#!/usr/bin/env python3
"""CPR Breakout alerts for Nifty and Sensex: live, free, no TradingView and no login needed.

Follows the same rules as tradingview/cpr_breakout.pine (its default settings) on live 1-minute candles from
Upstox's free public candle data. It tells you when to BUY (a call) or SELL (a put), where the stop and the target
are and when to exit: on this screen, and on your phone through Telegram if you set that up (free).
Default rules ('classic'): the daily plan (CPR Magnet at 9:16 or the 9:30 breakout) and the 3-day volume lines, one
trade at a time, set differently for each index (the most profit in the 2026 tests):
  Nifty:  the Magnet and the breakout only on the volume side of yesterday's POC (buys above it, sells below); no
          volume check.
  Sensex: the volume check on every signal (a BUY only when the last 2 hours' up candles carried more NIFTYBEES volume
          than the down candles, a SELL only when the down candles did); no POC filter.

    python cprb_alerts.py                       run today: start it any time before 9:15, leave it running
    python cprb_alerts.py --replay 2026-10-09   replay a past day in a few seconds, to see what it does
    python cprb_alerts.py --plan                only print the next session's plan (levels and trigger prices)
    python cprb_alerts.py --telegram-test       send a test message to your phone
    python cprb_alerts.py --telegram-chat-id    find your Telegram chat id (message your bot first)
On a phone (Pydroid 3) just press Run: the settings below do the same (REPLAY_DAY for a replay).
LIVE CHART: while it runs, open http://127.0.0.1:8000 in Chrome on the same phone: candles, the CPR (pink),
the volume POC and lines, the 15-minute range, and every trade as a small B / S / T / SL letter. On a weekend it
shows the last session.

Needs Python 3.8 or newer and nothing else. The settings are just below.
Times are the 1-minute candle in which something happened; the alert comes when that candle closes.
"""
import bisect
import datetime as dt
import json
import math
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

# ---------------- settings ----------------
INDICES = ['nifty', 'sensex']     # or ['nifty'] / ['sensex']
LOTS = 5                          # lots per trade, only for the rupee estimates (option moves about half the index)
RULES = 'classic'                 # 'classic': the original rules (daily plan + 3-day volume lines; wider stops, book
                                  #       half, trailing, out by 3:15)
                                  # 'rr': 1:4 trades. Stop at most STOP_PCT % of price, target RR_TARGET x the stop,
                                  #       held until the target, the stop or 3:15. Pullback entry and CPR Magnet only
                                  # 'small': stops of at most STOP_CAP points, out within HOLD_MIN minutes, pullback entry
VOLCHECK = {'nifty': False, 'sensex': True}   # 'classic' rules: the volume check (Dr David Paul): a BUY only when,
                                  # over the last VOL_WINDOW 5-minute candles, the up candles carried more volume than
                                  # the down candles (price and volume moving together); a SELL only when the down
                                  # candles did. One setting for each index (or True / False for both)
VOL_WINDOW = 24                   # 24 five-minute candles = the last 2 hours (early in the day: yesterday's last ones)
STOP_MAX = {'nifty': 0, 'sensex': 0}   # 'classic' rules: the most a stop may be from entry, in index points
                                  # (0 = each setup's own stop: 0.3% Magnet, the 15-minute range, the previous line)
STOP_MODE = 'pull'                # a wider stop is: 'pull' moved in (book half / trail scaled to the new stop),
                                  # 'stop' moved in (book half / trail as before), 'skip' not traded
POC_DAYS = {'nifty': 1, 'sensex': 0}    # the volume POC filter (buys only above it, sells only below) from the
                                  # last N sessions' volume (1 = yesterday's); 0 = no POC filter. 2026 tests
                                  # (research/quant/y2026_pocdays.py): Nifty made the most with yesterday's POC and no
                                  # volume check, Sensex with the volume check and no POC filter
SWEEP = False                     # 'classic' rules: also trade liquidity sweeps of yesterday's high / low
SWEEP_MAX = 3                     # at most this many sweep trades a day
STOP_PCT = 0.21                   # 'rr' rules: the most a stop may be from entry, in % of price (Sensex ~150, Nifty ~47 points)
RR_TARGET = 4.0                   # 'rr' rules: target = this x the stop
STOP_CAP = {'nifty': 45, 'sensex': 150}   # 'small' rules: the most a stop may be from entry, in index points
HOLD_MIN = 60                     # 'small' rules: out after this many minutes at the latest
PULLBACK_R = 2.0                  # 'small' rules: the pullback trade's target = this x its stop
LADDER = False                    # 'classic' rules: volume-line ladder (book half at the next line, ride to the one after)
TELEGRAM_TOKEN = ''               # from @BotFather in Telegram (see the guide); leave empty for screen only
TELEGRAM_CHAT_ID = ''             # found by itself once you've messaged your bot; then put it here
REPLAY_DAY = ''                   # e.g. '2026-10-08' to replay a past day instead of running live
CHART = True                      # live chart in the phone's browser: http://127.0.0.1:8000
CHART_PORT = 8000
LIVE_PRICE = True                 # the chart's price every 2 seconds (Groww's public data), not just whole minutes;
                                  # for the chart and the app only: the calls use the 1-minute candles as always
LOG = True                        # also save everything it prints in cprb_log.txt next to this file, so you can see
                                  # afterwards why it stopped (an error is written there; if the log just ends, the
                                  # phone closed Pydroid 3)

# On a server (trading-system/deploy): the same settings from environment variables, which win over the lines above
TELEGRAM_TOKEN = os.environ.get('CPRB_TELEGRAM_TOKEN') or TELEGRAM_TOKEN
TELEGRAM_CHAT_ID = os.environ.get('CPRB_TELEGRAM_CHAT_ID') or TELEGRAM_CHAT_ID
LOTS = int(os.environ.get('CPRB_LOTS') or LOTS)
CHART_HOST = os.environ.get('CPRB_CHART_HOST') or '127.0.0.1'   # who may open the chart: this device only
CHART_PORT = int(os.environ.get('CPRB_CHART_PORT') or CHART_PORT)
CHART_KEY = os.environ.get('CPRB_CHART_KEY') or ''              # if set, the chart opens only at .../?key=CHART_KEY
CHART_KEY_SHA256 = os.environ.get('CPRB_CHART_KEY_SHA256') or ''  # or only the key's SHA-256 (the key itself stays private)
DATA_DIR = os.environ.get('CPRB_DATA_DIR') or os.path.dirname(os.path.abspath(__file__))   # cache, log, app data
APP_APK = os.environ.get('CPRB_APP_APK') or ''   # the Eden Trader app, offered at /app.apk (no key needed)
APP_WWW = os.environ.get('CPRB_APP_WWW') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..',
                                                        'eden-trader', 'app', 'www')   # the app's screens, sent over the air
SUCCESS_PTS = {'NIFTY': 50, 'SENSEX': 150}  # the app's history: a call succeeded if the index went this far its way
                                  # before the stop loss

# ---------------- fixed rules (as tested on 2026) ----------------
SPEC = {
    'nifty':  dict(name='NIFTY',  key='NSE_INDEX|Nifty 50', bin=5.0,  cost=4.0,  lot=65, step=50,  cap=STOP_CAP['nifty'],
                   live=('NSE', 'NIFTY')),
    'sensex': dict(name='SENSEX', key='BSE_INDEX|SENSEX',   bin=16.0, cost=12.0, lot=20, step=100, cap=STOP_CAP['sensex'],
                   live=('BSE', 'SENSEX')),
}
BEES = 'NSE_EQ|INF204KB14I2'      # NIFTYBEES: its volume stands in for the index's (an index has no volume)
OPEN, RANGE_END, CUTOFF, VOL_END, OUT, CLOSE = 555, 570, 600, 870, 915, 930   # minutes from midnight
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
CACHE = os.path.join(DATA_DIR, 'cprb_cache.json')


# ---------------- data: Upstox public candles ----------------
def http_json(url, tries=4):
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'curl/8.5.0'})
    err = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:          # network hiccup: wait and try again
            err = e
            time.sleep(2 * (k + 1))
    raise err

def parse(rows):
    """Upstox candles -> {date: {minute: (open, high, low, close, volume)}}, 9:15 to 15:29 only."""
    out = {}
    for r in rows:
        m = int(r[0][11:13]) * 60 + int(r[0][14:16])
        if OPEN <= m < CLOSE:
            out.setdefault(r[0][:10], {})[m] = (r[1], r[2], r[3], r[4], r[5])
    return out

def fetch_range(key, a, b):
    """1-minute candles for the dates a to b (both included)."""
    out = {}
    while a <= b:
        e = min(b, a + dt.timedelta(days=24))
        url = f"https://api.upstox.com/v3/historical-candle/{urllib.parse.quote(key, safe='')}/minutes/1/{e}/{a}"
        for d, mm in parse(http_json(url)['data']['candles']).items():
            out.setdefault(d, {}).update(mm)
        a = e + dt.timedelta(days=1)
        time.sleep(0.3)
    return out

def fetch_daily(key, a, b):
    """The exchange's official daily candles (dates a to b): {date: (open, high, low, close)}. The official close
    often differs from the last 1-minute candle; the CPR uses the official one, as TradingView does."""
    url = f"https://api.upstox.com/v3/historical-candle/{urllib.parse.quote(key, safe='')}/days/1/{b}/{a}"
    return {r[0][:10]: (r[1], r[2], r[3], r[4]) for r in http_json(url)['data']['candles']}

def fetch_today(key):
    q = urllib.parse.quote(key, safe='')
    try:
        rows = http_json(f"https://api.upstox.com/v3/historical-candle/intraday/{q}/minutes/1", tries=2)['data']['candles']
    except Exception:
        rows = http_json(f"https://api.upstox.com/v2/historical-candle/intraday/{q}/1minute", tries=2)['data']['candles']
    return parse(rows)

# ---------------- the live price (for the chart and the app only) ----------------
LIVE = {}                         # index -> {'day', 'px', 'at' (time.time()), 'bars': {minute: [open, high, low, close]}}
LIVE_LOCK = threading.Lock()
LIVE_URL = 'https://groww.in/v1/api/stocks_data/v1/accord_points/exchange/{}/segment/CASH/latest_indices_ohlc/{}'
LIVE_THREAD = []

def live_prices(names):
    """Every 2 seconds in market hours: each index's last price, from Groww's public data. It draws the minute still
    forming on the chart (and the price in the app) until the 1-minute candle arrives; the calls don't use it."""
    if LIVE_THREAD or not LIVE_PRICE:
        return
    def tick(n):
        ex, sym = SPEC[n]['live']
        req = urllib.request.Request(LIVE_URL.format(ex, sym), headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.load(r)
        px, at = float(d['value']), float(d.get('tsInMillis') or 0)
        at = at / 1000 if at > 1e11 else at
        if at and abs(time.time() - at) > 120:
            return False                              # an old price (before the open, a holiday): not live
        now = now_ist()
        day, m = str(now.date()), now.hour * 60 + now.minute
        with LIVE_LOCK:
            L = LIVE.get(n)
            if not L or L['day'] != day:
                L = LIVE[n] = dict(day=day, bars={})
            b = L['bars'].get(m)
            if b:
                b[1], b[2], b[3] = max(b[1], px), min(b[2], px), px
            else:
                L['bars'][m] = [px, px, px, px]
            for k in [k for k in L['bars'] if k < m - 10]:
                del L['bars'][k]
            L['px'], L['at'] = px, time.time()
        return True
    def run():
        fails = 0
        while True:
            now = now_ist()
            m = now.hour * 60 + now.minute
            if now.weekday() >= 5 or not OPEN <= m < CLOSE:
                time.sleep(15)
                continue
            ok = False
            for n in names:
                try:
                    ok = tick(n) or ok
                except Exception:
                    pass
            fails = 0 if ok else fails + 1
            time.sleep(2 if fails < 10 else 30)       # the source is down: look again less often
    LIVE_THREAD.append(threading.Thread(target=run, daemon=True))
    LIVE_THREAD[0].start()

def live_now(n, fresh=20):
    """(price, 'hh:mm:ss') if the live price is recent, else None."""
    with LIVE_LOCK:
        L = LIVE.get(n)
        if not L or 'px' not in L or time.time() - L['at'] > fresh or L['day'] != str(now_ist().date()):
            return None
        return L['px'], dt.datetime.fromtimestamp(L['at'], IST).strftime('%H:%M:%S')

def with_live(n, d):
    """The chart data plus the live minutes after the last 1-minute candle."""
    lv = live_now(n)
    if not lv or d.get('day') != str(now_ist().date()):
        return d
    with LIVE_LOCK:
        bars = sorted(LIVE[n]['bars'].items())
    last = d['candles'][-1][0] if d.get('candles') else OPEN - 1
    extra = [[m] + list(b) for m, b in bars if m > last and m < CLOSE]
    return dict(d, candles=d.get('candles', []) + extra, live=dict(px=lv[0], at=lv[1]))

def history(keys, first, last):
    """Earlier sessions' candles for each key (dates first to last), kept in cprb_cache.json between runs."""
    try:
        with open(CACHE) as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    out = {}
    for key in keys:
        c = cache.get(key)
        if not c or c['from'] > str(first):
            c = {'from': str(first), 'upto': str(first - dt.timedelta(days=1)), 'days': {}}
        if c['upto'] < str(last):
            print(f"  downloading {key} candles {max(first, dt.date.fromisoformat(c['upto']) + dt.timedelta(days=1))} to {last} ...")
            new = fetch_range(key, dt.date.fromisoformat(c['upto']) + dt.timedelta(days=1), last)
            for d, mm in new.items():
                c['days'][d] = {str(m): v for m, v in mm.items()}
            c['upto'] = str(last)
        c['days'] = {d: v for d, v in c['days'].items() if d >= str(first)}
        c['from'] = str(first)
        cache[key] = c
        out[key] = {d: {int(m): v for m, v in mm.items()} for d, mm in c['days'].items() if d <= str(last)}
    try:
        with open(CACHE, 'w') as f:
            json.dump(cache, f)
    except Exception:
        pass
    return out


# ---------------- levels: CPR, volume POC, 3-day volume lines ----------------
def levels(h, l, c):
    p = (h + l + c) / 3
    bc = (h + l) / 2
    tc = 2 * p - bc
    return dict(p=p, top=max(tc, bc), bot=min(tc, bc), w=abs(tc - bc) / p * 100)

def day_hist(rows, vol, bin_):
    """NIFTYBEES volume of each minute spread evenly over the index's high-low range of that minute."""
    lo = min(x[3] for x in rows)
    hi = max(x[2] for x in rows)
    base = int(lo // bin_)
    h = [0.0] * (int(hi // bin_) - base + 1)
    for m, o, hh, l, c in rows:
        v = vol.get(m, 0)
        a, b = int(l // bin_) - base, int(hh // bin_) - base
        s = v / (b - a + 1)
        for k in range(a, b + 1):
            h[k] += s
    return base, h

def combine(hists):
    base = min(b for b, h in hists)
    p = [0.0] * (max(b + len(h) for b, h in hists) - base)
    for b0, h in hists:
        for k, v in enumerate(h):
            p[b0 - base + k] += v
    return base, p

def argmax(p):
    return max(range(len(p)), key=p.__getitem__)

def poc_va(base, p, bin_):
    """Point of control and the 70% value area around it."""
    k = argmax(p)
    tot = sum(p)
    a = b = k
    s = p[k]
    while s < 0.7 * tot:
        up = p[b + 1] if b + 1 < len(p) else -1
        dn = p[a - 1] if a > 0 else -1
        if up >= dn:
            b += 1
            s += up
        else:
            a -= 1
            s += dn
    return (base + k + 0.5) * bin_, (base + b + 1) * bin_, (base + a) * bin_

def percentile(vals, q):
    v = sorted(vals)
    pos = q / 100 * (len(v) - 1)
    lo = int(math.floor(pos))
    if lo + 1 >= len(v):
        return v[-1]
    t = pos - lo
    d = v[lo + 1] - v[lo]
    return v[lo + 1] - d * (1 - t) if t >= 0.5 else v[lo] + d * t

def vol_lines(base, p, bin_):
    """The point of control plus every high-volume peak (top 30% of the smoothed profile); lines within 0.15% merged."""
    n = len(p)
    t = 1 / 3
    sm = [(p[i - 1] * t if i > 0 else 0.0) + p[i] * t + (p[i + 1] * t if i + 1 < n else 0.0) for i in range(n)]
    thr = percentile([x for x in sm if x > 0], 70)
    pk = {i for i in range(1, n - 1) if sm[i] >= thr and sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1]}
    pk.add(argmax(p))
    out = []
    for x in sorted((base + i + 0.5) * bin_ for i in pk):
        if out and x - out[-1] <= 0.0015 * x:
            out[-1] = (out[-1] + x) / 2
        else:
            out.append(x)
    return out

def context(spec, sess, vol, today, daily=None):
    """Everything known before the open. sess: {date: [(minute, o, h, l, c)]}, vol: {date: {minute: NIFTYBEES volume}},
    daily: {date: official (o, h, l, c)} for the CPR."""
    days = sorted(d for d in sess if d < today and len(sess[d]) >= 300)[-60:]
    if len(days) < 31:
        raise SystemExit(f"Not enough earlier sessions ({len(days)}); need 31.")
    D = {d: (sess[d][0][1], max(x[2] for x in sess[d]), min(x[3] for x in sess[d]), sess[d][-1][4]) for d in days}
    for d in days:
        if daily and d in daily:
            D[d] = (D[d][0],) + tuple(daily[d][1:])
    lv = levels(*D[days[-1]][1:])
    past = [levels(*D[d][1:])['w'] for d in days[-21:-1]]
    rank = sum(x < lv['w'] for x in past) / 20
    ylv = levels(*D[days[-2]][1:])
    pn = POC_DAYS.get(spec['name'].lower(), 30)
    H = {d: day_hist(sess[d], vol.get(d, {}), spec['bin']) for d in days[-max(pn, 3):]}
    poc, vah, val = poc_va(*combine([H[d] for d in days[-pn:]]), spec['bin']) if pn else (None, None, None)
    return dict(spec, today=today, prev=days[-1], lv=lv, rank=rank, narrow=rank < 1 / 3,
                rel=1 if lv['bot'] > ylv['top'] else -1 if lv['top'] < ylv['bot'] else 0,
                yc=D[days[-1]][3], yh=D[days[-1]][1], yl=D[days[-1]][2], poc=poc, vah=vah, val=val, pocn=pn, yday=sess[days[-1]],
                yvol=vol.get(days[-1], {}),
                lines=vol_lines(*combine([H[d] for d in days[-3:]]), spec['bin']))

def vcheck(nm):
    """Is the volume check on for this index ('nifty' / 'NIFTY' / ...)?"""
    return VOLCHECK.get(nm.lower(), True) if isinstance(VOLCHECK, dict) else bool(VOLCHECK)

def poc_ok(cx, side, px):
    """On the trade's side of the volume POC (buys above, sells below); always, when the index has no POC filter."""
    return cx['poc'] is None or side * (px - cx['poc']) > 0


# ---------------- the trades, on 1-minute candles ----------------
def path(o, h, l, c):
    """Order of prices inside a 1-minute candle: green open-low-high-close, red open-high-low-close."""
    return (o, l, h, c) if c >= o else (o, h, l, c)

def done(m, px, why, pnl):
    return dict(m=m, px=px, why=why, pnl=pnl)

def run_magnet(c1, side, e, edge, over, cost, risk=None, R=None, start=556):
    """Stop 0.3% (or `risk` points); book half at 0.25 x the risk (or R) and move the stop to entry; the rest to the
    CPR edge; out by 3:15."""
    R0 = 0.3 / 100 * e
    stp = e - side * (R0 if risk is None else risk)
    t1 = e + side * 0.25 * (R0 if R is None else R)
    half, ev = None, []
    for m, o, h, l, c in c1:
        if m < start:
            continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e)
                return dict(ev=ev, stp=stp, exit=done(m, stp, 'stop' if half is None else 'stop at entry',
                                                      (rest if half is None else (half + rest) / 2) - cost))
            if half is None and side * (px - t1) >= 0:
                half = side * (t1 - e)
                stp = e
                ev.append(dict(m=m, kind='half', px=t1, pts=half, stp=stp))
            if half is not None and side * (px - edge) >= 0:
                return dict(ev=ev, stp=stp, exit=done(m, edge, 'target: CPR edge', (half + side * (edge - e)) / 2 - cost))
        if m >= OUT:
            rest = side * (c - e)
            return dict(ev=ev, stp=stp, exit=done(m, c, '3:15 time exit', (rest if half is None else (half + rest) / 2) - cost))
    if over and c1:
        rest = side * (c1[-1][4] - e)
        return dict(ev=ev, stp=stp, exit=done(c1[-1][0], c1[-1][4], 'close', (rest if half is None else (half + rest) / 2) - cost))
    return dict(ev=ev, stp=stp, exit=None)

def run_breakout(c1, side, e, start, stp, over, cost, R=None):
    """Book half at 0.25 x the risk (R: the stop distance unless given) and move the stop to entry; after +1R trail
    the stop 1R behind the best price."""
    R = side * (e - stp) if R is None else R
    tgt = e + side * 0.25 * R
    half, best, ev, trailing = None, e, [], False
    for m, o, h, l, c in c1:
        if m < start:
            continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e)
                why = 'stop' if half is None else 'trailing stop' if side * (stp - e) > 0 else 'stop at entry'
                return dict(ev=ev, stp=stp, exit=done(m, stp, why, (rest if half is None else (half + rest) / 2) - cost))
            if half is None and side * (px - tgt) >= 0:
                half = side * (tgt - e)
                if side * (e - stp) > 0:
                    stp = e
                ev.append(dict(m=m, kind='half', px=tgt, pts=half, stp=stp))
        best = max(best, h) if side > 0 else min(best, l)
        if side * (best - e) >= R:
            ns = best - side * R
            if side * (ns - stp) > 0:
                stp = ns
                if not trailing:
                    trailing = True
                    ev.append(dict(m=m, kind='trail', px=best, pts=None, stp=stp))
        if m >= OUT:
            rest = side * (c - e)
            return dict(ev=ev, stp=stp, exit=done(m, c, '3:15 time exit', (rest if half is None else (half + rest) / 2) - cost))
    if over and c1:
        rest = side * (c1[-1][4] - e)
        return dict(ev=ev, stp=stp, exit=done(c1[-1][0], c1[-1][4], 'close', (rest if half is None else (half + rest) / 2) - cost))
    return dict(ev=ev, stp=stp, exit=None)

def run_vol(c1, side, e, start, stp, tgt, x, tgt2, over, cost):
    """Target the next line, stop at the previous line. Ladder (tgt2 set): at the next line book half, move the
    stop to the broken line x and ride the rest to the line after."""
    half, ev = None, []
    for m, o, h, l, c in c1:
        if m < start:
            continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0:
                rest = side * (stp - e)
                return dict(ev=ev, stp=stp, exit=done(m, stp, 'stop' if half is None else 'stop at the broken line',
                                                      (rest if half is None else (half + rest) / 2) - cost))
            if half is None and side * (px - tgt) >= 0:
                if tgt2 is None:
                    return dict(ev=ev, stp=stp, exit=done(m, tgt, 'target: next line', side * (tgt - e) - cost))
                half = side * (tgt - e)
                stp = x
                ev.append(dict(m=m, kind='half', px=tgt, pts=half, stp=stp))
            if half is not None and side * (px - tgt2) >= 0:
                return dict(ev=ev, stp=stp, exit=done(m, tgt2, 'target: the line after', (half + side * (tgt2 - e)) / 2 - cost))
        if m >= OUT:
            rest = side * (c - e)
            return dict(ev=ev, stp=stp, exit=done(m, c, '3:15 time exit', (rest if half is None else (half + rest) / 2) - cost))
    if over and c1:
        return dict(ev=ev, stp=stp, exit=done(c1[-1][0], c1[-1][4], 'close', side * (c1[-1][4] - e) - cost))
    return dict(ev=ev, stp=stp, exit=None)

def touches(c1, orh, orl, after):
    """Touches of the 9:15-9:30 range in time order: (side, entry price, first exit-check minute, minute)."""
    for m, o, h, l, c in c1:
        if m < max(RANGE_END, after) or m >= 780:
            continue
        if h >= orh:
            yield 1, max(o, orh), m + 1, m
        elif l <= orl:
            yield -1, min(o, orl), m + 1, m

def vok(cx, side, m, src):
    """The volume check on a signal (cx['vf'](side, minute, setup) -> True / False); none = every signal. The first
    signal it stops of each kind is kept for the messages."""
    f = cx.get('vf')
    if f is None or f(side, m, src):
        return True
    if cx.get('vlog') is not None:
        cx['vlog'].setdefault((src, side), m)
    return False

def volume_fn(cx, c1, upto):
    """The volume check (Dr David Paul): over the last VOL_WINDOW 5-minute candles closed by the signal's minute
    (yesterday's included), the total NIFTYBEES volume of the up candles (close above open) must beat the down
    candles' for a BUY, and the other way for a SELL. cx['tvol'] = today's NIFTYBEES volume by minute."""
    yv, tv = cx.get('yvol', {}), cx.get('tvol', {})
    seq = [(m0 - 1440, c - o, sum(yv.get(m0 + k, 0) for k in range(5))) for m0, o, h, l, c in candles5(cx['yday'], CLOSE)]
    seq += [(m0, c - o, sum(tv.get(m0 + k, 0) for k in range(5))) for m0, o, h, l, c in candles5(c1, upto)]
    ends = [x[0] + 5 for x in seq]
    def f(side, m, src):
        k = bisect.bisect_right(ends, m)
        win = seq[max(0, k - VOL_WINDOW):k]
        up = sum(v for _, d, v in win if d > 0)
        dn = sum(v for _, d, v in win if d < 0)
        return up > dn if side > 0 else dn > up
    return f

def stop_max(cx):
    """STOP_MAX for this index (0 = none)."""
    return STOP_MAX.get(cx['name'].lower(), 0) if RULES == 'classic' or cx.get('rules_used') == 'classic' else 0

def capped_stop(cx, side, e, stp):
    """(stop, R for book half / trail) under STOP_MAX / STOP_MODE, or None when the trade is skipped."""
    cap, R0 = stop_max(cx), side * (e - stp)
    if not cap or R0 <= cap:
        return stp, R0
    if STOP_MODE == 'skip':
        return None
    return e - side * cap, (cap if STOP_MODE == 'pull' else R0)

def plan_trades(cx, c1, upto, over):
    """Daily plan: narrow-CPR day -> breakout; other day -> CPR Magnet at 9:16 if the open qualifies, else breakout."""
    if not c1:
        return []
    lv, cost = cx['lv'], cx['cost']
    if not cx['narrow']:
        o, e = c1[0][1], c1[0][4]
        side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
        if side:
            edge = lv['top'] if side < 0 else lv['bot']
            cs = capped_stop(cx, side, e, e - side * 0.3 / 100 * e)
            if side * (edge - e) >= 0.002 * e and poc_ok(cx, side, e) and vok(cx, side, 556, 'MAGNET') and cs:
                stp, R = cs
                if stop_max(cx):
                    r = run_magnet(c1, side, e, edge, over, cost, side * (e - stp), R)
                else:                                   # no stop limit: the exact 0.3% arithmetic
                    r = run_magnet(c1, side, e, edge, over, cost)
                    stp, R = e - side * 0.3 / 100 * e, 0.3 / 100 * e
                return [dict(src='MAGNET', side=side, m=556, known=556, e=e, stp0=stp, t1=e + side * 0.25 * R, edge=edge, **r)]
    if upto < RANGE_END - 1:
        return []
    first = [x for x in c1 if x[0] < RANGE_END]
    if not first:
        return []
    orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    gap = c1[0][1] - cx['yc']
    gap = 1 if gap > 0 else -1 if gap < 0 else 0
    for side, e, start, m in touches(c1, orh, orl, RANGE_END):
        if m >= CUTOFF:
            break
        if side == -cx['rel'] or gap != side or not poc_ok(cx, side, e) or not vok(cx, side, m, 'BREAKOUT'):
            continue
        stp = orl if side > 0 else orh
        if side * (e - stp) <= 0:
            continue
        cs = capped_stop(cx, side, e, stp)
        if not cs:
            continue
        stp, R = cs
        r = run_breakout(c1, side, e, start, stp, over, cost, R)
        out = [dict(src='BREAKOUT', side=side, m=m, known=m + 1, e=e, stp0=stp, R=R, **r)]
        if r['exit'] and r['exit']['pnl'] <= 0:          # the break failed: one trade the other way
            for s2, e2, st2, m2 in touches(c1, orh, orl, r['exit']['m'] + 1):
                if m2 >= CUTOFF:
                    break
                if s2 != -side or not poc_ok(cx, s2, e2) or not vok(cx, s2, m2, 'REVERSAL'):
                    continue
                stp2 = orl if s2 > 0 else orh
                if s2 * (e2 - stp2) <= 0:
                    break
                cs = capped_stop(cx, s2, e2, stp2)
                if not cs:
                    continue
                stp2, R2 = cs
                r2 = run_breakout(c1, s2, e2, st2, stp2, over, cost, R2)
                out.append(dict(src='REVERSAL', side=s2, m=m2, known=m2 + 1, e=e2, stp0=stp2, R=R2, **r2))
                break
        return out
    return []

def candles5(c1, upto):
    g = {}
    for x in c1:
        g.setdefault((x[0] - OPEN) // 5, []).append(x)
    return [(OPEN + 5 * k, ch[0][1], max(y[2] for y in ch), min(y[3] for y in ch), ch[-1][4])
            for k, ch in sorted(g.items()) if OPEN + 5 * k + 4 <= upto]

def vol_trades(cx, c1, upto, over, ladder):
    """3-day volume lines: a 5-minute close through a line (9:30-2:30) -> toward the next line, stop at the previous
    line, only when the next line is at least 1.5x the stop away. One at a time."""
    lv, cost = cx['lines'], cx['cost']
    b5 = candles5(c1, upto)
    out, free = [], 0
    for j in range(1, len(b5)):
        m0, o, h, l, c = b5[j]
        pc = b5[j - 1][4]
        if m0 < RANGE_END or m0 + 5 > VOL_END or m0 < free:
            continue
        for x in lv:
            side = 1 if pc < x <= c else -1 if pc > x >= c else 0
            if not side:
                continue
            nxt = sorted((y for y in lv if side * (y - x) > 0), key=lambda y: abs(y - x))
            prv = [y for y in lv if side * (x - y) > 0]
            if not nxt or not prv:
                break
            tgt = nxt[0]
            stp = max(prv) if side > 0 else min(prv)
            e = c
            if side * (e - stp) <= 0 or side * (tgt - e) < 1.5 * side * (e - stp) or not vok(cx, side, m0 + 5, 'VOLUME LINE'):
                break
            cs = capped_stop(cx, side, e, stp)
            if not cs:
                break
            stp = cs[0]
            tgt2 = nxt[1] if ladder and len(nxt) > 1 else None
            r = run_vol(c1, side, e, m0 + 5, stp, tgt, x, tgt2, over, cost)
            out.append(dict(src='VOLUME LINE', side=side, m=m0 + 5, known=m0 + 5, e=e, stp0=stp, tgt=tgt, tgt2=tgt2, x=x, **r))
            if r['exit'] is None:
                return out
            free = r['exit']['m'] + 1
            break
    return out


def sweep_trades(cx, c1, upto, over):
    """Liquidity sweeps of yesterday's high / low: a 5-minute candle (9:30-2:30) trades above yesterday's high and
    closes back below it (the candle before closed below it) -> SELL at the close; the mirror image at yesterday's
    low -> BUY. Stop 0.02% beyond the candle's high / low (skipped if wider than 0.5% of price), target 3x the stop,
    out by 3:15. Every signal; the book takes one trade at a time and at most SWEEP_MAX a day."""
    yh, yl, cost = cx['yh'], cx['yl'], cx['cost']
    b5 = candles5(c1, upto)
    out = []
    for j in range(1, len(b5)):
        m0, o, h, l, c = b5[j]
        pc = b5[j - 1][4]
        if m0 < RANGE_END:
            continue
        if m0 + 5 > VOL_END:
            break
        if pc < yh < h and c < yh:
            side, ext, lvl = -1, h, yh
        elif pc > yl > l and c > yl:
            side, ext, lvl = 1, l, yl
        else:
            continue
        if not vok(cx, side, m0 + 5, 'SWEEP'):
            continue
        stp = ext - side * 0.0002 * c
        risk = side * (c - stp)
        if risk > 0.005 * c:
            continue
        cs = capped_stop(cx, side, c, stp)
        if not cs:
            continue
        stp = cs[0]
        risk = side * (c - stp)
        tgt = c + side * 3 * risk
        r = run_fixed(c1, side, c, m0 + 5, stp, tgt, OUT, over, cost)
        out.append(dict(src='SWEEP', small=True, side=side, m=m0 + 5, known=m0 + 5, e=c, stp0=stp, tgt=tgt, lvl=lvl,
                        last=OUT, **r))
    return out


# ---------------- the 'rr' and 'small' rules: capped stops, fixed targets, pullback entry ----------------
def run_fixed(c1, side, e, start, stp, tgt, last_m, over, cost):
    """Stop, target, time limit (close of minute last_m), 3:15. No booking half, no trailing."""
    for m, o, h, l, c in c1:
        if m < start:
            continue
        for px in path(o, h, l, c):
            if side * (px - stp) <= 0:
                return dict(ev=[], stp=stp, exit=done(m, stp, 'stop', side * (stp - e) - cost))
            if side * (px - tgt) >= 0:
                return dict(ev=[], stp=stp, exit=done(m, tgt, 'target', side * (tgt - e) - cost))
        if m >= min(last_m, OUT):
            return dict(ev=[], stp=stp, exit=done(m, c, 'time limit' if m < OUT else '3:15 time exit', side * (c - e) - cost))
    if over and c1:
        return dict(ev=[], stp=stp, exit=done(c1[-1][0], c1[-1][4], 'close', side * (c1[-1][4] - e) - cost))
    return dict(ev=[], stp=stp, exit=None)

def capped(side, e, stp0, cap):
    """The stop moved in to at most `cap` points from entry."""
    return stp0 if side * (e - stp0) <= cap else e - side * cap

def risk_rules(cx, rules):
    """The stop limit (points, for an entry price), the targets and the time limit under the 'small' / 'rr' rules."""
    if rules == 'rr':
        return dict(cap=lambda e: STOP_PCT / 100 * e, mag=RR_TARGET, pb=RR_TARGET, hold=None)
    return dict(cap=lambda e: cx['cap'], mag=None, pb=PULLBACK_R, hold=HOLD_MIN)

def pullback_plan(cx, c1, upto, over, rules):
    """CPR Magnet at 9:16 (stop capped; target the CPR edge, or RR_TARGET x the stop) and the pullback after the 9:30
    breakout (a limit order back at the broken 15-minute high / low once price has gone 0.1% beyond it, until 12:00;
    target PULLBACK_R or RR_TARGET x the stop). Returns (trades, pending pullback or None)."""
    out, pend = [], None
    if not c1:
        return out, pend
    R = risk_rules(cx, rules)
    lv, cost = cx['lv'], cx['cost']
    if not cx['narrow']:
        o, e = c1[0][1], c1[0][4]
        side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
        if side:
            edge = lv['top'] if side < 0 else lv['bot']
            if side * (edge - e) >= 0.002 * e and poc_ok(cx, side, e):
                stp = capped(side, e, e - side * 0.003 * e, R['cap'](e))
                if R['mag']:
                    tgt, tdesc = e + R['mag'] * (e - stp), f"{R['mag']:g}x the stop"
                else:
                    tgt, tdesc = edge, 'the CPR edge'
                last = 556 - 1 + R['hold'] if R['hold'] else OUT
                r = run_fixed(c1, side, e, 556, stp, tgt, last, over, cost)
                out.append(dict(src='MAGNET', small=True, side=side, m=556, known=556, e=e, stp0=stp, tgt=tgt, tdesc=tdesc,
                                last=last, **r))
    if upto < RANGE_END - 1:
        return out, pend
    first = [x for x in c1 if x[0] < RANGE_END]
    if not first:
        return out, pend
    orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    gap = c1[0][1] - cx['yc']
    gap = 1 if gap > 0 else -1 if gap < 0 else 0
    sig = None
    for side, e, start, m in touches(c1, orh, orl, RANGE_END):
        if m >= CUTOFF:
            break
        if side != -cx['rel'] and gap == side and poc_ok(cx, side, e):
            sig = (side, m)
            break
    if not sig:
        return out, pend
    side, m = sig
    lvl = orh if side > 0 else orl
    tol = 0.0005 * lvl
    cx['breakout'] = dict(side=side, m=m, lvl=lvl, arm=lvl + side * 0.001 * lvl, px=lvl + side * tol)
    far = lvl
    mult = R['pb']
    for mm, o, h, l, c in c1:
        if mm <= m:
            continue
        if mm >= 720:
            break
        far = max(far, h) if side > 0 else min(far, l)
        if side * (far - lvl) < 0.001 * lvl:
            continue
        px = lvl + side * tol
        s0 = orl if side > 0 else orh
        if pend is None:
            risk = min(side * (px - s0), R['cap'](px))
            pend = dict(side=side, m=mm, px=px, lvl=lvl, stp=px - side * risk, tgt=px + side * mult * risk, hold=R['hold'],
                        tdesc=f"{mult:g}x the stop")
        if not ((l <= lvl + tol) if side > 0 else (h >= lvl - tol)):
            continue
        e = min(o, px) if side > 0 else max(o, px)
        risk = side * (e - s0)
        if risk <= 0:
            break
        stp = s0
        cap = R['cap'](e)
        if risk > cap:
            stp, risk = e - side * cap, cap
        tgt = e + side * mult * risk
        last = mm + R['hold'] if R['hold'] else OUT
        r = run_fixed(c1, side, e, mm + 1, stp, tgt, last, over, cost)
        out.append(dict(src='PULLBACK', small=True, side=side, m=mm, known=mm + 1, e=e, stp0=stp, tgt=tgt,
                        tdesc=f"{mult:g}x the stop", last=last, lvl=lvl, **r))
        break
    return out, pend

def small_vol_trades(cx, c1, upto, over):
    """3-day volume lines with the stop capped, target the next line, out within HOLD_MIN minutes."""
    lv, cost, cap = cx['lines'], cx['cost'], cx['cap']
    b5 = candles5(c1, upto)
    out, free = [], 0
    for j in range(1, len(b5)):
        m0, o, h, l, c = b5[j]
        pc = b5[j - 1][4]
        if m0 < RANGE_END or m0 + 5 > VOL_END or m0 < free:
            continue
        for x in lv:
            side = 1 if pc < x <= c else -1 if pc > x >= c else 0
            if not side:
                continue
            nxt = sorted((y for y in lv if side * (y - x) > 0), key=lambda y: abs(y - x))
            prv = [y for y in lv if side * (x - y) > 0]
            if not nxt or not prv:
                break
            stp0 = max(prv) if side > 0 else min(prv)
            e = c
            risk = side * (e - stp0)
            if risk > cap:
                risk = cap
            if risk <= 0 or side * (nxt[0] - e) < 1.5 * risk:
                break
            stp = capped(side, e, stp0, cap)
            last = m0 + 5 - 1 + HOLD_MIN
            r = run_fixed(c1, side, e, m0 + 5, stp, nxt[0], last, over, cost)
            out.append(dict(src='VOLUME LINE', small=True, side=side, m=m0 + 5, known=m0 + 5, e=e, stp0=stp, tgt=nxt[0], x=x,
                            tgt2=None, last=last, **r))
            if r['exit'] is None:
                return out
            free = r['exit']['m'] + 1
            break
    return out

def day_trades(cx, c1, upto, over=False, ladder=False, rules=None):
    """Every signal of the day so far, and which were taken: one trade at a time, whichever came first."""
    rules = rules or RULES
    if rules in ('small', 'rr'):
        cx['breakout'] = None
        plan, pend = pullback_plan(cx, c1, upto, over, rules)
        ts = plan + (small_vol_trades(cx, c1, upto, over) if rules == 'small' else [])
        cx['pending'] = pend
        cx['rules_used'] = rules
    else:
        cx['rules_used'] = 'classic'
        own = cx.get('vf') is not None                   # a check set from outside (tests)
        if vcheck(cx['name']) and not own:
            cx['vf'] = volume_fn(cx, c1, upto)
        cx['vlog'] = {}
        ts = plan_trades(cx, c1, upto, over) + vol_trades(cx, c1, upto, over, ladder) + \
            (sweep_trades(cx, c1, upto, over) if SWEEP else [])
        if vcheck(cx['name']) and not own:
            cx['vf'] = None
    ts.sort(key=lambda t: (t['m'], {'VOLUME LINE': 1, 'SWEEP': 2}.get(t['src'], 0)))
    free = nsw = 0
    for t in ts:
        t['full'] = t['src'] == 'SWEEP' and nsw >= SWEEP_MAX
        t['taken'] = t['m'] >= free and not t['full']
        if t['taken']:
            free = t['exit']['m'] + 1 if t['exit'] else 10 ** 9
            nsw += t['src'] == 'SWEEP'
    return ts


# ---------------- messages ----------------
def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"

def f2(x):
    return f"{x:,.2f}"

def rupees(cx, pts, lots):
    return pts * 0.5 * cx['lot'] * lots

def option(cx, side, px):
    k = round(px / cx['step']) * cx['step']
    return f"buy the {k:.0f} {'CE (call)' if side > 0 else 'PE (put)'}"

def poc_text(cx, extra):
    if cx['poc'] is None:
        return f"No volume POC filter on {cx['name']}: BUYs and SELLs on either side of it."
    span = "Yesterday's" if cx['pocn'] == 1 else f"{cx['pocn']}-day"
    return f"{span} volume POC {f2(cx['poc'])}{extra}: buys only above it, sells only below."

def plan_text(cx):
    if RULES in ('small', 'rr'):
        return plan_text_small(cx)
    lv, poc, nm = cx['lv'], cx['poc'], cx['name']
    out = [f"{nm} plan for the session after {cx['prev']}",
           f"CPR {f2(lv['bot'])} - {f2(lv['top'])}, pivot {f2(lv['p'])}: " +
           ("NARROW (breakout day)" if cx['narrow'] else "not narrow"),
           poc_text(cx, f" (value area {f2(cx['val'])} - {f2(cx['vah'])})" if poc is not None else ""),
           "Today's CPR vs yesterday's: " + ("higher -> no breakout SELLs" if cx['rel'] > 0 else
                                             "lower -> no breakout BUYs" if cx['rel'] < 0 else "overlapping -> both ways"),
           f"Yesterday's close {f2(cx['yc'])}: open above it -> breakout BUYs only; below -> SELLs only."]
    if cx['narrow']:
        out.append("9:30-10:00 BREAKOUT: BUY on a touch of the 9:15-9:30 high / SELL on a touch of its low (filters "
                   "above). Stop at the other side of the range; book half at 0.25x the risk, stop to entry, trail the rest.")
    else:
        sell, buy = lv['top'] / 0.998, lv['bot'] / 1.002
        out.append(f"9:16 CPR MAGNET: SELL if the 9:15 candle opens above {f2(lv['top'])} and closes at or above {f2(sell)}"
                   + ("" if poc is None else f" and below the POC {f2(poc)}" if sell < poc else " (not possible today: the POC is below that)") +
                   f"; BUY if it opens below {f2(lv['bot'])} and closes at or below {f2(buy)}"
                   + ("" if poc is None else f" and above the POC {f2(poc)}" if buy > poc else " (not possible today: the POC is above that)") +
                   ". Stop 0.3%, book half at 0.25x the risk, rest to the CPR edge. Otherwise the breakout plan (9:30-10:00).")
    out.append(f"3-day volume lines: {', '.join(f2(x) for x in cx['lines'])}. 9:30-2:30: a 5-minute close through a line "
               "-> trade toward the next line, stop at the previous line, only if the next line is at least 1.5x the stop "
               "away. One trade at a time." + (" Ladder on." if LADDER else ""))
    if stop_max(cx):
        out.append(f"Every stop at most {stop_max(cx):g} points from entry" +
                   (" (wider ones: trade skipped)." if STOP_MODE == 'skip' else " (wider ones moved in)."))
    if vcheck(cx['name']):
        out.append("Volume check on every signal: a BUY only if, over the last 2 hours, the up candles carried more volume "
                   "(NIFTYBEES) than the down candles; a SELL only if the down candles did. Otherwise the signal is skipped.")
    if SWEEP:
        out.append(f"Liquidity sweeps, 9:30-2:30: a 5-minute candle goes above yesterday's high {f2(cx['yh'])} and closes back "
                   f"below it -> SELL; goes below yesterday's low {f2(cx['yl'])} and closes back above it -> BUY. Stop just "
                   f"beyond the candle, target 3x the stop, at most {SWEEP_MAX} a day, only when no other trade is open.")
    return '\n'.join(out)

def plan_text_small(cx):
    lv, poc, nm, cap = cx['lv'], cx['poc'], cx['name'], cx['cap']
    sell, buy = lv['top'] / 0.998, lv['bot'] / 1.002
    rr = RULES == 'rr'
    if rr:
        cap = round(STOP_PCT / 100 * cx['yc'])
        rule = (f"stop at most {STOP_PCT:g}% of price (about {cap} points), target {RR_TARGET:g}x the stop, "
                "held until the target, the stop or 3:15")
        mult = RR_TARGET
    else:
        rule = f"stop at most {cap:g} points, out within {HOLD_MIN} minutes"
        mult = PULLBACK_R
    out = [f"{nm} plan for the session after {cx['prev']} ({'1:' + format(RR_TARGET, 'g') + ' trades' if rr else 'small stops'})",
           f"CPR {f2(lv['bot'])} - {f2(lv['top'])}, pivot {f2(lv['p'])}" + (" (NARROW)" if cx['narrow'] else ""),
           poc_text(cx, ""),
           "Today's CPR vs yesterday's: " + ("higher -> no SELL breakout" if cx['rel'] > 0 else
                                             "lower -> no BUY breakout" if cx['rel'] < 0 else "overlapping -> both ways") +
           f"; yesterday's close {f2(cx['yc'])}: open above it -> BUY breakout only, below -> SELL only."]
    if not cx['narrow']:
        out.append(f"9:16 CPR MAGNET: SELL if the 9:15 candle opens above {f2(lv['top'])} and closes at or above {f2(sell)}"
                   + ("" if poc is None else f" and below the POC" if sell < poc else " (not possible today)") +
                   f"; BUY if it opens below {f2(lv['bot'])} and closes at or below {f2(buy)}"
                   + ("" if poc is None else f" and above the POC" if buy > poc else " (not possible today)") +
                   (f". Target {mult:g}x the stop." if rr else ". Target the CPR edge."))
    out.append("9:30-10:00 BREAKOUT, then PULLBACK: when price breaks the 9:15-9:30 high / low (filters above) and goes 0.1% "
               f"beyond it, place a limit order back at that level (until 12:00). Target {mult:g}x the stop.")
    if not rr:
        out.append(f"3-day volume lines: {', '.join(f2(x) for x in cx['lines'])}. 9:30-2:30: a 5-minute close through a line "
                   "-> trade toward the next line (it must be at least 1.5x the stop away).")
    out.append(f"Every trade: {rule}, one trade at a time.")
    return '\n'.join(out)

def range_note_small(cx, c1):
    first = [x for x in c1 if x[0] < RANGE_END]
    orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    gap = c1[0][1] - cx['yc']
    gap = 1 if gap > 0 else -1 if gap < 0 else 0
    if gap == 0 or gap == -cx['rel']:
        return (f"{cx['name']} 15-minute range {f2(orl)} - {f2(orh)}. No breakout trade today." +
                (" Volume-line trades only." if cx.get('rules_used') == 'small' else ""))
    lvl, word = (orh, 'BUY') if gap > 0 else (orl, 'SELL')
    return (f"{cx['name']} 15-minute range {f2(orl)} - {f2(orh)}. Watching for a break of {f2(lvl)} before 10:00"
            + ("" if poc_ok(cx, gap, lvl) else f" (only counts beyond the POC {f2(cx['poc'])})") +
            f"; then a {word} limit order on the pullback to it.")

def range_note(cx, c1):
    """At 9:30: which breakout trade is still possible today."""
    first = [x for x in c1 if x[0] < RANGE_END]
    orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    gap = c1[0][1] - cx['yc']
    gap = 1 if gap > 0 else -1 if gap < 0 else 0
    if gap == 0 or gap == -cx['rel']:
        return f"{cx['name']} 15-minute range {f2(orl)} - {f2(orh)}. No breakout trade today (" + \
               ("flat open" if gap == 0 else "the opening gap is against today's CPR vs yesterday's") + "). Volume-line" + \
               (" and sweep" if SWEEP else "") + " trades only."
    lvl, word = (orh, 'BUY') if gap > 0 else (orl, 'SELL')
    other = orl if gap > 0 else orh
    pocok = poc_ok(cx, gap, lvl)
    return (f"{cx['name']} 15-minute range {f2(orl)} - {f2(orh)}. Until 10:00: {word} when price touches {f2(lvl)}"
            + ("" if pocok else f" (only if price is {'above' if gap > 0 else 'below'} the POC {f2(cx['poc'])} then)") +
            f", stop {f2(other)}, book half at {f2(lvl + gap * 0.25 * abs(lvl - other))}" +
            (" (only if the volume check agrees then)." if vcheck(cx['name']) else "."))

def messages(cx, ts, c1, upto, lots):
    """(id, minute known, text, important) for everything that has happened so far."""
    nm, out = cx['name'], []
    plan = [t for t in ts if t['src'] not in ('VOLUME LINE', 'SWEEP')]
    if cx.get('rules_used') in ('small', 'rr'):
        return messages_small(cx, ts, c1, upto, lots)
    if c1 and not cx['narrow'] and upto >= 556 and not any(t['src'] == 'MAGNET' for t in plan):
        out.append(('nomag', 556, f"{nm} 9:16: no CPR Magnet trade today; breakout plan from 9:30.", False))
    if c1 and upto >= RANGE_END - 1 and not any(t['src'] == 'MAGNET' for t in plan):
        out.append(('range', RANGE_END, range_note(cx, c1), True))
        if upto >= CUTOFF and not plan:
            out.append(('nobo', CUTOFF, f"{nm} 10:00: no breakout trade. Volume-line" + (" and sweep" if SWEEP else "") +
                        " trades only from now (till 2:30).", False))
    sn = f"at most {stop_max(cx):g} points" if stop_max(cx) else ''
    for (src, side), m in sorted((cx.get('vlog') or {}).items(), key=lambda kv: kv[1]):
        out.append((('vskip', src, side), m, f"{nm} {hhmm(m)} {src} {'BUY' if side > 0 else 'SELL'} signal skipped: the volume "
                    f"doesn't agree (over the last 2 hours the {'down' if side > 0 else 'up'} candles carried more volume). "
                    "Not taking it.", False))
    for t in ts:
        sd = 'BUY' if t['side'] > 0 else 'SELL'
        tid = (t['src'], t['m'])
        if not t['taken']:
            out.append((tid + ('skip',), t['known'], f"{nm} {hhmm(t['m'])} {t['src']} {sd} signal at {f2(t['e'])} skipped: " +
                        (f"{SWEEP_MAX} sweep trades already today." if t.get('full') else "another trade is still open."), False))
            continue
        if t['src'] == 'SWEEP':
            hi = t['side'] < 0
            how = (f"Price went {'above' if hi else 'below'} yesterday's {'high' if hi else 'low'} {f2(t['lvl'])} and closed back "
                   f"{'below' if hi else 'above'} it (liquidity sweep). Stop {f2(t['stp0'])} (just beyond the candle). "
                   f"Target {f2(t['tgt'])} (3x the stop). Out by 15:15 at the latest.")
        elif t['src'] == 'MAGNET':
            how = (f"Stop {f2(t['stp0'])} ({sn or '0.3%'}). Book half at {f2(t['t1'])}, then stop to entry; "
                   f"rest to the CPR edge {f2(t['edge'])}.")
        elif t['src'] == 'VOLUME LINE':
            how = (f"5-minute close through the line {f2(t['x'])}. Stop {f2(t['stp0'])} ({sn or 'previous line'}). "
                   f"Target {f2(t['tgt'])} (next line)" +
                   (f": book half there, move the stop to {f2(t['x'])}, rest to {f2(t['tgt2'])}." if t['tgt2'] else "."))
        else:
            how = (("Reversal after the failed break. " if t['src'] == 'REVERSAL' else "") +
                   f"Stop {f2(t['stp0'])} ({sn or 'other side of the 15-minute range'}). Book half at "
                   f"{f2(t['e'] + t['side'] * 0.25 * t['R'])}, then stop to entry; after {f2(t['e'] + t['side'] * t['R'])} "
                   "trail the stop 1R behind the best price.")
        tg = target_levels(cx, c1, t['side'], t['e'], t['known'], half_price(t))
        out.append((tid + ('in',), t['known'], f"{nm} {hhmm(t['m'] if t['src'] != 'MAGNET' else 556)} {t['src']} {sd} at "
                    f"{f2(t['e'])} -> {option(cx, t['side'], t['e'])}. {how} Targets: T1 {f2(tg[0])} ({t1_word(t)}), "
                    f"then the next levels T2 {f2(tg[1])}, T3 {f2(tg[2])} (for reference).", True))
        for k, ev in enumerate(t['ev']):
            if ev['kind'] == 'half':
                txt = (f"{nm} {hhmm(ev['m'])} BOOK HALF at {f2(ev['px'])} ({ev['pts']:+.0f} pts). Move the stop to {f2(ev['stp'])}."
                       + (f" Rest to {f2(t['tgt2'])}." if t['src'] == 'VOLUME LINE' and t.get('tgt2') else ""))
            else:
                txt = f"{nm} {hhmm(ev['m'])} +1R reached: trail the stop 1R behind the best price (now {f2(ev['stp'])})."
            out.append((tid + ('ev', k), ev['m'] + 1, txt, True))
        if t['exit']:
            x = t['exit']
            out.append((tid + ('out',), x['m'] + 1, f"{nm} {hhmm(x['m'])} EXIT ({x['why']}) at {f2(x['px'])}: {x['pnl']:+.0f} pts "
                        f"after costs (about Rs {rupees(cx, x['pnl'], lots):+,.0f} at {lots} lots).", True))
    return out

def messages_small(cx, ts, c1, upto, lots):
    nm, out = cx['name'], []
    if c1 and not cx['narrow'] and upto >= 556 and not any(t['src'] == 'MAGNET' for t in ts):
        out.append(('nomag', 556, f"{nm} 9:16: no CPR Magnet trade today.", False))
    if c1 and upto >= RANGE_END - 1:
        out.append(('range', RANGE_END, range_note_small(cx, c1), True))
    bo = cx.get('breakout')
    if bo:
        word = 'BUY' if bo['side'] > 0 else 'SELL'
        out.append(('bo', bo['m'] + 1, f"{nm} {hhmm(bo['m'])} broke the 15-minute {'high' if bo['side'] > 0 else 'low'} {f2(bo['lvl'])}. "
                    f"Don't chase it: once price reaches {f2(bo['arm'])} (0.1% beyond), place a {word} LIMIT order at {f2(bo['px'])} "
                    "for the pullback, valid until 12:00.", True))
    pend = cx.get('pending')
    if pend:
        word = 'BUY' if pend['side'] > 0 else 'SELL'
        out.append(('pend', pend['m'] + 1, f"{nm} {hhmm(pend['m'])} breakout {'UP' if pend['side'] > 0 else 'DOWN'} confirmed. Place a {word} "
                    f"LIMIT order at {f2(pend['px'])} (back at the broken 15-minute {'high' if pend['side'] > 0 else 'low'}), valid until "
                    f"12:00 -> {option(cx, pend['side'], pend['px'])}. Stop {f2(pend['stp'])}, target {f2(pend['tgt'])} ({pend['tdesc']}), " +
                    (f"out within {pend['hold']} minutes after the fill." if pend['hold'] else
                     "hold until the target, the stop or 3:15."), True))
        if upto >= 720 and not any(t['src'] == 'PULLBACK' for t in ts):
            out.append(('nopb', 720, f"{nm} 12:00: the pullback didn't come. Cancel the {word} limit order at {f2(pend['px'])}.", True))
    for t in ts:
        sd = 'BUY' if t['side'] > 0 else 'SELL'
        tid = (t['src'], t['m'])
        if not t['taken']:
            out.append((tid + ('skip',), t['known'], f"{nm} {hhmm(t['m'])} {t['src']} {sd} at {f2(t['e'])} skipped: "
                        "another trade is still open" + (" (cancel the limit order)." if t['src'] == 'PULLBACK' else "."), t['src'] == 'PULLBACK'))
            continue
        if t['src'] == 'MAGNET':
            how = f"Target {f2(t['tgt'])} ({t['tdesc']})."
        elif t['src'] == 'PULLBACK':
            how = (f"Limit order filled back at the broken 15-minute {'high' if t['side'] > 0 else 'low'}. "
                   f"Target {f2(t['tgt'])} ({t['tdesc']}).")
        else:
            how = f"5-minute close through the line {f2(t['x'])}. Target {f2(t['tgt'])} (next volume line)."
        out.append((tid + ('in',), t['known'], f"{nm} {hhmm(556 if t['src'] == 'MAGNET' else t['m'])} {t['src']} {sd} at {f2(t['e'])} -> "
                    f"{option(cx, t['side'], t['e'])}. Stop {f2(t['stp0'])}. {how} Out by {hhmm(t['last'])} at the latest.", True))
        if t['exit']:
            x = t['exit']
            out.append((tid + ('out',), x['m'] + 1, f"{nm} {hhmm(x['m'])} EXIT ({x['why']}) at {f2(x['px'])}: {x['pnl']:+.0f} pts "
                        f"after costs (about Rs {rupees(cx, x['pnl'], lots):+,.0f} at {lots} lots).", True))
    return out

def open_note(cx, ts):
    for t in ts:
        if t['taken'] and not t['exit']:
            half = any(e['kind'] == 'half' for e in t['ev'])
            return (f"open: {t['src']} {'BUY' if t['side'] > 0 else 'SELL'} from {f2(t['e'])}, stop now {f2(t['stp'])}"
                    + (", half booked" if half else ""))
    return "no trade open"

def day_summary(cx, ts, lots):
    done_ = [t for t in ts if t['taken'] and t['exit']]
    pts = sum(t['exit']['pnl'] for t in done_)
    won = sum(t['exit']['pnl'] > 0 for t in done_)
    return (f"{cx['name']} day: {len(done_)} trades, {won} won / {len(done_) - won} lost, {pts:+.0f} pts after costs "
            f"(about Rs {rupees(cx, pts, lots):+,.0f} at {lots} lots).")


# ---------------- alerts ----------------
def telegram(text):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        return False
    try:
        data = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': text}).encode()
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=data), timeout=15)
        return True
    except Exception as e:
        print(f"  (Telegram message failed: {e})")
        return False

def alert(text, push=True, kind='info', index=''):
    print(('\a>>> ' if push else '    ') + text, flush=True)
    if push:
        telegram(text)
        record_event(text, kind, index or text.split(' ', 1)[0])


# ---------------- the app: events (notifications), today's calls, history ----------------
EVENTS = []                       # the alerts sent, newest last (the app's notifications read them)
PLANS = {}                        # today's plan text of each index
EVENTS_FILE = os.path.join(DATA_DIR, 'events.jsonl')
HISTORY_FILE = os.path.join(DATA_DIR, 'history.json')
HISTORY_SEED = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'history-2026.json')

def load_events():
    if EVENTS or not os.path.exists(EVENTS_FILE):
        return
    try:
        with open(EVENTS_FILE, encoding='utf-8') as f:
            EVENTS.extend(json.loads(x) for x in f.read().splitlines()[-300:] if x.strip())
    except Exception as e:
        print(f"  (events not loaded: {e})")

def event_title(text, kind, index):
    import re
    if kind == 'plan':
        return f"{index} plan for today"
    if kind == 'summary':
        return f"{index} day result"
    m = re.match(r'^(\w+) (\d\d?:\d\d) (.+?) (BUY|SELL) at ([\d,.]+)', text)
    if kind == 'entry' and m:
        return f"{m.group(1)} {m.group(4)} {m.group(5)} ({m.group(3).lower()})"
    m = re.match(r'^(\w+) (\d\d?:\d\d) EXIT \(([^)]+)\) at ([\d,.]+): ([+-]?\d+) pts', text)
    if kind == 'exit' and m:
        return f"{m.group(1)} EXIT ({m.group(3)}): {m.group(5)} pts"
    first = text.split('. ')[0].split(' -> ')[0]
    return first if len(first) <= 70 else first[:67] + '...'

def record_event(text, kind, index):
    eid = max(int(time.time() * 1000), (EVENTS[-1]['id'] + 1) if EVENTS else 0)
    e = dict(id=eid, at=now_ist().strftime('%Y-%m-%d %H:%M:%S'), index=index, kind=kind, title=event_title(text, kind, index), text=text)
    EVENTS.append(e)
    del EVENTS[:-300]
    try:
        with open(EVENTS_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(e) + '\n')
    except Exception:
        pass

def kind_of(mid):
    if isinstance(mid, tuple):
        if mid[-1] == 'in':
            return 'entry'
        if mid[-1] == 'out':
            return 'exit'
        if len(mid) > 1 and mid[-2] == 'ev':
            return 'update'
        if mid[0] == 'vskip' or mid[-1] == 'skip':
            return 'skip'
    return 'info'

def mfe_before_stop(c1, side, e, stop, start_m, last_m=CLOSE - 1):
    """How far the index went the call's way (points) before touching the stop loss, and whether the stop was hit."""
    best = 0.0
    for m, o, h, l, c in c1:
        if m < start_m or m > last_m:
            continue
        for p in path(o, h, l, c):
            if side * (p - stop) <= 0:
                return best, True
            best = max(best, side * (p - e))
    return best, False

TARGETS_V = 2                     # the T1 / T2 / T3 kind in the saved history (2: T1 = where half is booked)

def half_price(t):
    """Where the call books half (or, for a single target, its target): T1."""
    if t.get('small') or t['src'] in ('VOLUME LINE', 'SWEEP'):
        return t['tgt']
    if t['src'] == 'MAGNET':
        return t['t1']
    return t['e'] + t['side'] * 0.25 * t['R']

def t1_word(t):
    """What the call does at T1: books half, or (a single target) books all."""
    return 'target' if t['src'] in ('VOLUME LINE', 'SWEEP') and not t.get('tgt2') else 'book half'

def target_levels(cx, c1, side, e, start, t1=None):
    """T1 / T2 / T3 for the app, the chart and the alerts. T1 = where the call books half (`t1`; the exits are the
    same as always). T2 / T3, for reference only (the exits don't use them): the next two price levels beyond T1 in
    the trade's direction (the CPR, the floor pivots R1-R3 / S1-S3, yesterday's high / low, the 15-minute high / low
    once known, the 3-day volume lines, the POC), at least 0.05% apart. Without `t1`: the next three levels."""
    lv, yh, yl = cx['lv'], cx['yh'], cx['yl']
    P = lv['p']
    L = [lv['top'], P, lv['bot'], yh, yl, 2 * P - yl, 2 * P - yh, P + (yh - yl), P - (yh - yl),
         yh + 2 * (P - yl), yl - 2 * (yh - P)] + list(cx['lines'])
    if cx.get('poc') is not None:
        L.append(cx['poc'])
    first = [x for x in c1 if x[0] < RANGE_END]
    if start >= RANGE_END and first:
        L += [max(x[2] for x in first), min(x[3] for x in first)]
    gap, t = 0.0005 * e, ([] if t1 is None else [t1])
    for x in sorted((x for x in L if side * (x - (e if t1 is None else t1)) >= gap), key=lambda x: side * (x - e)):
        if not t or side * (x - t[-1]) >= gap:
            t.append(x)
        if len(t) == 3:
            break
    if not t:
        t = [e + side * 0.0025 * e]
    while len(t) < 3:
        t.append(t[-1] + (t[-1] - (t[-2] if len(t) > 1 else e)))
    return [round(x, 2) for x in t]

def mae_until(c1, side, e, start_m, end_m):
    """How far the index went against the call (points) from its entry until it closed."""
    worst = 0.0
    for m, o, h, l, c in c1:
        if start_m <= m <= end_m:
            worst = max(worst, side * (e - (l if side > 0 else h)))
    return worst

def call_info(cx, t, c1):
    """One taken trade as the app shows it."""
    sd, x = t['side'], t['exit']
    mfe, stopped = mfe_before_stop(c1, sd, t['e'], t['stp0'], t['known'])
    need = SUCCESS_PTS.get(cx['name'], 0)
    m0 = 556 if t['src'] == 'MAGNET' else t['m']           # as the alert says it
    tg = target_levels(cx, c1, sd, t['e'], t['known'], half_price(t))
    mae = mae_until(c1, sd, t['e'], t['known'], x['m'] if x else (c1[-1][0] if c1 else t['known']))
    return dict(time=hhmm(m0), side='BUY' if sd > 0 else 'SELL', setup=t['src'].lower(), entry=round(t['e'], 2),
                stop=round(t['stp0'], 2), stop_now=round(t['stp'], 2), open=not x, status=(f"{x['why']} at {f2(x['px'])}" if x else 'open'),
                pts=round(x['pnl'], 1) if x else None, mfe=round(mfe, 1), mae=round(mae, 1), stopped=stopped, success=mfe >= need,
                need=need, option=option(cx, sd, t['e']), targets=tg, t1=t1_word(t),
                hit=[mfe >= sd * (v - t['e']) - 0.005 for v in tg])

def record_history(cx, ts, c1, day):
    """At the close: the day's calls, with their result and whether they reached the success move."""
    rows = []
    for t in ts:
        if t['taken'] and t['exit']:
            ci = call_info(cx, t, c1)
            rows.append(dict(d=day, index=cx['name'], time=ci['time'], side=ci['side'], setup=ci['setup'], entry=ci['entry'],
                             stop=ci['stop'], pts=ci['pts'], mfe=ci['mfe'], mae=ci['mae'], success=ci['success'],
                             targets=ci['targets'], hit=ci['hit'], tv=TARGETS_V))
    try:
        old = json.load(open(HISTORY_FILE)) if os.path.exists(HISTORY_FILE) else []
        have = {(r['d'], r['index'], r['time'], r['side']) for r in old}
        new = [r for r in rows if (r['d'], r['index'], r['time'], r['side']) not in have]
        if new:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(old + new, f)
    except Exception as e:
        print(f"  (history not saved: {e})")

def history_all():
    rows = {}
    for path_ in (HISTORY_SEED, HISTORY_FILE):
        try:
            for r in json.load(open(path_)) if os.path.exists(path_) else []:
                rows[(r['d'], r['index'], r['time'], r['side'])] = r
        except Exception as e:
            print(f"  (history file {path_}: {e})")
    calls = sorted(rows.values(), key=lambda r: (r['d'], r['time']), reverse=True)
    def stats(rs):
        n = len(rs); w = sum(r['success'] for r in rs)
        avg = lambda k: round(sum(r.get(k) or 0 for r in rs) / n) if n else None
        hits = [r['hit'] for r in rs if r.get('hit')]
        return dict(calls=n, success=w, rate=round(100 * w / n) if n else None, pts=round(sum(r['pts'] or 0 for r in rs)),
                    up=avg('mfe'), down=avg('mae'),
                    t1=round(100 * sum(h[0] for h in hits) / len(hits)) if hits else None,
                    t2=round(100 * sum(h[1] for h in hits) / len(hits)) if hits else None,
                    t3=round(100 * sum(h[2] for h in hits) / len(hits)) if hits else None)
    out = dict(rule={k: v for k, v in SUCCESS_PTS.items()}, calls=calls, stats={})
    cut = str(dt.date.fromisoformat(calls[0]['d']) - dt.timedelta(days=30)) if calls else ''
    for idx in ('ALL', 'NIFTY', 'SENSEX'):
        rs = [r for r in calls if idx == 'ALL' or r['index'] == idx]
        out['stats'][idx] = dict(all=stats(rs), last30=stats([r for r in rs if r['d'] > cut]))
    return out

def app_state():
    out = dict(updated=now_ist().strftime('%Y-%m-%d %H:%M:%S'), indices={})
    for n, d in CHART_DATA.items():
        lv = live_now(n) if d.get('day') == str(now_ist().date()) else None
        out['indices'][n] = dict(name=d.get('name'), day=d.get('day'), status=d.get('status'), plan=PLANS.get(n, ''),
                                 last=lv[0] if lv else d['candles'][-1][4] if d.get('candles') else None,
                                 live=lv[1] if lv else None, calls=d.get('calls', []), updated=d.get('updated'))
    return out

def app_ota():
    """The app's screens (app.js, style.css, index.html), sent over the air: the installed app takes a new version
    the next time it opens, without a new APK. `ver` changes whenever one of the files does; `apk` is the newest
    APK's build number (the app offers it when it is newer than the installed one)."""
    import hashlib
    files, h = {}, hashlib.sha256()
    for f in ('app.js', 'style.css', 'index.html'):
        try:
            with open(os.path.join(APP_WWW, f), encoding='utf-8') as fh:
                files[f] = fh.read()
        except OSError:
            return dict(ver=None)
        h.update(f.encode() + b'\0' + files[f].encode() + b'\0')
    apk = 0
    try:
        with open(os.path.join(APP_WWW, '..', '..', 'dist', 'eden-trader.json')) as fh:
            apk = int(json.load(fh).get('build', 0))
    except (OSError, ValueError):
        pass
    return dict(ver=h.hexdigest()[:12], apk=apk, files=files)

def now_ist():
    return dt.datetime.now(IST)


# ---------------- live chart in the phone's browser ----------------
CHART_DATA = {}                   # index -> what the chart page shows, refreshed by the main loop

def mark_of(why):
    return 'SL' if why == 'stop' else 'BE' if why == 'stop at entry' else 'T' if why.startswith('target') else 'X'

def chart_update(n, cx, c_all, ts, got, day):
    """Everything the chart page draws for one index: today's (and yesterday's) 1-minute candles, levels, marks."""
    lv = cx['lv']
    pink = '#ff9800' if cx['narrow'] else '#e91e63'
    levels = [dict(p=lv['top'], c=pink, t='CPR top', s=0, w=2), dict(p=lv['p'], c=pink, t='Pivot', s=0, w=1),
              dict(p=lv['bot'], c=pink, t='CPR bottom', s=0, w=2)]
    if cx['poc'] is not None:
        levels.append(dict(p=cx['poc'], c='#9c6ade', t='POC yesterday' if cx['pocn'] == 1 else f"POC {cx['pocn']} days", s=0, w=1))
    levels += [dict(p=x, c='#26a69a', t='Vol line', s=1, w=1) for x in cx['lines']]
    levels += [dict(p=cx['yh'], c='#fdd835', t='Yesterday high', s=2, w=1), dict(p=cx['yl'], c='#fdd835', t='Yesterday low', s=2, w=1)]
    first = [x for x in c_all if x[0] < RANGE_END]
    if first and got >= RANGE_END - 1:
        levels += [dict(p=max(x[2] for x in first), c='#4caf50', t='15-min high', s=2, w=1),
                   dict(p=min(x[3] for x in first), c='#f44336', t='15-min low', s=2, w=1)]
    marks, rows, open_t = [], [], None
    for t in ts:
        if not t['taken']:
            continue
        sd = t['side']
        m0 = 555 if t['src'] == 'MAGNET' else t['m'] - 1 if t['src'] in ('VOLUME LINE', 'SWEEP') else t['m']
        marks.append(dict(m=m0, pos='belowBar' if sd > 0 else 'aboveBar', c='#26a69a' if sd > 0 else '#ef5350', x='B' if sd > 0 else 'S'))
        for ev in t['ev']:
            if ev['kind'] == 'half':
                marks.append(dict(m=ev['m'], pos='aboveBar' if sd > 0 else 'belowBar', c='#26a69a', x='T'))
        x = t['exit']
        if x:
            k = mark_of(x['why'])
            marks.append(dict(m=x['m'], pos=('belowBar' if sd > 0 else 'aboveBar') if k in ('SL', 'BE') else ('aboveBar' if sd > 0 else 'belowBar'),
                              c='#9e9e9e' if k == 'BE' else '#26a69a' if x['pnl'] > 0 else '#ef5350', x=k))
        else:
            open_t = t
        rows.append([hhmm(m0 + (1 if t['src'] in ('VOLUME LINE', 'SWEEP') else 0)), ('BUY' if sd > 0 else 'SELL') + ' ' + t['src'].lower(), f2(t['e']), f2(t['stp0']),
                     (f"{x['why']} at {f2(x['px'])}: {x['pnl']:+.0f} pts" if x else f"open, stop now {f2(t['stp'])}")])
    pend = cx.get('pending')
    if pend and got < 720 and not any(t['src'] == 'PULLBACK' for t in ts):
        levels.append(dict(p=pend['px'], c='#2962ff', t='LIMIT ' + ('BUY' if pend['side'] > 0 else 'SELL'), s=2, w=2))
    if open_t:
        levels.append(dict(p=open_t['stp'], c='#ef5350', t='Stop loss', s=2, w=1))
        T = target_levels(cx, c_all, open_t['side'], open_t['e'], open_t['known'], half_price(open_t))
        for k, v in enumerate(T):
            levels.append(dict(p=v, c='#26a69a' if k == 0 else '#80cbc4', t='T1 ' + t1_word(open_t) if k == 0 else f'T{k + 1}', s=2 if k == 0 else 1, w=1))
        half = any(e['kind'] == 'half' for e in open_t['ev'])
        sd = open_t['side']
        if open_t.get('small'):
            tg = open_t['tgt']
        elif open_t['src'] == 'MAGNET':
            tg = open_t['edge'] if half else open_t['t1']
        elif open_t['src'] == 'VOLUME LINE':
            tg = open_t['tgt2'] if half else open_t['tgt']
        else:
            tg = None if half else open_t['e'] + sd * 0.25 * open_t['R']      # after half: trailing, no target
        if tg and abs(tg - T[0]) > 0.01:
            levels.append(dict(p=tg, c='#26a69a', t='Target', s=2, w=1))
    done_ = [t for t in ts if t['taken'] and t['exit']]
    net = sum(t['exit']['pnl'] for t in done_)
    last = c_all[-1] if c_all else None
    status = (f"{cx['name']} {f2(last[4]) if last else '-'}" + (f" (data to {hhmm(last[0])})" if last else '') +
              f" | CPR {f2(lv['bot'])} - {f2(lv['top'])} " + ('NARROW' if cx['narrow'] else '') +
              f" | {open_note(cx, ts)} | today {len(done_)} trade{'' if len(done_) == 1 else 's'}, {net:+.0f} pts")
    upto_c = [x for x in c_all if x[0] <= got]
    calls = [call_info(cx, t, upto_c) for t in ts if t['taken']]
    CHART_DATA[n] = dict(name=cx['name'], day=day, yday_date=cx['prev'], yday=[list(x) for x in cx['yday']],
                         candles=[list(x) for x in c_all], levels=levels, marks=sorted(marks, key=lambda k: k['m']),
                         rows=rows, status=status, updated=now_ist().strftime('%H:%M:%S'), calls=calls)

CHART_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0f1419">
<meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes"><title>CPRB live chart</title>
<style>
body{margin:0;background:#0f1419;color:#d1d4dc;font:14px system-ui,-apple-system,sans-serif}
#bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:8px}
button{background:#1e2530;color:#d1d4dc;border:1px solid #2a3240;border-radius:6px;padding:6px 12px;font:inherit}
button.on{background:#2962ff;border-color:#2962ff;color:#fff}
#st{width:100%;font-size:13px;color:#9aa4b2}
#c{height:68vh}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:5px 8px;border-bottom:1px solid #222a35;text-align:left}
#key{font-size:12px;color:#7d8794;padding:6px 8px}
</style></head><body>
<div id="bar"></div><div id="c"></div>
<div id="key">Pink: CPR top / pivot / bottom (orange on a narrow day). Purple: the volume POC, where the most volume traded over the
days its label says (buys above it, sells below; not drawn for an index with no POC filter: Sensex). Teal dots: 3-day volume lines. Green / red dashed: the first 15 minutes' high / low (a BUY on a
touch of the high, a SELL on the low, until 10:00, if the filters allow), and the open trade's target / stop loss. Yellow dashed:
yesterday's high / low. Letters: B buy, S sell, T target or half booked, SL stop loss, BE stop at entry, X other exit.
In market hours the last candle moves with the live price (every 2 seconds); the calls use whole 1-minute candles.
Fit: back to the latest candles with the price scale fitted.</div>
<table><thead><tr><th>Time</th><th>Trade</th><th>Entry</th><th>Stop</th><th>Result</th></tr></thead><tbody id="list"></tbody></table>
<script src="/lwc.js"></script>
<script>
const IDX = %INDICES%; let cur = IDX[0][0], tf = 5, plines = [], lastKey = '', fitted = '', seq = 0, shownSeq = 0;
const box = document.getElementById('c');
if (!window.LightweightCharts) document.getElementById('bar').textContent = 'The chart library did not load: check the internet connection and reload.';
const chart = LightweightCharts.createChart(box, {layout: {background: {color: '#0f1419'}, textColor: '#d1d4dc', fontSize: 14},
  grid: {vertLines: {color: '#18202a'}, horzLines: {color: '#18202a'}}, rightPriceScale: {borderColor: '#2a3240'},
  timeScale: {timeVisible: true, secondsVisible: false, borderColor: '#2a3240', rightOffset: 6}, crosshair: {mode: 0},
  handleScroll: {vertTouchDrag: false},      // a finger moving up / down scrolls the page, not the price scale
  localization: {locale: 'en-IN'}});
const s = chart.addCandlestickSeries({upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
  wickUpColor: '#26a69a', wickDownColor: '#ef5350', priceLineVisible: false});
new ResizeObserver(() => chart.applyOptions({width: box.clientWidth, height: box.clientHeight})).observe(box);
const ts = (day, m) => { const [y, mo, d] = day.split('-').map(Number); return Date.UTC(y, mo - 1, d) / 1000 + m * 60; };
const bucket = m => 555 + Math.floor((m - 555) / tf) * tf;
function agg(day, rows, out) {
  for (const [m, o, h, l, c] of rows) {
    const t = ts(day, bucket(m)), x = out[out.length - 1];
    if (x && x.time === t) { x.high = Math.max(x.high, h); x.low = Math.min(x.low, l); x.close = c; }
    else out.push({time: t, open: o, high: h, low: l, close: c});
  }
  return out;
}
function buttons() {
  const bar = document.getElementById('bar'); bar.innerHTML = '';
  for (const [k, name] of IDX) { const b = document.createElement('button'); b.textContent = name; b.className = k === cur ? 'on' : '';
    b.onclick = () => { if (k !== cur) { cur = k; clear(); } fitted = ''; buttons(); load(); }; bar.appendChild(b); }
  for (const f of [1, 3, 5, 15]) { const b = document.createElement('button'); b.textContent = f + 'm'; b.className = f === tf ? 'on' : '';
    b.onclick = () => { tf = f; fitted = ''; buttons(); load(); }; bar.appendChild(b); }
  const fit = document.createElement('button'); fit.textContent = 'Fit'; fit.title = 'Show the latest candles, price scale to fit';
  fit.onclick = () => { fitted = ''; load(); }; bar.appendChild(fit);
  const st = document.createElement('div'); st.id = 'st'; st.textContent = 'loading...'; bar.appendChild(st);
}
function clear() {                          // another index: nothing of the last one stays on the chart
  plines.forEach(p => s.removePriceLine(p)); plines = []; lastKey = '';
  s.setData([]); s.setMarkers([]);
  document.getElementById('list').innerHTML = '';
}
async function load() {
  let d;
  const want = cur, my = ++seq;
  const kq = new URLSearchParams(location.search).get('key');
  try { d = await (await fetch('/data?i=' + want + (kq ? '&key=' + encodeURIComponent(kq) : ''), {cache: 'no-store'})).json(); }
  catch (e) { if (want === cur) document.getElementById('st').textContent = 'No data: the program is not running (start it in Pydroid 3, or check the server).'; return; }
  if (want !== cur || my < shownSeq) return;   // an older answer, or for the index shown before: ignore it
  shownSeq = my;
  if (!d.day) { document.getElementById('st').textContent = 'No data for this index yet.'; return; }
  s.setData(agg(d.day, d.candles, agg(d.yday_date, d.yday, [])));
  s.setMarkers(d.marks.map(k => ({time: ts(d.day, bucket(k.m)), position: k.pos, color: k.c, shape: k.pos === 'belowBar' ? 'arrowUp' : 'arrowDown', size: 1.2, text: k.x})));
  const key = JSON.stringify(d.levels);
  if (key !== lastKey) { plines.forEach(p => s.removePriceLine(p)); lastKey = key;
    plines = d.levels.map(l => s.createPriceLine({price: l.p, color: l.c, lineWidth: l.w, lineStyle: l.s, axisLabelVisible: l.t !== '', title: l.t})); }
  if (fitted !== cur + tf) { fitted = cur + tf; chart.priceScale('right').applyOptions({autoScale: true});
    chart.timeScale().setVisibleLogicalRange({from: Math.max(0, s.data().length - 90), to: s.data().length + 6}); }
  const px = n => Number(n).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  document.getElementById('st').textContent = (d.live ? '● LIVE ' + d.name + ' ' + px(d.live.px) + ' at ' + d.live.at + ' | ' : '') +
    d.status + ' | updated ' + d.updated;
  document.getElementById('list').innerHTML = d.rows.map(r => '<tr>' + r.map(x => '<td>' + x + '</td>').join('') + '</tr>').join('') ||
    '<tr><td colspan="5">No trades yet today.</td></tr>';
}
buttons(); load(); setInterval(load, 2000);
</script></body></html>"""

LWC_URL = 'https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js'
LWC_FILE = os.path.join(DATA_DIR, 'lightweight-charts-4.1.3.js')

def chart_library():
    """TradingView's free open-source chart library, downloaded once and kept next to this file."""
    if not os.path.exists(LWC_FILE):
        try:
            req = urllib.request.Request(LWC_URL, headers={'User-Agent': 'curl/8.5.0'})
            with urllib.request.urlopen(req, timeout=60) as r, open(LWC_FILE, 'wb') as f:
                f.write(r.read())
        except Exception as e:
            print(f"  (chart library not downloaded: {e}; the page will try the internet directly)")
            return None
    with open(LWC_FILE, 'rb') as f:
        return f.read()

CHART_SERVER = []                 # the chart server, once it runs (it is started only once)

def key_ok(handler):
    """With a key set (CHART_KEY, or only its SHA-256): the key in the address (?key=...), in an X-Key header, or in
    the cookie set the first time."""
    import hashlib
    import hmac
    if not (CHART_KEY or CHART_KEY_SHA256):
        return True, False
    def good(v):
        if not v:
            return False
        if CHART_KEY_SHA256:
            return hmac.compare_digest(hashlib.sha256(v.encode()).hexdigest(), CHART_KEY_SHA256.lower())
        return hmac.compare_digest(v, CHART_KEY)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query).get('key', [''])[0]
    if good(q):
        return True, True
    if good(handler.headers.get('X-Key', '')):
        return True, False
    for part in (handler.headers.get('Cookie') or '').split(';'):
        k, _, v = part.strip().partition('=')
        if k == 'cprb_key' and good(urllib.parse.unquote(v)):
            return True, False
    return False, False

def serve_chart(names):
    """Serve the chart page: on this phone / computer only (127.0.0.1), or as set by CPRB_CHART_HOST on a server."""
    import http.server
    import threading
    if CHART_SERVER:
        return True
    page = CHART_HTML.replace('%INDICES%', json.dumps([[n, SPEC[n]['name']] for n in names]))
    lib = chart_library()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split('?')[0] == '/app.apk' and APP_APK and os.path.exists(APP_APK):
                with open(APP_APK, 'rb') as f:
                    body = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.android.package-archive')
                self.send_header('Content-Disposition', 'attachment; filename="eden-trader.apk"')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            ok, fresh = key_ok(self)
            if not ok and not self.path.startswith('/lwc.js'):
                body = b'This chart needs its key: open the address with ?key=... at the end (see /etc/cprb.env on the server).'
                self.send_response(403)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith('/lwc.js') and not lib:
                self.send_response(302)
                self.send_header('Location', LWC_URL)
                self.end_headers()
                return
            if self.path.startswith('/lwc.js'):
                body, ctype = lib, 'application/javascript'
            elif self.path.startswith('/data'):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                i = q.get('i', [names[0]])[0]
                body, ctype = json.dumps(with_live(i, CHART_DATA.get(i, {}))).encode(), 'application/json'
            elif self.path.startswith('/app/ota.json'):
                body, ctype = json.dumps(app_ota()).encode(), 'application/json'
            elif self.path.startswith('/api/state'):
                body, ctype = json.dumps(app_state()).encode(), 'application/json'
            elif self.path.startswith('/api/events'):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                since = int((q.get('since') or ['0'])[0] or 0)
                body, ctype = json.dumps(dict(last=EVENTS[-1]['id'] if EVENTS else 0,
                                              events=[e for e in EVENTS if e['id'] > since][-50:])).encode(), 'application/json'
            elif self.path.startswith('/api/history'):
                body, ctype = json.dumps(history_all()).encode(), 'application/json'
            else:
                body, ctype = page.encode(), 'text/html; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            if ctype == 'application/json':
                self.send_header('Access-Control-Allow-Origin', '*')      # the phone app reads these
            if fresh:                                 # remember the key, so the page's data requests carry it
                secure = '; Secure' if self.headers.get('X-Forwarded-Proto') == 'https' else ''
                given = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get('key', [''])[0]
                self.send_header('Set-Cookie', f'cprb_key={urllib.parse.quote(given)}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax{secure}')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    try:
        srv = http.server.ThreadingHTTPServer((CHART_HOST, CHART_PORT), Handler)
    except OSError as e:
        print(f"  (chart not started: {e})")
        return False
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    CHART_SERVER.append(srv)
    if CHART_HOST == '127.0.0.1' and not (CHART_KEY or CHART_KEY_SHA256):
        print(f"LIVE CHART: open http://127.0.0.1:{CHART_PORT} in Chrome on this phone.")
    else:
        print(f"LIVE CHART: serving on {CHART_HOST}:{CHART_PORT}" + (" (key required)" if CHART_KEY else ""))
    return True

def keep_serving(text):
    print(text + " The chart stays open; press Stop in Pydroid 3 (or Ctrl+C) to end.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


# ---------------- running ----------------
def load(names, today):
    """Contexts for each index for the session `today` (a date string)."""
    t0 = dt.date.fromisoformat(today)
    keys = [SPEC[n]['key'] for n in names] + [BEES]
    data = history(keys, t0 - dt.timedelta(days=80), t0 - dt.timedelta(days=1))
    vol = {d: {m: v[4] for m, v in mm.items()} for d, mm in data[BEES].items()}
    out = {}
    for n in names:
        sess = {d: [(m,) + tuple(mm[m][:4]) for m in sorted(mm)] for d, mm in data[SPEC[n]['key']].items()}
        daily = fetch_daily(SPEC[n]['key'], t0 - dt.timedelta(days=80), t0 - dt.timedelta(days=1))
        out[n] = context(SPEC[n], sess, vol, today, daily)
    return out

def replay(names, day, lots, ladder, hold=True):
    cxs = load(names, day)
    rows = {n: fetch_range(SPEC[n]['key'], dt.date.fromisoformat(day), dt.date.fromisoformat(day)).get(day, {}) for n in names}
    tvol = {m: v[4] for m, v in fetch_range(BEES, dt.date.fromisoformat(day), dt.date.fromisoformat(day)).get(day, {}).items()}
    for n in names:
        cx = cxs[n]
        cx['tvol'] = tvol
        print("\n" + plan_text(cx).replace(f"the session after {cx['prev']}", day))
        c_all = [(m,) + tuple(rows[n][m][:4]) for m in sorted(rows[n])]
        if not c_all:
            print(f"  no candles for {day}")
            continue
        seen = set()
        ts = []
        for upto in range(OPEN, CLOSE):
            c1 = [x for x in c_all if x[0] <= upto]
            ts = day_trades(cx, c1, upto, upto == CLOSE - 1, ladder)
            for mid, mk, text, push in messages(cx, ts, c1, upto, lots):
                if mid not in seen:
                    seen.add(mid)
                    print(('>>> ' if push else '    ') + text)
        print('    ' + day_summary(cx, ts, lots))
        chart_update(n, cx, c_all, ts, CLOSE - 1, day)
    if CHART and CHART_DATA and serve_chart(names) and hold:
        keep_serving(f"Replay of {day} is on the chart.")

def live(names, lots, ladder, plan_only=False, forever=False):
    now = now_ist()
    today = str(now.date())
    print(f"CPR Breakout alerts, {now:%Y-%m-%d %H:%M} IST. Loading earlier sessions ...")
    cxs = load(names, today)
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID and not plan_only:
        telegram("CPR Breakout alerts started. The plan follows.")
    load_events()
    for n in names:
        PLANS[n] = plan_text(cxs[n])
        alert(PLANS[n], push=not plan_only, kind='plan', index=cxs[n]['name'])
    if plan_only:
        return
    if now.weekday() >= 5:
        print("Market closed today (weekend). The plan above is for the next session.")
        if CHART:
            print(f"Showing the last session ({cxs[names[0]]['prev']}) on the chart.")
            replay(names, cxs[names[0]]['prev'], lots, ladder, hold=not forever)
        return
    if CHART:
        serve_chart(names)
        live_prices(names)
        for n in names:
            chart_update(n, cxs[n], [], [], OPEN - 1, today)
    seen, first, last_ts, waited, shown, last_c = set(), True, {}, False, {}, {}
    while True:
        now = now_ist()
        mnow = now.hour * 60 + now.minute
        if mnow < OPEN:
            print(f"\r  waiting for the 9:15 open ({hhmm(mnow)} now) ...", end='', flush=True)
            waited = True
            time.sleep(min(30, max(1, (OPEN - mnow) * 60 - now.second + 15)))
            continue
        if waited:
            print()
            waited = False
        upto = min(mnow - 1, CLOSE - 1)
        late = False
        vlast = CLOSE
        if any(vcheck(n) for n in names) and RULES == 'classic':
            try:
                tvol = {m: v[4] for m, v in fetch_today(BEES).get(today, {}).items()}
                vlast = max(tvol) if tvol else OPEN - 1
            except Exception as e:
                print(f"  NIFTYBEES volume: data error ({e}); trying again next minute")
                time.sleep(15)
                continue
            for n in names:
                cxs[n]['tvol'] = tvol
        for n in names:
            cx = cxs[n]
            try:
                rows = fetch_today(cx['key']).get(today, {})
            except Exception as e:
                print(f"  {cx['name']}: data error ({e}); trying again next minute")
                continue
            c_all = [(m,) + tuple(rows[m][:4]) for m in sorted(rows)]       # includes the minute still forming
            c1 = [x for x in c_all if x[0] <= upto]
            if not c1:
                if mnow >= OPEN + 10 and shown.get(n) != 'none':
                    print(f"  {cx['name']}: no candles yet today ({hhmm(mnow)}). Market holiday or a data problem?")
                    shown[n] = 'none'
                continue
            vl = vlast if vcheck(n) else CLOSE               # the NIFTYBEES volume matters only with the volume check
            if (c1[-1][0] < upto or vl < upto) and now.second < 40:
                late = True                                   # the last minute isn't in yet: look again soon
                if CHART:
                    chart_update(n, cx, c_all, last_ts.get(n, []), c1[-1][0], today)
                continue
            got = min(upto, c1[-1][0], vl)                    # data complete up to here (the source can lag)
            c1 = [x for x in c1 if x[0] <= got]
            if not c1:
                continue
            ts = day_trades(cx, c1, got, got == CLOSE - 1, ladder)
            last_ts[n] = ts
            for mid, mk, text, push in messages(cx, ts, c1, got, lots):
                if (n, mid) in seen:
                    continue
                seen.add((n, mid))
                if first and mk < got - 1:
                    print('    [earlier today] ' + text)
                else:
                    alert(text, push, kind=kind_of(mid), index=cx['name'])
            last_c[n] = c1
            if CHART:
                chart_update(n, cx, c_all, ts, got, today)
            if shown.get(n) != got:
                shown[n] = got
                print(f"  {hhmm(mnow)} {cx['name']} {f2(c1[-1][4])} (data to {hhmm(c1[-1][0])}) | {open_note(cx, ts)}", flush=True)
        first = False if not late else first
        if mnow >= CLOSE:
            for n in names:
                if n in last_ts:
                    alert(day_summary(cxs[n], last_ts[n], lots), kind='summary', index=cxs[n]['name'])
                    if n in last_c:
                        record_history(cxs[n], last_ts[n], last_c[n], today)
            print("Market closed." + ("" if forever else " Run it again tomorrow before 9:15."))
            if CHART and not forever:
                keep_serving("")
            return
        now = now_ist()
        time.sleep(5 if late else max(2, min(15, 63 - now.second)) if CHART else max(2, 63 - now.second))

def find_chat_id():
    """The chat id of the last message sent to your bot (Telegram keeps them for about a day)."""
    try:
        res = http_json(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates", tries=2)
    except Exception as e:
        print(f"  (Telegram: {e})")
        return None
    ids = [u['message']['chat']['id'] for u in res.get('result', []) if 'message' in u]
    return str(ids[-1]) if ids else None

def telegram_setup():
    """With a token but no chat id: find the chat id and say where to put it."""
    global TELEGRAM_CHAT_ID
    if TELEGRAM_TOKEN and not TELEGRAM_CHAT_ID:
        cid = find_chat_id()
        if cid:
            TELEGRAM_CHAT_ID = cid
            print(f"Telegram chat id: {cid}. Put it at the top of this file: TELEGRAM_CHAT_ID = '{cid}'")
        else:
            print("Telegram: no chat id yet. Send any message to your bot, then start this again.")

class Tee:
    """Everything printed goes to the screen and to the log file."""
    def __init__(self, stream, f):
        self.stream, self.f = stream, f

    def write(self, s):
        self.stream.write(s)
        try:
            self.f.write(('\n' + s[1:]) if s.startswith('\r') else s)
            self.f.flush()
        except Exception:
            pass

    def flush(self):
        self.stream.flush()

    def __getattr__(self, k):
        return getattr(self.stream, k)

def start_log():
    path = os.path.join(DATA_DIR, 'cprb_log.txt')
    try:
        if os.path.exists(path) and os.path.getsize(path) > 2_000_000:
            os.remove(path)
        f = open(path, 'a', encoding='utf-8')
        sys.stdout, sys.stderr = Tee(sys.stdout, f), Tee(sys.stderr, f)
        print(f"\n===== started {now_ist():%Y-%m-%d %H:%M:%S} IST (this log: {path}) =====")
    except Exception as e:
        print(f"(no log file: {e})")

def next_morning():
    """The next weekday at 8:45 IST (the next session's plan is sent then)."""
    now = now_ist()
    t = now.replace(hour=8, minute=45, second=0, microsecond=0)
    while t <= now or t.weekday() >= 5:
        t = (t + dt.timedelta(days=1)).replace(hour=8, minute=45)
    return t

def backfill_history(names):
    """Days after the last one in the history, up to yesterday, that this program didn't run: add their calls. Days
    saved with older targets (T1 / T2 / T3) are worked out again."""
    try:
        if os.path.exists(HISTORY_FILE):
            saved = json.load(open(HISTORY_FILE))
            keep = [r for r in saved if r.get('tv') == TARGETS_V]
            if len(keep) < len(saved):
                with open(HISTORY_FILE, 'w') as f:
                    json.dump(keep, f)
    except Exception as e:
        print(f"  (history targets: {e})")
    have = {r['d'] for r in history_all()['calls']}
    if not have:
        return
    d, today = dt.date.fromisoformat(max(have)) + dt.timedelta(days=1), now_ist().date()
    while d < today and (today - d).days <= 20:
        day = str(d)
        if d.weekday() < 5 and day not in have:
            try:
                cxs = load(names, day)
                tvol = {m: v[4] for m, v in fetch_range(BEES, d, d).get(day, {}).items()}
                for n in names:
                    rows = fetch_range(SPEC[n]['key'], d, d).get(day, {})
                    c_all = [(m,) + tuple(rows[m][:4]) for m in sorted(rows)]
                    if len(c_all) < 300:
                        continue                          # a holiday, or not a full session
                    cx = cxs[n]
                    cx['tvol'] = tvol
                    record_history(cx, day_trades(cx, c_all, CLOSE - 1, True, False), c_all, day)
                print(f"  history: {day} checked")
            except (Exception, SystemExit) as e:
                print(f"  (history for {day} not added: {e})")
        d += dt.timedelta(days=1)

def run_forever(names, lots, ladder):
    """On a server: every trading day, without stopping (starts each weekday at 8:45 IST)."""
    try:
        backfill_history(names)
    except Exception as e:
        print(f"  (history catch-up: {e})")
    while True:
        try:
            live(names, lots, ladder, forever=True)
        except KeyboardInterrupt:
            return
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Stopped by an error: {e}. Starting again in 60 seconds ...", flush=True)
            time.sleep(60)
            continue
        t = next_morning()
        print(f"Next start {t:%a %d %b %H:%M} IST. The chart keeps showing the last session.", flush=True)
        while now_ist() < t:
            time.sleep(60)

if __name__ == '__main__':
    if LOG:
        start_log()
    args = sys.argv[1:]
    names = [a for a in args if a in SPEC] or INDICES
    ladder = LADDER or '--ladder' in args
    lots = int(args[args.index('--lots') + 1]) if '--lots' in args else LOTS
    if not TELEGRAM_TOKEN and ('--telegram-test' in args or '--telegram-chat-id' in args):
        raise SystemExit("Put your bot's token in TELEGRAM_TOKEN at the top of this file first (see the guide).")
    telegram_setup()
    if '--replay' in args or REPLAY_DAY:
        replay(names, args[args.index('--replay') + 1] if '--replay' in args else REPLAY_DAY, lots, ladder)
    elif '--telegram-test' in args:
        if telegram("Test from cprb_alerts.py: alerts will arrive here."):
            print("Sent: check Telegram.")
        else:
            print("Telegram did not take it: check TELEGRAM_TOKEN and TELEGRAM_CHAT_ID (on a server: /etc/cprb.env).")
    elif '--telegram-chat-id' in args:
        pass                                          # telegram_setup() above printed it
    elif '--forever' in args or os.environ.get('CPRB_FOREVER') == '1':
        run_forever(names, lots, ladder)
    else:
        while True:                                   # after an error (no internet, a data problem): start again
            try:
                live(names, lots, ladder, plan_only='--plan' in args)
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Stopped by an error: {e}. Starting again in 60 seconds (press Stop to end) ...", flush=True)
                time.sleep(60)
