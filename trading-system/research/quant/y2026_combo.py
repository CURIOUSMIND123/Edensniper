"""2026 only: the CPR daily plan (tradingview/cpr_breakout.pine defaults) plus 3-day volume-line breakouts.

    python y2026_combo.py nifty        (or sensex)

Daily plan: y2026_losses.plan(poc=True). Volume lines: y2026_vol_lines.day(3 sessions, stop at the previous line,
target the next line, target at least 1.5x (or 1x) the stop).
  separate   both run on their own; on some days both have a trade open at once (needs lots for both)
  one book   one trade at a time: whichever signal comes first is taken, the other waits until it closes
Results for January-June and July-9 October 2026, and in rupees at 2 lots (delta 0.5; Nifty lot 65, Sensex 20).
"""
import collections, sys
import y2026 as Y, y2026_losses as L, y2026_vol_lines as V

RS = {'nifty': 0.5 * 65, 'sensex': 0.5 * 20}[Y.B.name] * 2

def plan_trades():
    out = []
    for d in Y.D26:
        for t in L.plan(d, poc=True):
            if t['src'] == 'MAG': m, mx = 556, 556 + t['mins']
            else: m, mx = t['m'], t['mx']
            out.append((d, t['pnl'], m, mx, 'plan'))
    return out

def vol_trades(rr):
    return [(d, p, m, mx, 'vol') for dd in Y.D26 for d, p, m, mx in V.day(dd, 3, 'prev', rr, times=True)]

def one_book(ts):
    out = []; by = collections.defaultdict(list)
    for t in ts: by[t[0]].append(t)
    for d in sorted(by):
        free = 0
        for t in sorted(by[d], key=lambda t: (t[2], t[4] != 'plan')):
            if t[2] >= free: out.append(t); free = t[3] + 1
    return out

def show(label, ts):
    p = [t[1] for t in ts]; w = [v for v in p if v > 0]; l = [v for v in p if v <= 0]
    a = sum(t[1] for t in ts if t[0] in Y.H1); eq = pk = dd = 0
    for t in sorted(ts): eq += t[1]; pk = max(pk, eq); dd = min(dd, eq - pk)
    days = len({t[0] for t in ts})
    print(f"  {label:44} {len(p):3} trades on {days:3} days ({len(p)/9.3:4.1f} a month), {len(w):3} won / {len(l):<3} lost, "
          f"won {sum(w):+7,.0f} lost {sum(l):+7,.0f} net {sum(p):+7,.0f} (Jan-Jun {a:+6,.0f}, Jul-Oct {sum(p)-a:+6,.0f}), "
          f"worst fall {dd:,.0f} | 2 lots: Rs {sum(p)*RS:+,.0f}")

if __name__ == '__main__':
    print(f"{Y.B.name.upper()} 2026 ({len(Y.D26)} sessions)")
    pl = plan_trades()
    show('daily plan alone (indicator default)', pl)
    for rr in (1.5, 1.0):
        vo = vol_trades(rr)
        show(f'3-day volume lines alone (target >= {rr}x)', vo)
        show(f'  + both, separate (target >= {rr}x)', pl + vo)
        show(f'  + both, one trade at a time (target >= {rr}x)', one_book(pl + vo))
