#!/usr/bin/env python3
"""CPR Breakout alerts for Nifty and Sensex: live, free, no TradingView and no login needed.

Follows the same rules as tradingview/cpr_breakout.pine (its default settings) on live 1-minute candles from
Upstox's free public candle data. It tells you when to BUY (a call) or SELL (a put), where the stop and the target
are and when to exit: on this screen, and on your phone through Telegram if you set that up (free).
Default rules ('classic'): the daily plan (CPR Magnet at 9:16 or the 9:30 breakout) and the 3-day volume lines, one
trade at a time, set differently for each index (the most profit in the 2026 tests); and, as their own trades, the
extra calls that made money (CPR BREAK on both; OPEN HIGH LOW on Nifty; GAP FILL, SECOND CHANCE and OI WALL on Sensex):
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
import collections
import csv
import datetime as dt
import io
import json
import math
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile

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
STOP_MAX = {'nifty': 55, 'sensex': 170}   # 'classic' rules: the most a stop may be from entry, in index points
                                  # (0 = each setup's own stop: 0.3% Magnet, the 15-minute range, the previous line).
                                  # 2023-2026: 95% of the calls that reached T1 came back less than 55 Nifty / 171
                                  # Sensex points first (research/quant/mae_study.py)
STOP_MODE = 'stop'                # a wider stop is: 'pull' moved in (book half / trail scaled to the new stop),
                                  # 'stop' moved in (book half / trail as before), 'skip' not traded
POC_DAYS = {'nifty': 1, 'sensex': 0}    # the volume POC filter (buys only above it, sells only below) from the
                                  # last N sessions' volume (1 = yesterday's); 0 = no POC filter. 2026 tests
                                  # (research/quant/y2026_pocdays.py): Nifty made the most with yesterday's POC and no
                                  # volume check, Sensex with the volume check and no POC filter
CPR_CALLS = True                  # 'classic' rules: also the CPR BREAK calls: the first touch of the CPR top (BUY) /
                                  # bottom (SELL), 9:16-2:30, when one of four things holds (cpr_conditions()); a
                                  # fixed target and stop, out by 3:15; their own trades, one at a time (one may be
                                  # open together with another call). 2023-2026 they made money in every year on
                                  # both indices, winning 34-46% of the time (research/quant/cpr_plus.py)
OHL_CALLS = {'nifty': True, 'sensex': False}   # OPEN HIGH LOW calls (ohl_trades()): the first 15 minutes never
                                  # above the open -> SELL at 9:30 (never below -> BUY), stop just beyond the open,
                                  # target 1x the stop. Nifty 2024 / 2025 / 2026 +138 / +188 / +445 (won 54-64%),
                                  # 2023 -74 (research/quant/classic_setups.py)
GAPFILL_CALLS = {'nifty': False, 'sensex': True}   # GAP FILL calls (gapfill_trades()): a gap of 0.5-1.5% and a first
                                  # 5 minutes that closed back against it -> toward the gap's fill, half way to
                                  # yesterday's close. Sensex 2024 / 2025 / 2026 +190 / +1,278 / +611 (won 50-61%),
                                  # 2023 -514 (classic_setups.py)
REENTRY_CALLS = {'nifty': False, 'sensex': True}   # SECOND CHANCE calls (reentry_trades()): after a call is stopped
                                  # out, the day turns that call's way (a 5-minute close beyond both the open and the
                                  # CPR) -> a limit order back at the broken CPR edge, stop REENTRY_STOP points, held
                                  # to 3:15. Sensex 2023-2026 +865 / +298 / +1,725 / +371 (won 36-56%); on Nifty no
                                  # version made money every year (research/quant/reentry.py)
REENTRY_STOP = 170
OIWALL_CALLS = {'nifty': False, 'sensex': True}   # OI WALL calls (oiwall_trades()): yesterday's strike with the most call
                                  # open interest (the call wall) and with the most put OI (the put wall), nearest
                                  # expiry (the exchange's F&O bhavcopy, oi_walls()); a 5-minute candle reaches the call
                                  # wall from below and closes back under it -> SELL at its close (the put wall from
                                  # above and back over it -> BUY), 9:20-2:30, not against today's CPR vs yesterday's;
                                  # stop at that candle's high (low), at most OIWALL_STOP; target 2x the stop; out by
                                  # 3:15; each wall once a day. Sensex 2024 / 2025 / 2026 +464 / +401 / +406 (won 46%;
                                  # no Sensex OI before 2024); on Nifty it lost (research/quant/oi_test.py)
OIWALL_STOP = 170
EXTRA_SRC = ('CPR BREAK', 'OPEN HIGH LOW', 'GAP FILL', 'SECOND CHANCE', 'OI WALL')   # their own trades, next to the others
CPR_TP = {'nifty': 60, 'sensex': 200}   # the CPR BREAK calls' target and stop, index points
CPR_SL = {'nifty': 35, 'sensex': 100}
REV_CHANCE = {'nifty': (34, 29, 22), 'sensex': (31, 28, 20)}   # on a trending day (price below both the day's open
                                  # and the CPR, or above both) a trade against the move reached CPR_TP before CPR_SL
                                  # against it on this % of the moments, 2023-2026, before 10:30 / 10:30-12:30 /
                                  # after 12:30; break-even 41% / 37%; no reversal sign changed that
                                  # (research/quant/reversal_odds.py). The chart, the app and an alert say so
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
LIVE_PRICE = True                 # the chart's price every second (Groww's public data), not just whole minutes;
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
    """Every second in market hours: each index's last price, from Groww's public data. It draws the minute still
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
            time.sleep(1 if fails < 10 else 30)       # the source is down: look again less often
    LIVE_THREAD.append(threading.Thread(target=run, daemon=True))
    LIVE_THREAD[0].start()

# ---------------- the option chain (current expiry) and option charts, for the Options screen ----------------
OPT_IDS = {'nifty': 'nifty', 'sensex': 'sp-bse-sensex'}     # Groww's names for the indices
OPT_URL = 'https://groww.in/v1/api/option_chain_service/v1/option_chain/derivatives/{}'
OPT_STRIKES = 12                  # strikes shown each side of the at-the-money one
OPT = {}                          # index -> (time.time(), the chain as the screen shows it)
OPT_BARS = {}                     # (exchange, token) -> {'day', 'bars': {minute: [o, h, l, c]}} from the live prices
OPT_CANDLES = {}                  # (exchange, token) -> (time.time(), day, [[minute, o, h, l, c]]) from Upstox
OPT_CPR = {}                      # (exchange, token, day) -> the option's CPR from its previous day
OPT_LOCK = threading.Lock()
OPT_COST = {'nifty': 2.0, 'sensex': 5.0}   # the indicator's calls on option charts: costs in premium points
OPT_CX = {}                       # (exchange, token, day) -> the indicator's context on that option's chart (None: too new)
OPT_SIG = {}                      # (exchange, token) -> (day, data to minute, the indicator's calls on it that day)
OPT_VOL = {}                      # day -> NIFTYBEES volume of the sessions before it
OPT_SIG_LOCK = threading.Lock()   # day_trades() writes into the context: one at a time

def groww_json(url):
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.load(r)

def option_chain(n, fresh=3.0):
    """The current expiry's calls and puts around the at-the-money strike, live (Groww's public data, at most `fresh`
    seconds old). Each price also builds that contract's minute still forming, for its chart."""
    with OPT_LOCK:
        c = OPT.get(n)
        if c and time.time() - c[0] < fresh:
            return c[1]
    d = groww_json(OPT_URL.format(OPT_IDS[n]))
    lp, oc = d.get('livePrice') or {}, d['optionChain']
    spot = float(lp.get('value') or 0)
    ts = float(lp.get('tsInMillis') or 0)
    ts = ts / 1000 if ts > 1e11 else ts
    ex = SPEC[n]['live'][0]
    rows = sorted(((r['callOption']['strikePrice'] / 100, r.get('callOption') or {}, r.get('putOption') or {})
                   for r in oc['optionChains'] if r.get('callOption')), key=lambda x: x[0])
    if not rows:
        raise ValueError('no option chain')
    atm = min(range(len(rows)), key=lambda i: abs(rows[i][0] - spot))
    now = now_ist()
    day, m = str(now.date()), now.hour * 60 + now.minute
    live = bool(ts) and abs(time.time() - ts) < 120 and OPEN <= m < CLOSE and now.weekday() < 5
    def side(o):
        if not o:
            return None
        t, ltp = str(o.get('token') or ''), float(o.get('ltp') or 0)
        if live and t and ltp > 0:
            with OPT_LOCK:
                B = OPT_BARS.get((ex, t))
                if not B or B['day'] != day:
                    B = OPT_BARS[(ex, t)] = dict(day=day, bars={})
                b = B['bars'].get(m)
                if b:
                    b[1], b[2], b[3] = max(b[1], ltp), min(b[2], ltp), ltp
                else:
                    B['bars'][m] = [ltp, ltp, ltp, ltp]
                for k in [k for k in B['bars'] if k < m - 15]:
                    del B['bars'][k]
        oi = o.get('openInterest') or 0
        return dict(t=t, name=o.get('longDisplayName', ''), ltp=ltp, chg=round(float(o.get('dayChange') or 0), 2),
                    pct=round(float(o.get('dayChangePerc') or 0), 1), oi=oi, doi=oi - (o.get('prevOpenInterest') or 0),
                    vol=o.get('volume') or 0)
    coi = sum(ce.get('openInterest') or 0 for k, ce, pe in rows)
    poi = sum(pe.get('openInterest') or 0 for k, ce, pe in rows)
    out = dict(name=SPEC[n]['name'], ex=ex, spot=spot, live=live, lot=SPEC[n]['lot'],
               chg=round(float(lp.get('dayChange') or 0), 2), pct=round(float(lp.get('dayChangePerc') or 0), 2),
               at=dt.datetime.fromtimestamp(ts, IST).strftime('%H:%M:%S') if ts else '',
               expiry=(oc.get('expiryDetailsDto') or {}).get('currentExpiry'),
               pcr=round(poi / coi, 2) if coi else None,
               res=max(rows, key=lambda r: r[1].get('openInterest') or 0)[0],     # the most call OI: resistance
               sup=max(rows, key=lambda r: r[2].get('openInterest') or 0)[0],     # the most put OI: support
               rows=[dict(k=k, atm=i == atm, ce=side(ce), pe=side(pe)) for i, (k, ce, pe) in enumerate(rows)
                     if abs(i - atm) <= OPT_STRIKES])
    with OPT_LOCK:
        OPT[n] = (time.time(), out)
    return out

OI_DIR = os.path.join(DATA_DIR, 'oi')    # the option chain every minute, for testing open-interest rules later
OI_THREAD = []

def oi_recorder(names):
    """In market hours, once a minute: each index's option chain around the money (strike, call OI / price, put OI /
    price) to oi/<day>-<index>.jsonl. Free intraday open-interest history doesn't exist for past days, so this builds
    it from now on (about 1 MB a day)."""
    if OI_THREAD:
        return
    def run():
        last = {}
        while True:
            now = now_ist()
            m = now.hour * 60 + now.minute
            if now.weekday() < 5 and OPEN <= m < CLOSE:
                for n in names:
                    if last.get(n) == (now.date(), m) or n not in OPT_IDS:
                        continue
                    try:
                        ch = option_chain(n, fresh=20)
                        if not ch.get('live'):
                            continue
                        os.makedirs(OI_DIR, exist_ok=True)
                        row = dict(m=m, spot=ch['spot'], pcr=ch['pcr'], res=ch['res'], sup=ch['sup'], expiry=ch['expiry'],
                                   k=[[r['k'], (r['ce'] or {}).get('oi'), (r['ce'] or {}).get('ltp'), (r['pe'] or {}).get('oi'),
                                       (r['pe'] or {}).get('ltp')] for r in ch['rows']])
                        with open(os.path.join(OI_DIR, f"{now.date()}-{n}.jsonl"), 'a') as f:
                            f.write(json.dumps(row, separators=(',', ':')) + '\n')
                        last[n] = (now.date(), m)
                    except Exception:
                        pass
            time.sleep(max(5, 62 - now_ist().second))
    OI_THREAD.append(threading.Thread(target=run, daemon=True))
    OI_THREAD[0].start()

