"""Line-by-line Python mirror of tradingview/combo4.pine, to check it reproduces combine_test.py."""
import json, collections, statistics as st
raw = json.load(open('../.cache/nifty_1m.json'))
by = collections.defaultdict(list)
for k in sorted(raw):
    hm = k[11:16]
    if '09:15' <= hm < '15:30': by[k[:10]].append((int(hm[:2]) * 60 + int(hm[3:]), *raw[k]))
days = [d for d in sorted(by) if len(by[d]) >= 300]
COST = 4.0; WIN = 30
T = []   # trades: dict
ranges, dHi, dLo = [], [], []
def exit5(side, stp, tgt, o, h, l, c):
    a, b = (h, l) if abs(h - o) < abs(o - l) else (l, h)
    for px in (o, a, b):
        if side * (px - stp) <= 0: return stp
        if tgt is not None and side * (px - tgt) >= 0: return tgt
    return None
prevday = None
for d in days:
    b1 = by[d]
    b5 = []
    for i in range(0, len(b1), 5):
        ch = b1[i:i + 5]
        b5.append(dict(m=ch[0][0], o=ch[0][1], h=max(x[2] for x in ch), l=min(x[3] for x in ch), c=ch[-1][4], ones=ch))
    U = st.median(ranges[-20:]) if len(ranges) >= 10 else None
    if prevday is not None:
        pdh, pdl = prevday
    if U is not None and prevday is not None:
        sg = []                                   # today's signals (strat, minute, side)
        def new(st_, side, m, e, s, tg, bi):
            t = dict(st=st_, side=side, m=m, e=e, s=s, tg=tg, open=True, x=None, take=-1, bar=bi, day=d); T.append(t); sg.append((st_, m, side)); return t
        # FP state
        fair = None; fp = None; loss = 0; stopped = False; swH = swL = None; H, L_, C = [], [], []
        fpSL = 0.4 * U; fpTP = 3 * fpSL
        # LT
        lt = None; hU = lU = False
        # BR
        br = None; brN = 0; brBest = 0.0; brRisk = None
        lv = [[pdh, 1, 0, 0], [pdl, -1, 0, 0]]
        # LV levels
        cand = sorted(dHi + dLo); aP = []
        cp = None; cn = 0
        for p in cand:
            if cp is not None and p - cp <= 0.1 * U: cp = (cp * cn + p) / (cn + 1); cn += 1
            else:
                if cp is not None and cn >= 2: aP.append([cp, cn, 0, 0])
                cp, cn = p, 1
        if cp is not None and cn >= 2: aP.append([cp, cn, 0, 0])
        lvT = None; lvN = 0
        for bi, b in enumerate(b5):
            barsToday = bi + 1; mins = b['m']; o, h, l, c = b['o'], b['h'], b['l'], b['c']
            new_this_bar = []
            # FP replay
            for (bm, bo, bh, bl, bc) in b['ones']:
                if fp is not None:
                    s = fp['side']; p1, p2 = (bl, bh) if bc >= bo else (bh, bl); hit = None
                    for px in (bo, p1, p2):
                        if s * (px - fp['s']) <= 0: hit = fp['s']; break
                        if s * (px - fp['tg']) >= 0: hit = fp['tg']; break
                    if hit is not None:
                        g = s * (hit - fp['e']); fp.update(open=False, x=hit); fp = None
                        if g < 0:
                            loss += 1; stopped = stopped or loss >= 2
                        elif g > 0: loss = 0
                if fair is None: fair = bo
                if fp is not None and bm >= 915:
                    g = fp['side'] * (bc - fp['e']); fp.update(open=False, x=bc); fp = None
                    if g < 0:
                        loss += 1; stopped = stopped or loss >= 2
                    elif g > 0: loss = 0
                H.append(bh); L_.append(bl); C.append(bc); n = len(C)
                if n == 1: continue
                if n >= 5:
                    mh, ml = H[n - 3], L_[n - 3]
                    if all(ml < L_[j] for j in (n - 5, n - 4, n - 2, n - 1)): swL = ml
                    if all(mh > H[j] for j in (n - 5, n - 4, n - 2, n - 1)): swH = mh
                if fp is not None or stopped or bm < 555 or bm >= 645: continue
                gap = fair - bc; dd = 1 if gap > 0 else -1
                if abs(gap) >= 0.8 * fpTP:
                    pc = C[n - 2]
                    bos = (swH is not None and bc > swH >= pc) if dd > 0 else (swL is not None and bc < swL <= pc)
                    if bos:
                        fp = new(0, dd, bm, bc, bc - dd * fpSL, bc + dd * fpTP, bi); new_this_bar.append(fp)
            # manage
            if lt is not None and lt['bar'] < bi:
                px = exit5(lt['side'], lt['s'], lt['tg'], o, h, l, c)
                if px is not None: lt.update(open=False, x=px); lt = None
                elif mins >= 915: lt.update(open=False, x=c); lt = None
            if br is not None and br['bar'] < bi:
                s, e = br['side'], br['e']; px = exit5(s, br['s'], None, o, h, l, c)
                if px is not None: br.update(open=False, x=px); br = None
                elif mins >= 915: br.update(open=False, x=c); br = None
                else:
                    brBest = max(brBest, s * (c - e)); stp = br['s']
                    stp = max(stp, e + brBest - 0.6 * U) if s > 0 else min(stp, e - brBest + 0.6 * U)
                    if brBest >= 0.5 * brRisk: stp = max(stp, e) if s > 0 else min(stp, e)
                    br['s'] = stp
            if lvT is not None and lvT['bar'] < bi:
                px = exit5(lvT['side'], lvT['s'], lvT['tg'], o, h, l, c)
                if px is not None: lvT.update(open=False, x=px); lvT = None
                elif mins >= 915: lvT.update(open=False, x=c); lvT = None
            inWin = 570 <= mins < 870
            pc5 = b5[bi - 1]['c'] if bi else None
            # LT
            if lt is None and inWin and barsToday > 3:
                SW = 0.08 * U; sig = 0
                if not hU and h > pdh + SW and c < pdh and pc5 <= pdh: sig = -1; hU = True
                elif not lU and l < pdl - SW and c > pdl and pc5 >= pdl: sig = 1; lU = True
                if sig: lt = new(1, sig, mins, c, c - sig * 0.6 * U, c + sig * 0.25 * U, bi); new_this_bar.append(lt)
            # BR levels
            if barsToday == 3:
                lv.append([max(x['h'] for x in b5[:3]), 1, 0, 0]); lv.append([min(x['l'] for x in b5[:3]), -1, 0, 0])
            if barsToday >= 5:
                w = b5[bi - 4:bi + 1]; mid = w[2]
                if all(mid['h'] > x['h'] for k, x in enumerate(w) if k != 2): lv.append([mid['h'], 1, 0, 0])
                if all(mid['l'] < x['l'] for k, x in enumerate(w) if k != 2): lv.append([mid['l'], -1, 0, 0])
            expandOK = barsToday > 6 and (h - l) >= 1.5 * st.mean(x['h'] - x['l'] for x in b5[bi - 6:bi])
            brSig = 0
            for z in lv:
                Lp, dd, s_ = z[0], z[1], z[2]
                if s_ == 0:
                    if ((c > Lp and pc5 is not None and pc5 <= Lp) if dd > 0 else (c < Lp and pc5 is not None and pc5 >= Lp)) and expandOK: z[2], z[3] = 1, 0
                    continue
                if s_ != 1: continue
                if (c < Lp - 0.1 * U) if dd > 0 else (c > Lp + 0.1 * U): z[2] = 2; continue
                if (l <= Lp + 0.12 * U) if dd > 0 else (h >= Lp - 0.12 * U): z[3] = 1
                if z[3] == 1 and brSig == 0 and ((c > Lp and c > b5[bi - 1]['h']) if dd > 0 else (c < Lp and c < b5[bi - 1]['l'])): brSig = dd; z[3] = 0
            if brSig and br is None and inWin and brN < 3:
                brN += 1; brRisk = 0.3 * U; brBest = 0.0
                br = new(2, brSig, mins, c, c - brSig * brRisk, None, bi); new_this_bar.append(br)
            # LV
            rngB = h - l
            sU = c > o and rngB > 0 and (c - o) >= 0.6 * rngB and (c - l) >= 0.75 * rngB
            sD = c < o and rngB > 0 and (o - c) >= 0.6 * rngB and (h - c) >= 0.75 * rngB
            if lvT is None and inWin and lvN < 3 and barsToday > 1 and aP:
                best = -1; bestS = -1; bestD = 0
                for j, z in enumerate(aP):
                    if z[1] > bestS:
                        if z[2] == 0 and pc5 <= z[0] and c > z[0] + 0.03 * U and sU: best, bestS, bestD = j, z[1], 1
                        elif z[3] == 0 and pc5 >= z[0] and c < z[0] - 0.03 * U and sD: best, bestS, bestD = j, z[1], -1
                if best >= 0:
                    lvl = aP[best][0]
                    if bestD > 0: aP[best][2] = 1
                    else: aP[best][3] = 1
                    stopPx = lvl - bestD * 0.12 * U; risk = bestD * (c - stopPx)
                    if 0.05 * U <= risk <= 0.8 * U:
                        tgt = c + bestD * 2 * risk
                        cands = [z[0] for z in aP if bestD * (z[0] - c) >= 2 * risk]
                        if cands: tgt = min(cands, key=lambda q: abs(q - c))
                        lvN += 1; lvT = new(3, bestD, mins, c, stopPx, tgt, bi); new_this_bar.append(lvT)
            # decide
            for t in new_this_bar:
                t['take'] = 0 if any(u[0] != t['st'] and 0 <= t['m'] - u[1] <= WIN and u[2] != t['side'] for u in sg) else 1
        for t in (fp, lt, br, lvT):
            if t is not None and t['open']: t.update(open=False, x=b5[-1]['c'])
    # end of day bookkeeping
    am = [x for x in b1 if x[0] < 645]
    ranges.append(max(x[2] for x in am) - min(x[3] for x in am))
    dHi.append(max(x[2] for x in b1)); dLo.append(min(x[3] for x in b1))
    dHi, dLo = dHi[-15:], dLo[-15:]
    prevday = (max(x[2] for x in b1), min(x[3] for x in b1))
names = ['Fair Price Reversal', 'Liquidity Trap', 'Breakout Retest', '15-Day Levels']
start = '2023-02-06'
TT = [t for t in T if t['day'] >= start]
for k, n in enumerate(names):
    print(f"{n:22s} base {sum(t['side'] * (t['x'] - t['e']) - COST for t in TT if t['st'] == k):+,.0f} ({sum(1 for t in TT if t['st'] == k)} trades)")
tk = [t for t in TT if t['take'] == 1]
yrs = collections.defaultdict(float)
for t in tk: yrs[t['day'][:4]] += t['side'] * (t['x'] - t['e']) - COST
print('TAKEN (skip conflicts):', f"{sum(t['side'] * (t['x'] - t['e']) - COST for t in tk):+,.0f}", {y: round(v) for y, v in sorted(yrs.items())}, 'last 90:', round(sum(t['side'] * (t['x'] - t['e']) - COST for t in tk if t['day'] >= '2026-07-03')))
