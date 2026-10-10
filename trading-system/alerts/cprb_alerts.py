#!/usr/bin/env python3
"""CPR Breakout alerts for Nifty and Sensex: live, free, no TradingView and no login needed.

Follows the same rules as tradingview/cpr_breakout.pine (its default settings) on live 1-minute candles from
Upstox's free public candle data. It tells you when to BUY (a call) or SELL (a put), where the stop is, when to
book half and when to exit: on this screen, and on your phone through Telegram if you set that up (free).

    python cprb_alerts.py                       run today: start it any time before 9:15, leave it running
    python cprb_alerts.py --replay 2026-10-09   replay a past day in a few seconds, to see what it does
    python cprb_alerts.py --plan                only print the next session's plan (levels and trigger prices)
    python cprb_alerts.py --telegram-test       send a test message to your phone
    python cprb_alerts.py --telegram-chat-id    find your Telegram chat id (message your bot first)
On a phone (Pydroid 3) just press Run: the settings below do the same (REPLAY_DAY for a replay).

Needs Python 3.8 or newer and nothing else. The settings are just below.
Times are the 1-minute candle in which something happened; the alert comes when that candle closes.
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

# ---------------- settings ----------------
INDICES = ['nifty', 'sensex']     # or ['nifty'] / ['sensex']
LOTS = 5                          # lots per trade, only for the rupee estimates (option moves about half the index)
LADDER = False                    # volume-line ladder: at the next line book half, stop to the broken line, ride on
TELEGRAM_TOKEN = ''               # from @BotFather in Telegram (see the guide); leave empty for screen only
TELEGRAM_CHAT_ID = ''             # found by itself once you've messaged your bot; then put it here
REPLAY_DAY = ''                   # e.g. '2026-10-08' to replay a past day instead of running live

# ---------------- fixed rules (as tested on 2026) ----------------
SPEC = {
    'nifty':  dict(name='NIFTY',  key='NSE_INDEX|Nifty 50', bin=5.0,  cost=4.0,  lot=65, step=50),
    'sensex': dict(name='SENSEX', key='BSE_INDEX|SENSEX',   bin=16.0, cost=12.0, lot=20, step=100),
}
BEES = 'NSE_EQ|INF204KB14I2'      # NIFTYBEES: its volume stands in for the index's (an index has no volume)
OPEN, RANGE_END, CUTOFF, VOL_END, OUT, CLOSE = 555, 570, 600, 870, 915, 930   # minutes from midnight
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cprb_cache.json')


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

def fetch_today(key):
    q = urllib.parse.quote(key, safe='')
    try:
        rows = http_json(f"https://api.upstox.com/v3/historical-candle/intraday/{q}/minutes/1", tries=2)['data']['candles']
    except Exception:
        rows = http_json(f"https://api.upstox.com/v2/historical-candle/intraday/{q}/1minute", tries=2)['data']['candles']
    return parse(rows)

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


# ---------------- levels: CPR, 30-day volume POC, 3-day volume lines ----------------
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

def context(spec, sess, vol, today):
    """Everything known before the open. sess: {date: [(minute, o, h, l, c)]}, vol: {date: {minute: NIFTYBEES volume}}."""
    days = sorted(d for d in sess if d < today and len(sess[d]) >= 300)[-60:]
    if len(days) < 31:
        raise SystemExit(f"Not enough earlier sessions ({len(days)}); need 31.")
    D = {d: (sess[d][0][1], max(x[2] for x in sess[d]), min(x[3] for x in sess[d]), sess[d][-1][4]) for d in days}
    lv = levels(*D[days[-1]][1:])
    past = [levels(*D[d][1:])['w'] for d in days[-21:-1]]
    rank = sum(x < lv['w'] for x in past) / 20
    ylv = levels(*D[days[-2]][1:])
    H = {d: day_hist(sess[d], vol.get(d, {}), spec['bin']) for d in days[-30:]}
    poc, vah, val = poc_va(*combine([H[d] for d in days[-30:]]), spec['bin'])
    return dict(spec, today=today, prev=days[-1], lv=lv, rank=rank, narrow=rank < 1 / 3,
                rel=1 if lv['bot'] > ylv['top'] else -1 if lv['top'] < ylv['bot'] else 0,
                yc=D[days[-1]][3], poc=poc, vah=vah, val=val,
                lines=vol_lines(*combine([H[d] for d in days[-3:]]), spec['bin']))


# ---------------- the trades, on 1-minute candles ----------------
def path(o, h, l, c):
    """Order of prices inside a 1-minute candle: green open-low-high-close, red open-high-low-close."""
    return (o, l, h, c) if c >= o else (o, h, l, c)

def done(m, px, why, pnl):
    return dict(m=m, px=px, why=why, pnl=pnl)

def run_magnet(c1, side, e, edge, over, cost):
    """Stop 0.3%; book half at 0.25 x the risk and move the stop to entry; the rest to the CPR edge; out by 3:15."""
    R = 0.3 / 100 * e
    stp = e - side * R
    t1 = e + side * 0.25 * R
    half, ev = None, []
    for m, o, h, l, c in c1:
        if m < 556:
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

def run_breakout(c1, side, e, start, stp, over, cost):
    """Book half at 0.25 x the risk and move the stop to entry; after +1R trail the stop 1R behind the best price."""
    R = side * (e - stp)
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

def plan_trades(cx, c1, upto, over):
    """Daily plan: narrow-CPR day -> breakout; other day -> CPR Magnet at 9:16 if the open qualifies, else breakout."""
    if not c1:
        return []
    lv, poc, cost = cx['lv'], cx['poc'], cx['cost']
    if not cx['narrow']:
        o, e = c1[0][1], c1[0][4]
        side = -1 if o > lv['top'] else 1 if o < lv['bot'] else 0
        if side:
            edge = lv['top'] if side < 0 else lv['bot']
            if side * (edge - e) >= 0.002 * e and side * (e - poc) > 0:
                r = run_magnet(c1, side, e, edge, over, cost)
                return [dict(src='MAGNET', side=side, m=556, known=556, e=e, stp0=e - side * 0.3 / 100 * e,
                             t1=e + side * 0.25 * 0.3 / 100 * e, edge=edge, **r)]
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
        if side == -cx['rel'] or gap != side or side * (e - poc) <= 0:
            continue
        stp = orl if side > 0 else orh
        if side * (e - stp) <= 0:
            continue
        r = run_breakout(c1, side, e, start, stp, over, cost)
        out = [dict(src='BREAKOUT', side=side, m=m, known=m + 1, e=e, stp0=stp, R=side * (e - stp), **r)]
        if r['exit'] and r['exit']['pnl'] <= 0:          # the break failed: one trade the other way
            for s2, e2, st2, m2 in touches(c1, orh, orl, r['exit']['m'] + 1):
                if m2 >= CUTOFF:
                    break
                if s2 != -side or s2 * (e2 - poc) <= 0:
                    continue
                stp2 = orl if s2 > 0 else orh
                if s2 * (e2 - stp2) <= 0:
                    break
                r2 = run_breakout(c1, s2, e2, st2, stp2, over, cost)
                out.append(dict(src='REVERSAL', side=s2, m=m2, known=m2 + 1, e=e2, stp0=stp2, R=s2 * (e2 - stp2), **r2))
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
            if side * (e - stp) <= 0 or side * (tgt - e) < 1.5 * side * (e - stp):
                break
            tgt2 = nxt[1] if ladder and len(nxt) > 1 else None
            r = run_vol(c1, side, e, m0 + 5, stp, tgt, x, tgt2, over, cost)
            out.append(dict(src='VOLUME LINE', side=side, m=m0 + 5, known=m0 + 5, e=e, stp0=stp, tgt=tgt, tgt2=tgt2, x=x, **r))
            if r['exit'] is None:
                return out
            free = r['exit']['m'] + 1
            break
    return out

def day_trades(cx, c1, upto, over=False, ladder=False):
    """Every signal of the day so far, and which were taken: one trade at a time, whichever came first."""
    ts = plan_trades(cx, c1, upto, over) + vol_trades(cx, c1, upto, over, ladder)
    ts.sort(key=lambda t: (t['m'], t['src'] == 'VOLUME LINE'))
    free = 0
    for t in ts:
        t['taken'] = t['m'] >= free
        if t['taken']:
            free = t['exit']['m'] + 1 if t['exit'] else 10 ** 9
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

def plan_text(cx):
    lv, poc, nm = cx['lv'], cx['poc'], cx['name']
    out = [f"{nm} plan for the session after {cx['prev']}",
           f"CPR {f2(lv['bot'])} - {f2(lv['top'])}, pivot {f2(lv['p'])}: " +
           ("NARROW (breakout day)" if cx['narrow'] else "not narrow"),
           f"30-day volume POC {f2(poc)} (value area {f2(cx['val'])} - {f2(cx['vah'])}): buys only above it, sells only below.",
           "Today's CPR vs yesterday's: " + ("higher -> no breakout SELLs" if cx['rel'] > 0 else
                                             "lower -> no breakout BUYs" if cx['rel'] < 0 else "overlapping -> both ways"),
           f"Yesterday's close {f2(cx['yc'])}: open above it -> breakout BUYs only; below -> SELLs only."]
    if cx['narrow']:
        out.append("9:30-10:00 BREAKOUT: BUY on a touch of the 9:15-9:30 high / SELL on a touch of its low (filters "
                   "above). Stop at the other side of the range; book half at 0.25x the risk, stop to entry, trail the rest.")
    else:
        sell, buy = lv['top'] / 0.998, lv['bot'] / 1.002
        out.append(f"9:16 CPR MAGNET: SELL if the 9:15 candle opens above {f2(lv['top'])} and closes at or above {f2(sell)}"
                   + (f" and below the POC {f2(poc)}" if sell < poc else " (not possible today: the POC is below that)") +
                   f"; BUY if it opens below {f2(lv['bot'])} and closes at or below {f2(buy)}"
                   + (f" and above the POC {f2(poc)}" if buy > poc else " (not possible today: the POC is above that)") +
                   ". Stop 0.3%, book half at 0.25x the risk, rest to the CPR edge. Otherwise the breakout plan (9:30-10:00).")
    out.append(f"3-day volume lines: {', '.join(f2(x) for x in cx['lines'])}. 9:30-2:30: a 5-minute close through a line "
               "-> trade toward the next line, stop at the previous line, only if the next line is at least 1.5x the stop "
               "away. One trade at a time." + (" Ladder on." if LADDER else ""))
    return '\n'.join(out)

def range_note(cx, c1):
    """At 9:30: which breakout trade is still possible today."""
    first = [x for x in c1 if x[0] < RANGE_END]
    orh, orl = max(x[2] for x in first), min(x[3] for x in first)
    gap = c1[0][1] - cx['yc']
    gap = 1 if gap > 0 else -1 if gap < 0 else 0
    if gap == 0 or gap == -cx['rel']:
        return f"{cx['name']} 15-minute range {f2(orl)} - {f2(orh)}. No breakout trade today (" + \
               ("flat open" if gap == 0 else "the opening gap is against today's CPR vs yesterday's") + "). Volume-line trades only."
    lvl, word = (orh, 'BUY') if gap > 0 else (orl, 'SELL')
    other = orl if gap > 0 else orh
    pocok = gap * (lvl - cx['poc']) > 0
    return (f"{cx['name']} 15-minute range {f2(orl)} - {f2(orh)}. Until 10:00: {word} when price touches {f2(lvl)}"
            + ("" if pocok else f" (only if price is {'above' if gap > 0 else 'below'} the POC {f2(cx['poc'])} then)") +
            f", stop {f2(other)}, book half at {f2(lvl + gap * 0.25 * abs(lvl - other))}.")

def messages(cx, ts, c1, upto, lots):
    """(id, minute known, text, important) for everything that has happened so far."""
    nm, out = cx['name'], []
    plan = [t for t in ts if t['src'] != 'VOLUME LINE']
    if c1 and not cx['narrow'] and upto >= 556 and not any(t['src'] == 'MAGNET' for t in plan):
        out.append(('nomag', 556, f"{nm} 9:16: no CPR Magnet trade today; breakout plan from 9:30.", False))
    if c1 and upto >= RANGE_END - 1 and not any(t['src'] == 'MAGNET' for t in plan):
        out.append(('range', RANGE_END, range_note(cx, c1), True))
        if upto >= CUTOFF and not plan:
            out.append(('nobo', CUTOFF, f"{nm} 10:00: no breakout trade. Volume-line trades only from now (till 2:30).", False))
    for t in ts:
        sd = 'BUY' if t['side'] > 0 else 'SELL'
        tid = (t['src'], t['m'])
        if not t['taken']:
            out.append((tid + ('skip',), t['known'], f"{nm} {hhmm(t['m'])} {t['src']} {sd} signal at {f2(t['e'])} skipped: "
                        "another trade is still open.", False))
            continue
        if t['src'] == 'MAGNET':
            how = (f"Stop {f2(t['stp0'])} (0.3%). Book half at {f2(t['t1'])}, then stop to entry; "
                   f"rest to the CPR edge {f2(t['edge'])}.")
        elif t['src'] == 'VOLUME LINE':
            how = (f"5-minute close through the line {f2(t['x'])}. Stop {f2(t['stp0'])} (previous line). "
                   f"Target {f2(t['tgt'])} (next line)" +
                   (f": book half there, move the stop to {f2(t['x'])}, rest to {f2(t['tgt2'])}." if t['tgt2'] else "."))
        else:
            how = (("Reversal after the failed break. " if t['src'] == 'REVERSAL' else "") +
                   f"Stop {f2(t['stp0'])} (other side of the 15-minute range). Book half at "
                   f"{f2(t['e'] + t['side'] * 0.25 * t['R'])}, then stop to entry; after {f2(t['e'] + t['side'] * t['R'])} "
                   "trail the stop 1R behind the best price.")
        out.append((tid + ('in',), t['known'], f"{nm} {hhmm(t['m'] if t['src'] != 'MAGNET' else 556)} {t['src']} {sd} at "
                    f"{f2(t['e'])} -> {option(cx, t['side'], t['e'])}. {how}", True))
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
        return
    try:
        data = urllib.parse.urlencode({'chat_id': TELEGRAM_CHAT_ID, 'text': text}).encode()
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=data), timeout=15)
    except Exception as e:
        print(f"  (Telegram message failed: {e})")

def alert(text, push=True):
    print(('\a>>> ' if push else '    ') + text, flush=True)
    if push:
        telegram(text)

def now_ist():
    return dt.datetime.now(IST)


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
        out[n] = context(SPEC[n], sess, vol, today)
    return out

def replay(names, day, lots, ladder):
    cxs = load(names, day)
    rows = {n: fetch_range(SPEC[n]['key'], dt.date.fromisoformat(day), dt.date.fromisoformat(day)).get(day, {}) for n in names}
    for n in names:
        cx = cxs[n]
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

def live(names, lots, ladder, plan_only=False):
    now = now_ist()
    today = str(now.date())
    print(f"CPR Breakout alerts, {now:%Y-%m-%d %H:%M} IST. Loading earlier sessions ...")
    cxs = load(names, today)
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID and not plan_only:
        telegram("CPR Breakout alerts started. The plan follows.")
    for n in names:
        alert(plan_text(cxs[n]), push=not plan_only)
    if plan_only:
        return
    if now.weekday() >= 5:
        print("Market closed today (weekend). The plan above is for the next session.")
        return
    seen, first, last_ts, waited = set(), True, {}, False
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
        for n in names:
            cx = cxs[n]
            try:
                rows = fetch_today(cx['key']).get(today, {})
            except Exception as e:
                print(f"  {cx['name']}: data error ({e}); trying again next minute")
                continue
            c1 = [(m,) + tuple(rows[m][:4]) for m in sorted(rows) if m <= upto]
            if not c1:
                if mnow >= OPEN + 10:
                    print(f"  {cx['name']}: no candles yet today ({hhmm(mnow)}). Market holiday or a data problem?")
                continue
            if c1[-1][0] < upto and now.second < 40:
                late = True                                   # the last minute isn't in yet: look again soon
                continue
            got = min(upto, c1[-1][0])                        # data complete up to here (the source can lag)
            ts = day_trades(cx, c1, got, got == CLOSE - 1, ladder)
            last_ts[n] = ts
            for mid, mk, text, push in messages(cx, ts, c1, got, lots):
                if (n, mid) in seen:
                    continue
                seen.add((n, mid))
                if first and mk < got - 1:
                    print('    [earlier today] ' + text)
                else:
                    alert(text, push)
            print(f"  {hhmm(mnow)} {cx['name']} {f2(c1[-1][4])} (data to {hhmm(c1[-1][0])}) | {open_note(cx, ts)}", flush=True)
        first = False if not late else first
        if mnow >= CLOSE:
            for n in names:
                if n in last_ts:
                    alert(day_summary(cxs[n], last_ts[n], lots))
            print("Market closed. Run it again tomorrow before 9:15.")
            return
        now = now_ist()
        time.sleep(5 if late else max(2, 63 - now.second))

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

if __name__ == '__main__':
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
        telegram("Test from cprb_alerts.py: alerts will arrive here.")
        print("Sent. If nothing arrives, check TELEGRAM_TOKEN and TELEGRAM_CHAT_ID at the top of the file.")
    elif '--telegram-chat-id' in args:
        pass                                          # telegram_setup() above printed it
    else:
        live(names, lots, ladder, plan_only='--plan' in args)