def option_chart(ex, t, fresh=20.0):
    """One option contract: today's 1-minute candles (Upstox, complete minutes; the last session's before the open),
    the minutes after them from the live prices, and the option's CPR from its previous day."""
    key, now = (ex, t), time.time()
    with OPT_LOCK:
        c = OPT_CANDLES.get(key)
    if not c or now - c[0] > fresh:
        ik = f"{ex}_FO|{t}"
        rows = fetch_today(ik)
        if not rows:
            d0 = now_ist().date()
            rows = fetch_range(ik, d0 - dt.timedelta(days=7), d0 - dt.timedelta(days=1))
        day = max(rows) if rows else str(now_ist().date())
        mm = rows.get(day, {})
        c = (now, day, [[m] + list(mm[m][:4]) for m in sorted(mm)])
        with OPT_LOCK:
            OPT_CANDLES[key] = c
            for k in [k for k in OPT_CANDLES if now - OPT_CANDLES[k][0] > 3600]:
                del OPT_CANDLES[k]
    _, day, cs = c
    with OPT_LOCK:
        B = OPT_BARS.get(key)
        last = cs[-1][0] if cs else OPEN - 1
        live = [[m] + list(b) for m, b in sorted(B['bars'].items()) if m > last] if B and B['day'] == day else []
    ck = (ex, t, day)
    if ck not in OPT_CPR:
        try:
            d0 = dt.date.fromisoformat(day)
            daily = fetch_daily(f"{ex}_FO|{t}", d0 - dt.timedelta(days=10), d0 - dt.timedelta(days=1))
            if daily:
                h, l, cl = daily[max(daily)][1:]
                lv = levels(h, l, cl)
                OPT_CPR[ck] = dict(top=round(lv['top'], 2), p=round(lv['p'], 2), bot=round(lv['bot'], 2), yh=h, yl=l)
            else:
                OPT_CPR[ck] = None
        except Exception:
            pass                                      # no CPR this time; asked again with the next chart
    cp = OPT_CPR.get(ck)
    lines = [] if not cp else [dict(p=cp['top'], c='#e91e63', t='CPR top', w=2, s=0), dict(p=cp['p'], c='#e91e63', t='Pivot', w=1, s=0),
                               dict(p=cp['bot'], c='#e91e63', t='CPR bottom', w=2, s=0),
                               dict(p=cp['yh'], c='#f9a825', t='Yesterday high', w=1, s=2), dict(p=cp['yl'], c='#f9a825', t='Yesterday low', w=1, s=2)] + \
        pivot_lines(cp['p'], cp['yh'], cp['yl'])
    n = 'nifty' if ex == 'NSE' else 'sensex'
    today = now_ist()
    comp = [r for r in cs if day != str(today.date()) or r[0] < today.hour * 60 + today.minute]   # complete minutes
    try:
        ts = option_trades(n, ex, t, day, comp)
    except Exception:
        ts = (OPT_SIG.get(key) or (None, None, []))[2]
    ocx = OPT_CX.get((ex, t, day))
    marks, boxes, rows, last = [], [], [], None
    for x in ts:
        sd, out = x['side'], x['exit']
        m0 = x['m'] - 1 if x['src'] == 'VOLUME LINE' else 555 if x['src'] == 'MAGNET' else x['m']
        marks.append(dict(m=m0, pos='belowBar' if sd > 0 else 'aboveBar', c='#089981' if sd > 0 else '#f23645', x='BUY' if sd > 0 else 'SELL'))
        if out:
            k = mark_of(out['why'])
            marks.append(dict(m=out['m'], pos=('belowBar' if sd > 0 else 'aboveBar') if k in ('SL', 'BE') else ('aboveBar' if sd > 0 else 'belowBar'),
                              c='#9e9e9e' if k == 'BE' else '#089981' if out['pnl'] > 0 else '#f23645', x=k))
        if ocx:                                   # drawn like TradingView's long / short position tool, as on the index chart
            boxes.append(dict(m0=m0, m1=out['m'] if out else None, side=sd, e=round(x['e'], 2), sl=round(x['stp0'], 2),
                              sl_now=round(x['stp'], 2), t=target_levels(ocx, comp, sd, x['e'], x['known'], half_price(x)),
                              t1w=t1_word(x), pnl=round(out['pnl'], 1) if out else None, prob=None))
        rows.append([hhmm(m0 + (1 if x['src'] == 'VOLUME LINE' else 0)), ('BUY ' if sd > 0 else 'SELL ') + x['src'].lower(), f2(x['e']),
                     f2(x['stp0']), f"{out['why']} at {f2(out['px'])}: {out['pnl']:+.1f} pts" if out else f"open, stop now {f2(x['stp'])}"])
        last = dict(side='BUY' if sd > 0 else 'SELL', time=hhmm(x['m']), e=round(x['e'], 2), src=x['src'].lower(),
                    stop=round(x['stp'], 2), why=out['why'] if out else None, px=round(out['px'], 2) if out else None,
                    pnl=round(out['pnl'], 1) if out else None)
    info = []
    if ocx:
        lv, done_ = ocx['lv'], [x for x in ts if x['exit']]
        first = [r for r in comp if r[0] < RANGE_END]
        won = [x['exit']['pnl'] for x in done_ if x['exit']['pnl'] > 0]
        lost = [x['exit']['pnl'] for x in done_ if x['exit']['pnl'] <= 0]
        rng = first and comp[-1][0] >= RANGE_END - 1
        info = [["Today's CPR", f"{f2(lv['bot'])} - {f2(lv['top'])}, {lv['top'] - lv['bot']:.1f} pts " + ('NARROW' if ocx['narrow'] else 'wide')],
                ['Bias', 'up: no breakout SELLs' if ocx['rel'] > 0 else 'down: no breakout BUYs' if ocx['rel'] < 0 else 'both ways'],
                ['15-minute range', f"{f2(min(r[3] for r in first))} - {f2(max(r[2] for r in first))}" if rng else 'forming'],
                ['Volume POC / value area', f"{f2(ocx['poc'])} / {f2(ocx['val'])} - {f2(ocx['vah'])}" if ocx['poc'] is not None else '-'],
                ['Today', open_note(ocx, ts)],
                ['On this chart', f"{len(done_)} trade{'' if len(done_) == 1 else 's'}, {len(won)} won, {len(lost)} lost"],
                ['Points won / lost / net', f"+{sum(won):.1f} / {sum(lost):.1f} / {sum(won) + sum(lost):+.1f}"]]
        if rng:
            lines = lines + [dict(p=max(r[2] for r in first), c='#4caf50', t='15-min high', w=1, s=2),
                             dict(p=min(r[3] for r in first), c='#f44336', t='15-min low', w=1, s=2)]
    if ocx:                                       # its POC and the volume lines nearest the price (3 above, 3 below)
        px = (cs + live)[-1][4] if cs or live else ocx['yc']
        near = sorted(x for x in ocx['lines'] if x > px)[:3] + sorted(x for x in ocx['lines'] if x <= px)[-3:]
        lines = lines + ([dict(p=ocx['poc'], c='#9c6ade', t='POC yesterday', w=1, s=0)] if ocx['poc'] is not None else []) + \
            [dict(p=x, c='#26a69a', t='Vol line', w=1, s=1) for x in near]
    if last and last['why'] is None:
        lines = lines + [dict(p=last['e'], c='#2962ff', t=last['side'], w=1, s=0), dict(p=last['stop'], c='#f23645', t='SL', w=1, s=2),
                         dict(p=round(half_price(ts[-1]), 2), c='#089981', t='T1', w=1, s=2)]
    return dict(day=day, candles=cs + live, cpr=cp, lines=lines, marks=sorted(marks, key=lambda k: k['m']), last=last,
                boxes=boxes, rows=rows, info=info)

def option_cx(n, ex, t, day):
    """The indicator's context on one option's chart for `day`, as TradingView runs it there (an option's price is under
    50,000, so the Nifty settings: yesterday's POC, no volume check, stops at most 55 points): the CPR from the option's
    previous daily candle, the POC and the 3-day volume lines from its 1-minute candles with NIFTYBEES volume (as
    research/quant/option_flip.py tests it). None when the contract has fewer than 3 earlier sessions."""
    ck = (ex, t, day)
    if ck in OPT_CX:
        return OPT_CX[ck]
    ik, d0 = f"{ex}_FO|{t}", dt.date.fromisoformat(day)
    raw = fetch_range(ik, d0 - dt.timedelta(days=12), d0 - dt.timedelta(days=1))
    sess = {d: [(m,) + tuple(mm[m][:4]) for m in sorted(mm)] for d, mm in raw.items()}
    days = sorted(d for d in sess if d < day and len(sess[d]) >= 100)
    if len(days) < 3:
        OPT_CX[ck] = None
        return None
    if day not in OPT_VOL:
        bees = fetch_range(BEES, d0 - dt.timedelta(days=12), d0 - dt.timedelta(days=1))
        OPT_VOL[day] = {d: {m: v[4] for m, v in mm.items()} for d, mm in bees.items()}
    vol = OPT_VOL[day]
    D = {d: (sess[d][0][1], max(x[2] for x in sess[d]), min(x[3] for x in sess[d]), sess[d][-1][4]) for d in days}
    D.update({d: r for d, r in fetch_daily(ik, d0 - dt.timedelta(days=45), d0 - dt.timedelta(days=1)).items() if d < day})
    dd = sorted(D)
    prev = dd[-1]
    lv = levels(*D[prev][1:])
    past = [levels(*D[d][1:])['w'] for d in dd[-21:-1]]
    ylv = levels(*D[dd[-2]][1:])
    spec = SPEC['nifty']
    H = {d: day_hist(sess[d], vol.get(d, {}), spec['bin']) for d in days[-3:]}
    poc, vah, val = poc_va(*combine([H[days[-1]]]), spec['bin'])
    rank = sum(w < lv['w'] for w in past) / len(past) if len(past) >= 5 else 0.5
    cx = dict(spec, key=ik, cost=OPT_COST[n], lot=SPEC[n]['lot'], option=True, today=day, prev=prev, lv=lv, rank=rank,
              narrow=rank < 1 / 3, rel=1 if lv['bot'] > ylv['top'] else -1 if lv['top'] < ylv['bot'] else 0,
              yc=D[prev][3], yh=D[prev][1], yl=D[prev][2], poc=poc, vah=vah, val=val, pocn=1,
              yday=sess.get(prev) or sess[days[-1]], yvol=vol.get(prev, {}), c5h=closes5(sess, days[-3:]),
              lines=vol_lines(*combine([H[d] for d in days[-3:]]), spec['bin']), tvol={})
    OPT_CX[ck] = cx
    for k in [k for k in OPT_CX if k[2] != day]:
        del OPT_CX[k]
    return cx

def option_trades(n, ex, t, day, c1):
    """The indicator's calls on one option's chart (the original calls: CPR Magnet, the 15-minute breakout, the volume
    lines; one at a time) from its complete 1-minute candles c1, worked out once a minute."""
    if not c1:
        return []
    key, upto = (ex, t), c1[-1][0]
    c = OPT_SIG.get(key)
    if c and c[0] == day and c[1] == upto:
        return c[2]
    cx = option_cx(n, ex, t, day)
    if not cx:
        return []
    with OPT_SIG_LOCK:
        ts = [x for x in day_trades(cx, [tuple(r) for r in c1], upto, upto >= CLOSE - 1)
              if x['taken'] and x['src'] not in EXTRA_SRC]
    OPT_SIG[key] = (day, upto, ts)
    return ts

OPTSIG_THREAD = []
def option_alerts(names):
    """In market hours, once a minute: the indicator's calls on each index's at-the-money and one-strike-out call and
    put. A new SELL on one -> an alert to buy the other side (a new BUY -> to buy that side), naming the at-the-money
    and the one-strike-out contract with their prices; when that call's trade ends, an EXIT alert. Kind 'option': the
    app shows them only while 'Option alerts' is on (app_settings()). One alert at a time for each side of an index."""
    if OPTSIG_THREAD:
        return
    def run():
        day0 = str(now_ist().date())
        sent = {e['oid'] for e in EVENTS if e.get('oid') and str(e.get('at', '')).startswith(day0)}
        ended = {e['oid'] for e in EVENTS if e.get('oid') and e.get('exit')}
        open_ = {e['oid']: e['opt'] for e in EVENTS if e.get('opt') and e['oid'] not in ended and
                 str(e.get('at', '')).startswith(day0)}       # alerted calls still open (after a restart too)
        while True:
            now = now_ist()
            m, day = now.hour * 60 + now.minute, str(now.date())
            if now.weekday() < 5 and OPEN + 1 <= m <= CLOSE:
                for n in names:
                    try:
                        option_alert_pass(n, day, m, sent, open_)
                    except Exception as e:
                        print(f"  (option alerts, {n}: {e})")
            time.sleep(((80 - now_ist().second) % 60) or 60)    # 20 seconds into each minute: its candle is in
    OPTSIG_THREAD.append(threading.Thread(target=run, daemon=True))
    OPTSIG_THREAD[0].start()

def option_alert_pass(n, day, m, sent, open_):
    ch = option_chain(n, fresh=20)
    if not ch.get('live'):
        return
    ex, step, nm = ch['ex'], SPEC[n]['step'], SPEC[n]['name']
    k0 = round(ch['spot'] / step) * step
    rows = {r['k']: r for r in ch['rows']}
    def contract(k, typ):
        o = (rows.get(k) or {}).get(typ.lower())
        return o if o and o.get('t') else None
    now4 = [(k0, 'CE'), (k0 + step, 'CE'), (k0, 'PE'), (k0 - step, 'PE')]
    watch = {kt: (contract(*kt) or {}).get('t') for kt in now4}
    for a in open_.values():
        if a['n'] == n:
            watch[(a['k'], a['typ'])] = a['t']
    for (k, typ), t in watch.items():
        if not t:
            continue
        mm = fetch_today(f"{ex}_FO|{t}").get(day, {})
        c1 = [(x,) + tuple(mm[x][:4]) for x in sorted(mm) if x < m]
        if not c1:
            continue
        for tr in option_trades(n, ex, t, day, c1):
            oid = f"{day}|{ex}|{t}|{tr['src']}|{tr['m']}"
            sd, out = tr['side'], tr['exit']
            sig = 'BUY' if sd > 0 else 'SELL'
            if oid in open_ and out:
                a = open_.pop(oid)
                word = 'CALL' if a['buy'] == 'CE' else 'PUT'
                record_event(f"{nm} EXIT {word}: {hhmm(out['m'])} the {k:,.0f} {typ} {sig} trade ended ({out['why']} at "
                             f"{out['px']:,.2f}) -> sell the {word.lower()} bought on the {hhmm(a['m'])} alert.",
                             'option', nm, title=f"{nm} EXIT {word} ({out['why']})", oid=oid, exit=True)
                continue
            if oid in sent:
                continue
            sent.add(oid)
            if out or tr['known'] < m - 3 or (k, typ) not in now4:
                continue                              # an earlier call (before this strike was watched) or not ATM now
            buy = typ if sd > 0 else 'PE' if typ == 'CE' else 'CE'
            if any(a['n'] == n and a['buy'] == buy for a in open_.values()):
                continue                              # already told to buy this side; that call is still open
            word, ko = ('CALL', k0 + step) if buy == 'CE' else ('PUT', k0 - step)
            px = lambda k_: f"{contract(k_, buy)['ltp']:,.2f}" if contract(k_, buy) else '-'
            why = 'the other side' if sd < 0 else 'this side'
            record_event(f"{nm} BUY {word}: {k0:,.0f} {buy} at the money ({px(k0)}) or {ko:,.0f} {buy} one strike out "
                         f"({px(ko)}). {hhmm(tr['m'])} {sig} on the {k:,.0f} {typ} chart at {tr['e']:,.2f} "
                         f"({tr['src'].lower()}, its stop {tr['stp0']:,.2f}) -> buy {why}. Out when that trade ends: an "
                         f"EXIT alert follows. These win about 4 in 10; most of the profit came on a few trend days.",
                         'option', nm, title=f"{nm} BUY {word} {k0:,.0f} / {ko:,.0f} {buy}", oid=oid,
                         opt=dict(n=n, k=k, typ=typ, t=t, buy=buy, m=tr['m']))
            open_[oid] = dict(n=n, k=k, typ=typ, t=t, buy=buy, m=tr['m'])

def pivot_lines(P, H, L):
    """The floor pivots around the CPR's pivot P from yesterday's high H / low L, as chart lines (orange)."""
    return [dict(p=round(p, 2), c='#ff9800', t=t, w=1, s=0)
            for t, p in (('R1', 2 * P - L), ('S1', 2 * P - H), ('R2', P + (H - L)), ('S2', P - (H - L)))]

def index_chart(n):
    """The index for the Options screen: today's candles and live minutes (as the chart page), its CPR, pivots
    R1 / S1 / R2 / S2, yesterday's high / low, the 15-minute range, the POC, and the strikes with the most call / put
    open interest."""
    d = CHART_DATA.get(n) or {}
    if d.get('candles'):
        lp = live_part(n, d)
        last = d['candles'][-1][0]
        day, cs = d.get('day'), d['candles'] + ([b for b in lp['bars'] if b[0] > last] if lp else [])
    elif d.get('yday'):                           # before the open: yesterday's session, with today's levels
        day, cs = d.get('yday_date'), d['yday']
    else:
        return dict(error='no chart data yet')
    keep = ('CPR top', 'Pivot', 'CPR bottom', 'Yesterday high', 'Yesterday low', '15-min high', '15-min low', 'Vol line',
            'R1', 'S1', 'R2', 'S2')
    lines = [dict(p=l['p'], c=l['c'], t=l['t'], w=l['w'], s=l['s']) for l in d.get('levels', []) if l['t'] in keep or l['t'].startswith('POC')]
    try:
        ch = option_chain(n)
        lines += [dict(p=ch['res'], c='#ef5350', t='Call OI wall', w=1, s=1), dict(p=ch['sup'], c='#26a69a', t='Put OI wall', w=1, s=1)]
    except Exception:
        pass
    today = day == d.get('day')
    return dict(day=day, candles=cs, lines=lines, marks=d.get('marks', []) if today else [], boxes=d.get('boxes', []) if today else [],
                rows=d.get('rows', []) if today else [], info=d.get('info', []))

