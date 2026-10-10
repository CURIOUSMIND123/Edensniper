"""Turn Binance's public 1-minute BTCUSDT futures archives (data.binance.vision zips) into ../.cache/btc_1m.json.

    python -I btc_load.py ../.cache/btc_raw ../.cache/btc_1m.json
Keys are UTC times "YYYY-MM-DD HH:MM"; values are [open, high, low, close, volume in BTC].
"""
import csv, datetime as dt, io, json, os, sys, zipfile
src, dst = sys.argv[1], sys.argv[2]
out = {}
for fn in sorted(os.listdir(src)):
    if not fn.endswith('.zip'): continue
    with zipfile.ZipFile(os.path.join(src, fn)) as z:
        for name in z.namelist():
            for row in csv.reader(io.TextIOWrapper(z.open(name))):
                if not row or not row[0].isdigit(): continue          # header line
                t = dt.datetime.fromtimestamp(int(row[0]) / 1000, dt.timezone.utc)
                out[t.strftime('%Y-%m-%d %H:%M')] = [float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])]
json.dump(out, open(dst, 'w'))
ks = sorted(out); print(len(ks), ks[0], ks[-1], out[ks[-1]])
