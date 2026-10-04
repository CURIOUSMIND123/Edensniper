"""Build one row per 5-minute decision point (9:30 .. 14:55) with only information known at that moment,
plus forward returns over the next 15 / 30 / 60 minutes."""
import json, sys, numpy as np, pandas as pd, datetime as dt
name = sys.argv[1]
raw = json.load(open(f'../.cache/{name}_1m.json'))
df = pd.DataFrame([(k, *v) for k, v in raw.items()], columns=['t', 'o', 'h', 'l', 'c'])
df['t'] = pd.to_datetime(df['t']); df = df.sort_values('t')
df = df[(df.t.dt.time >= dt.time(9, 15)) & (df.t.dt.time < dt.time(15, 30))]
df['d'] = df.t.dt.date
cnt = df.groupby('d').size(); good = cnt[cnt >= 300].index
df = df[df.d.isin(good)].reset_index(drop=True)
days = sorted(df.d.unique())
rows = []; ranges = []; prev = None
for d in days:
    g = df[df.d == d]
    t = g.t.dt.hour.values * 60 + g.t.dt.minute.values - 555   # minutes since 9:15
    o, h, l, c = g.o.values, g.h.values, g.l.values, g.c.values
    am = t < 90
    rng_today = h[am].max() - l[am].min()
    U = np.median(ranges[-20:]) if len(ranges) >= 10 else None
    if U and prev is not None:
        pdh, pdl, pdc, pdo = prev
        op = o[0]
        orh, orl = h[t < 15].max(), l[t < 15].min()
        cumhi = np.maximum.accumulate(h); cumlo = np.minimum.accumulate(l)
        for i in range(len(t)):
            m = t[i] + 1                       # decision at the close of minute bar i
            if m < 15 or m % 5 or m > 340: continue
            px = c[i]
            def ret(back):
                j = i - back
                return (px - c[j]) / U if j >= 0 else np.nan
            def fwd(k):
                j = i + k
                return c[j] - px if j < len(c) else np.nan
            j30 = max(0, i - 29)
            rv30 = np.abs(np.diff(c[j30:i + 1])).sum() / U if i > j30 else 0
            hi, lo = cumhi[i], cumlo[i]
            r100 = (px % 100) / 100.0
            rows.append(dict(
                day=str(d), m=m, U=U, px=px,
                fair=(px - op) / U, gap=(op - pdc) / U, prevret=(pdc - pdo) / U,
                d_pdh=(px - pdh) / U, d_pdl=(px - pdl) / U, d_pdc=(px - pdc) / U,
                d_orh=(px - orh) / U, d_orl=(px - orl) / U,
                swept_pdh=float(hi > pdh and px < pdh), swept_pdl=float(lo < pdl and px > pdl),
                swept_orh=float(hi > orh + 0.05 * U and px < orh), swept_orl=float(lo < orl - 0.05 * U and px > orl),
                above_pdh=float(px > pdh), below_pdl=float(px < pdl),
                r5=ret(5), r15=ret(15), r30=ret(30), r60=ret(60),
                pos=(px - lo) / (hi - lo) if hi > lo else 0.5, d_hi=(hi - px) / U, d_lo=(px - lo) / U,
                dayrng=(hi - lo) / U, rv30=rv30, round100=r100,
                dow=pd.Timestamp(d).dayofweek,
                f15=fwd(15), f30=fwd(30), f60=fwd(60),
                eod=c[-1] - px))
    ranges.append(rng_today); prev = (h.max(), l.min(), c[-1], o[0])
out = pd.DataFrame(rows)
out.to_pickle(f'../.cache/{name}_rows.pkl')
print(name, len(out), 'rows,', out.day.nunique(), 'days')