def live_now(n, fresh=20):
    """(price, 'hh:mm:ss') if the live price is recent, else None."""
    with LIVE_LOCK:
        L = LIVE.get(n)
        if not L or 'px' not in L or time.time() - L['at'] > fresh or L['day'] != str(now_ist().date()):
            return None
        return L['px'], dt.datetime.fromtimestamp(L['at'], IST).strftime('%H:%M:%S')

def live_part(n, d):
    """The live price and the live minutes after the last 1-minute candle (the chart draws them until the candle
    arrives), or None."""
    lv = live_now(n)
    if not lv or d.get('day') != str(now_ist().date()):
        return None
    with LIVE_LOCK:
        bars = sorted(LIVE[n]['bars'].items())
    last = d['candles'][-1][0] if d.get('candles') else OPEN - 1
    return dict(px=lv[0], at=lv[1], bars=[[m] + list(b) for m, b in bars if last < m < CLOSE])

def with_live(n, d):
    """The chart data plus its live part."""
    return dict(d, live=live_part(n, d)) if d else d

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
                poc_ref=poc_va(*combine([H[days[-1]]]), spec['bin'])[0],
                yvol=vol.get(days[-1], {}), c5h=closes5(sess, days[-3:]),
                lines=vol_lines(*combine([H[d] for d in days[-3:]]), spec['bin']))

def closes5(sess, days):
    """The closes of these sessions' 5-minute candles, oldest first (the start of the CPR BREAK calls' RSI)."""
    return [c for d in days for m0, o, h, l, c in candles5(sess[d], CLOSE)]

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
def rsi(closes, k=14):
    """RSI (Wilder) at the last close."""
    ag = al = 0.0
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        g, l_ = max(ch, 0), max(-ch, 0)
        if i <= k:
            ag, al = ag + g / k, al + l_ / k
        else:
            ag, al = (ag * (k - 1) + g) / k, (al * (k - 1) + l_) / k
    return 100 - 100 / (1 + ag / al) if al > 0 else 100.0

def cpr_conditions(cx, c1, side, m, e):
    """Which of the four conditions a touch of the CPR at minute m (price e) meets; none = no call. Each made money in
    every year 2023-2025 on both indices (research/quant/cpr_confluence.py)."""
    lv, out = cx['lv'], []
    if cx['rel'] == 0:
        out.append("today's CPR overlaps yesterday's")
    if 600 <= m < 690:
        out.append('the touch is between 10:00 and 11:30')
    if side * (c1[0][1] - (lv['top'] if side > 0 else lv['bot'])) > 0:
        s = OPEN + (m - OPEN) // 5 * 5 - 5            # the last 5-minute candle complete before this one began
        r = rsi(cx.get('c5h', []) + [x[4] for x in candles5(c1, s + 4)])
        if side * (r - 50) > 5:
            out.append(f"the day opened {'above' if side > 0 else 'below'} the CPR, came back into it and broke out again "
                       f"with RSI {r:.0f}")
    if m >= RANGE_END:
        first = [x for x in c1 if x[0] < RANGE_END]
        if first and ((e <= max(x[2] for x in first)) if side > 0 else (e >= min(x[3] for x in first))):
            out.append('price is still inside the 15-minute range')
    return out

def cpr_trades(cx, c1, upto, over):
    """CPR BREAK calls: the first 1-minute touch of the CPR top from below (BUY) / of its bottom from above (SELL), each
    once a day, 9:16-2:30, when cpr_conditions() finds one; entry at the close of that candle, target CPR_TP / stop
    CPR_SL points, out by 3:15. One at a time, apart from the other calls. Touches without a condition:
    cx['cpr_none']."""
    nm = cx['name'].lower()
    tp, sl = CPR_TP.get(nm), CPR_SL.get(nm)
    cx['cpr_none'] = []
    if not (tp and sl):
        return []
    top, bot = cx['lv']['top'], cx['lv']['bot']
    out, seen, free = [], set(), 0
    for i in range(1, len(c1)):
        m, o, h, l, c = c1[i]
        if m < 556 or m > min(VOL_END, upto):
            continue
        pc = c1[i - 1][4]
        for side, hit in ((1, pc < top <= h), (-1, pc > bot >= l)):
            if side in seen or not hit:
                continue
            seen.add(side)
            why = cpr_conditions(cx, c1, side, m, c)
            if not why:
                cx['cpr_none'].append((m, side, c))
                continue
            stp, tgt = c - side * sl, c + side * tp
            r = run_fixed(c1, side, c, m + 1, stp, tgt, OUT, over, cx['cost'])
            t = dict(src='CPR BREAK', side=side, m=m, known=m + 1, e=c, stp0=stp, tgt=tgt, why=why, full=False,
                     taken=m >= free, **r)
            if t['taken']:
                free = r['exit']['m'] + 1 if r['exit'] else 10 ** 9
            out.append(t)
    return out

def ohl_trades(cx, c1, upto, over):
    """OPEN HIGH LOW: the first 15 minutes never traded above the open (by more than 0.02%) -> SELL at the close of
    the 9:29 candle; never below it -> BUY. Stop 0.05% beyond the open (at least 0.1% from the entry, at most
    STOP_MAX); target 1x the stop; out by 3:15."""
    if not OHL_CALLS.get(cx['name'].lower()) or upto < RANGE_END - 1:
        return []
    first = [x for x in c1 if x[0] < RANGE_END]
    if len(first) < 10:
        return []
    o, e = c1[0][1], first[-1][4]
    hi, lo = max(x[2] for x in first), min(x[3] for x in first)
    side = -1 if hi <= o * 1.0002 else 1 if lo >= o * 0.9998 else 0
    if not side:
        return []
    stp = o - side * 0.0005 * o
    if side * (e - stp) < 0.001 * e:
        stp = e - side * 0.001 * e
    cap = stop_max(cx)
    if cap and side * (e - stp) > cap:
        stp = e - side * cap
    tgt = e + side * side * (e - stp)
    r = run_fixed(c1, side, e, RANGE_END, stp, tgt, OUT, over, cx['cost'])
    return [dict(src='OPEN HIGH LOW', side=side, m=RANGE_END - 1, known=RANGE_END, e=e, stp0=stp, tgt=tgt, o=o,
                 full=False, taken=True, **r)]

def gapfill_trades(cx, c1, upto, over):
    """GAP FILL: the open 0.5-1.5% away from yesterday's close and the first 5-minute candle closed back against the
    gap -> that way at its close; stop 0.05% beyond that candle's high (low), at most STOP_MAX; target half way to
    yesterday's close; out by 3:15."""
    if not GAPFILL_CALLS.get(cx['name'].lower()) or upto < OPEN + 4 or not c1:
        return []
    b = candles5(c1, upto)[0]
    o0, yc = c1[0][1], cx['yc']
    g = (o0 - yc) / yc * 100
    side = -1 if g > 0 else 1
    if not 0.5 <= abs(g) <= 1.5 or side * (b[4] - b[1]) <= 0 or side * (yc - b[4]) <= 0:
        return []
    e, ext = b[4], (b[2] if side < 0 else b[3])
    stp = ext - side * 0.0005 * ext
    cap = stop_max(cx)
    if cap and side * (e - stp) > cap:
        stp = e - side * cap
    tgt = e + side * 0.5 * abs(yc - e)
    r = run_fixed(c1, side, e, OPEN + 5, stp, tgt, OUT, over, cx['cost'])
    return [dict(src='GAP FILL', side=side, m=OPEN + 4, known=OPEN + 5, e=e, stp0=stp, tgt=tgt, gap=g, full=False,
                 taken=True, **r)]

def oi_walls(n, prev):
    """(call wall, put wall) from the exchange's F&O bhavcopy of session `prev` (published that evening): the strikes
    with the most call / put open interest in the nearest expiry after it (as research/quant/fetch_pcr.py), or None."""
    ymd = prev.replace('-', '')
    if n == 'nifty':
        url, ref = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip", 'https://www.nseindia.com/'
    else:
        url, ref = f"https://www.bseindia.com/download/Bhavcopy/Derivative/BhavCopy_BSE_FO_0_0_0_{ymd}_F_0000.CSV", 'https://www.bseindia.com/'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                               '(KHTML, like Gecko) Chrome/124.0 Safari/537.36', 'Referer': ref, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    if n == 'nifty':
        z = zipfile.ZipFile(io.BytesIO(raw))
        raw = z.read(z.namelist()[0])
    text = raw.decode('utf-8', 'replace')
    if not text.lstrip().startswith('TradDt'):
        return None
    oi = collections.defaultdict(lambda: collections.defaultdict(float))     # (expiry, CE / PE) -> strike -> OI
    for r in csv.DictReader(io.StringIO(text)):
        if r.get('TckrSymb') == SPEC[n]['name'] and r.get('FinInstrmTp') == 'IDO' and r.get('OptnTp') in ('CE', 'PE'):
            oi[(r['XpryDt'], r['OptnTp'])][float(r['StrkPric'] or 0)] += float(r['OpnIntrst'] or 0)
    tot = {k: sum(v.values()) for k, v in oi.items()}
    exps = sorted({x for x, _ in tot if tot.get((x, 'CE'), 0) > 0 and tot.get((x, 'PE'), 0) > 0})
    if not exps:
        return None
    near = min([x for x in exps if x > prev] or [exps[-1]])
    return tuple(max(oi[(near, k)].items(), key=lambda kv: kv[1])[0] for k in ('CE', 'PE'))

def oiwall_trades(cx, c1, upto, over):
    """OI WALL: a 5-minute candle reaches yesterday's call wall from below and closes back under it -> SELL at its close
    (the put wall from above and back over it -> BUY), 9:20-2:30, not against today's CPR vs yesterday's; stop at that
    candle's high (low), at most OIWALL_STOP; target 2x the stop; out by 3:15. Each wall once a day; one at a time."""
    if not OIWALL_CALLS.get(cx['name'].lower()) or not cx.get('walls') or not c1:
        return []
    out, used, free = [], set(), 0
    b5 = candles5(c1, upto)
    for j in range(1, len(b5)):
        m0, o, h, l, c = b5[j]
        pc = b5[j - 1][4]
        if m0 < OPEN + 5 or m0 + 5 > VOL_END or m0 < free:
            continue
        for w, side in zip(cx['walls'], (-1, 1)):
            if not w or side in used or not ((side < 0 and pc < w <= h and c < w) or (side > 0 and pc > w >= l and c > w)):
                continue
            used.add(side)
            risk = min(OIWALL_STOP, c - l if side > 0 else h - c)
            if side == -cx['rel'] or risk <= 0:
                continue
            stp, tgt = c - side * risk, c + side * 2 * risk
            r = run_fixed(c1, side, c, m0 + 5, stp, tgt, OUT, over, cx['cost'])
            out.append(dict(src='OI WALL', side=side, m=m0 + 5, known=m0 + 5, e=c, stp0=stp, tgt=tgt, wall=w, full=False,
                            taken=True, **r))
            free = r['exit']['m'] + 1 if r['exit'] else 10 ** 9
            break
    return out

def reentry_trades(cx, c1, upto, over, ts):
    """SECOND CHANCE: after a call (not an extra one but CPR BREAK) loses at its stop (before 2:20), the first 5-minute
    close that makes it a trend day that call's way (beyond both the day's open and the CPR, until 2:30) arms a limit
    order back at the CPR edge it broke (SELL: the bottom; BUY: the top), valid until 2:30; stop REENTRY_STOP points;
    held to 3:15. One a day. -> (trades, the armed order or None)."""
    if not REENTRY_CALLS.get(cx['name'].lower()) or not c1:
        return [], None
    o0, top, bot = c1[0][1], cx['lv']['top'], cx['lv']['bot']
    b5 = candles5(c1, upto)
    for t in sorted(ts, key=lambda t: t['m']):
        if (t['src'] in EXTRA_SRC and t['src'] != 'CPR BREAK') or not t['taken'] or not t['exit'] \
                or t['exit']['why'] != 'stop' or t['exit']['m'] >= 860:
            continue
        sd, x0 = t['side'], t['exit']['m']
        conf = next(((s + 5, c) for s, o, h, l, c in b5 if x0 < s + 5 <= VOL_END and
                     ((sd < 0 and c < min(o0, bot)) or (sd > 0 and c > max(o0, top)))), None)
        if not conf:
            continue
        lvl = bot if sd < 0 else top
        fill = next(((m, max(o, lvl) if sd < 0 else min(o, lvl)) for m, o, h, l, c in c1
                     if conf[0] <= m <= VOL_END and ((sd < 0 and h >= lvl) or (sd > 0 and l <= lvl))), None)
        arm = dict(side=sd, m=conf[0], lvl=lvl, call=t, expired=upto >= VOL_END)
        if not fill:
            if upto < VOL_END:
                return [], arm
            continue
        e = fill[1]
        stp = e - sd * REENTRY_STOP
        r = run_fixed(c1, sd, e, fill[0] + 1, stp, e + sd * 10 ** 6, OUT, over, cx['cost'])
        return [dict(src='SECOND CHANCE', side=sd, m=fill[0], known=fill[0] + 1, e=e, stp0=stp, tgt=None, lvl=lvl,
                     call=t, armed=conf[0], full=False, taken=True, **r)], dict(arm, done=True)
    return [], None

