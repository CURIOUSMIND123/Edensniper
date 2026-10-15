"""How often the alert program's calls reached T1 / T2 / T3 (the app's targets: T1 = where half is booked, T2 / T3 = the
next two price levels beyond it), January 2023 - 9 October 2026: the chances the app and the alerts show.

    python target_probs.py nifty      then  python target_probs.py sensex      then  python target_probs.py
writes ../../alerts/target-probs.json

Reached = touched before the stop loss; after T1 the stop is at the entry (as the calls manage it), so T2 / T3 count
only when price got there without coming back to the entry first. Per index and setup (breakout, Magnet, volume line),
with 2023-2025 and 2026 separately to show how steady the numbers are.
"""
import collections, json, sys

def run(nm):
    sys.argv = [sys.argv[0], nm]
    import levels_style as LS
    A = LS.A
    cnt = collections.defaultdict(lambda: [0, 0, 0, 0])
    for d in LS.DAYS:
        cx, c1 = LS.CX[d], LS.sess[d]
        for t in A.day_trades(cx, c1, 929, True, False, 'classic'):
            if not (t['taken'] and t['exit']):
                continue
            T = A.target_levels(cx, c1, t['side'], t['e'], t['known'], A.half_price(t))
            _, _, k = LS.walk(c1, t['side'], t['e'], t['known'], t['stp0'], T, (0, 0, 1), be_at=1)
            for key in ((t['src'], d[:4] < '2026'), ('ALL', d[:4] < '2026')):
                for g in (key, (key[0], None)):
                    c = cnt[g]
                    c[0] += 1
                    for j in range(3):
                        c[j + 1] += k > j
    out = {}
    for (src, early), c in cnt.items():
        name = src + ('' if early is None else ' 2023-25' if early else ' 2026')
        out[name] = dict(n=c[0], t1=round(100 * c[1] / c[0]), t2=round(100 * c[2] / c[0]), t3=round(100 * c[3] / c[0]),
                         t2_after_t1=round(100 * c[2] / c[1]) if c[1] else None, t3_after_t2=round(100 * c[3] / c[2]) if c[2] else None)
    json.dump(out, open(f'../.cache/target_probs_{nm}.json', 'w'))
    for k in sorted(out):
        v = out[k]
        print(f"  {nm.upper():6} {k:22} {v['n']:4} calls: T1 {v['t1']:3}%  T2 {v['t2']:3}%  T3 {v['t3']:3}%  | after T1, T2 {v['t2_after_t1']}%; after T2, T3 {v['t3_after_t2']}%")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        run(sys.argv[1]); sys.exit()
    out = {}
    for nm in ('nifty', 'sensex'):
        allp = json.load(open(f'../.cache/target_probs_{nm}.json'))
        out[nm.upper()] = {k.split(' ')[0] if ' ' not in k else k: v for k, v in allp.items() if ' 20' not in k}
    json.dump(dict(note='How often the calls reached T1 / T2 / T3 before the stop (after T1: before the entry), '
                        'January 2023 - October 2026 (research/quant/target_probs.py).', probs=out),
              open('../../alerts/target-probs.json', 'w'), indent=1)
    print('written ../../alerts/target-probs.json')
