"""Daily option prices for Nifty (NSE) and Sensex (BSE) from the exchanges' F&O bhavcopy, every 2026 session.

    python fetch_options.py            (or: python fetch_options.py sensex)

Saved to ../.cache/opt_{nifty,sensex}.json: {date: {expiry: {strike: {'CE': [open, high, low, close, volume],
'PE': [...]}}}} for the two nearest expiries on or after that day and strikes within 15 steps of the index close.
Used by y2026_options.py to price the indicator's trades as real options (time decay included).
"""
import csv, io, json, os, sys, time, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor
import fetch_pcr as F

STEP = {'nifty': 50, 'sensex': 100}

def one_day(name, sym, d, close):
    ymd = d.replace('-', '')
    if name == 'nifty':
        raw = F.get(f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip", 'https://www.nseindia.com/')
        if not raw: return d, None
        z = zipfile.ZipFile(io.BytesIO(raw)); text = z.read(z.namelist()[0]).decode()
    else:
        raw = F.get(f"https://www.bseindia.com/download/Bhavcopy/Derivative/BhavCopy_BSE_FO_0_0_0_{ymd}_F_0000.CSV", 'https://www.bseindia.com/')
        if not raw: return d, None
        text = raw.decode()
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r['TckrSymb'] == sym and r['FinInstrmTp'] == 'IDO' and r['OptnTp'] in ('CE', 'PE')]
    exps = sorted({r['XpryDt'] for r in rows if r['XpryDt'] >= d})[:2]
    out = {x: {} for x in exps}
    for r in rows:
        if r['XpryDt'] not in out: continue
        k = float(r['StrkPric'])
        if abs(k - close) > 15 * STEP[name]: continue
        try: v = [float(r['OpnPric'] or 0), float(r['HghPric'] or 0), float(r['LwPric'] or 0), float(r['ClsPric'] or 0), float(r['TtlTradgVol'] or 0)]
        except ValueError: continue
        out[r['XpryDt']].setdefault(str(int(k)), {})[r['OptnTp']] = v
    return d, out

if __name__ == '__main__':
    for name, sym in (('nifty', 'NIFTY'), ('sensex', 'SENSEX')):
        if len(sys.argv) > 1 and name not in sys.argv[1:]: continue
        path = f'../.cache/opt_{name}.json'
        out = json.load(open(path)) if os.path.exists(path) else {}
        daily = json.load(open(f'../.cache/{name}_daily.json'))
        todo = [d for d in sorted(daily) if d >= '2026-01-01' and d not in out]
        close = {d: (v[4] if isinstance(v, list) else v['close']) for d, v in daily.items()}
        with ThreadPoolExecutor(3) as ex:
            for k, (d, res) in enumerate(ex.map(lambda d: one_day(name, sym, d, close[d]), todo)):
                if res: out[d] = res
                else: print('missing', name, d, flush=True)
                if k % 20 == 19: json.dump(out, open(path, 'w')); print(name, k + 1, 'of', len(todo), flush=True)
        json.dump(out, open(path, 'w'))
        print(name, len(out), 'days', flush=True)