def trend_now(cx, c1, upto):
    """The day's trend at the last 5-minute close (from 9:35): falling = below both the day's open and the CPR, rising =
    above both, else none; with how often price reversed from moments like it (REV_CHANCE). None before 9:35."""
    b5 = [b for b in candles5(c1, upto) if b[0] >= RANGE_END] if c1 else []
    if not b5:
        return None
    m, c, o0, lv, nm = b5[-1][0] + 5, b5[-1][4], c1[0][1], cx['lv'], cx['name']
    d = -1 if c < min(o0, lv['bot']) else 1 if c > max(o0, lv['top']) else 0
    if not d:
        return dict(dir=0, m=m, pct=None, short="No clear trend: price is between the day's open and the CPR.",
                    text=f"{nm} {hhmm(m)}: no clear trend (price {f2(c)} is between the day's open {f2(o0)} and the CPR).")
    pct = REV_CHANCE.get(nm.lower(), (None,) * 3)[0 if m < 630 else 1 if m < 750 else 2]
    tp, sl = CPR_TP.get(nm.lower(), 0), CPR_SL.get(nm.lower(), 0)
    word, lvl = ('FALLING', min(o0, lv['bot'])) if d < 0 else ('RISING', max(o0, lv['top']))
    when = 'before 10:30' if m < 630 else 'between 10:30 and 12:30' if m < 750 else 'after 12:30'
    against = 'BUY' if d < 0 else 'SELL'
    short = (f"{word} DAY: no sign of a reversal. Only {pct}% of such moments turned {tp:g} pts the other way before "
             f"{sl:g} more {'down' if d < 0 else 'up'}: don't {against} against it (while {'below' if d < 0 else 'above'} {f2(lvl)}).")
    text = (f"{nm} {hhmm(m)} {word} DAY: price {f2(c)} is {'below' if d < 0 else 'above'} the day's open {f2(o0)} and the CPR "
            f"{f2(lv['bot'] if d < 0 else lv['top'])}. No sign of a reversal: from moments like this ({when}, 2023-2026) price went "
            f"{tp:g} points {'up' if d < 0 else 'down'} before {sl:g} more {'down' if d < 0 else 'up'} only {pct}% of the time; "
            f"trades against the move lost money in every year, and no reversal sign tested (new {'lows' if d < 0 else 'highs'} "
            f"stopping, RSI, volume, support levels, a {'green' if d < 0 else 'red'} candle) changed that. Don't {against} against "
            f"it while price stays {'below' if d < 0 else 'above'} {f2(lvl)}.")
    return dict(dir=d, m=m, pct=pct, short=short, text=text)

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
    if rules == 'classic':
        ts = ts + (cpr_trades(cx, c1, upto, over) if CPR_CALLS else [])
        re, cx['re_arm'] = reentry_trades(cx, c1, upto, over, ts)
        ts = sorted(ts + ohl_trades(cx, c1, upto, over) + gapfill_trades(cx, c1, upto, over) + re +
                    oiwall_trades(cx, c1, upto, over), key=lambda t: t['m'])
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
    if OHL_CALLS.get(nm.lower()):
        out.append(f"OPEN HIGH LOW call at 9:30 (its own trade): if the first 15 minutes never trade above the open -> SELL, "
                   "never below it -> BUY; stop just beyond the open, target 1x the stop, out by 3:15.")
    if GAPFILL_CALLS.get(nm.lower()):
        out.append(f"GAP FILL call at 9:20 (its own trade): if the open is 0.5-1.5% away from yesterday's close {f2(cx['yc'])} "
                   "and the first 5 minutes close back against the gap -> toward the fill; stop beyond the first 5 minutes, "
                   "target half way to yesterday's close, out by 3:15.")
    if OIWALL_CALLS.get(nm.lower()):
        w = cx.get('walls')
        out.append(f"OI WALL calls, 9:20-2:30 (their own trades): " + (
            f"yesterday's call OI wall {w[0]:,.0f}, put OI wall {w[1]:,.0f}. A 5-minute candle reaching the call wall and "
            "closing back under it -> SELL (the put wall and back over it -> BUY), not against today's CPR vs yesterday's; "
            f"stop at that candle's high / low (at most {OIWALL_STOP} points), target 2x the stop, out by 3:15."
            if w else "not today (yesterday's option OI could not be had)."))
    if REENTRY_CALLS.get(nm.lower()):
        out.append(f"SECOND CHANCE (its own trade): if a call is stopped out and the day then turns its way (beyond both the "
                   f"open and the CPR), a limit order back at the CPR edge, stop {REENTRY_STOP} points, held to 3:15.")
    if CPR_CALLS and CPR_TP.get(nm.lower()):
        out.append(f"CPR BREAK calls, 9:16-2:30 (their own trades; the CPR / gap / POC / volume rules above don't apply): "
                   f"the first touch of the CPR top {f2(lv['top'])} -> BUY, of its bottom {f2(lv['bot'])} -> SELL, at the "
                   "close of that 1-minute candle, " +
                   ("every first touch today (today's CPR overlaps yesterday's)" if cx['rel'] == 0 else
                    "when the touch is between 10:00 and 11:30, or price is still inside the 15-minute range, or the day "
                    "opened beyond that side of the CPR, came back and broke out again with RSI 14 (5-minute) above 55 "
                    "(BUY) / below 45 (SELL)") +
                   f". Target {CPR_TP[nm.lower()]} points, stop {CPR_SL[nm.lower()]} points, out by 3:15.")
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
               (" and sweep" if SWEEP else "") + (" and CPR BREAK" if CPR_CALLS else "") + " trades only."
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
    plan = [t for t in ts if t['src'] not in ('VOLUME LINE', 'SWEEP') + EXTRA_SRC]
    if cx.get('rules_used') in ('small', 'rr'):
        return messages_small(cx, ts, c1, upto, lots)
    if c1 and not cx['narrow'] and upto >= 556 and not any(t['src'] == 'MAGNET' for t in plan):
        out.append(('nomag', 556, f"{nm} 9:16: no CPR Magnet trade today; breakout plan from 9:30.", False))
    if c1 and upto >= RANGE_END - 1 and not any(t['src'] == 'MAGNET' for t in plan):
        out.append(('range', RANGE_END, range_note(cx, c1), True))
        if upto >= CUTOFF and not plan:
            out.append(('nobo', CUTOFF, f"{nm} 10:00: no breakout trade. Volume-line" + (" and sweep" if SWEEP else "") +
                        (" and CPR BREAK" if CPR_CALLS else "") + " trades only from now (till 2:30).", False))
    cap = stop_max(cx)
    for (src, side), m in sorted((cx.get('vlog') or {}).items(), key=lambda kv: kv[1]):
        out.append((('vskip', src, side), m, f"{nm} {hhmm(m)} {src} {'BUY' if side > 0 else 'SELL'} signal skipped: the volume "
                    f"doesn't agree (over the last 2 hours the {'down' if side > 0 else 'up'} candles carried more volume). "
                    "Not taking it.", False))
    for t in ts:
        sd = 'BUY' if t['side'] > 0 else 'SELL'
        tid = (t['src'], t['m'])
        sn = f"capped at {cap:g} points" if cap and abs(abs(t['e'] - t['stp0']) - cap) < 0.01 else ''
        if not t['taken']:
            out.append((tid + ('skip',), t['known'], f"{nm} {hhmm(t['m'])} {t['src']} {sd} signal at {f2(t['e'])} skipped: " +
                        (f"{SWEEP_MAX} sweep trades already today." if t.get('full') else "another CPR BREAK call is still open."
                         if t['src'] == 'CPR BREAK' else "another trade is still open."), False))
            continue
        own = " Its own trade: it can be open together with another call."
        if t['src'] == 'CPR BREAK':
            how = (f"First touch of the CPR {'top' if t['side'] > 0 else 'bottom'} today; " + '; '.join(t['why']) +
                   f". Stop {f2(t['stp0'])} ({abs(t['e'] - t['stp0']):.0f} points). Target {f2(t['tgt'])} "
                   f"({abs(t['tgt'] - t['e']):.0f} points), all out there. Out by 15:15 at the latest." + own)
        elif t['src'] == 'OPEN HIGH LOW':
            how = (f"The first 15 minutes never traded {'above' if t['side'] < 0 else 'below'} the open {f2(t['o'])} (open = "
                   f"{'high' if t['side'] < 0 else 'low'}). Stop {f2(t['stp0'])} ({abs(t['e'] - t['stp0']):.0f} points). Target "
                   f"{f2(t['tgt'])} (1x the stop), all out there. Out by 15:15 at the latest." + own)
        elif t['src'] == 'GAP FILL':
            how = (f"Opened {abs(t['gap']):.2f}% {'above' if t['gap'] > 0 else 'below'} yesterday's close {f2(cx['yc'])} and the "
                   f"first 5 minutes closed back {'down' if t['side'] < 0 else 'up'}: toward filling the gap. Stop {f2(t['stp0'])} "
                   f"(beyond the first 5 minutes' {'high' if t['side'] < 0 else 'low'}). Target {f2(t['tgt'])} (half way to "
                   "yesterday's close), all out there. Out by 15:15 at the latest." + own)
        elif t['src'] == 'OI WALL':
            how = (f"The 5-minute candle reached yesterday's {'call' if t['side'] < 0 else 'put'} OI wall {t['wall']:,.0f} (the strike "
                   f"with the most {'call' if t['side'] < 0 else 'put'} open interest) and closed back {'under' if t['side'] < 0 else 'over'} "
                   f"it. Stop {f2(t['stp0'])} (the candle's {'high' if t['side'] < 0 else 'low'}, {abs(t['e'] - t['stp0']):.0f} points). "
                   f"Target {f2(t['tgt'])} (2x the stop), all out there. Out by 15:15 at the latest." + own)
        elif t['src'] == 'SECOND CHANCE':
            c0 = t['call']
            how = (f"Limit order filled back at the CPR {'bottom' if t['side'] < 0 else 'top'} {f2(t['lvl'])}: the {c0['src'].lower()} "
                   f"{sd} from {hhmm(c0['m'])} was stopped out, then the day turned {'falling' if t['side'] < 0 else 'rising'}. "
                   f"Stop {f2(t['stp0'])} ({REENTRY_STOP} points). No target: hold until 15:15 (or the stop)." + own)
        elif t['src'] == 'SWEEP':
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
        tn = trend_now(cx, c1, t['m']) if t['src'] not in EXTRA_SRC else None
        if tn and tn['dir'] == -t['side']:
            how += (f" CAREFUL: this is against today's trend (price {'below' if tn['dir'] < 0 else 'above'} the day's open and "
                    "the CPR); calls like this won only about 3 in 10 in 2023-2026 and lost money overall.")
        tg = target_levels(cx, c1, t['side'], t['e'], t['known'], half_price(t))
        pr = t_probs(cx['name'], t['src'])
        pc = lambda k: f", {pr['t' + str(k + 1)]}% of such calls got there" if pr and k == 0 else (f" {pr['t' + str(k + 1)]}%" if pr else '')
        out.append((tid + ('in',), t['known'], f"{nm} {hhmm(t['m'] if t['src'] != 'MAGNET' else 556)} {t['src']} {sd} at "
                    f"{f2(t['e'])} -> {option(cx, t['side'], t['e'])}. {how} Targets: T1 {f2(tg[0])} ({t1_word(t)}{pc(0)}), "
                    f"then the next levels T2 {f2(tg[1])}{pc(1)}, T3 {f2(tg[2])}{pc(2)} (for reference).", True))
        for k, ev in enumerate(t['ev']):
            if ev['kind'] == 'half':
                txt = (f"{nm} {hhmm(ev['m'])} BOOK HALF at {f2(ev['px'])} ({ev['pts']:+.0f} pts). Move the stop to {f2(ev['stp'])}."
                       + (f" From here, T2 {f2(tg[1])} was reached on {pr['t2_after_t1']}% of such calls, T3 {f2(tg[2])} on "
                          f"{round(pr['t2_after_t1'] * pr['t3_after_t2'] / 100)}%." if pr and pr.get('t2_after_t1') is not None
                          and t['src'] not in ('VOLUME LINE', 'SWEEP') else "")
                       + (f" Rest to {f2(t['tgt2'])}." if t['src'] == 'VOLUME LINE' and t.get('tgt2') else ""))
            else:
                txt = f"{nm} {hhmm(ev['m'])} +1R reached: trail the stop 1R behind the best price (now {f2(ev['stp'])})."
            out.append((tid + ('ev', k), ev['m'] + 1, txt, True))
        if t['exit']:
            x = t['exit']
            out.append((tid + ('out',), x['m'] + 1, f"{nm} {hhmm(x['m'])} EXIT ({x['why']}) at {f2(x['px'])}: {x['pnl']:+.0f} pts "
                        f"after costs (about Rs {rupees(cx, x['pnl'], lots):+,.0f} at {lots} lots).", True))
    tn = trend_now(cx, c1, upto)
    if tn and tn['dir']:
        out.append((('trend', tn['dir']), tn['m'], tn['text'], True))
    ra = cx.get('re_arm')
    if ra:
        w, c0 = ('SELL' if ra['side'] < 0 else 'BUY'), ra['call']
        out.append((('re-arm', ra['m']), ra['m'], f"{nm} {hhmm(ra['m'])} SECOND CHANCE: the {c0['src'].lower()} {w} from "
                    f"{hhmm(c0['m'])} was stopped out and now it is a {'falling' if ra['side'] < 0 else 'rising'} day. Place a {w} "
                    f"LIMIT order at {f2(ra['lvl'])} (back at the CPR {'bottom' if ra['side'] < 0 else 'top'}), valid until 14:30 -> "
                    f"{option(cx, ra['side'], ra['lvl'])}. Stop {f2(ra['lvl'] - ra['side'] * REENTRY_STOP)} ({REENTRY_STOP} points); "
                    "no target, hold until 15:15.", True))
        if ra.get('expired') and not ra.get('done'):
            out.append((('re-cancel', ra['m']), VOL_END, f"{nm} 14:30: the SECOND CHANCE limit order at {f2(ra['lvl'])} wasn't "
                        f"filled. Cancel it.", True))
    for m, side, e in cx.get('cpr_none') or []:
        out.append((('cprnone', side), m + 1, f"{nm} {hhmm(m)} first touch of the CPR {'top' if side > 0 else 'bottom'} at "
                    f"{f2(e)}: no CPR BREAK call (none of its four conditions today).", False))
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
    out = [f"{t['src']} {'BUY' if t['side'] > 0 else 'SELL'} from {f2(t['e'])}, stop now {f2(t['stp'])}" +
           (", half booked" if any(e['kind'] == 'half' for e in t['ev']) else "")
           for t in ts if t['taken'] and not t['exit']]
    return "open: " + "; ".join(out) if out else "no trade open"

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
    if push and said_today(text):
        push = False                  # sent already today (the program was restarted): not again
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

def said_today(text):
    day = now_ist().strftime('%Y-%m-%d')
    return any(e.get('text') == text and str(e.get('at', '')).startswith(day) for e in EVENTS)

def record_event(text, kind, index, title=None, **extra):
    eid = max(int(time.time() * 1000), (EVENTS[-1]['id'] + 1) if EVENTS else 0)
    e = dict(id=eid, at=now_ist().strftime('%Y-%m-%d %H:%M:%S'), index=index, kind=kind,
             title=title or event_title(text, kind, index), text=text, **extra)
    EVENTS.append(e)
    del EVENTS[:-300]
    try:
        with open(EVENTS_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(e) + '\n')
    except Exception:
        pass

SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
SETTINGS = {}

def app_settings(**change):
    """The app's settings, kept here so the phone's notification service follows them too: opt_alerts = the option
    alerts on / off (off until the user turns them on); opt_from = they show from this event on (not the ones from
    before they were turned on)."""
    if not SETTINGS:
        try:
            with open(SETTINGS_FILE, encoding='utf-8') as f:
                SETTINGS.update(json.load(f))
        except (OSError, ValueError):
            pass
        SETTINGS.setdefault('opt_alerts', False)
        SETTINGS.setdefault('opt_from', 0)
    if change:
        if change.get('opt_alerts') and not SETTINGS['opt_alerts']:
            SETTINGS['opt_from'] = EVENTS[-1]['id'] if EVENTS else 0
        SETTINGS.update(change)
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(SETTINGS, f)
        except OSError:
            pass
    return dict(SETTINGS)

def shown_event(e, st):
    """Does the app get this alert? The option alerts only while they are on."""
    return e.get('kind') != 'option' or (st['opt_alerts'] and e['id'] > st['opt_from'])

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

TARGETS_V = 5                     # the saved history's version (2: T1 = where half is booked; 3: stops capped at
                                  # 55 Nifty / 170 Sensex points; 4: the CPR BREAK calls; 5: all the extra calls):
                                  # days saved with an older one are worked out again

def half_price(t):
    """Where the call books half (or, for a single target, its target): T1."""
    if t.get('small') or t['src'] in ('VOLUME LINE', 'SWEEP') + EXTRA_SRC:
        return t['tgt']
    if t['src'] == 'MAGNET':
        return t['t1']
    return t['e'] + t['side'] * 0.25 * t['R']

PROBS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'target-probs.json')
PROBS = {}

