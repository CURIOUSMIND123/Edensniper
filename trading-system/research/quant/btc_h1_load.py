"""Binance public archives -> ../.cache/btc_1h.json (UTC hour -> [o, h, l, c, volume]) and ../.cache/btc_funding.json
(UTC funding time -> rate).

    python -I btc_h1_load.py ../.cache/btc_h1_raw ../.cache/btc_fund_raw
"""
import csv, datetime as dt, io, json, os, sys, zipfile
def rows(folder):
    for fn in sorted(os.listdir(folder)):
        if fn.endswith('.zip'):
            with zipfile.ZipFile(os.path.join(folder, fn)) as z:
                for name in z.namelist():
                    for r in csv.reader(io.TextIOWrapper(z.open(name))):
                        if r and r[0].isdigit(): yield r
utc = lambda ms: dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')
h1 = {utc(r[0]): [float(x) for x in r[1:6]] for r in rows(sys.argv[1])}
fund = {utc(int(r[0]) // 1000 * 1000): float(r[2]) for r in rows(sys.argv[2])}
json.dump(h1, open('../.cache/btc_1h.json', 'w')); json.dump(fund, open('../.cache/btc_funding.json', 'w'))
k = sorted(h1); f = sorted(fund)
print(len(h1), 'hours', k[0], k[-1], '|', len(fund), 'funding times', f[0], f[-1], 'mean rate', sum(fund.values()) / len(fund))
