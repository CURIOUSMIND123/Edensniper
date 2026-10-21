"""Daily put-call ratio (PCR) and the strikes with the most open interest, Nifty (NSE) and Sensex (BSE).

    python fetch_pcr.py            (or: python fetch_pcr.py sensex)

From the exchanges' daily F&O bhavcopy files, for every session in ../.cache/{nifty,sensex}_daily.json (run
fetch_daily.py first). Saved to ../.cache/pcr_{nifty,sensex}.json, one entry per day:
  pcr_all    put OI / call OI, all expiries
  pcr_near   the same for the next expiry after that day (on an expiry day: the following one)
  chg_near   put OI change / call OI change, that expiry (the day's fresh positions; None if not both > 0)
  ce_max, pe_max   the strikes with the most call / put OI, that expiry (often read as resistance / support)
  expiry     that expiry
  exp        every expiry: [call OI, put OI, call OI change, put OI change, most-call-OI strike, most-put-OI strike]
Known only after the close, so a day's numbers are for the next session.
"""
import collections, csv, io, json, os, time, urllib.request, zipfile

HDR = {'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'}

def get(url, referer):
    req = urllib.request.Request(url, headers=dict(HDR, Referer=referer))
    for k in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r: return r.read()
        except Exception as e:
            if getattr(e, 'code', None) == 404: return None
            time.sleep(2 * (k + 1))
    return None

def summarise(rows, sym, day):
    """Per expiry: [call OI, put OI, call OI change, put OI change, strike with the most call OI, most put OI]."""
    oi = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]); strike = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        if r['TckrSymb'] != sym or r['FinInstrmTp'] != 'IDO': continue
        x, k = r['XpryDt'], 0 if r['OptnTp'] == 'CE' else 1
        v = float(r['OpnIntrst'] or 0)
        oi[x][k] += v; oi[x][k + 2] += float(r['ChngInOpnIntrst'] or 0); strike[(x, k)][float(r['StrkPric'])] += v
    exp = {x: v + [max(strike[(x, 0)].items(), key=lambda kv: kv[1])[0] if strike[(x, 0)] else None,
                   max(strike[(x, 1)].items(), key=lambda kv: kv[1])[0] if strike[(x, 1)] else None]
           for x, v in oi.items() if v[0] > 0 and v[1] > 0}
    if not exp: return None
    near = min([x for x in exp if x > day] or [max(exp)])          # the next expiry after today (not today's)
    n = exp[near]
    return dict(pcr_all=sum(v[1] for v in exp.values()) / sum(v[0] for v in exp.values()), pcr_near=n[1] / n[0],
                chg_near=n[3] / n[2] if n[2] > 0 and n[3] > 0 else None, ce_max=n[4], pe_max=n[5], expiry=near, exp=exp)

MON = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

def old_nse(d):
    """NSE's older F&O bhavcopy (before 2024), as rows of the newer one (the columns summarise() reads)."""
    y, m, dd = d.split('-')
    raw = get(f"https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{y}/{MON[int(m) - 1]}/fo{dd}{MON[int(m) - 1]}{y}bhav.csv.zip",
              'https://www.nseindia.com/')
    if not raw: return None
    z = zipfile.ZipFile(io.BytesIO(raw))
    out = []
    for r in csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode())):
        r = {k.strip(): (v or '').strip() for k, v in r.items() if k}
        try:
            x = time.strftime('%Y-%m-%d', time.strptime(r['EXPIRY_DT'], '%d-%b-%Y'))
        except (KeyError, ValueError):
            continue
        out.append(dict(TckrSymb=r.get('SYMBOL'), FinInstrmTp='IDO' if r.get('INSTRUMENT') == 'OPTIDX' else '', XpryDt=x,
                        OptnTp=r.get('OPTION_TYP'), OpnIntrst=r.get('OPEN_INT') or 0, ChngInOpnIntrst=r.get('CHG_IN_OI') or 0,
                        StrkPric=r.get('STRIKE_PR') or 0))
    return out

def one_day(name, sym, d):
    ymd = d.replace('-', '')
    if name == 'nifty':
        raw = get(f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip", 'https://www.nseindia.com/')
        if not raw:
            rows = old_nse(d)
            return d, (summarise(rows, sym, d) if rows else None)
        z = zipfile.ZipFile(io.BytesIO(raw)); text = z.read(z.namelist()[0]).decode()
    else:
        raw = get(f"https://www.bseindia.com/download/Bhavcopy/Derivative/BhavCopy_BSE_FO_0_0_0_{ymd}_F_0000.CSV", 'https://www.bseindia.com/')
        if not raw or not raw.lstrip().startswith(b'TradDt'): return d, None    # before 2024: a web page, no file
        text = raw.decode()
    return d, summarise(csv.DictReader(io.StringIO(text)), sym, d)

if __name__ == '__main__':
    import sys
    from concurrent.futures import ThreadPoolExecutor
    for name, sym in (('nifty', 'NIFTY'), ('sensex', 'SENSEX')):
        names = [a for a in sys.argv[1:] if not a.startswith('--')]
        if names and name not in names: continue
        path = f'../.cache/pcr_{name}.json'
        out = json.load(open(path)) if os.path.exists(path) else {}
        days = set(json.load(open(f'../.cache/{name}_daily.json')))
        if '--all' in sys.argv:                       # every session with 1-minute data (2023-2026)
            days |= {k[:10] for k in json.load(open(f'../.cache/{name}_1m.json'))} if os.path.exists(f'../.cache/{name}_1m.json') else set()
        todo = [d for d in sorted(days) if d not in out]
        with ThreadPoolExecutor(3) as ex:
            for k, (d, res) in enumerate(ex.map(lambda d: one_day(name, sym, d), todo)):
                if res: out[d] = res
                else: print('missing', name, d, flush=True)
                if k % 20 == 19: json.dump(out, open(path, 'w'))
        json.dump(out, open(path, 'w'))
        print(name, len(out), 'days', flush=True)
