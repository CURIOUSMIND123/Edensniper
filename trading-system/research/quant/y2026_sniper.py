"""2026 only: sharper entries for the indicator's default (original rules + volume check), measured as real options
(time decay included, y2026_options.py) as well as index points.

    python y2026_sniper.py nifty        (or sensex)

Each rule only removes signals, through the alert program's own trade logic (a removed signal lets the next one in,
as it would live):
  volume  the up candles' volume must beat the down candles' by 1.25 / 1.5 / 2x (BUY; the other way for SELL), not
          just beat it
  time    entries only before 11:00 / 12:00
  expiry  no trades on the nearest expiry's day (the option would be expiring that afternoon)
  range   no breakout when the 9:15-9:30 range is wider than 0.5% / 0.7% of price (a big stop)
  setups  without the CPR Magnet / without the volume lines / without the breakout
and a few together. Exits as now; options at the money, nearest expiry (next expiry on expiry day where that helps).
"""
import collections, sys
import y2026_options as OP

A, Y, D26, H1, NM, CX = OP.A, OP.Y, OP.D26, OP.H1, OP.NM, OP.CX
import y2026_volume as VV
VCHK = {k: VV.check(dict(mode='sum', w=24, k=k)) for k in (1.0, 1.25, 1.5, 2.0)}
EXP0 = {d: sorted(OP.OPT.get(d, {}))[:1] == [d] for d in D26}
ORW = {}
for d in D26:
    first = [x for x in Y.one[d] if x[0] < 570]
    ORW[d] = (max(x[2] for x in first) - min(x[3] for x in first)) / first[-1][4]

def rule(P):
    def f(d):
        def g(side, m, src):
            if not VCHK[P.get('k', 1.0)](d, side, m): return False
            if P.get('before') and m >= P['before']: return False
            if P.get('noexp') and EXP0[d]: return False
            if P.get('orw') and src in ('BREAKOUT', 'REVERSAL') and ORW[d] > P['orw']: return False
            if src in P.get('drop', ()): return False
            return True
        return g
    return f

def run(P, expiry='near'):
    f = rule(P); rows = []
    for d in D26:
        cx = CX[d]; cx['vf'] = f(d)
        for t in A.day_trades(cx, Y.one[d], 929, True, False, 'classic'):
            if not t['taken']: continue
            r = OP.option_trade(d, t['side'], OP.legs_now(t), 'ATM', expiry)
            rows.append(dict(d=d, pts=t['exit']['pnl'], rs=r[0] if r else 0.0))
        cx['vf'] = None
    return rows

def show(label, rows, base=None):
    rs = [r['rs'] for r in rows]; a = sum(r['rs'] for r in rows if r['d'] in H1)
    pts = sum(r['pts'] for r in rows)
    eq = pk = dd = 0
    for v in rs: eq += v; pk = max(pk, eq); dd = min(dd, eq - pk)
    tag = ''
    if base:
        ba = sum(r['rs'] for r in base if r['d'] in H1); bb = sum(r['rs'] for r in base) - ba
        tag = '  <- better in both halves' if a > ba and sum(rs) - a > bb else ''
    print(f"  {label:40} {len(rs):3} tr, {100 * sum(v > 0 for v in rs) / max(1, len(rs)):3.0f}% won | points {pts:+7,.0f} | options Rs {sum(rs):+10,.0f} "
          f"(Jan-Jun {a:+9,.0f}, Jul-Oct {sum(rs) - a:+9,.0f}), worst fall Rs {dd:9,.0f}{tag}")

if __name__ == '__main__':
    A.RULES, A.SWEEP, A.VOLCHECK = 'classic', False, False      # the checks are set here (cx['vf'])
    print(f"{NM.upper()} 2026, 5 lots, at-the-money options, time decay included")
    base = run({})
    show('default (volume check)', base)
    show('default, next expiry on expiry day', run({}, 'skip0'), base)
    for lab, P in (('volume 1.25x', dict(k=1.25)), ('volume 1.5x', dict(k=1.5)), ('volume 2x', dict(k=2.0)),
                   ('entries before 11:00', dict(before=660)), ('entries before 12:00', dict(before=720)),
                   ('no trades on expiry day', dict(noexp=True)),
                   ('no breakout if range > 0.5%', dict(orw=0.005)), ('no breakout if range > 0.7%', dict(orw=0.007)),
                   ('without the Magnet', dict(drop=('MAGNET',))), ('without the volume lines', dict(drop=('VOLUME LINE',))),
                   ('without the breakout', dict(drop=('BREAKOUT', 'REVERSAL'))),
                   ('volume 1.5x + before 12:00', dict(k=1.5, before=720)),
                   ('volume 1.5x + no expiry day', dict(k=1.5, noexp=True)),
                   ('before 12:00 + no expiry day', dict(before=720, noexp=True))):
        show(lab, run(P), base)