def t_probs(name, src):
    """How often calls like this one reached T1 / T2 / T3 (percent), and T2 / T3 once T1 / T2 was reached, 2023-2026
    (research/quant/target_probs.py); a setup with fewer than 30 calls: all calls of the index."""
    if not PROBS:
        try:
            with open(PROBS_FILE, encoding='utf-8') as f:
                PROBS.update(json.load(f)['probs'])
        except Exception:
            PROBS['-'] = {}
    by = PROBS.get(name, {})
    v = by.get(src) if by.get(src, {}).get('n', 0) >= 30 else None if src in EXTRA_SRC else by.get('ALL')
    return v or None

def t1_word(t):
    """What the call does at T1: books half, or (a single target) books all."""
    if t['src'] == 'SECOND CHANCE':
        return 'reference: held to 3:15'
    return 'target' if t['src'] in ('VOLUME LINE', 'SWEEP') + EXTRA_SRC and not t.get('tgt2') else 'book half'

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
    need = abs(t['tgt'] - t['e']) if t['src'] in EXTRA_SRC and t.get('tgt') else SUCCESS_PTS.get(cx['name'], 0)   # extra calls: their target
    m0 = 556 if t['src'] == 'MAGNET' else t['m']           # as the alert says it
    tg = target_levels(cx, c1, sd, t['e'], t['known'], half_price(t))
    pr = t_probs(cx['name'], t['src'])
    mae = mae_until(c1, sd, t['e'], t['known'], x['m'] if x else (c1[-1][0] if c1 else t['known']))
    return dict(time=hhmm(m0), side='BUY' if sd > 0 else 'SELL', setup=t['src'].lower(), entry=round(t['e'], 2),
                stop=round(t['stp0'], 2), stop_now=round(t['stp'], 2), open=not x, status=(f"{x['why']} at {f2(x['px'])}" if x else 'open'),
                pts=round(x['pnl'], 1) if x else None, mfe=round(mfe, 1), mae=round(mae, 1), stopped=stopped, success=mfe >= need,
                need=need, option=option(cx, sd, t['e']), targets=tg, t1=t1_word(t),
                prob=[pr['t1'], pr['t2'], pr['t3']] if pr else None,
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
        have = {(r['d'], r['index'], r['time'], r['side'], r.get('setup')) for r in old}
        new = [r for r in rows if (r['d'], r['index'], r['time'], r['side'], r['setup']) not in have]
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
                rows[(r['d'], r['index'], r['time'], r['side'], r.get('setup'))] = r
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
    out = dict(rule={k: v for k, v in SUCCESS_PTS.items()}, cpr={k.upper(): (CPR_TP[k], CPR_SL[k]) for k in CPR_TP},
               calls=calls, stats={})
    cut = str(dt.date.fromisoformat(calls[0]['d']) - dt.timedelta(days=30)) if calls else ''
    extra = {x.lower() for x in EXTRA_SRC}
    for idx in ('ALL', 'NIFTY', 'SENSEX', 'X NIFTY', 'X SENSEX'):     # ALL / NIFTY / SENSEX: the calls; X: the extra ones
        x = idx.startswith('X ')
        rs = [r for r in calls if (r.get('setup') in extra) == x and idx in ('ALL', r['index'], 'X ' + r['index'])]
        if x and not rs:
            continue
        out['stats'][idx] = dict(all=stats(rs), last30=stats([r for r in rs if r['d'] > cut]))
    return out

def app_state():
    out = dict(updated=now_ist().strftime('%Y-%m-%d %H:%M:%S'), indices={})
    for n, d in CHART_DATA.items():
        lv = live_now(n) if d.get('day') == str(now_ist().date()) else None
        out['indices'][n] = dict(name=d.get('name'), day=d.get('day'), status=d.get('status'), plan=PLANS.get(n, ''),
                                 last=lv[0] if lv else d['candles'][-1][4] if d.get('candles') else None,
                                 live=lv[1] if lv else None, calls=d.get('calls', []), updated=d.get('updated'),
                                 trend=d.get('trend'))
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
    levels += [dict(p=cx['yh'], c='#f9a825', t='Yesterday high', s=2, w=1), dict(p=cx['yl'], c='#f9a825', t='Yesterday low', s=2, w=1)]
    levels += pivot_lines(lv['p'], cx['yh'], cx['yl'])
    if cx['poc'] is None and cx.get('poc_ref') is not None:      # no POC filter on this index: yesterday's, for reference
        levels.append(dict(p=cx['poc_ref'], c='#9c6ade', t='POC yesterday (info)', s=0, w=1))
    first = [x for x in c_all if x[0] < RANGE_END]
    if first and got >= RANGE_END - 1:
        levels += [dict(p=max(x[2] for x in first), c='#4caf50', t='15-min high', s=2, w=1),
                   dict(p=min(x[3] for x in first), c='#f44336', t='15-min low', s=2, w=1)]
    marks, rows, opens, boxes = [], [], [], []
    for t in ts:
        if not t['taken']:
            continue
        sd = t['side']
        m0 = 555 if t['src'] == 'MAGNET' else t['m'] - 1 if t['src'] in ('VOLUME LINE', 'SWEEP', 'OI WALL') else t['m']
        # the position, drawn like TradingView's long / short position tool: green to the targets, red to the stop
        boxes.append(dict(m0=m0, m1=t['exit']['m'] if t['exit'] else None, side=sd, e=round(t['e'], 2), sl=round(t['stp0'], 2),
                          sl_now=round(t['stp'], 2), t=target_levels(cx, c_all, sd, t['e'], t['known'], half_price(t)),
                          t1w=t1_word(t), pnl=round(t['exit']['pnl'], 1) if t['exit'] else None,
                          prob=[(t_probs(cx['name'], t['src']) or {}).get(k) for k in ('t1', 't2', 't3')]))
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
            opens.append(t)
        rows.append([hhmm(m0 + (1 if t['src'] in ('VOLUME LINE', 'SWEEP', 'OI WALL') else 0)), ('BUY' if sd > 0 else 'SELL') + ' ' + t['src'].lower(), f2(t['e']), f2(t['stp0']),
                     (f"{x['why']} at {f2(x['px'])}: {x['pnl']:+.0f} pts" if x else f"open, stop now {f2(t['stp'])}")])
    pend = cx.get('pending')
    if pend and got < 720 and not any(t['src'] == 'PULLBACK' for t in ts):
        levels.append(dict(p=pend['px'], c='#2962ff', t='LIMIT ' + ('BUY' if pend['side'] > 0 else 'SELL'), s=2, w=2))
    for open_t in opens:
        moved = open_t['side'] * (open_t['stp'] - open_t['e'])
        levels.append(dict(p=open_t['stp'], c='#9e9e9e' if abs(moved) < 0.01 else '#ef5350', s=2, w=1,
                           t='BE' if abs(moved) < 0.01 else 'Trailing SL' if moved > 0 else 'SL'))
        T = target_levels(cx, c_all, open_t['side'], open_t['e'], open_t['known'], half_price(open_t))
        levels.append(dict(p=T[0], c='#26a69a', t='T1', s=2, w=1))      # T2 / T3: in the position box
        half = any(e['kind'] == 'half' for e in open_t['ev'])
        sd = open_t['side']
        if open_t.get('small') or open_t['src'] in EXTRA_SRC:
            tg = open_t.get('tgt')
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
    won = [t['exit']['pnl'] for t in done_ if t['exit']['pnl'] > 0]
    lost = [t['exit']['pnl'] for t in done_ if t['exit']['pnl'] <= 0]
    w = lv['top'] - lv['bot']
    info = [["Today's CPR", f"{f2(lv['bot'])} - {f2(lv['top'])}, {w:.0f} pts ({100 * w / lv['p']:.2f}%) " + ('NARROW' if cx['narrow'] else 'wide')],
            ['Bias', 'up: no breakout SELLs' if cx['rel'] > 0 else 'down: no breakout BUYs' if cx['rel'] < 0 else 'both ways'],
            ['15-minute range', f"{f2(min(x[3] for x in first))} - {f2(max(x[2] for x in first))}" if first and got >= RANGE_END - 1 else 'forming'],
            ['Volume POC' if cx['poc'] is None else 'Volume POC / value area' if cx['pocn'] == 1 else f"{cx['pocn']}-day volume POC / value area",
             f"{f2(cx['poc'])} / {f2(cx['val'])} - {f2(cx['vah'])}" if cx['poc'] is not None else 'no POC filter'],
            ['Today', open_note(cx, ts)],
            ['On this chart', f"{len(done_)} trade{'' if len(done_) == 1 else 's'}, {len(won)} won, {len(lost)} lost"],
            ['Points won / lost / net', f"+{sum(won):.0f} / {sum(lost):.0f} / {net:+.0f}"]]
    import hashlib
    d = dict(name=cx['name'], day=day, yday_date=cx['prev'], yday=[list(x) for x in cx['yday']],
             candles=[list(x) for x in c_all], levels=levels, marks=sorted(marks, key=lambda k: k['m']),
             rows=rows, boxes=boxes, status=status, info=info)
    tn = trend_now(cx, upto_c, got)
    d['trend'] = dict(dir=tn['dir'], short=tn['short'], pct=tn['pct']) if tn else None
    d['ver'] = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:12]   # changes with what is drawn
    CHART_DATA[n] = dict(d, updated=now_ist().strftime('%H:%M:%S'), calls=calls)

CHART_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#ffffff">
<meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes"><title>CPRB live chart</title>
<style>
html,body{height:100%}
body{margin:0;background:#ffffff;color:#131722;font:14px -apple-system,BlinkMacSystemFont,Roboto,Ubuntu,'Trebuchet MS',sans-serif;
  display:flex;flex-direction:column;overflow:hidden}
