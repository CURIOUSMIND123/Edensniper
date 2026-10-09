"""CPR and floor pivots: which situations repeat, and what the day did after them.

    python cpr_study.py nifty        (or sensex)

CPR from the previous day's high, low and close: pivot P = (H + L + C) / 3, BC = (H + L) / 2, TC = 2P - BC.
Width = (top - bottom) / P. Pivots: R1 = 2P - L, S1 = 2P - H, R2 = P + (H - L), S2 = P - (H - L).
"Narrow" means today's width is in the narrowest third of the last 20 days. Prints the same tables for the last
60 sessions, the 30 sessions before them, and every day since 2023.
"""
import json, collections, statistics as st, sys
name = sys.argv[1] if len(sys.argv) > 1 else 'nifty'
raw = json.load(open(f'../.cache/{name}_1m.json'))
by = collections.defaultdict(list)
for k in sorted(raw):
    hm = int(k[11:13]) * 60 + int(k[14:16])
    if 555 <= hm < 930: by[k[:10]].append((hm, *raw[k]))
days = [d for d in sorted(by) if len(by[d]) >= 300]
D = {d: (by[d][0][1], max(x[2] for x in by[d]), min(x[3] for x in by[d]), by[d][-1][4]) for d in days}

def levels(prev):
    h, l, c = D[prev][1], D[prev][2], D[prev][3]
    p = (h + l + c) / 3; bc = (h + l) / 2; tc = 2 * p - bc
    return dict(p=p, top=max(tc, bc), bot=min(tc, bc), r1=2 * p - l, s1=2 * p - h, r2=p + h - l, s2=p - (h - l))

rows = []
for i in range(21, len(days)):
    d = days[i]; lv = levels(days[i - 1]); o, h, l, c = D[d]
    w = (lv['top'] - lv['bot']) / lv['p'] * 100
    past = [(levels(days[j - 1])['top'] - levels(days[j - 1])['bot']) / levels(days[j - 1])['p'] * 100 for j in range(i - 20, i)]
    rank = sum(x < w for x in past) / 20                             # 0 = narrowest of the last 20 days
    pos = 'above' if o > lv['top'] else 'below' if o < lv['bot'] else 'inside'
    y = levels(days[i - 2])
    rel = 'higher' if lv['bot'] > y['top'] else 'lower' if lv['top'] < y['bot'] else 'overlap'
    rows.append(dict(d=d, w=w, rank=rank, narrow=rank < 1 / 3, wide=rank >= 2 / 3, pos=pos, rel=rel,
                     rng=(h - l) / o * 100, oc=(c - o) / o * 100, up=(h - o) / o * 100, dn=(o - l) / o * 100,
                     back=(l <= lv['top']) if pos == 'above' else (h >= lv['bot']) if pos == 'below' else None,
                     gap=(o - D[days[i - 1]][3]) / o * 100, r1=h >= lv['r1'], s1=l <= lv['s1'],
                     closeAbove=c > lv['top'], closeBelow=c < lv['bot']))

def table(rs, label):
    print(f"\n=== {label}: {len(rs)} sessions, {rs[0]['d']} to {rs[-1]['d']} ===")
    m = lambda xs: st.mean(xs) if xs else float('nan')
    pc = lambda xs: 100 * sum(xs) / len(xs) if xs else float('nan')
    print(" CPR width   days  avg width  avg range  range>=1%  moved>=0.5% from open  avg |open-close|  hit R1 or S1")
    for lab, f in (('narrow', lambda r: r['narrow']), ('middle', lambda r: not r['narrow'] and not r['wide']), ('wide', lambda r: r['wide'])):
        s = [r for r in rs if f(r)]
        if s: print(f" {lab:9} {len(s):6} {m([r['w'] for r in s]):9.3f}% {m([r['rng'] for r in s]):9.2f}% {pc([r['rng'] >= 1 for r in s]):9.0f}% "
                    f"{pc([max(r['up'], r['dn']) >= 0.5 for r in s]):17.0f}% {m([abs(r['oc']) for r in s]):17.2f}% {pc([r['r1'] or r['s1'] for r in s]):12.0f}%")
    print(" Open vs CPR      days  came back to CPR  closed up  avg open->close  avg up from open  avg down from open")
    for pos in ('above', 'inside', 'below'):
        for nar in (None, True, False):
            s = [r for r in rs if r['pos'] == pos and (nar is None or r['narrow'] == nar)]
            if not s: continue
            lab = pos + ('' if nar is None else ', narrow' if nar else ', not narrow')
            back = pc([r['back'] for r in s]) if pos != 'inside' else float('nan')
            print(f" {lab:18} {len(s):4} {back:14.0f}% {pc([r['oc'] > 0 for r in s]):9.0f}% {m([r['oc'] for r in s]):+14.2f}% {m([r['up'] for r in s]):15.2f}% {m([r['dn'] for r in s]):17.2f}%")
    print(" Today's CPR vs yesterday's   days  closed up  avg open->close")
    for rel in ('higher', 'overlap', 'lower'):
        s = [r for r in rs if r['rel'] == rel]
        if s: print(f" {rel:28} {len(s):4} {pc([r['oc'] > 0 for r in s]):8.0f}% {m([r['oc'] for r in s]):+14.2f}%")

n = len(rows)
table(rows[-60:], f'{name.upper()} LAST 60 SESSIONS')
table(rows[-90:-60], f'{name.upper()} THE 30 SESSIONS BEFORE THOSE')
table(rows, f'{name.upper()} EVERY SESSION SINCE 2023')
print('\nlast 60 sessions, day by day: date, width %, narrow?, open vs CPR, came back?, range %, open->close %')
for r in rows[-60:]:
    print(f" {r['d']}  {r['w']:.3f}  {'NARROW' if r['narrow'] else 'wide  ' if r['wide'] else '      '}  {r['pos']:6} {'' if r['back'] is None else 'back' if r['back'] else 'no  '}  range {r['rng']:.2f}  o->c {r['oc']:+.2f}")
