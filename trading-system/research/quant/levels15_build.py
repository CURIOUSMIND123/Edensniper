"""Rolling 15-day levels: daily highs / lows, profile peaks (time at price), consolidation boxes, merged into clusters."""
import json, collections, statistics as st, numpy as np, pickle, sys
def load(name):
    raw = json.load(open(f'../.cache/{name}_1m.json'))
    by = collections.defaultdict(list)
    for k in sorted(raw):
        hm = k[11:16]
        if '09:15' <= hm < '15:30': by[k[:10]].append((int(hm[:2]) * 60 + int(hm[3:]), *raw[k]))
    days = [d for d in sorted(by) if len(by[d]) >= 300]
    out = []
    ranges = []
    for d in days:
        b1 = by[d]
        b5 = []
        for i in range(0, len(b1), 5):
            ch = b1[i:i + 5]
            b5.append((ch[0][0], ch[0][1], max(x[2] for x in ch), min(x[3] for x in ch), ch[-1][4]))
        am = [x for x in b1 if x[0] < 645]
        U = st.median(ranges[-20:]) if len(ranges) >= 10 else None
        out.append(dict(d=d, b1=np.array([x[1:] for x in b1]), b5=b5, U=U))
        ranges.append(max(x[2] for x in am) - min(x[3] for x in am))
    return out

def build(days, idx, U, look=15, bin_k=0.05, hvn_pct=70, cons_w=12, cons_k=0.3):
    past = days[max(0, idx - look):idx]
    cands = []
    for p in past:
        cands.append((p['b1'][:, 1].max(), 1.0, 'D')); cands.append((p['b1'][:, 2].min(), 1.0, 'D'))
    # time-at-price profile from 1-minute bars
    b = bin_k * U
    allb = np.vstack([p['b1'] for p in past])
    lo0 = allb[:, 2].min(); nb = int((allb[:, 1].max() - lo0) / b) + 2
    hist = np.zeros(nb)
    i0 = ((allb[:, 2] - lo0) / b).astype(int); i1 = ((allb[:, 1] - lo0) / b).astype(int)
    for a, z in zip(i0, i1): hist[a:z + 1] += 1.0 / (z - a + 1)
    sm = np.convolve(hist, np.ones(3) / 3, mode='same')
    thr = np.percentile(sm[sm > 0], hvn_pct); k = max(1, int(round(0.15 * U / b)))
    for j in range(len(sm)):
        if sm[j] >= thr and sm[j] == sm[max(0, j - k):j + k + 1].max():
            cands.append((lo0 + (j + 0.5) * b, 2.0, 'V'))
    # consolidation boxes: 12 five-minute candles (1 hour) inside 0.3 x usual range, same day, merged
    for p in past:
        b5 = p['b5']; boxes = []
        for s in range(0, len(b5) - cons_w + 1):
            w = b5[s:s + cons_w]; hi = max(x[2] for x in w); lo = min(x[3] for x in w)
            if hi - lo <= cons_k * U:
                if boxes and s <= boxes[-1][1]: boxes[-1] = [boxes[-1][0], s + cons_w - 1, max(boxes[-1][2], hi), min(boxes[-1][3], lo)]
                else: boxes.append([s, s + cons_w - 1, hi, lo])
        for bx in boxes: cands.append(((bx[2] + bx[3]) / 2, 1.5, 'C'))
    return cands

def merge(cands, kinds, tol):
    xs = sorted([c for c in cands if c[2] in kinds])
    clusters = []
    for p, w, k in xs:
        if clusters and p - clusters[-1]['p'] <= tol:
            c = clusters[-1]; c['p'] = (c['p'] * c['s'] + p * w) / (c['s'] + w); c['s'] += w; c['k'].add(k)
        else: clusters.append(dict(p=p, s=w, k={k}))
    return [(c['p'], c['s'], ''.join(sorted(c['k']))) for c in clusters]

if __name__ == '__main__':
    name = sys.argv[1]
    days = load(name)
    out = {}
    for i, dd in enumerate(days):
        if i < 15 or dd['U'] is None: continue
        U = dd['U']; cands = build(days, i, U)
        out[dd['d']] = {f'{ks}|{mt}': merge(cands, set(ks), mt * U) for ks in ('D', 'DV', 'DVC') for mt in (0.05, 0.1)}
    pickle.dump(dict(days=[dict(d=x['d'], b5=x['b5'], U=x['U']) for x in days], levels=out), open(f'../.cache/{name}_levels.pkl', 'wb'))
    last = days[-1]['d']; L = out[last]['DVC|0.1']
    print(name, len(out), 'days; levels on', last, ':', len(L), 'clusters; strongest:', sorted(L, key=lambda c: -c[1])[:6])