#bar{display:flex;flex-wrap:wrap;gap:2px;align-items:center;padding:4px 6px;border-bottom:1px solid #e0e3eb}
button{background:transparent;color:#131722;border:0;border-radius:4px;padding:7px 9px;font:inherit}
button.on{color:#2962ff;background:#f0f3fa;font-weight:600}
.sep{width:1px;height:20px;background:#e0e3eb;margin:0 4px}
#wrap{position:relative;flex:1;min-height:200px}
#c{position:absolute;inset:0}
#legend{position:absolute;left:6px;top:4px;z-index:3;font-size:12px;line-height:1.6;pointer-events:none;background:rgba(255,255,255,0.85);padding:0 4px;border-radius:3px}
#legend b{font-weight:600;color:#131722;margin-right:6px}
#legend i{font-style:normal;color:#787b86;margin-left:6px}
.up{color:#089981}.dn{color:#f23645}
#trend{font-size:12px;line-height:1.4;padding:4px 8px;background:#f0f3fa;color:#50535e;border-bottom:1px solid #e0e3eb}
#trend.dn{background:#c62828;color:#fff;font-weight:600}#trend.up{background:#00796b;color:#fff;font-weight:600}
#trend.hidden{display:none}
#st{font-size:12px;color:#787b86;padding:5px 8px;border-top:1px solid #e0e3eb}
#st .lv{color:#089981;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:5px 8px;border-bottom:1px solid #e0e3eb;text-align:left}
th{color:#787b86;font-weight:normal}
#key{font-size:12px;color:#787b86;padding:6px 8px}
#panel{position:fixed;left:0;right:0;bottom:0;max-height:55%;overflow:auto;background:#ffffff;border-top:1px solid #e0e3eb;z-index:5;
  box-shadow:0 -4px 16px rgba(0,0,0,0.12)}
#panel.hidden{display:none}
#panel h4{margin:8px;font-size:13px;color:#131722}
#tbl{position:absolute;right:72px;top:4px;z-index:3;background:rgba(255,255,255,0.94);border:1px solid #d1d4dc;font-size:11px;max-width:min(430px,calc(100% - 84px))}
#tbl td{padding:3px 7px;border-bottom:1px solid #e0e3eb;border-right:1px solid #e0e3eb;vertical-align:top}
#tbl td:first-child{color:#50535e;white-space:nowrap}#tbl td:last-child{color:#f23645;border-right:0}
#tbl tr:first-child td{font-weight:600;color:#131722}
#tbl.hidden{display:none}
</style></head><body>
<div id="bar"></div>
<div id="trend" class="hidden"></div>
<div id="wrap"><div id="c"></div><div id="legend"></div><table id="tbl" class="hidden"></table></div>
<div id="st">loading...</div>
<div id="panel" class="hidden"><h4>Today's trades</h4>
<table><thead><tr><th>Time</th><th>Trade</th><th>Entry</th><th>Stop</th><th>Result</th></tr></thead><tbody id="list"></tbody></table>
<h4>How to read it</h4>
<div id="key"><b>The red / green bar at the top</b>: a FALLING day (price below both the day's open and the CPR) or a
RISING day (above both). From moments like that (2023-2026) price turned 60 Nifty / 200 Sensex points the other way before
going 35 / 100 further only about 1 time in 3 before 10:30, 1 in 4 to 12:30 and 1 in 5 after; trades against the move lost
money in every year and no reversal sign tested changed that. So: don't trade against it. Grey: no clear trend.<br>
The % after T1 / T2 / T3: how often calls of this kind got there (2023-2026; after T1, before price came
back to the entry). <b>SL</b>: the stop loss when the trade starts. <b>BE</b> (breakeven): after half is booked at T1 the stop
moves to the entry price, so the rest can't lose. <b>Trailing SL</b>: once price has gone as far beyond the entry as the
first stop was (1R), the stop follows 1R behind the best price, locking in profit. Each trade is drawn like TradingView's long / short position tool: green from the entry to T1 (where half is
booked; a volume-line trade: its target), lighter green on to T3 (T2 / T3: the next price levels, for reference), red to
the stop loss; an open trade's box runs to the right edge, with its stop now (dashed) once it has moved. Pink: CPR top /
pivot / bottom (orange on a narrow day). Orange: the pivots R1 / S1 / R2 / S2. Purple: the volume POC (Sensex: yesterday's,
for reference only - no POC filter there). Teal
dots: 3-day volume lines. Green / red dashed: the first 15 minutes' high / low. Yellow dashed: yesterday's high / low.
Letters: B buy, S sell, T target or half booked, SL stop loss, BE stop at entry, X other exit. In market hours the last
candle and the price line move with the live price every second; the calls use whole 1-minute candles. Fit: back to the
latest candles with the price scale fitted. Zoom: pinch the chart, or drag the price scale (right) up / down and the
time scale (bottom) left / right; double-tap a scale or press Fit to reset.</div></div>
<script src="/lwc.js"></script>
<script>
const IDX = %INDICES%;
const PV = '%PAGEVER%';                     // this page's version: reload when the server has a newer one
let cur = IDX[0][0], tf = 5, plines = [], linesKey = '', fitted = '', seq = 0, shown = 0, D = null, loading = false;
const $ = (id) => document.getElementById(id);
const box = $('c');
const fmt = (n) => Number(n).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const fmt0 = (n) => Number(n).toLocaleString('en-IN', {maximumFractionDigits: 0});
const sgn = (n) => (n > 0 ? '+' : n < 0 ? '-' : '') + Math.abs(Math.round(n));
if (!window.LightweightCharts) $('bar').textContent = 'The chart library did not load: check the internet connection and reload.';
const chart = LightweightCharts.createChart(box, {
  layout: {background: {type: 'solid', color: '#ffffff'}, textColor: '#131722', fontSize: 12},
  grid: {vertLines: {color: '#f0f3fa'}, horzLines: {color: '#f0f3fa'}},
  rightPriceScale: {borderColor: '#e0e3eb', scaleMargins: {top: 0.12, bottom: 0.08}},
  timeScale: {timeVisible: true, secondsVisible: false, borderColor: '#e0e3eb', rightOffset: 8},
  crosshair: {mode: 0, vertLine: {color: '#758696', labelBackgroundColor: '#131722'}, horzLine: {color: '#758696', labelBackgroundColor: '#131722'}},
  localization: {locale: 'en-IN', priceFormatter: fmt}});
const s = chart.addCandlestickSeries({upColor: '#089981', downColor: '#f23645', borderVisible: false,
  wickUpColor: '#089981', wickDownColor: '#f23645', priceLineVisible: true, priceLineStyle: 1, lastValueVisible: true});
new ResizeObserver(() => chart.applyOptions({width: box.clientWidth, height: box.clientHeight})).observe(box);
const ts = (day, m) => { const [y, mo, d] = day.split('-').map(Number); return Date.UTC(y, mo - 1, d) / 1000 + m * 60; };
const bucket = (m) => 555 + Math.floor((m - 555) / tf) * tf;
function agg(day, rows, out) {
  for (const [m, o, h, l, c] of rows) {
    const t = ts(day, bucket(m)), x = out[out.length - 1];
    if (x && x.time === t) { x.high = Math.max(x.high, h); x.low = Math.min(x.low, l); x.close = c; }
    else out.push({time: t, open: o, high: h, low: l, close: c});
  }
  return out;
}

// ---- trades as TradingView's long / short position tool ----
function pill(g, x, y, text, bg, right) {
  g.font = '11px -apple-system,Roboto,sans-serif';
  const w = g.measureText(text).width + 10, h = 17, x0 = right ? x - w : x;
  g.fillStyle = bg; g.beginPath();
  if (g.roundRect) g.roundRect(x0, y - h / 2, w, h, 3); else g.rect(x0, y - h / 2, w, h);
  g.fill(); g.fillStyle = '#fff'; g.textBaseline = 'middle'; g.fillText(text, x0 + 5, y + 0.5);
  return w;
}
function hline(g, x1, x2, y, color, dash) {
  if (y == null) return;
  g.strokeStyle = color; g.lineWidth = 1; g.setLineDash(dash); g.beginPath(); g.moveTo(x1, Math.round(y) + 0.5); g.lineTo(x2, Math.round(y) + 0.5); g.stroke(); g.setLineDash([]);
}
class Positions {
  constructor() { this.items = []; }
  attached(p) { this.chart = p.chart; this.series = p.series; this.req = p.requestUpdate; }
  detached() { this.req = null; }
  set(items) { this.items = items || []; if (this.req) this.req(); }
  updateAllViews() {}
  autoscaleInfo() {                          // the price scale always shows an open trade's T1 and stop loss
    const o = this.items.filter((b) => b.t1 == null);
    if (!o.length) return null;
    const v = [].concat(...o.map((b) => [b.e, b.sl, b.sl_now, b.t[0]]));
    return {priceRange: {minValue: Math.min(...v), maxValue: Math.max(...v)}};
  }
  paneViews() {                              // the zones under the candles, the labels over them
    return [{zOrder: () => 'bottom', renderer: () => ({draw: (t) => this.draw(t, false)})},
            {zOrder: () => 'top', renderer: () => ({draw: (t) => this.draw(t, true)})}];
  }
  draw(target, labels) {
    target.useMediaCoordinateSpace(({context: g, mediaSize: sz}) => {
      const tsc = this.chart.timeScale(), y = (p) => (p == null ? null : this.series.priceToCoordinate(p));
      for (const b of this.items) {
        const x1 = tsc.timeToCoordinate(b.t0);
        if (x1 == null) continue;
        const open = b.t1 == null;
        let x2 = open ? sz.width : tsc.timeToCoordinate(b.t1);      // an open trade: on to the price scale
        if (x2 == null || x2 - x1 < 14) x2 = x1 + 14;
        const ye = y(b.e), ys = y(b.sl), y1 = y(b.t[0]), y2 = y(b.t[1]), y3 = y(b.t[2]), yn = y(b.sl_now);
        if (ye == null || ys == null || y1 == null) continue;
        const moved = open && Math.abs(b.sl_now - b.sl) > 0.01, dir = b.side > 0 ? 1 : -1;
        if (!labels) {
          const fill = (ya, yb, c) => { g.fillStyle = c; g.fillRect(x1, Math.min(ya, yb), x2 - x1, Math.abs(yb - ya)); };
          fill(ye, ys, 'rgba(242,54,69,0.22)');
          fill(ye, y1, 'rgba(8,153,129,0.30)');
          if (y3 != null) fill(y1, y3, 'rgba(8,153,129,0.10)');
          hline(g, x1, x2, ye, '#9598a1', []);
          hline(g, x1, x2, y2, 'rgba(8,153,129,0.8)', [4, 3]);
          hline(g, x1, x2, y3, 'rgba(8,153,129,0.8)', [4, 3]);
          if (moved) hline(g, x1, x2, yn, '#f23645', [4, 3]);
          continue;
        }
        const left = x2 - x1 < 110, used = [];       // a narrow box (a recent entry): the labels left of it
        const put = (yy, text, bg) => {              // a label at its price, moved aside if it would cover another
          if (yy == null) return;
          let xx = left ? x1 - 3 : x1 + 3;
          for (const u of used) if (Math.abs(u.y - yy) < 17) xx = left ? Math.min(xx, u.l - 4) : Math.max(xx, u.r + 4);
          const w = pill(g, xx, yy, text, bg, left);
          used.push({y: yy, l: left ? xx - w : xx, r: left ? xx : xx + w});
        };
        put(ye, (b.side > 0 ? 'BUY ' : 'SELL ') + fmt0(b.e) + (open ? '' : '  ' + sgn(b.pnl) + ' pts'), open ? '#2962ff' : '#5d606b');
        const pct = (k) => (b.prob && b.prob[k] != null ? ' ' + b.prob[k] + '%' : '');
        put(y1, 'T1 ' + fmt0(b.t[0]) + ' (' + sgn(dir * (b.t[0] - b.e)) + ')' + pct(0), '#089981');
        if (open || x2 - x1 > 90) {
          put(y2, 'T2 ' + fmt0(b.t[1]) + ' (' + sgn(dir * (b.t[1] - b.e)) + ')' + pct(1), 'rgba(8,153,129,0.8)');
          put(y3, 'T3 ' + fmt0(b.t[2]) + ' (' + sgn(dir * (b.t[2] - b.e)) + ')' + pct(2), 'rgba(8,153,129,0.8)');
        }
        put(ys, 'SL ' + fmt0(b.sl) + ' (' + sgn(dir * (b.sl - b.e)) + ')', '#f23645');
        if (moved) put(yn, stopName(b) + ' ' + fmt0(b.sl_now), stopName(b) === 'BE' ? '#787b86' : '#f23645');
      }
    });
  }
}
function stopName(b) {                      // the stop now: the first one, at the entry (breakeven), or trailing
  const d = (b.side > 0 ? 1 : -1) * (b.sl_now - b.e);
  return Math.abs(d) < 0.01 ? 'BE' : d > 0 ? 'Trailing SL' : 'SL';
}
const pos = new Positions();
s.attachPrimitive(pos);

// ---- legend (like TradingView's: symbol, timeframe, O H L C and the change) ----
function legend(bar) {
  if (!D || !bar) { $('legend').innerHTML = ''; return; }
  const data = s.data(), i = data.findIndex((x) => x.time === bar.time), prev = i > 0 ? data[i - 1].close : bar.open;
  const ch = bar.close - prev, cls = ch >= 0 ? 'up' : 'dn';
  $('legend').innerHTML = '<b>' + D.name + ' &middot; ' + tf + 'm</b>' +
    ['O', 'H', 'L', 'C'].map((k, j) => '<i>' + k + '</i> <span class="' + cls + '">' + fmt([bar.open, bar.high, bar.low, bar.close][j]) + '</span>').join('') +
    ' <span class="' + cls + '">' + (ch >= 0 ? '+' : '') + fmt(ch) + ' (' + (ch >= 0 ? '+' : '') + (100 * ch / prev).toFixed(2) + '%)</span>';
}
let hover = false;
chart.subscribeCrosshairMove((p) => {
  const b = p && p.time ? p.seriesData.get(s) : null;
  hover = !!b; legend(b || lastBar());
});
const lastBar = () => { const d = s.data(); return d.length ? d[d.length - 1] : null; };

// ---- buttons ----
function buttons() {
  const bar = $('bar'); bar.innerHTML = '';
  const add = (text, on, fn) => { const b = document.createElement('button'); b.textContent = text; b.className = on ? 'on' : ''; b.onclick = fn; bar.appendChild(b); };
  const sep = () => { const d = document.createElement('div'); d.className = 'sep'; bar.appendChild(d); };
  for (const [k, name] of IDX) add(name, k === cur, () => { if (k !== cur) { cur = k; clear(); } fitted = ''; buttons(); full(); });
  sep();
  for (const f of [1, 3, 5, 15]) add(f + 'm', f === tf, () => { tf = f; fitted = ''; buttons(); draw(); });
  sep();
  add('Fit', false, () => { fitted = ''; draw(); });
  add('Info', !$('tbl').classList.contains('hidden'), () => {
    $('tbl').classList.toggle('hidden'); try { localStorage.setItem('tbl', $('tbl').classList.contains('hidden') ? 'off' : 'on'); } catch (e) {} buttons(); });
  add('☰', !$('panel').classList.contains('hidden'), () => { $('panel').classList.toggle('hidden'); buttons(); });
}
function clear() {                          // another index: nothing of the last one stays on the chart
  plines.forEach((p) => s.removePriceLine(p)); plines = []; linesKey = ''; D = null;
  s.setData([]); s.setMarkers([]); pos.set([]); $('list').innerHTML = ''; $('legend').innerHTML = ''; $('st').textContent = 'loading...';
  $('trend').className = 'hidden';
}
const keyq = () => { const k = new URLSearchParams(location.search).get('key'); return k ? '&key=' + encodeURIComponent(k) : ''; };
function status() {
  if (!D) return;
  const L = D.live;
  $('st').innerHTML = (L ? '<span class="lv">&#9679; LIVE ' + fmt(L.px) + '</span> at ' + L.at + ' | ' : '') + D.status;
}

// ---- drawing ----
function draw() {
  if (!D) return;
  const live = (D.live && D.live.bars) || [];
  s.setData(agg(D.day, D.candles.concat(live), agg(D.yday_date, D.yday, [])));
  s.setMarkers(D.marks.map((k) => ({time: ts(D.day, bucket(k.m)), position: k.pos, color: k.c, shape: k.pos === 'belowBar' ? 'arrowUp' : 'arrowDown', size: 1.2, text: k.x})));
  const key = JSON.stringify(D.levels);
  if (key !== linesKey) {
    plines.forEach((p) => s.removePriceLine(p)); linesKey = key;
    plines = D.levels.map((l) => s.createPriceLine({price: l.p, color: l.c, lineWidth: l.w, lineStyle: l.s, axisLabelVisible: l.t !== '', title: l.t}));
  }
  pos.set((D.boxes || []).map((b) => Object.assign({}, b, {t0: ts(D.day, bucket(b.m0)), t1: b.m1 == null ? null : ts(D.day, bucket(b.m1))})));
  if (fitted !== cur + tf) {
    fitted = cur + tf;
    chart.priceScale('right').applyOptions({autoScale: true});
    const n = s.data().length;
    chart.timeScale().setVisibleLogicalRange({from: Math.max(0, n - 90), to: n + 8});
  }
  if (!hover) legend(lastBar());
  status();
  const T = D.trend, tb = $('trend');
  tb.className = T ? (T.dir < 0 ? 'dn' : T.dir > 0 ? 'up' : '') : 'hidden';
  tb.textContent = T ? T.short : '';
  $('tbl').innerHTML = '<tr><td>CPR Breakout</td><td>' + D.name + '</td></tr>' +
    (D.info || []).map((r) => '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td></tr>').join('');
  $('list').innerHTML = D.rows.map((r) => '<tr>' + r.map((x) => '<td>' + x + '</td>').join('') + '</tr>').join('') ||
    '<tr><td colspan="5">No trades yet today.</td></tr>';
}
async function full() {
  const want = cur, my = ++seq;
  loading = true;
  try {
    const d = await (await fetch('/data?i=' + want + keyq(), {cache: 'no-store'})).json();
    if (want !== cur || my < shown) return;    // an older answer, or for the index shown before: ignore it
    shown = my;
    if (!d.day) { $('st').textContent = 'No data for this index yet.'; return; }
    D = d; draw();
  } catch (e) {
    if (want === cur) $('st').textContent = 'No data: the program is not running (start it in Pydroid 3, or check the server).';
  } finally { loading = false; }
}
async function tick() {                       // every second: the live price only (small); all of it when something new is drawn
  if (!D || loading) return;
  const want = cur;
  let L;
  try { L = await (await fetch('/live?i=' + want + keyq(), {cache: 'no-store'})).json(); } catch (e) { return; }
  if (want !== cur || !D) return;
  if (L.pv && L.pv !== PV) { location.reload(); return; }
  if (L.ver !== D.ver || L.day !== D.day) return full();
  D.live = L.live; D.status = L.status;
  const live = (L.live && L.live.bars) || [];
  if (live.length) {
    const from = bucket(live[0][0]);
    try { for (const b of agg(D.day, D.candles.filter((r) => bucket(r[0]) >= from).concat(live), [])) s.update(b); }
    catch (e) { return full(); }
    if (!hover) legend(lastBar());
  }
  status();
}
let tblOn = innerWidth >= 700;              // the table: shown on a wide screen, behind the Info button on a phone
try { const v = localStorage.getItem('tbl'); if (v) tblOn = v === 'on'; } catch (e) {}
$('tbl').classList.toggle('hidden', !tblOn);
buttons(); full();
setInterval(tick, 1000);
setInterval(() => { if (!loading) full(); }, 60000);
</script></body></html>"""

OPTIONS_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#ffffff"><title>Options</title>
<style>
html,body{height:100%}
body{margin:0;background:#ffffff;color:#131722;font:13px -apple-system,BlinkMacSystemFont,Roboto,Ubuntu,sans-serif;display:flex;flex-direction:column;overflow:hidden}
#bar{display:flex;flex-wrap:wrap;gap:2px;align-items:center;padding:3px 6px;border-bottom:1px solid #e0e3eb}
button{background:transparent;color:#131722;border:0;border-radius:4px;padding:7px 8px;font:inherit}
button.on{color:#2962ff;background:#f0f3fa;font-weight:600}
.sep{width:1px;height:20px;background:#e0e3eb;margin:0 3px}
#info{margin-left:auto;font-size:11px;color:#787b86;text-align:right;line-height:1.3;padding-right:2px}
#main{flex:1;display:flex;min-height:0}
#left{flex:1;display:flex;flex-direction:column;min-width:0}
#head{display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline;padding:4px 8px;border-bottom:1px solid #e0e3eb;min-height:18px;font-size:12px}
#head .nm{font-weight:600;font-size:13px}
#head button{padding:2px 7px;color:#2962ff}
#cw{position:relative;flex:1;min-height:150px}
#c{position:absolute;inset:0}
#side{width:min(48vw,380px);border-left:1px solid #e0e3eb;display:flex;flex-direction:column;min-height:0}
#sidehead{display:flex;flex-wrap:wrap;gap:2px 8px;padding:5px 6px;font-size:11px;color:#787b86;border-bottom:1px solid #e0e3eb}
#chain{flex:1;overflow:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th{position:sticky;top:0;background:#f0f3fa;color:#787b86;font-weight:normal;font-size:11px;padding:5px 3px;z-index:1}
td{padding:7px 4px;text-align:right;border-bottom:1px solid #f0f3fa;font-size:12px;white-space:nowrap}
td.k{text-align:center;font-weight:600;color:#131722}
tr.atm td.k{color:#2962ff}
td.itm{background:#fff8e6}
td.px{cursor:pointer;font-weight:600;color:#131722}
td.px.pe{text-align:left}
td.px small{display:block;font-weight:normal;font-size:10px}
td.sel{box-shadow:inset 0 0 0 2px #2962ff}
.bars{display:flex;height:3px;margin-top:4px;gap:2px}
.bars span{flex:1;display:flex}.bars span:first-child{justify-content:flex-end}
.bars i{display:block;height:3px;border-radius:2px}.bars .cb{background:#f23645}.bars .pb{background:#089981}
tr.spot td{padding:2px 0;text-align:center;border:0}
tr.spot span{display:inline-block;background:#e3effd;color:#131722;border-radius:10px;padding:2px 8px;font-size:11px}
.up{color:#089981!important}.dn{color:#f23645!important}.mut{color:#787b86}
#msg{padding:10px;color:#787b86;font-size:12px}
#head .sig{font-weight:600}
#bell.on{color:#f5a623}
body.table #main{flex-direction:column}
body.table #side{width:auto;border-left:0;border-top:1px solid #e0e3eb;flex:1.3}
body.table #left{flex:1}
body.table td.px.pe{text-align:right}
#tbl{position:absolute;right:72px;top:4px;z-index:3;background:rgba(255,255,255,0.94);border:1px solid #d1d4dc;font-size:11px;max-width:min(430px,calc(100% - 84px));border-collapse:collapse}
#tbl td{padding:3px 7px;border-bottom:1px solid #e0e3eb;border-right:1px solid #e0e3eb;text-align:left;white-space:normal}
#tbl td:first-child{color:#50535e;white-space:nowrap}#tbl td:last-child{color:#f23645;border-right:0}
#tbl tr:first-child td{font-weight:600;color:#131722}
#panel{position:fixed;left:0;right:0;bottom:0;max-height:55%;overflow:auto;background:#ffffff;border-top:1px solid #e0e3eb;z-index:5;box-shadow:0 -4px 16px rgba(0,0,0,0.12)}
#panel h4{margin:8px;font-size:13px}#panel td{text-align:left;font-size:12px}
.hidden{display:none!important}
@media (max-width:699px){                 /* a phone (the app): the chart on top, full width, the chain under it */
#main{flex-direction:column}
#left{flex:none;height:50vh;min-height:250px}
#side{width:auto;border-left:0;border-top:1px solid #e0e3eb;flex:1;min-height:0}
body.table #left{flex:none}
#info{font-size:10px}
#tbl{font-size:10px;right:62px;max-width:calc(100% - 66px)}#tbl td{padding:2px 5px}
}
</style></head><body>
<div id="bar"><button data-i="nifty" class="on">NIFTY</button><button data-i="sensex">SENSEX</button><span class="sep"></span>
<button data-tf="1">1m</button><button data-tf="3">3m</button><button data-tf="5" class="on">5m</button><span class="sep"></span>
<button id="infob">Info</button><button id="tradesb">&#9776; Trades</button><button id="mode">OI table</button><button id="bell" title="BUY CALL / BUY PUT alerts from the option charts">&#128277; alerts off</button><div id="info"></div></div>
<div id="main">
<div id="left"><div id="head"></div><div id="cw"><div id="c"></div><table id="tbl" class="hidden"></table></div></div>
<div id="side"><div id="sidehead"></div><div id="chain"><table><thead id="th"></thead><tbody id="rows"></tbody></table><div id="msg">loading...</div></div></div>
</div>
<div id="panel" class="hidden"><h4>Trades on this chart</h4>
<table><thead><tr><th>Time</th><th>Trade</th><th>Entry</th><th>Stop</th><th>Result</th></tr></thead><tbody id="list"></tbody></table></div>
<script src="/lwc.js"></script>
<script>
const $ = (id) => document.getElementById(id);
const keyq = () => { const k = new URLSearchParams(location.search).get('key'); return k ? '&key=' + encodeURIComponent(k) : ''; };
const fmt = (x) => x == null ? '-' : Number(x).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const big = (x) => { const a = Math.abs(x), s = x < 0 ? '-' : ''; return a >= 1e7 ? s + (a / 1e7).toFixed(2) + 'Cr' : a >= 1e5 ? s + (a / 1e5).toFixed(1) + 'L' : a >= 1e3 ? s + (a / 1e3).toFixed(1) + 'K' : s + a; };
const sg = (x) => (x > 0 ? '+' : '') + fmt(x);
const PV = '%PAGEVER%';                     // this page's version: reload when the server has a newer one
let idx = 'nifty', tf = 5, C = null, sel = null, chainBusy = false, chartBusy = false, fitted = '', lines = [], centred = '';
let table = false, L = null, alertsOn = null;
try { table = localStorage.getItem('optmode') === 'table'; } catch (e) {}
const box = $('c');
const chart = LightweightCharts.createChart(box, {
  layout: {background: {type: 'solid', color: '#ffffff'}, textColor: '#131722', fontSize: 11},
  grid: {vertLines: {color: '#f0f3fa'}, horzLines: {color: '#f0f3fa'}},
  rightPriceScale: {borderColor: '#e0e3eb', scaleMargins: {top: 0.1, bottom: 0.08}},
  timeScale: {timeVisible: true, secondsVisible: false, borderColor: '#e0e3eb', rightOffset: 4},
  crosshair: {mode: 0}, localization: {locale: 'en-IN', priceFormatter: fmt}});
const s = chart.addCandlestickSeries({upColor: '#089981', downColor: '#f23645', borderVisible: false,
  wickUpColor: '#089981', wickDownColor: '#f23645', priceLineStyle: 1});
new ResizeObserver(() => chart.applyOptions({width: box.clientWidth, height: box.clientHeight})).observe(box);
const fmt0 = (n) => Math.abs(n) < 2000 ? fmt(n) : Number(n).toLocaleString('en-IN', {maximumFractionDigits: 0});
const sgn = (n) => (n > 0 ? '+' : n < 0 ? '-' : '') + (Math.abs(n) < 100 ? Math.abs(n).toFixed(1) : Math.round(Math.abs(n)));
// ---- trades as TradingView's long / short position tool ----
function pill(g, x, y, text, bg, right) {
  g.font = '11px -apple-system,Roboto,sans-serif';
  const w = g.measureText(text).width + 10, h = 17, x0 = right ? x - w : x;
  g.fillStyle = bg; g.beginPath();
  if (g.roundRect) g.roundRect(x0, y - h / 2, w, h, 3); else g.rect(x0, y - h / 2, w, h);
  g.fill(); g.fillStyle = '#fff'; g.textBaseline = 'middle'; g.fillText(text, x0 + 5, y + 0.5);
  return w;
}
function hline(g, x1, x2, y, color, dash) {
  if (y == null) return;
  g.strokeStyle = color; g.lineWidth = 1; g.setLineDash(dash); g.beginPath(); g.moveTo(x1, Math.round(y) + 0.5); g.lineTo(x2, Math.round(y) + 0.5); g.stroke(); g.setLineDash([]);
}
class Positions {
  constructor() { this.items = []; }
  attached(p) { this.chart = p.chart; this.series = p.series; this.req = p.requestUpdate; }
  detached() { this.req = null; }
  set(items) { this.items = items || []; if (this.req) this.req(); }
  updateAllViews() {}
  autoscaleInfo() {                          // the price scale always shows an open trade's T1 and stop loss
    const o = this.items.filter((b) => b.t1 == null);
    if (!o.length) return null;
    const v = [].concat(...o.map((b) => [b.e, b.sl, b.sl_now, b.t[0]]));
    return {priceRange: {minValue: Math.min(...v), maxValue: Math.max(...v)}};
  }
  paneViews() {                              // the zones under the candles, the labels over them
    return [{zOrder: () => 'bottom', renderer: () => ({draw: (t) => this.draw(t, false)})},
            {zOrder: () => 'top', renderer: () => ({draw: (t) => this.draw(t, true)})}];
  }
  draw(target, labels) {
    target.useMediaCoordinateSpace(({context: g, mediaSize: sz}) => {
      const tsc = this.chart.timeScale(), y = (p) => (p == null ? null : this.series.priceToCoordinate(p));
      for (const b of this.items) {
        const x1 = tsc.timeToCoordinate(b.t0);
        if (x1 == null) continue;
        const open = b.t1 == null;
        let x2 = open ? sz.width : tsc.timeToCoordinate(b.t1);      // an open trade: on to the price scale
        if (x2 == null || x2 - x1 < 14) x2 = x1 + 14;
        const ye = y(b.e), ys = y(b.sl), y1 = y(b.t[0]), y2 = y(b.t[1]), y3 = y(b.t[2]), yn = y(b.sl_now);
        if (ye == null || ys == null || y1 == null) continue;
        const moved = open && Math.abs(b.sl_now - b.sl) > 0.01, dir = b.side > 0 ? 1 : -1;
        if (!labels) {
          const fill = (ya, yb, c) => { g.fillStyle = c; g.fillRect(x1, Math.min(ya, yb), x2 - x1, Math.abs(yb - ya)); };
          fill(ye, ys, 'rgba(242,54,69,0.22)');
          fill(ye, y1, 'rgba(8,153,129,0.30)');
          if (y3 != null) fill(y1, y3, 'rgba(8,153,129,0.10)');
          hline(g, x1, x2, ye, '#9598a1', []);
          hline(g, x1, x2, y2, 'rgba(8,153,129,0.8)', [4, 3]);
          hline(g, x1, x2, y3, 'rgba(8,153,129,0.8)', [4, 3]);
          if (moved) hline(g, x1, x2, yn, '#f23645', [4, 3]);
          continue;
        }
        const left = x2 - x1 < 110, used = [];       // a narrow box (a recent entry): the labels left of it
        const put = (yy, text, bg) => {              // a label at its price, moved aside if it would cover another
          if (yy == null) return;
          let xx = left ? x1 - 3 : x1 + 3;
          for (const u of used) if (Math.abs(u.y - yy) < 17) xx = left ? Math.min(xx, u.l - 4) : Math.max(xx, u.r + 4);
          const w = pill(g, xx, yy, text, bg, left);
          used.push({y: yy, l: left ? xx - w : xx, r: left ? xx : xx + w});
        };
        put(ye, (b.side > 0 ? 'BUY ' : 'SELL ') + fmt0(b.e) + (open ? '' : '  ' + sgn(b.pnl) + ' pts'), open ? '#2962ff' : '#5d606b');
        const pct = (k) => (b.prob && b.prob[k] != null ? ' ' + b.prob[k] + '%' : '');
        put(y1, 'T1 ' + fmt0(b.t[0]) + ' (' + sgn(dir * (b.t[0] - b.e)) + ')' + pct(0), '#089981');
        if (open || x2 - x1 > 90) {
          put(y2, 'T2 ' + fmt0(b.t[1]) + ' (' + sgn(dir * (b.t[1] - b.e)) + ')' + pct(1), 'rgba(8,153,129,0.8)');
          put(y3, 'T3 ' + fmt0(b.t[2]) + ' (' + sgn(dir * (b.t[2] - b.e)) + ')' + pct(2), 'rgba(8,153,129,0.8)');
        }
        put(ys, 'SL ' + fmt0(b.sl) + ' (' + sgn(dir * (b.sl - b.e)) + ')', '#f23645');
        if (moved) put(yn, stopName(b) + ' ' + fmt0(b.sl_now), stopName(b) === 'BE' ? '#787b86' : '#f23645');
      }
    });
  }
}
function stopName(b) {                      // the stop now: the first one, at the entry (breakeven), or trailing
  const d = (b.side > 0 ? 1 : -1) * (b.sl_now - b.e);
  return Math.abs(d) < 0.01 ? 'BE' : d > 0 ? 'Trailing SL' : 'SL';
}
const pos = new Positions();
s.attachPrimitive(pos);
let tblOn = innerWidth >= 700;              // the table: shown on a wide screen, behind the Info button on a phone
try { const v = localStorage.getItem('opttbl'); if (v) tblOn = v === 'on'; } catch (e) {}
function extras(d) {                        // the info table and the trades list of the chart shown
  const name = sel ? (($('head').querySelector('.nm') || {}).textContent || '') : (C ? C.name : '');
  $('tbl').innerHTML = (d && d.info && d.info.length) ? '<tr><td>CPR Breakout</td><td>' + name + '</td></tr>' +
    d.info.map((r) => '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td></tr>').join('') : '';
  $('tbl').classList.toggle('hidden', !tblOn || !(d && d.info && d.info.length));
  $('infob').classList.toggle('on', tblOn);
  $('list').innerHTML = (d && d.rows && d.rows.length) ? d.rows.map((r) => '<tr>' + r.map((x) => '<td>' + x + '</td>').join('') + '</tr>').join('')
    : '<tr><td colspan="5">No trades on this chart today.</td></tr>';
}
const ts = (day, m) => { const [y, mo, d] = day.split('-').map(Number); return Date.UTC(y, mo - 1, d) / 1000 + m * 60; };
const bucket = (m) => 555 + Math.floor((m - 555) / tf) * tf;
function agg(day, rows) {
  const out = [];
  for (const [m, o, h, l, c] of rows) {
    const t = ts(day, bucket(m)), x = out[out.length - 1];
    if (x && x.time === t) { x.high = Math.max(x.high, h); x.low = Math.min(x.low, l); x.close = c; }
    else out.push({time: t, open: o, high: h, low: l, close: c});
  }
  return out;
}
function setMode() {
  document.body.classList.toggle('table', table);
  $('mode').textContent = table ? 'Chain' : 'OI table';
  $('th').innerHTML = table ? '<tr><th>OI chg</th><th>OI</th><th>CALL</th><th>STRIKE</th><th>PUT</th><th>OI</th><th>OI chg</th></tr>'
                            : '<tr><th>Call LTP</th><th>Strike</th><th style="text-align:left">Put LTP</th></tr>';
  centred = ''; render();
}
function pxCell(o, typ, itm) {
  if (!o) return '<td></td>';
  const chg = o.chg > 0 ? 'up' : o.chg < 0 ? 'dn' : 'mut', on = sel && sel.t === o.t ? ' sel' : '';
  return `<td class="px ${typ.toLowerCase()}${itm ? ' itm' : ''}${on}" data-t="${o.t}" data-typ="${typ}">${fmt(o.ltp)}<small class="${chg}">${o.pct > 0 ? '+' : ''}${o.pct}%</small></td>`;
}
function oiCells(o, typ, itm) {
  if (!o) return '<td></td><td></td>';
  const it = itm ? ' itm' : '', oi = `<td class="${it}">${big(o.oi)}</td>`, doi = `<td class="${it} ${o.doi > 0 ? 'up' : o.doi < 0 ? 'dn' : 'mut'}">${big(o.doi)}</td>`;
  return typ === 'CE' ? doi + oi : oi + doi;
}
function render() {
  if (!C) return;
  if (C.error) { $('msg').textContent = C.error; return; }
  $('msg').textContent = C.live ? '' : 'Market closed: last prices.';
  $('info').innerHTML = `expiry ${C.expiry || '-'}<br>${C.live ? 'live ' : ''}${C.at}`;
  $('sidehead').innerHTML = `<span>PCR <b class="${C.pcr >= 1 ? 'up' : 'dn'}">${C.pcr == null ? '-' : C.pcr}</b></span>` +
    `<span>Call OI wall <b class="dn">${(C.res || 0).toLocaleString('en-IN')}</b></span><span>Put OI wall <b class="up">${(C.sup || 0).toLocaleString('en-IN')}</b></span>`;
  const mx = Math.max(1, ...C.rows.map((r) => Math.max(r.ce ? r.ce.oi : 0, r.pe ? r.pe.oi : 0)));
  let html = '', spotDone = false;
  const cols = table ? 7 : 3;
  for (const r of C.rows) {
    if (!spotDone && r.k > C.spot) {
      html += `<tr class="spot"><td colspan="${cols}"><span>${fmt(C.spot)} | <b class="${C.chg >= 0 ? 'up' : 'dn'}">${sg(C.chg)} (${C.pct}%)</b></span></td></tr>`;
      spotDone = true;
    }
    const kc = `<td class="k">${r.k.toLocaleString('en-IN')}` + (table ? '' : `<div class="bars"><span><i class="cb" style="width:${r.ce ? Math.round(100 * r.ce.oi / mx) : 0}%"></i></span><span><i class="pb" style="width:${r.pe ? Math.round(100 * r.pe.oi / mx) : 0}%"></i></span></div>`) + '</td>';
    html += `<tr class="${r.atm ? 'atm' : ''}">` + (table ? oiCells(r.ce, 'CE', r.k < C.spot) : '') + pxCell(r.ce, 'CE', r.k < C.spot) + kc +
            pxCell(r.pe, 'PE', r.k > C.spot) + (table ? oiCells(r.pe, 'PE', r.k > C.spot) : '') + '</tr>';
  }
  $('rows').innerHTML = html;
  for (const td of document.querySelectorAll('td.px')) td.onclick = () => pick(td.dataset.t, td.dataset.typ);
  const a = document.querySelector('tr.atm');
  if (a && centred !== idx + table) { centred = idx + table; const ch = $('chain'); ch.scrollTop = Math.max(0, a.offsetTop - ch.clientHeight / 2); }
  head();
}
function head() {
  if (!C || C.error) return;
  if (!sel) {
    $('head').innerHTML = `<span class="nm">${C.name}</span><b>${fmt(C.spot)}</b><span class="${C.chg >= 0 ? 'up' : 'dn'}">${sg(C.chg)} (${C.pct}%)</span>` +
      '<span class="mut">tap a call or put price to chart it</span>';
    return;
  }
  const r = C.rows.find((r) => (r.ce && r.ce.t === sel.t) || (r.pe && r.pe.t === sel.t));
  const o = r && (r.ce && r.ce.t === sel.t ? r.ce : r.pe);
  if (!o) return;
  sel.typ = r.ce && r.ce.t === sel.t ? 'CE' : 'PE';
  $('head').innerHTML = `<span class="nm">${o.name}</span><b>${fmt(o.ltp)}</b><span class="${o.chg >= 0 ? 'up' : 'dn'}">${sg(o.chg)} (${o.pct}%)</span>` +
    `<span class="mut">OI ${big(o.oi)} (${o.doi >= 0 ? '+' : ''}${big(o.doi)}) &middot; lot ${C.lot}</span>${sigText()}<button id="back">&#10005; ${C.name} chart</button>`;
  $('back').onclick = () => { sel = null; fitted = ''; L = null; const u = new URL(location.href); u.searchParams.delete('t'); history.replaceState(null, '', u); render(); loadChart(); };
}
function sigText() {
  // the indicator's latest call on this option's chart; a SELL on one side -> buy the other side
  if (!L) return '<span class="mut">indicator: no call on this chart today</span>';
  const other = sel.typ === 'CE' ? 'PE (put)' : 'CE (call)', me = sel.typ === 'CE' ? 'CE (call)' : 'PE (put)';
  const st = L.why ? `${L.why} at ${fmt(L.px)}` : `open, stop ${fmt(L.stop)} &rarr; ${L.side === 'SELL' ? 'buy the ' + other : 'buy this ' + me}`;
  return `<span class="sig ${L.side === 'BUY' ? 'up' : 'dn'}">${L.side} ${L.time} at ${fmt(L.e)} (${L.src}) &middot; ${st}</span>`;
}
function markText(x) {
  if (x === 'B' || x === 'S') return x === 'B' ? 'BUY' : 'SELL';
  if (x === 'SELL' && sel && sel.typ) return 'SELL \u2192 ' + (sel.typ === 'CE' ? 'PE' : 'CE');
  return x;
}
async function bell(change) {
  try {
    const d = await (await fetch('/api/settings?' + (change == null ? '' : 'opt_alerts=' + (change ? 1 : 0)) + keyq(), {cache: 'no-store'})).json();
    alertsOn = !!d.opt_alerts;
  } catch (e) {}
  $('bell').innerHTML = alertsOn ? '&#128276; alerts on' : '&#128277; alerts off';
  $('bell').classList.toggle('on', !!alertsOn);
}
function pick(t, typ) {
  sel = {t, typ, ex: C.ex}; fitted = ''; L = null;
  const u = new URL(location.href); u.searchParams.set('t', t); u.searchParams.set('i', idx); history.replaceState(null, '', u);
  render(); loadChart();
}
async function loadChain() {
  if (chainBusy) return;
  chainBusy = true;
  const want = idx;
  try {
    const d = await (await fetch('/api/options?i=' + want + keyq(), {cache: 'no-store'})).json();
    if (d.pv && d.pv !== PV) { location.reload(); return; }
    if (want !== idx) return;
    const first = !C;
    C = d;
    if (first && !d.error) {
      const t0 = new URLSearchParams(location.search).get('t');
      if (t0 && d.rows.some((r) => (r.ce && r.ce.t === t0) || (r.pe && r.pe.t === t0))) sel = {t: t0, ex: d.ex};
      loadChart();
    }
    render();
  } catch (e) { $('msg').textContent = 'No data: is the program running?'; }
  finally { chainBusy = false; }
}
async function loadChart() {
  if (chartBusy) return;
  chartBusy = true;
  const my = sel ? sel.t : 'index:' + idx;
  try {
    const url = sel ? `/api/optchart?ex=${sel.ex}&t=${sel.t}` : `/api/optchart?t=index&i=${idx}`;
    const d = await (await fetch(url + keyq(), {cache: 'no-store'})).json();
    if ((sel ? sel.t : 'index:' + idx) !== my || d.error) return;
    s.setData(agg(d.day, d.candles));
    L = sel ? d.last || null : null;
    head();
    s.setMarkers((d.marks || []).map((k) => ({time: ts(d.day, bucket(k.m)), position: k.pos, color: k.c, text: markText(k.x),
      shape: k.x === 'B' || k.x === 'BUY' ? 'arrowUp' : k.x === 'S' || k.x === 'SELL' ? 'arrowDown' : 'circle'})));
    pos.set((d.boxes || []).map((b) => Object.assign({}, b, {t0: ts(d.day, bucket(b.m0)), t1: b.m1 == null ? null : ts(d.day, bucket(b.m1))})));
    extras(d);
    const key = JSON.stringify(d.lines || []);
    if (key !== s._lk) {
      lines.forEach((l) => s.removePriceLine(l)); lines = []; s._lk = key;
      for (const l of d.lines || []) lines.push(s.createPriceLine({price: l.p, color: l.c, lineWidth: l.w, lineStyle: l.s, axisLabelVisible: true, title: l.t}));
    }
    if (fitted !== my + tf) { fitted = my + tf; const n = s.data().length; chart.timeScale().setVisibleLogicalRange({from: Math.max(0, n - (tf === 1 ? 120 : 80)), to: n + 3}); }
  } catch (e) {}
  finally { chartBusy = false; }
}
for (const b of document.querySelectorAll('#bar button')) b.onclick = () => {
  if (b.id === 'infob') { tblOn = !tblOn; try { localStorage.setItem('opttbl', tblOn ? 'on' : 'off'); } catch (e) {} $('tbl').classList.toggle('hidden', !tblOn || !$('tbl').innerHTML); b.classList.toggle('on', tblOn); return; }
  if (b.id === 'tradesb') { $('panel').classList.toggle('hidden'); b.classList.toggle('on', !$('panel').classList.contains('hidden')); return; }
  if (b.id === 'bell') { if (alertsOn !== null) bell(!alertsOn); return; }
  if (b.id === 'mode') { table = !table; try { localStorage.setItem('optmode', table ? 'table' : 'chain'); } catch (e) {} setMode(); return; }
  if (b.dataset.i) {
    if (b.dataset.i === idx) return;
    idx = b.dataset.i; sel = null; C = null; fitted = ''; s.setData([]); pos.set([]); extras(null); lines.forEach((l) => s.removePriceLine(l)); lines = []; s._lk = '';
    $('rows').innerHTML = ''; $('msg').textContent = 'loading...'; $('head').innerHTML = ''; $('sidehead').innerHTML = '';
    for (const x of document.querySelectorAll('#bar button[data-i]')) x.classList.toggle('on', x === b);
    const u = new URL(location.href); u.searchParams.delete('t'); u.searchParams.set('i', idx); history.replaceState(null, '', u);
    loadChain();
  } else {
    tf = +b.dataset.tf; fitted = '';
    for (const x of document.querySelectorAll('#bar button[data-tf]')) x.classList.toggle('on', x === b);
    loadChart();
  }
};
const i0 = new URLSearchParams(location.search).get('i');
if (i0 === 'sensex') { idx = 'sensex'; for (const x of document.querySelectorAll('#bar button[data-i]')) x.classList.toggle('on', x.dataset.i === idx); }
setMode();
bell();
loadChain();
setInterval(loadChain, 3000);
setInterval(loadChart, 3000);
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

CHART_PAGE = {}

def chart_page(var='CHART_HTML'):
    """CHART_HTML (or OPTIONS_HTML), read again from this file whenever the file changes (on a server, a change to
    the page shows without restarting the program)."""
    src = os.path.abspath(__file__)
    P = CHART_PAGE.setdefault(var, {})
    try:
        mt = os.path.getmtime(src)
        if P.get('mt') != mt:
            import ast
            with open(src, encoding='utf-8') as f:
                tree = ast.parse(f.read())
            html = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                        and getattr(n.targets[0], 'id', '') == var)
            P.update(mt=mt, html=html)
    except Exception:
        pass
    html = P.get('html', globals()[var])
    if P.get('src') is not html:
        import hashlib
        P.update(src=html, pv=hashlib.sha256(html.encode()).hexdigest()[:10])
    return html.replace('%PAGEVER%', P['pv'])

def page_ver(var):
    """The version of the page now in this file: a page open in a phone reloads itself when it changes."""
    chart_page(var)
    return CHART_PAGE[var]['pv']

def serve_chart(names):
    """Serve the chart page: on this phone / computer only (127.0.0.1), or as set by CPRB_CHART_HOST on a server."""
    import http.server
    import threading
    if CHART_SERVER:
        return True
    idx = json.dumps([[n, SPEC[n]['name']] for n in names])
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
            pth = self.path.split('?')[0]
            if pth == '/web':                          # the app's screens in a web browser (data still needs the key)
                self.send_response(302)
                self.send_header('Location', '/web/' + (self.path[4:] if '?' in self.path else ''))
                self.end_headers()
                return
            if pth.startswith('/web/'):
                name = pth[5:] or 'index.html'
                kinds = {'index.html': 'text/html; charset=utf-8', 'app.js': 'application/javascript',
                         'boot.js': 'application/javascript', 'ota-ver.js': 'application/javascript', 'style.css': 'text/css'}
                fp = os.path.join(APP_WWW, name)
                if name in kinds and os.path.exists(fp):
                    with open(fp, 'rb') as f:
                        body = f.read()
                    self.send_response(200)
                    self.send_header('Content-Type', kinds[name])
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()
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
            elif self.path.startswith('/live'):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                d = CHART_DATA.get(q.get('i', [names[0]])[0], {})
                body = json.dumps(dict(ver=d.get('ver'), day=d.get('day'), status=d.get('status'), updated=d.get('updated'),
                                       live=live_part(q.get('i', [names[0]])[0], d) if d else None, pv=page_ver('CHART_HTML'))).encode()
                ctype = 'application/json'
            elif self.path.startswith('/app/ota.json'):
                body, ctype = json.dumps(app_ota()).encode(), 'application/json'
            elif self.path.startswith('/api/state'):
                body, ctype = json.dumps(app_state()).encode(), 'application/json'
            elif self.path.startswith('/api/events'):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                since = int((q.get('since') or ['0'])[0] or 0)
                st = app_settings()
                body, ctype = json.dumps(dict(last=EVENTS[-1]['id'] if EVENTS else 0,
                                              events=[e for e in EVENTS if e['id'] > since and shown_event(e, st)][-50:])).encode(), 'application/json'
            elif self.path.startswith('/api/settings'):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                ch = {k: q[k][0] == '1' for k in ('opt_alerts',) if k in q}
                body, ctype = json.dumps(app_settings(**ch)).encode(), 'application/json'
            elif self.path.startswith('/api/history'):
                body, ctype = json.dumps(history_all()).encode(), 'application/json'
            elif self.path.startswith('/api/options'):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                n = q.get('i', ['nifty'])[0]
                try:
                    body = json.dumps(dict(option_chain(n if n in OPT_IDS else 'nifty'), pv=page_ver('OPTIONS_HTML'))).encode()
                except Exception as e:
                    body = json.dumps(dict(error=f"option chain not available ({e})")).encode()
                ctype = 'application/json'
            elif self.path.startswith('/api/optchart'):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                ex, t = q.get('ex', ['NSE'])[0], q.get('t', [''])[0]
                try:
                    if t == 'index':
                        body = json.dumps(index_chart(q.get('i', ['nifty'])[0])).encode()
                    elif ex not in ('NSE', 'BSE') or not t.isdigit():
                        raise ValueError('which contract?')
                    else:
                        body = json.dumps(option_chart(ex, t)).encode()
                except Exception as e:
                    body = json.dumps(dict(error=f"chart not available ({e})")).encode()
                ctype = 'application/json'
            elif self.path.split('?')[0] == '/options':
                body, ctype = chart_page('OPTIONS_HTML').encode(), 'text/html; charset=utf-8'
            else:
                body, ctype = chart_page().replace('%INDICES%', idx).encode(), 'text/html; charset=utf-8'
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
        if OIWALL_CALLS.get(n):
            try:
                out[n]['walls'] = oi_walls(n, out[n]['prev'])
            except Exception as e:
                print(f"  {SPEC[n]['name']}: yesterday's option OI not available ({e}); no OI WALL calls today")
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
        oi_recorder(names)
        option_alerts(names)
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
